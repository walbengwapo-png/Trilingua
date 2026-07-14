# TriLingua — AI-Powered Translation Platform

A web-based translation platform that uses AI (GPT-OSS via Ollama or Mistral AI) to translate text and documents (DOCX, PDF, PPTX, XLSX, CSV) while preserving formatting, images, tables, and layout.

---

## System Requirements

| Requirement | Version |
|-------------|---------|
| PHP | 8.2+ (with `pdo_pgsql`, `openssl`, `mbstring`, `xml`, `curl`, `zip`, `bcmath`, `tokenizer`) |
| Composer | 2.x |
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |
| Ollama | Latest (for GPT-OSS provider) |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/XTrilloX/Trilingua.git
cd Trilingua/trilingua-code

# 2. PHP / Laravel
composer install
cp .env.example .env
php artisan key:generate
php artisan migrate

# 3. Python translation engine
pip install -r requirements.txt

# 4. Frontend assets
npm install
npm run build

# 5. Run (see "Running the Project" below)
```

---

## Detailed Setup

### 1. Clone the Repository

```bash
git clone https://github.com/XTrilloX/Trilingua.git
cd Trilingua/trilingua-code
```

### 2. PHP / Laravel Setup

```bash
composer install
cp .env.example .env
php artisan key:generate
php artisan migrate
```

> **Note:** If you get "Class 'Illuminate\Foundation\Configuration\Exceptions' not found", run `composer update` — you likely have a cached old vendor directory.

### 3. Supabase (Cloud Database)

The database is hosted on **Supabase** (PostgreSQL). The `.env` file is already configured with live credentials:

| Variable | Value |
|----------|-------|
| `DB_CONNECTION` | `pgsql` |
| `DB_HOST` | `aws-1-ap-southeast-1.pooler.supabase.com` |
| `DB_PORT` | `6543` |
| `DB_DATABASE` | `postgres` |
| `DB_USERNAME` | `postgres.wetafzmelvwiaerofuvh` |
| `DB_PASSWORD` | `s5aGTXgf4S1UL3De` |
| `SUPABASE_URL` | `https://wetafzmelvwiaerofuvh.supabase.co` |
| `SUPABASE_ANON_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndldGFmem1lbHZ3aWFlcm9mdXZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEyNDE3OTYsImV4cCI6MjA5NjgxNzc5Nn0.HFKxV5FZL3e8ilucXUW3sCg8TjFDQPm3H3KZuI8jzcU` |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndldGFmem1lbHZ3aWFlcm9mdXZoIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MTI0MTc5NiwiZXhwIjoyMDk2ODE3Nzk2fQ.g4GO4m5T4I95p0rSe-Pz-AG9ZidstTFrqqkUETsWX7E` |
| `SUPABASE_BUCKET` | `trailingua` |

### 4. Python Translation Engine

```bash
# From the trilingua-code directory:
pip install -r requirements.txt

# Optional — for running tests:
pip install -r requirements-dev.txt
```

The Python server runs on `http://127.0.0.1:5000` and handles document translation (DOCX, PDF, PPTX, XLSX, CSV).

### 5. Node.js / Frontend

```bash
npm install
npm run build        # production build
# or
npm run dev          # hot-reload dev server
```

### 6. Mistral AI (API Key)

Mistral AI is available as a fallback translation provider.

| Variable | Value |
|----------|-------|
| `MISTRAL_API_KEY` | `BpzZLNAlMOKQ7IRNRbnRwkyR3vxYmFRP` |
| `MISTRAL_MODEL` | `mistral-small-latest` |

Get your own key at: https://console.mistral.ai/api-keys/

### 7. GPT-OSS via Ollama (Default Provider)

GPT-OSS is the **default** translation provider. It runs locally via [Ollama](https://ollama.com).

#### Install Ollama

**Windows:**
1. Download the installer from https://ollama.com/download/windows
2. Run the installer and follow the prompts
3. Ollama will start automatically and run on `http://localhost:11434`

**macOS:**
```bash
# Option A — Homebrew
brew install ollama

# Option B — Direct download
# Download from https://ollama.com/download/mac
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### Pull the GPT-OSS Model

```bash
ollama pull gpt-oss:20b-cloud
```

#### Verify It Works

```bash
ollama list                # should show gpt-oss:20b-cloud
ollama run gpt-oss:20b-cloud   # optional — interactive test
```

#### Ollama Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_CLOUD_URL` | `http://localhost:11434/api/chat` | Ollama API endpoint |
| `OLLAMA_CLOUD_MODEL` | `gpt-oss:20b-cloud` | Model name to use |

> **Important:** Ollama must be running before you start the Python translation server. The server connects to Ollama for GPT-OSS translations.

---

## Running the Project

### Option A: One-Click Start (Windows)

Double-click `start-all.bat` — this launches both the Python server (port 5000) and Laravel (port 8000) in separate windows.

### Option B: Manual Start (Two Terminals)

**Terminal 1 — Python Translation Server:**
```bash
cd Model
python server.py
```
Runs on `http://127.0.0.1:5000`

**Terminal 2 — Laravel Web Server:**
```bash
# Windows (with PHP in C:\php82):
php -S 127.0.0.1:8000 -t public

# Or with Laravel:
php artisan serve
```
Opens at `http://127.0.0.1:8000`

---

## Environment Variables Reference

All variables are in `.env` (gitignored). Here is the full reference:

### Core Laravel

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `Laravel` | Application name |
| `APP_ENV` | `local` | Environment (`local`, `production`) |
| `APP_KEY` | *(auto-generated)* | Encryption key — run `php artisan key:generate` |
| `APP_DEBUG` | `true` | Show detailed errors |
| `APP_URL` | `http://localhost` | Base URL |
| `APP_LOCALE` | `en` | Default locale |
| `APP_MAINTENANCE_DRIVER` | `file` | Maintenance mode driver |
| `BCRYPT_ROUNDS` | `12` | Password hashing rounds |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_CHANNEL` | `stack` | Log channel |
| `LOG_STACK` | `single` | Log stack |
| `LOG_LEVEL` | `debug` | Minimum log level |

### Database (Supabase PostgreSQL)

| Variable | Value |
|----------|-------|
| `DB_CONNECTION` | `pgsql` |
| `DB_HOST` | `aws-1-ap-southeast-1.pooler.supabase.com` |
| `DB_PORT` | `6543` |
| `DB_DATABASE` | `postgres` |
| `DB_USERNAME` | `postgres.wetafzmelvwiaerofuvh` |
| `DB_PASSWORD` | `s5aGTXgf4S1UL3De` |

### Session

| Variable | Value | Description |
|----------|-------|-------------|
| `SESSION_DRIVER` | `database` | Store sessions in PostgreSQL |
| `SESSION_LIFETIME` | `120` | Minutes before session expires |
| `SESSION_ENCRYPT` | `true` | Encrypt session data |
| `SESSION_SECURE_COOKIE` | `false` | Require HTTPS for cookies |
| `SESSION_PATH` | `/` | Cookie path |
| `SESSION_DOMAIN` | `null` | Cookie domain |

### Queue & Cache

| Variable | Value | Description |
|----------|-------|-------------|
| `QUEUE_CONNECTION` | `sync` | Queue driver (sync = immediate) |
| `CACHE_STORE` | `file` | Cache driver |

### Supabase (Storage & Auth)

| Variable | Value |
|----------|-------|
| `SUPABASE_URL` | `https://wetafzmelvwiaerofuvh.supabase.co` |
| `SUPABASE_ANON_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndldGFmem1lbHZ3aWFlcm9mdXZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEyNDE3OTYsImV4cCI6MjA5NjgxNzc5Nn0.HFKxV5FZL3e8ilucXUW3sCg8TjFDQPm3H3KZuI8jzcU` |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndldGFmem1lbHZ3aWFlcm9mdXZoIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MTI0MTc5NiwiZXhwIjoyMDk2ODE3Nzk2fQ.g4GO4m5T4I95p0rSe-Pz-AG9ZidstTFrqqkUETsWX7E` |
| `SUPABASE_BUCKET` | `trailingua` |

### Translation Providers

| Variable | Value | Description |
|----------|-------|-------------|
| `TRANSLATION_PROVIDER` | `gptoss` | Active provider: `gptoss` or `mistral` |
| `OLLAMA_CLOUD_URL` | `http://localhost:11434/api/chat` | Ollama API endpoint |
| `OLLAMA_CLOUD_MODEL` | `gpt-oss:20b-cloud` | Ollama model name |
| `MISTRAL_API_KEY` | `BpzZLNAlMOKQ7IRNRbnRwkyR3vxYmFRP` | Mistral API key |
| `MISTRAL_MODEL` | `mistral-small-latest` | Mistral model name |

### Python AI Engine

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHON_SERVICE_URL` | `http://127.0.0.1:5000` | Python server URL |
| `PYTHON_SERVICE_TIMEOUT` | `600` | Request timeout (seconds) |

### Future Providers (Stubs — Not Yet Implemented)

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | e.g. `gpt-4o` |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | e.g. `gemini-pro` |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `DEEPSEEK_MODEL` | e.g. `deepseek-chat` |

---

## Project Structure

```
trilingua-code/
├── app/                    # Laravel PHP backend
│   ├── Console/Commands/   # Artisan commands (CleanupTempFiles)
│   ├── Http/Controllers/   # Route controllers
│   ├── Jobs/               # Background jobs (TranslateDocumentJob)
│   ├── Models/             # Eloquent models (User, TranslationHistory)
│   └── Services/           # (deprecated — removed)
├── database/migrations/    # Database migrations
├── Model/                  # Python AI translation engine
│   ├── document/           # Document extraction & reconstruction
│   ├── dto/                # Data transfer objects
│   ├── memory/             # Translation memory
│   ├── pipeline/           # Translation pipeline
│   ├── prompts/            # System prompts for AI
│   ├── providers/          # AI providers (GPT-OSS, Mistral)
│   ├── validators/         # Input validation
│   ├── server.py           # FastAPI server (port 5000)
│   └── tests/              # Python tests
├── public/                 # Laravel public directory
├── resources/              # Views, CSS, JS
│   ├── views/              # Blade templates
│   └── css/                # Stylesheets
├── start-all.bat           # One-click launcher (Windows)
├── requirements.txt        # Python dependencies
├── requirements-dev.txt    # Python test dependencies
├── .env                    # Environment config (gitignored)
├── .env.example            # Environment template
└── .gitignore
```

---

## Troubleshooting

### "Class 'Illuminate\Foundation\Configuration\Exceptions' not found"
Run `composer update` — your `vendor/` directory is stale.

### Ollama not running / connection refused
Make sure Ollama is installed and running:
```bash
ollama serve          # start Ollama manually
ollama list           # verify gpt-oss:20b-cloud is pulled
```

### Port 5000 already in use
Kill the existing process:
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Linux/macOS
lsof -ti:5000 | xargs kill -9
```

### Port 8000 already in use
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/macOS
lsof -ti:8000 | xargs kill -9
```

### PHP extensions missing
On Windows, make sure your `php.ini` has these extensions enabled:
```
extension=pdo_pgsql
extension=openssl
extension=mbstring
extension=xml
extension=curl
extension=zip
extension=bcmath
extension=tokenizer
```

### Python `ModuleNotFoundError`
```bash
pip install -r requirements.txt
```

### npm `ERR! peer dep` warnings
```bash
npm install --legacy-peer-deps
```

---

## License

MIT
