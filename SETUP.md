# Setup

## Prerequisites

- Git
- Python 3.11 or newer
- Docker Desktop (needed only to run the database locally)
- VS Code (recommended; install the extensions it suggests when you open the project)

## Backend

Run all commands from the repository root.

### 1. Environment file

```powershell
copy .env.example .env
```

Open `.env` and replace `change_me` with a password of your own, both in
`POSTGRES_PASSWORD` and inside `DATABASE_URL` (letters and digits only).
Never commit `.env`: it is gitignored on purpose.

### 2. Database

```powershell
docker compose up -d
docker compose ps             # wait for "healthy"
```

Each developer runs their own local database. To reset it to empty:
`docker compose down -v`.

### 3. Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1            #if you get unauthorized access error, use
                                        # Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
pip install -r backend/requirements-dev.txt
```

### 4. Run the API

```powershell
uvicorn backend.main:app --reload
```

- Health check: http://127.0.0.1:8000/api/v1/health
- Interactive docs: http://127.0.0.1:8000/docs

## Secrets

Real keys (RPC URLs with API keys, `VERIFIER_PRIVATE_KEY`) live only in your
local `.env` and are shared through a private channel, never through Git.
