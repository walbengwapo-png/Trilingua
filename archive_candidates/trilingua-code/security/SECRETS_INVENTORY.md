# Trilingua — Secret Inventory (raw findings, 2026-09-07)

Prepared during Step 1 of the remediation plan. Lists where live credentials exist in the
worktree and in git history. **Raw secret VALUES are never printed here.** Only file names,
locations, and remediation status. This file is safe to commit.

## Legend

- Worktree = file present in the working tree today
- Tracked = committed in HEAD
- History = present in reachable commits (not necessarily HEAD)

---

## 1. Live secrets in the working tree

| File | Tracked? | Contents | Action |
|---|---|---|---|
| `trilingua-code/.env` | No (gitignored) | Real production secrets: DB pooler password, Supabase URL + anon + service_role JWTs, Google client id/secret, Mistral API key | Leave ignored; rotate per 0C; never commit |
| `trilingua-code/passwords.txt` (repo root `passwords.txt`) | **Yes** | Plaintext DB password, Supabase keys, Mistral key | Remove from index + delete from tree; add to ignore; scrub history |
| `trilingua-code/pass.txt` | **Yes** | Two plaintext passwords (`rWAJQMQIdio8o3JY`, `W@lben152005`) | Remove from index + delete; ignore; scrub history |
| `cookies.txt` | **Yes** | Netscape-format cookie jar (session cookies) | Remove from index + delete; ignore; scrub history |
| `env content.txt` (repo root) | **Yes** | Currently empty (0 bytes) but named as a secret dump | Remove from index; ignore; scrub history (values existed in 5172f9f) |
| `trilingua-code/.env.testing` | **Yes** | Real-looking APP_KEY; dummy Supabase values | **Regenerate APP_KEY (fresh random)**; keep tracked afterwards |
| `trilingua-code/.env.demo` | No | **Real** pooler DB_HOST, Supabase URL, anon + service_role keys | Add to ignore; do NOT commit; scrub history (present in checkpoint commits) |
| `trilingua-code/bootstrap/cache/config.php` | No (ignored via `*`) | **Embedded resolved secrets**: Google secret, Supabase URL/JWTs, pooler host | Delete now; keep ignored; never commit |
| `trilingua-code/bootstrap/cache/packages.php`, `services.php` | **Yes** | Compiled config/service manifests | Untrack + ignore (generated artifacts) |
| `trilingua-code/Model/cache/translations.db` | **Yes** | 1539 rows `source_text`/`translated_text` **plaintext** user translation cache (1.3 MB) | Untrack + ignore; treat as sensitive PII; scrub history |
| `trilingua-code/review_render_out/*.html` | **Yes** | Admin view render snapshots (may embed user data) | Untrack + ignore (generated test artifacts) |

## 2. Secrets in git history (need scrub + force-push coordination)

Confirmed via `git log --all --name-only` and `git rev-list --all --objects`:

| File | First/contributing commits | Why it matters |
|---|---|---|
| `passwords.txt` | `6ba4b30`, `7399f38` | Live Supabase DB + Mistral credentials in plaintext |
| `trilingua-code/pass.txt` | `124a245` | Plaintext password dump |
| `cookies.txt` | `18f5910` | Session cookie jar |
| `trilingua-code/.env.testing` | `42879e6`, `d8931c6` | APP_KEY exposure |
| `trilingua-code/.env.demo` | checkpoint commits `7135636`, `3f0519a`, `be274b7`, `89aa324`, `9e5f170`, `be6f203`, `daa3be7` | Real Supabase keys + pooler host baked into history although never in HEAD |
| `trilingua-code/Model/cache/translations.db` | many (see `bc45244`, `8c0e5ea`, `18f5910`, `6b8b185`, `0daa0a8`, `8de98fd`, `6e432f4`, ...) | Plaintext user translation content |
| `env content.txt` | `5172f9f` | Secret dump file name (value currently empty) |
| `COMMIT_MESSAGE.txt` | `42879e6`, `6323083` | Unknown; verify content during scrub review |

`.env` itself: `git rev-list --all --objects` found **no** `.env` file in any historical tree.
The earlier audit note that `.env` was committed is NOT confirmed; the confirmed set is above.

## 3. Highest-priority rotation targets (0C)

1. Supabase anon + service_role (regenerate together in project).
2. Supabase DB pooler password.
3. Mistral API key.
4. Google OAuth client secret.
5. `APP_KEY` last (invalidates sessions; see `security/rotation-runbook.md`).

## 4. Interim protective actions (already/being taken)

- All above files excluded from the Step-3 commit chunks.
- `.gitignore` both levels extended (see Step-1 edits).
- Generated SQLite cache + compiled config removed from tracking.