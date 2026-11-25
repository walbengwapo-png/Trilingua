"""Short-lived PDF render inputs, scoped to a single translation job."""

from contextlib import closing
from hashlib import sha256
import json
import logging
from pathlib import Path
import sqlite3
import time

from cache.sqlite_cache import CACHE_DIR
from document.pdf_regions import sha256 as file_sha256


DB_PATH = Path(CACHE_DIR) / 'pdf_checkpoints.db'
TTL_SECONDS = 24 * 60 * 60
MAX_ENTRIES = 32
MAX_BYTES = 24_000_000
logger = logging.getLogger(__name__)


class PDFRenderCheckpointError(ValueError):
    """The original PDF and translated blocks can be retried on this engine."""


def checkpoint_key(request):
    if not request.render_checkpoint_id:
        return None
    identity = [1, request.render_checkpoint_id, file_sha256(request.file_path),
                request.source_lang, request.target_lang, request.mode,
                request.pdf_column_mode, request.ocr_mode, request.glossary_pairs]
    return sha256(json.dumps(identity, ensure_ascii=False).encode('utf-8')).hexdigest()


def _prepare(connection, now):
    connection.execute('PRAGMA secure_delete = ON')
    connection.execute('''CREATE TABLE IF NOT EXISTS pdf_checkpoints (
        job_key TEXT PRIMARY KEY, payload BLOB NOT NULL, expires_at REAL NOT NULL
    )''')
    connection.execute('DELETE FROM pdf_checkpoints WHERE expires_at <= ?', (now,))


def load_checkpoint(key):
    if key is None or not DB_PATH.is_file():
        return None
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=2)) as connection, connection:
            _prepare(connection, time.time())
            row = connection.execute('SELECT payload FROM pdf_checkpoints WHERE job_key = ?', (key,)).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        if (not isinstance(payload, dict)
                or not {'blocks', 'sidecar', 'extraction', 'warnings', 'provider', 'model'} <= payload.keys()):
            logger.warning('PDF render checkpoint has an invalid structure')
            return None
        return payload
    except (sqlite3.Error, ValueError):
        logger.warning('PDF render checkpoint could not be loaded')
        return None


def save_checkpoint(key, payload):
    if key is None:
        return False
    try:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        if len(data) > MAX_BYTES:
            logger.warning('PDF render checkpoint exceeds the size limit')
            return False
        now = time.time()
        with closing(sqlite3.connect(DB_PATH, timeout=2)) as connection, connection:
            _prepare(connection, now)
            connection.execute('INSERT OR REPLACE INTO pdf_checkpoints VALUES (?, ?, ?)',
                               (key, data, now + TTL_SECONDS))
            connection.execute('''DELETE FROM pdf_checkpoints WHERE job_key IN (
                SELECT job_key FROM pdf_checkpoints ORDER BY expires_at DESC, rowid DESC LIMIT -1 OFFSET ?
            )''', (MAX_ENTRIES,))
        return True
    except (sqlite3.Error, TypeError, ValueError):
        logger.warning('PDF render checkpoint could not be written')
        return False
