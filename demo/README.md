# TerraCycle Proof — local demo runbook (Windows)

Everything below was **tested on this machine**. It starts the whole MVP from a clean
state: the real satellite pipeline, a local blockchain transaction, the FastAPI
backend and both visual surfaces.

Nothing here touches a public network, real funds or real credentials.

## What you get

| Surface | URL | Shows |
|---|---|---|
| React app — Step 01 "Choose a field" | http://localhost:5173/ | the genuine parcels from the FastAPI backend |
| React app — Step 05 "Verification" | http://localhost:5173/#verification | the real satellite verdict, canonical evidence and local-Anvil record |
| Standalone dashboard (fallback) | http://127.0.0.1:8090/ | the same verified proof, no build step, no framework |
| FastAPI backend | http://127.0.0.1:8000/api/v1/health | the real API |
| Local Anvil | http://127.0.0.1:8547 | the throwaway chain the proof was recorded on |

Ports used: **8000** (FastAPI), **8090** (proof server), **5173** (React dev), **8547**
(Anvil). Port 8080 is used by a local PostgreSQL on this machine — leave it alone.

## 0. One-time setup

```powershell
cd C:\Users\Crenguta Ciobanica\Desktop\TerraCycle\TerraCycle-IEEE-ClimateChain-Hackathon

# Python environment (already created in .venv)
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt

# Frontend dependencies
cd frontend
npm install
cd ..

# Foundry is NOT on this machine's PATH. It lives in a local folder:
$env:FOUNDRY = "C:\Users\Crenguta Ciobanica\AppData\Local\Temp\opencode\foundry"
& "$env:FOUNDRY\forge.exe" --version
```

**Node 22.11 note.** Vite 8 wants Node `>=22.12`, so `npm install` skips the optional
native package and `npm run build` fails with `Cannot find module
'@rolldown/binding-win32-x64-msvc'`. Install that one optional package into
`node_modules` (no manifest change, no global toolchain change):

```powershell
cd frontend
npm install --no-save --force @rolldown/binding-win32-x64-msvc@1.2.14
cd ..
```

**Local database.** The plans → commitments workflow needs the `parcels` rows
(`plans.parcel_id` is a foreign key). Create the database once and seed it from the
shared fixture:

```powershell
# one-time: create the role and database with the project's documented dev values
$env:PGPASSWORD = "postgres"
$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"     # psql is not on PATH

if (-not (& $psql -U postgres -h localhost -tAc "SELECT 1 FROM pg_roles WHERE rolname='terracycle'")) {
  & $psql -U postgres -h localhost -c "CREATE ROLE terracycle LOGIN PASSWORD 'change_me' SUPERUSER"
}
if (-not (& $psql -U postgres -h localhost -tAc "SELECT 1 FROM pg_database WHERE datname='terracycle'")) {
  & $psql -U postgres -h localhost -c "CREATE DATABASE terracycle OWNER terracycle"
}

# create the schema and the parcel rows (idempotent, safe to re-run)
$env:DATABASE_URL = "postgresql+psycopg://terracycle:change_me@localhost:5432/terracycle"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts\seed_parcels.py
```

**Frontend configuration.** The React app needs the backend origin. Create
`frontend/.env` (git-ignored) — **without a BOM**:

```powershell
cd frontend
"VITE_API_BASE_URL=http://127.0.0.1:8000`nPROOF_SERVER_ORIGIN=http://127.0.0.1:8090`nVITE_PROOF_BASE_URL=" | Set-Content -Encoding ascii .env
cd ..
```

> **Do not use `Set-Content -Encoding utf8` for this file.** PowerShell 5.1 writes a
> UTF-8 BOM, Vite's dotenv then fails to read the first variable, and the app shows
> "API CONFIGURATION ERROR — API base URL is not configured". `-Encoding ascii` avoids
> the BOM.

## 1. Start Anvil (terminal 1)

```powershell
$env:FOUNDRY = "C:\Users\Crenguta Ciobanica\AppData\Local\Temp\opencode\foundry"
& "$env:FOUNDRY\anvil.exe" --host 127.0.0.1 --port 8547 --chain-id 31337
```

Anvil prints its development accounts and keys. Copy the **first** key
(`0xac0974...`, account `0xf39Fd6e5...`) — it is the authorized verifier for the demo.
These are Anvil's public development keys; never use a real key here.

## 2. Generate the fresh evidence and record it (terminal 2)

```powershell
cd C:\Users\Crenguta Ciobanica\Desktop\TerraCycle\TerraCycle-IEEE-ClimateChain-Hackathon

$env:ANVIL_RPC_URL = "http://127.0.0.1:8547"
$env:ANVIL_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

cd contracts
& "$env:FOUNDRY\forge.exe" build          # once, for the deployment bytecode
cd ..

.\.venv\Scripts\python.exe contracts\smoke_test_real_evidence.py --output data\demo\latest_proof.json
```

This runs the real pipeline (Sentinel-2 CSV → verifier → canonical evidence → SHA-256),
deploys the registry, records one transaction and writes
`data/demo/latest_proof.json` **only after all integrity checks pass**. A failed run
exits non-zero and removes the previous document, so a stale proof can never be
mistaken for a current one.

## 3. Start the FastAPI backend (terminal 3)

```powershell
cd C:\Users\Crenguta Ciobanica\Desktop\TerraCycle\TerraCycle-IEEE-ClimateChain-Hackathon
$env:DATABASE_URL = "postgresql+psycopg://terracycle:change_me@localhost:5432/terracycle"
$env:ALLOWED_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Check: http://127.0.0.1:8000/api/v1/health → `{"status":"ok","database":"ok"}`

## 4. Start the proof server (terminal 4)

```powershell
cd C:\Users\Crenguta Ciobanica\Desktop\TerraCycle\TerraCycle-IEEE-ClimateChain-Hackathon
.\.venv\Scripts\python.exe scripts\serve_demo.py
```

Serves the standalone dashboard on http://127.0.0.1:8090/ and the JSON at
`/api/proof`. It exposes only those two things — the repository is never served.

## 5. Start the React app (terminal 5)

```powershell
cd C:\Users\Crenguta Ciobanica\Desktop\TerraCycle\TerraCycle-IEEE-ClimateChain-Hackathon\frontend
npm run dev
```

Vite binds the IPv6 loopback, so use **http://localhost:5173/** (not
`http://127.0.0.1:5173/`). The dev server proxies `/api/proof` to the proof server, so
the browser always talks to its own origin and no CORS change is needed.

## 6. Open the demo

- **Step 01** — http://localhost:5173/ → the three genuine parcels from the backend.
- **Step 05** — http://localhost:5173/#verification → the verified proof.
- **Standalone** — http://127.0.0.1:8090/ → the same proof, no build step.

## 7. Stop only what you started

Close each terminal with `Ctrl+C`. If a port is still held, stop the process that owns
it:

```powershell
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 8000,8090,5173,8547 } |
  ForEach-Object { Stop-Process -Id $_.OwningProcess }
```

Do not stop the local PostgreSQL (port 8080) — it is not part of this demo.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "API CONFIGURATION ERROR" | `frontend/.env` has a UTF-8 BOM, so Vite ignores the first variable | rewrite it with `Set-Content -Encoding ascii` |
| `Cannot find module '@rolldown/binding-win32-x64-msvc'` | Node 22.11 < Vite 8's `>=22.12` | `npm install --no-save --force @rolldown/binding-win32-x64-msvc@1.2.14` |
| `foreign key constraint "plans_parcel_id_fkey"` | the `parcels` table is empty | `python scripts\seed_parcels.py` |
| `connection failed ... password authentication` | the demo role/database does not exist | create it (section 0) |
| `connect ECONNREFUSED 127.0.0.1:8090` | the proof server is not running | start it (section 4) |
| `forge: command not found` | Foundry is not on PATH | use the full path `$env:FOUNDRY\forge.exe` |

## What the demo does not show

- The verdict is **nonconform** for `parcel_01` — a valid scientific result, not a
  compliance success.
- The chain is a **local Anvil** instance; the transaction is not public testnet proof.
- The registry stores evidence **metadata** only: no escrow, no EIP-712 signing, no
  settlement and no payment.
- NDVI describes vegetation conditions; it is not an organic certification.
