# -*- coding: utf-8 -*-
"""
Persistent SQLite-backed translation cache.

Replaces the in-memory TranslationCache for cross-session persistence.
Cache key is SHA-256(source_text + source_lang + target_lang + provider_name),
versioned with a "v2|" prefix so pre-fix entries (which omitted source_lang and
could collide across source languages) are never served.

Architecture:
  ┌──────────────────────┐
  │  SQLiteTranslation   │  ← Persistent layer (SQLite file)
  │  Cache               │
  ├──────────────────────┤
  │  _doc_cache: dict    │  ← In-memory document-level layer (cleared per doc)
  └──────────────────────┘

The in-memory layer provides faster lookups during a single document
translation. The SQLite layer persists across sessions.

Thread safety: SQLite WAL mode + threading lock for writes.
"""

import os
import sqlite3
import hashlib
import threading
import time
from typing import Any

# Default cache directory (relative to this file's location)
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(CACHE_DIR, "translations.db")


class _CacheStats:
    """Per-thread in-memory doc cache + counters.

    A document translation runs on ONE worker thread per HTTP request (its
    own nested pool aside), so scoping the in-memory cache and its counters to
    the thread keeps concurrent jobs from clearing each other's fast layer and
    makes every counter increment race-free without a lock.

    The registry lives on the cache instance so clear_document_cache() can
    wipe all threads' caches at once after a job completes.
    """

    __slots__ = ("doc_cache", "doc_hits", "doc_misses",
                 "persistent_hits", "persistent_misses", "puts")

    def __init__(self):
        self.doc_cache: dict[str, str] = {}
        self.doc_hits: int = 0
        self.doc_misses: int = 0
        self.persistent_hits: int = 0
        self.persistent_misses: int = 0
        self.puts: int = 0


class SQLiteTranslationCache:
    """Persistent, SQLite-backed translation cache.

    Usage:
        cache = SQLiteTranslationCache()

        # Before translating:
        cached = cache.get(source_text, target_lang, provider_name)
        if cached is not None:
            return cached

        # After translating:
        cache.put(source_text, target_lang, provider_name, translated_text)
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH,
                 ttl_days: int = 30, enabled: bool = True,
                 namespace: str = ""):
        """Initialize the cache.

        Args:
            db_path: Path to the SQLite database file.
            ttl_days: Number of days before an entry expires.
            enabled: If False, get() always returns None and put() is a no-op.
        """
        self._db_path = db_path
        self._ttl_seconds = ttl_days * 86400
        self._enabled = enabled
        # Isolate entries when a provider, model, or prompt policy changes.
        self._namespace = namespace

        # Writes are serialized with this lock (SQLite allows a single writer).
        # Reads are LOCK-FREE: WAL mode permits concurrent readers, and each
        # thread uses its own connection so threads never block each other.
        self._lock = threading.Lock()
        self._local = threading.local()          # per-thread read connection
        self._pending: list[tuple] = []          # batched writes awaiting flush
        self._WRITE_BATCH_SIZE = 100

        # In-memory document-level cache (faster than SQLite per-document).
        # Scoped per THREAD so concurrent document jobs never clear each
        # other's fast layer; the registry allows a global clear at job end.
        self._stats_local = threading.local()
        self._stats_registry: list[_CacheStats] = []

        if self._enabled:
            self._init_db()

    # ── Public API ─────────────────────────────────────────────────────────

    def get(self, source_text: str, target_lang: str,
            provider_name: str = "", source_lang: str = "") -> str | None:
        """Get a cached translation if available.

        Checks in-memory cache first, then persistent SQLite cache.
        Returns None if not found or if cache is disabled.

        Args:
            source_text: The source text to look up.
            target_lang: The target language.
            provider_name: The provider name (included in cache key).
            source_lang: The source language (included in cache key; the
                text/word can mean different things in different source
                languages, so it must be part of the key).

        Returns:
            Cached translated text, or None if not found.
        """
        if not self._enabled:
            return None

        cache_key = self._make_key(source_text, target_lang, provider_name, source_lang, self._namespace)
        stats = self._stats()

        # 1. Check this thread's in-memory cache first (fast path)
        doc_result = stats.doc_cache.get(cache_key)
        if doc_result is not None:
            stats.doc_hits += 1
            return doc_result
        stats.doc_misses += 1

        # 2. Check persistent cache. A local miss may be because a *different*
        #    thread (e.g. a parallel document worker) wrote the entry but its
        #    batched write is still pending — flush first so that write is
        #    visible here instead of re-translating.
        self._maybe_flush()
        try:
            conn = self._read_conn()
            row = conn.execute(
                "SELECT translated_text, created_at FROM translation_cache "
                "WHERE cache_key = ? AND expires_at > ?",
                (cache_key, time.time()),
            ).fetchone()
            if row is not None:
                translated_text, created_at = row
                # Store in this thread's doc cache for faster subsequent access
                stats.doc_cache[cache_key] = translated_text
                stats.persistent_hits += 1
                return translated_text
        except sqlite3.Error as e:
            # OPTIMIZATION: If cache read fails, just log and continue
            print(f"  [Cache] SQLite read error: {e}")

        stats.persistent_misses += 1
        return None

    def put(self, source_text: str, target_lang: str,
            provider_name: str, translated_text: str,
            source_lang: str = "") -> None:
        """Store a translation in both in-memory and persistent cache.

        Args:
            source_text: The source text.
            target_lang: The target language.
            provider_name: The provider name.
            translated_text: The translated text to cache.
            source_lang: The source language (included in cache key).
        """
        if not self._enabled:
            return

        cache_key = self._make_key(source_text, target_lang, provider_name, source_lang, self._namespace)
        now = time.time()

        # Store in this thread's in-memory cache
        stats = self._stats()
        stats.doc_cache[cache_key] = translated_text
        stats.puts += 1

        # Batch the write; flush lazily on a read, at the batch threshold,
        # or when flush()/clear_document_cache() runs. Batching turns N
        # fsync-per-write commits into a single transaction.
        with self._lock:
            self._pending.append((
                cache_key,
                source_text[:500],  # Truncate to save space
                translated_text,
                target_lang,
                provider_name,
                now,
                now + self._ttl_seconds,
            ))
            if len(self._pending) >= self._WRITE_BATCH_SIZE:
                self._flush_pending_locked()

    def has(self, source_text: str, target_lang: str,
            provider_name: str = "", source_lang: str = "") -> bool:
        """Check if a translation is cached."""
        return self.get(source_text, target_lang, provider_name, source_lang) is not None

    def clear_document_cache(self) -> None:
        """Clear the in-memory document caches for ALL threads.

        Called at the start/end of each document translation. Flushes batched
        writes first so per-document entries persist, then wipes every thread's
        fast cache so one job's leftovers never serve another job.
        """
        self.flush()
        with self._lock:
            for stats in self._stats_registry:
                stats.doc_cache.clear()
                stats.doc_hits = 0
                stats.doc_misses = 0

    def clear_all(self) -> dict[str, Any]:
        """Clear ALL cached translations (both in-memory and persistent).

        Returns:
            Stats about what was cleared.
        """
        with self._lock:
            for stats in self._stats_registry:
                stats.doc_cache.clear()
                stats.doc_hits = 0
                stats.doc_misses = 0

        deleted = 0
        if self._enabled:
            try:
                with self._lock:
                    self._flush_pending_locked()
                    conn = sqlite3.connect(self._db_path, timeout=10)
                    try:
                        cursor = conn.execute("SELECT COUNT(*) FROM translation_cache")
                        deleted = cursor.fetchone()[0]
                        conn.execute("DELETE FROM translation_cache")
                        conn.commit()
                    finally:
                        conn.close()
            except sqlite3.Error as e:
                print(f"  [Cache] SQLite clear error: {e}")

        return {
            "cleared": True,
            "entries_deleted": deleted,
            "in_memory_cleared": True,
        }

    def prune_expired(self) -> int:
        """Remove expired entries from the persistent cache.

        Returns:
            Number of entries pruned.
        """
        if not self._enabled:
            return 0

        try:
            with self._lock:
                self._flush_pending_locked()
                conn = sqlite3.connect(self._db_path, timeout=10)
                try:
                    cursor = conn.execute(
                        "DELETE FROM translation_cache WHERE expires_at < ?",
                        (time.time(),),
                    )
                    conn.commit()
                    return cursor.rowcount
                finally:
                    conn.close()
        except sqlite3.Error as e:
            print(f"  [Cache] SQLite prune error: {e}")
            return 0

    def stats(self) -> dict[str, Any]:
        """Return cache statistics, aggregated across all worker threads."""
        total_calls = 0
        persistent_hits = 0
        persistent_misses = 0
        doc_hits = 0
        doc_misses = 0
        doc_size = 0
        puts = 0
        seen: set[int] = set()
        with self._lock:
            for stats in self._stats_registry:
                if id(stats) in seen:
                    continue
                seen.add(id(stats))
                persistent_hits += stats.persistent_hits
                persistent_misses += stats.persistent_misses
                doc_hits += stats.doc_hits
                doc_misses += stats.doc_misses
                doc_size += len(stats.doc_cache)
                puts += stats.puts
        total_calls = persistent_hits + persistent_misses + doc_hits + doc_misses
        persistent_total = persistent_hits + persistent_misses
        persistent_hit_rate = (
            (persistent_hits / persistent_total * 100)
            if persistent_total > 0 else 0.0
        )

        db_size = 0
        entry_count = 0
        if self._enabled and os.path.exists(self._db_path):
            try:
                db_size = os.path.getsize(self._db_path)
                self._maybe_flush()
                with self._lock:
                    conn = sqlite3.connect(self._db_path, timeout=10)
                    try:
                        cursor = conn.execute(
                            "SELECT COUNT(*) FROM translation_cache"
                        )
                        entry_count = cursor.fetchone()[0]
                    finally:
                        conn.close()
            except (sqlite3.Error, OSError):
                pass

        return {
            "enabled": self._enabled,
            "db_path": self._db_path,
            "db_size_bytes": db_size,
            "db_entry_count": entry_count,
            "persistent_hits": persistent_hits,
            "persistent_misses": persistent_misses,
            "persistent_hit_rate": f"{persistent_hit_rate:.1f}%",
            "doc_cache_hits": doc_hits,
            "doc_cache_misses": doc_misses,
            "doc_cache_size": doc_size,
            "puts": puts,
            "ttl_seconds": self._ttl_seconds,
        }

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    # ── Internal ───────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Persist any batched writes to disk (public, safe to call anytime)."""
        if not self._enabled:
            return
        self._maybe_flush()

    def _maybe_flush(self) -> None:
        """Flush batched writes when non-empty. Lock-free when there is
        nothing pending, so the read fast path never blocks."""
        if self._pending:
            with self._lock:
                self._flush_pending_locked()

    def _flush_pending_locked(self) -> None:
        """Write all pending entries in one transaction. Caller holds lock."""
        if not self._pending:
            return
        try:
            conn = sqlite3.connect(self._db_path, timeout=10)
            try:
                conn.executemany(
                    "INSERT OR REPLACE INTO translation_cache "
                    "(cache_key, source_text, translated_text, target_lang, "
                    " provider_name, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    self._pending,
                )
                conn.commit()
                self._pending = []
            finally:
                conn.close()
        except sqlite3.Error as e:
            print(f"  [Cache] SQLite write error: {e}")

    def _read_conn(self) -> sqlite3.Connection:
        """Return this thread's cached read connection (created lazily).

        WAL mode allows many concurrent readers, so reads need no lock and
        never block writers (or each other).
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=10)
            self._local.conn = conn
        return conn

    def _stats(self) -> _CacheStats:
        """Return this thread's _CacheStats, registering it on first use.

        Thread-local, so increments are race-free. The registry entry lets
        clear_document_cache()/clear_all() wipe every thread's fast cache.
        """
        stats = getattr(self._stats_local, "stats", None)
        if stats is None:
            stats = _CacheStats()
            self._stats_local.stats = stats
            with self._lock:
                self._stats_registry.append(stats)
        return stats

    def _init_db(self) -> None:
        """Create the database and table if they don't exist."""
        try:
            with self._lock:
                conn = sqlite3.connect(self._db_path, timeout=10)
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS translation_cache (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            cache_key TEXT NOT NULL UNIQUE,
                            source_text TEXT,
                            translated_text TEXT NOT NULL,
                            target_lang TEXT NOT NULL,
                            provider_name TEXT DEFAULT '',
                            created_at REAL NOT NULL,
                            expires_at REAL NOT NULL
                        )
                    """)
                    conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_cache_key
                        ON translation_cache(cache_key)
                    """)
                    conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_expires_at
                        ON translation_cache(expires_at)
                    """)
                    conn.commit()
                finally:
                    conn.close()

            # Prune expired entries on startup
            pruned = self.prune_expired()
            if pruned > 0:
                print(f"  [Cache] Pruned {pruned} expired entries on startup")
            print(f"  [Cache] SQLite cache ready at: {self._db_path}")
        except sqlite3.Error as e:
            print(f"  [Cache] WARNING: Could not initialize SQLite cache: {e}")
            print(f"  [Cache] Disabling persistent cache")
            self._enabled = False

    @staticmethod
    def _make_key(source_text: str, target_lang: str,
                  provider_name: str = "", source_lang: str = "",
                  namespace: str = "") -> str:
        """Create a deterministic SHA-256 hash key.

        Key = SHA-256(v3|namespace + source_text + source_lang + target_lang + provider)

        The ``v2|`` prefix distinguishes this scheme from the pre-fix
        ``v1`` scheme that omitted ``source_lang`` (which could return the
        wrong translation when identical text came from different source
        languages, e.g. Cebuano vs Filipino). Old v1 entries are simply never
        matched and expire naturally via their existing TTL.

        Args:
            source_text: The source text.
            target_lang: The target language.
            provider_name: The provider name.
            source_lang: The source language.

        Returns:
            A hex digest string.
        """
        normalized = source_text.strip().lower()
        raw = (f"v3|{namespace}||{normalized}||{source_lang.lower()}||"
               f"{target_lang.lower()}||{provider_name.lower()}")
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
