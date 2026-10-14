# CORINA — GHID COMPLET: BACKEND, POSTGRESQL, ROTAȚII, CLIMĂ, HASH, INTEGRARE

**Rol:** construiești motorul central al produsului. Frontendul, blockchain-ul și modulul satelitar depind de API-ul tău.  
**Tehnologii:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, PostgreSQL 16, httpx, pytest; script Node de semnare primit de la Dorian.  
**Citește înainte:** `START_AICI.md`, `Agent.md`, `TerraCycle_Ghid_Integrare.md`.

## 1. Ce construiești, explicat ca pentru cineva nou

În browser, Oana face click pe `Generate options`. Acțiunea trimite JSON către server. Serverul tău validează datele, construiește opțiuni de rotație, poate citi istoricul meteo cache-uit și trimite răspunsul către UI. La înregistrarea angajamentului, îngheață **o copie exactă** a planului, calculează hash și păstrează acei octeți. Mai târziu, verifică tranzacții reale din contract, cheamă modulul Python al Crenguței pentru dovezi și Node signer-ul Dorian pentru EIP-712.

**Nu implementezi** grafice React, parser satelitar alternativ, al doilea model LightGBM sau cheia de semnare în frontend.

### Glosarul tău minim

- **Endpoint:** funcție apelabilă prin HTTP (`GET /health`).
- **Schema Pydantic:** shape și validarea JSON-ului de intrare/ieșire.
- **ORM/SQLAlchemy:** transformă obiectele Python în rânduri SQL.
- **CORS:** politică a browserului care controlează dacă `localhost:5173` poate face fetch spre `localhost:8000`.
- **Hash:** amprentă criptografică a unor octeți; nu criptare.
- **ABI:** descrierea funcțiilor și evenimentelor smart contractului.
- **Receipt:** dovada că o tranzacție a fost inclusă și a reușit/eșuat pe chain.
- **Idempotency:** aceeași cerere repetată nu produce două angajamente/plăți.

## 2. Setup pe Windows / PowerShell

### 2.1 Ai nevoie de:

Python 3.11+, Git, VS Code; Docker Desktop + PostgreSQL container dacă laptopul suportă Docker. **Dacă nu există Docker, instalează PostgreSQL local**, dar adaptează `DATABASE_URL`; nu transforma instalarea Docker într-o condiție blocantă pentru întregul proiect.

Din rădăcina repo-ului:

```powershell
py --version
docker --version
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install 'fastapi[standard]' sqlalchemy 'psycopg[binary]' pydantic-settings httpx requests pytest
pip freeze > requirements.txt
```

Dacă `Activate.ps1` e blocat de ExecutionPolicy, rulează **doar pentru sesiunea terminalului curent**:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Pornește PostgreSQL (după ce Docker Desktop arată `Engine running`):

```powershell
docker run --name terracycle-pg -e POSTGRES_USER=terracycle -e POSTGRES_PASSWORD=dev_only_change -e POSTGRES_DB=terracycle -p 5432:5432 -d postgres:16
```

La repornirea laptopului, dacă containerul există deja:

```powershell
docker start terracycle-pg
```

**NU folosi parola demonstrativă în deployment public.** Nu face commit la `.env`.

`backend/.env.example`:

```dotenv
DATABASE_URL=postgresql+psycopg://terracycle:dev_only_change@localhost:5432/terracycle
ALLOWED_ORIGINS=http://localhost:5173
CHAIN_RPC_URL=http://127.0.0.1:8545
CHAIN_ID=31337
CONTRACT_ADDRESS=
SIGNER_NODE_BINARY=node
VERIFIER_ADDRESS=
VERIFIER_PRIVATE_KEY=
PUBLIC_APP_URL=http://localhost:5173
```

**În producție:** RPC URL-ul poate conține token secret; nu îl urcați. `VERIFIER_PRIVATE_KEY` este citită **numai de backend/Node signer**. Dorian poate livra adresa verifierului, nu cheia sa privată. Construiți `.env` în repo local, ignorat prin `.gitignore`.

## 3. Structură fișiere: cine le deține

```text
backend/
├── main.py                     # Corina: FastAPI app
├── settings.py                 # Corina: .env, validare config
├── database.py                 # Corina: engine + Session
├── models.py                   # Corina: tabele SQLAlchemy
├── schemas.py                  # Corina: modele Pydantic
├── hashing.py                  # Corina: octeți canonici + SHA-256
├── routes/
│   ├── parcels.py              # Corina
│   ├── plans.py                # Corina
│   ├── commitments.py          # Corina
│   └── passports.py            # Corina
├── services/
│   ├── rotation_service.py     # Corina
│   ├── climate_service.py      # Corina
│   ├── chain_service.py        # Corina: receipt confirmation
│   └── attestation_service.py  # Corina: import ML + subprocess Node
├── rules/rotation.py           # Corina
├── signer/sign_verdict.mjs     # DORIAN (nu rescrie tu)
├── ml/*                        # CRENGUȚA (nu rescrie tu)
└── tests/
    ├── test_health.py
    ├── test_plans.py
    ├── test_hashing.py
    └── test_commitments.py
```

`backend/ml` este modul Python importat în același proces, **NU API Flask separat**. `sign_verdict.mjs` este rulat de backend prin `subprocess`.

## 4. Primul API în 10 minute

`backend/main.py` (schelet minimal care pornește independent):

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TerraCycle Proof API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # ulterior din ALLOWED_ORIGINS
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.get("/health")
def health():
    return {"status": "ok"}
```

Din terminal, fiind în `backend` și cu venv activ:

```powershell
uvicorn main:app --reload --port 8000
```

Deschide `http://localhost:8000/health` -> `{"status":"ok"}` și `http://localhost:8000/docs` -> Swagger UI. Acesta este **primul handoff pentru Oana**. Dacă merge doar în Postman dar nu din browser, problema poate fi CORS.

### Primul test automat

`backend/tests/test_health.py`:

```python
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
```

```powershell
python -m pytest -q
```

**Testul de mai sus poate fi rulat înainte de DB.** Nu blocați începutul API-ului de toată schema SQL.

## 5. Baza de date: ce înseamnă fiecare tabel

Folosește SQLAlchemy 2.0. La demo, 6 tabele de bază sunt suficiente; poți avea tabele ajutătoare pentru istoricul culturilor și tranzacții.

| Tabel | Cheie / câmpuri principale | Ce reține | Ce NU reține |
|---|---|---|---|
| `parcels` | `id` (string slug), `bytes32_id`, `geojson_path`, `data_origin` | identitate și geometrie predefinită | proprietar real fără consimțământ |
| `plans` | `id`, `parcel_id`, `request_json`, `options_json`, `rules_version` | recomandări/istoric declarat | verdict satelitar |
| `commitments` | `id bytes32` unic, `parcel_id`, `season_id`, `plan_id`, `plan_hash`, `snapshot_bytes`, `beneficiary`, `status`, `deadline` | legătura exactă plan ↔ chain | seed phrases |
| `transactions` | `tx_hash` unic, `commitment_id`, `action`, `block_number`, `chain_id`, `confirmed` | dovada tranzacțiilor confirmate | private keys |
| `verdicts` | `id`, `commitment_id`, `verdict`, `evidence_hash`, `evidence_bytes`, `signature`, `model_version` | verificarea înghețată | probabilitate AI inventată |
| `passports` | `commitment_id`, `public_payload_json`, `created_at` | reprezentare publicabilă | istoricul tratamentelor nepermis public |

**Constraints** obligatorii: `UNIQUE(parcel_id_bytes32, season_id_bytes32)` pentru angajamente în backend, `UNIQUE(tx_hash, chain_id)`, FK, NOT NULL pentru hash-uri după `prepare`; status enum controlat. **Unique backend NU înlocuiește** controlul de duplicat on-chain.

### DB fără să scrii toată aplicația din prima

`backend/database.py`:

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as session:
        yield session
```

La început poate crea tabele cu `Base.metadata.create_all(bind=engine)` doar pentru local/dev. Pentru reproducibilitate serioasă se trece la Alembic (nu e obligatoriu dacă timpul e foarte limitat); nu rulați `DROP ALL` la restart.

**Config sigur:** în PowerShell, fișierul `.env` **nu se încarcă singur** în `os.environ`. Integrează `pydantic-settings` / `python-dotenv` în `settings.py` sau pornește `uvicorn --env-file .env`; documentează clar varianta aleasă. În `SETUP.md` să nu existe comenzi care „magically” au access la variabile inexistente.

## 6. Definește Pydantic și endpointurile ÎNAINTE de a programa logică complicată

Schema agreată este **propunerea** din `TerraCycle_Ghid_Integrare.md`; Corina + Dorian o aprobă în PR. Nu schimba `POST /plans` în `POST /api/plan` pe parcurs fără să modificați ambele părți.

### Modele minime utile

```python
from pydantic import BaseModel, Field
from typing import Literal

class HistoryItem(BaseModel):
    year: int = Field(ge=1990, le=2026)
    crop: str = Field(min_length=2, max_length=60)
    treatments: list[str] = []

class PlanRequest(BaseModel):
    parcel_id: str
    season_id: str
    history: list[HistoryItem] = Field(min_length=1)
    desired_crop: str

class TxRequest(BaseModel):
    action: Literal["register", "fund", "settle", "refund"]
    tx_hash: str = Field(pattern=r"^0x[a-fA-F0-9]{64}$")
```

`2026` este suficient pentru demonstrația din octombrie 2026, nu un schema eternă. În funcție de faza proiectului, poate fi `max=datetime.now(UTC).year` prin validator.

**Validare de business peste Pydantic:** anul nu se repetă, `season_id` există în fixture, cultura este din lista voastră 6–10, wallet valid, ID parcelă există.

### Endpointuri în ordinea implementării

1. `GET /health`
2. `GET /parcels` (citește fișierele/fixtures de la Crenguța)
3. `POST /plans` (inițial regulă simplă, deterministică)
4. `GET /config` (ABI/adresa de la Dorian)
5. `POST /commitments/prepare` (snapshot + DB + hash)
6. `GET /commitments/{id}`
7. `POST /commitments/{id}/transactions` (verify tx)
8. `POST /commitments/{id}/verify` (Python ML -> evidence -> Node)
9. `GET /passports/{id}`
10. `GET /commitments/{id}/snapshot` (octeți exacți)

**Nu include `/predict` sau `/api/commit` suplimentar** decât dacă îl propuneți și aprobați oficial. Avem timp scurt; suprafața API trebuie să rămână mică.

## 7. ROTATION RULES: logică simplă și explicabilă

### Ce rezolvă?

Nu trebuie să „inventezi un agronom AI”. Construiești un motor de **recomandare preliminară** a rotației pe 3 ani, în care fiecare recomandare are o justificare clară și o avertizare. Input: istoricul declarat, cultura dorită, calendar/clima din Open-Meteo. Output: 2–3 opțiuni, scor aproximativ bazat pe reguli (dacă e cazul) și motive. Regulile agronomice trebuie **documentate cu surse**, nu prezentate drept norme universale.

### Propunere implementabilă

`backend/rules/rotation.py`:

```python
CROP_FAMILY = {
    "wheat": "cereal", "maize": "cereal", "barley": "cereal",
    "sunflower": "asteraceae", "rapeseed": "brassicaceae",
    "peas": "legume", "soybean": "legume", "alfalfa": "legume",
}

def score_sequence(previous_crop: str, sequence: list[str]) -> dict:
    """Scor demonstrativ, NU sfat agronomic complet."""
    score = 100
    warnings = []
    reasons = []
    crops = [previous_crop] + sequence
    for before, after in zip(crops, crops[1:]):
        if before == after:
            score -= 35
            warnings.append(f"Avoid repeating {after} immediately in this demo rule.")
        elif CROP_FAMILY.get(before) == CROP_FAMILY.get(after):
            score -= 10
            warnings.append("Two consecutive crops share a broad family grouping.")
        else:
            score += 0
            reasons.append("Alternation across the demo crop groups.")
    return {"score": max(0, score), "reasons": reasons, "warnings": warnings}
```

Aceasta este **doar o regulă de demaraj**, nu dovadă că „două cereale consecutive” sunt întotdeauna interzise. Familia biologică și grupa de rotație agricolă nu sunt identice; validați lista şi logica pe surse agronomice potrivite zonei. `climate_service` poate adăuga o explicație informativă despre precipitații/temperatură, dar nu impuneți un scor pseudoștiințific netestat.

### Cum generezi cele 3 opțiuni

Păstrează un catalog de 6–10 culturi. Enumeră maxim câteva combinații permise pe 3 ani, aplică scorul și sortează. Pentru aceeași intrare și versiune de reguli, rezultatul este mereu identic (important pentru hashing). Test cu 3 istorice diferite: recomandări și motive distincte.

## 8. CLIMA Open-Meteo: cere date și salvează răspunsul

Documentația oficială este [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api). Pentru comparații istorice coerente, cere explicit modelul `era5_land` și pune în request `timezone=UTC`; datele istorice reanalizate **nu sunt stația meteo din parcelă** și rezoluția lor spațială este mai grosieră.

```python
# backend/services/climate_service.py
import json
import requests
from pathlib import Path

CACHE_DIR = Path("../data/climate")  # din cwd=backend

def fetch_climate(latitude: float, longitude: float, start: str, end: str, cache_id: str):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    file = CACHE_DIR / f"{cache_id}.json"
    if file.exists():
        return json.loads(file.read_text(encoding="utf-8"))
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude, "longitude": longitude,
        "start_date": start, "end_date": end,
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "UTC", "models": "era5_land",
    }
    response = requests.get(url, params=params, timeout=25)
    response.raise_for_status()
    result = response.json()
    file.write_text(json.dumps({"source_url": response.url, "payload": result},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return {"source_url": response.url, "payload": result}
```

**Înainte de folosire verificați formatul răspunsului**: `daily.time`, `daily.precipitation_sum`, `daily.temperature_2m_mean` și numărul de elemente egal; dacă API returnează altceva/erori, salvați eroarea în log și folosiți un fixture CLAR marcat. Nu încercați API remote în timpul demo-ului: cache local. Pune în `data/climate/README.md` sursa, data descărcării, modelul, coordonatele folosite, licența și limita rezoluției.

## 9. HASHING: responsabilitatea TA cea mai importantă

**Este nevoie de doi algoritmi diferiți:**

- `plan_hash = SHA-256(canonical plan snapshot bytes)` în Python;
- `commitment_id = Keccak-256(ABI.encode(parcelIdBytes32, seasonIdBytes32))` în EVM / ethers (verificat în test cu Dorian).

Nu converti un `bytes32` în text înainte de hash. Nu pune JSON-ul întreg în Solidity. Nu folosi `json.dumps` cu defaults diferite în altă parte.

`backend/hashing.py`: implementează `canonical_bytes`, `hash_snapshot` **exact ca în Ghidul de Integrare**. IMPORTANT:

- snapshotul trebuie să includă istoricul declarat **complet**, opțiunea de rotație selectată, tratamentele declarate, parcelă, sezon, versiunea regulilor, politica verificării, perioada, owner-ul și scheme version;
- fixează UTC și unitățile înainte de serializare;
- nu include float-uri JSON, folosește întregi/șiruri cu precizie fixă în snapshot;
- persistă `snapshot_bytes` și `sha256` în aceeași tranzacție SQL;
- câmpul original devine IMUTABIL după `prepare`;
- compară snapshotul, nu copia regenerată a datelor editabile, la scenariul istoric modificat.

### Teste de hashing obligatorii

1. Chei în ordine diferită -> aceiași octeți canonici.
2. Diacritice și Unicode -> hash reproducibil din aceiași octeți salvați.
3. O valoare modificată (`crop`, `treatment` ori `policy_version`) -> alt hash.
4. Un float nepermis -> eroare explicită.
5. Snapshot salvat -> read DB -> bytes identici, nu text refăcut.
6. Valoarea SHA-256 este mereu `0x` + 64 hex.

**Atenție:** `json.dumps(sort_keys=True)` NU este standard general multi-limbaj RFC 8785. Regula funcționează aici tocmai pentru că **nimeni altcineva nu reconstruiește JSON-ul**. În contract și browser circulă hash-ul deja produs.

## 10. Confirmați tranzacțiile, nu acceptați un hash tastat de client

Dorian implementează contractul, tu implementezi `chain_service.py`. La `POST /commitments/{id}/transactions`:

1. validează formatul `tx_hash`, rețeaua RPC, adresa contractului;
2. ia receipt-ul din RPC, confirmă `status=1`, bloc și destination `to`;
3. recuperează tranzacția și decodează inputul metodei cu ABI, verifică exact funcția declarată de `action`;
4. compară `commitmentId` sau perechea `parcelId + seasonId`, `planHash`, `amount`, `from`, `funder/beneficiary` unde sunt relevante;
5. verifică evenimentul emis și argumentele, **nu doar existența unui log**;
6. citește `commitments(id)` sau getterul contractului pentru starea rezultată;
7. salvează tx și status în DB printr-o operație idempotentă;
8. returnează `confirmed` doar după toate aceste verificări.

Poți folosi `web3.py` (instalează separat `pip install web3`) pentru RPC și ABI, dar asta e **o dependență suplimentară aprobată**, nu presupune că `requests` știe decodare ABI. Pentru MVP local, dacă nu ai timp, *backendul tot trebuie să poată verifica* un receipt și să respingă tranzacții care nu aparțin angajamentului. Nu afișa `Paid` bazat pe `tx.wait()` doar în browser.

Erori: `TX_NOT_FOUND`, `PENDING_CONFIRMATION`, `TX_FAILED`, `TX_MISMATCH`, `WRONG_NETWORK`, `ALREADY_COMMITTED`, `PLAN_HASH_MISMATCH`. Returnează HTTP 409/422/503 după caz plus structura stabilă `{"error":{"code":"...","message":"..."}}`.

## 11. INTEGRARE ML: nu duplica algoritmul Crenguței

Crenguța îți predă `backend/ml/rules.py` cu:

```python
verify_parcel(parcel_id: str, policy: dict, evidence_directory: str) -> dict
```

Tu faci doar orchestrarea:

```text
POST /commitments/{id}/verify
   -> selectezi commitment Funded
   -> compari planHash cu snapshot bytes
   -> citești politica înghețată
   -> import backend.ml.rules.verify_parcel
   -> primești verdict și observații + metadate
   -> verifici structura rezultatului cu Pydantic
   -> construiești evidence_document complet (vezi ghid)
   -> calculezi SHA-256 și salvezi evidence bytes
   -> invoci signer-ul Node (Dorian) cu EIP-712 message
   -> salvezi verdict, semnătură, validUntil
   -> returnezi attestation pentru settle în UI
```

**Nu transforma `MODEL_UNAVAILABLE` în `nonconform`.** Eșecul procesării e eroare tehnică, în timp ce `inconclusive` este verdict științific de dovezi insuficiente.

### Node signer: subprocess cu timeout, fără chei în stdin

```python
import json
import subprocess


def sign_attestation(payload: dict):
    completed = subprocess.run(
        ["node", "backend/signer/sign_verdict.mjs"],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=15, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("SIGNER_UNAVAILABLE")
    return json.loads(completed.stdout)
```

**Atenție cale:** exemplul pornește din **rădăcina repo-ului**; dacă rulezi `uvicorn` din `backend`, calea corectă este `signer/sign_verdict.mjs`. Nu lăsa `cwd` implicit ambigu: în codul final folosește `Path(__file__).resolve().parent / 'signer' / 'sign_verdict.mjs'` și variabile de mediu stabilite. Nu loga `VERIFIER_PRIVATE_KEY` și nu returna `stderr` complet la user.

Validare după semnare: signature hex 65 bytes, digest consistent, signer recovering address egal `VERIFIER_ADDRESS`, domain cu chainId/adresă reale. **Nu semna verdicturi pe date mock ca și cum ar fi reale**, pune o etichetă/flag în raport.

## 12. Pașaport digital: ce poate vedea publicul

Response `GET /passports/{id}` are: parcela/regiunea, perioada, angajamentul, hashul planului, politica, observațiile cu sursă/filtrare, model/rule version, verdict + motiv, evidence hash, starea de contract, tx links, limitări. Conform planului, QR-ul deschide pagina React, nu API brut.

Ferește API-ul de divulgarea datelor personale sau a istoricului integral de tratamente dacă nu a fost stabilit să fie public. În proiectul demo, folosiți parcele și istorice demonstrative sau anonimizate. E clar că digital passport **nu este certificat eco**.

## 13. Testare: matrice minimă

| Test | Input | Rezultat corect |
|---|---|---|
| health | GET | 200 `ok` |
| parcel invalid | `parcel_id` inexistent | 404/422, nu crash |
| plan invalid | istoric cu ani repetați | 422 cu mesaj util |
| rotation | 3 istorice diferite | opțiuni/explicații coerente |
| hashing | reorder chei JSON | același SHA |
| hashing mutation | schimbi `treatments` | SHA diferit și verificarea refuzată |
| tx false | tx hash aleator | `TX_NOT_FOUND` |
| tx other contract | receipt valid dar alt contract | `TX_MISMATCH` |
| ML insufficient | 3 observații din minimum 5 | `inconclusive`, cod 2 |
| signer offline | `node` absent / timeout | `SIGNER_UNAVAILABLE`, nu `nonconform` |
| double confirm | aceeași tx trimisă de 2 ori | fără rând duplicat |
| passport | id valid/invalid | payload complet / 404 |

**Rulare:** `python -m pytest -q` pentru backend, `curl`/PowerShell `Invoke-RestMethod` pentru health, Swagger `/docs` pentru explorarea API-ului. `GET /docs` este și documentarea voastră OpenAPI; exportă `docs/openapi.json` după ultima modificare de endpoints.

## 14. Calendar strict pe zile

| Zi | Ce faci în ordinea recomandată | Ce predai |
|---|---|---|
| **14 oct** | setup Python + health + CORS, schemă API cu toți, model DB simplu, 3 exemple JSON | `/docs`, PR contract și health |
| **15 oct** | `GET /parcels`, `POST /plans`, `/prepare`, hashing și DB, `GET /commitments` | demo cap-coadă pe fixture |
| **16 oct** | reguli rotație + `climate_service` + cache + `docs/decisions.md` | 3 rezultate diferite și surse clima |
| **17 oct** | `/passports/{id}` cu fixture, evidence schema, test comun Crenguța | pașaport vizibil Oana |
| **18 oct** | import `verify_parcel` real, tratează `inconclusive` și `MODEL_UNAVAILABLE`, signer Node | verdict API reproductibil |
| **19 oct** | chain_service: verifică receipt, hash, roluri, sumă, chain, contract, stare; flow complet | un `tx_hash` real și eroare TX_MISMATCH demonstrată |
| **20 oct** | pytest health/plans/hashing/tx/ML, cazuri refund/expire cu Dorian | teste și loguri |
| **21 oct** | scenariu istoric modificat: backend refuză, nu UI-only | API PLAN_HASH_MISMATCH |
| **22 oct** | SETUP.md pentru o clonă nouă, PostgreSQL/config `.env.example` | coleg poate porni sistemul |
| **23 oct** | bug fix + README/API freeze | PR final backend |
| **24 oct** | `docs/openapi.json` export, tehnical audit, video handoff | setup verificat și explicații |
| **25 oct** | ultimă verificare în Devpost; fără features | stare stabilă |

**Poartă 14 oct 20:00:** cu Dorian, contract compilat + un test; schema EIP-712 stabilită. Fără asta, nu simulați integrarea de criptografie ca fiind „funcțională”.

## 15. Probleme frecvente + soluții simple

| Problemă | Ce verifici întâi |
|---|---|
| `ModuleNotFoundError: fastapi` | e activ venv-ul? `python -m pip show fastapi` |
| `psycopg.OperationalError` | Docker container rulează? URL/parolă/port 5432? |
| `blocked by CORS` | port frontend exact, CORS middleware și origin fără slash final |
| `422 Unprocessable Entity` | request Pydantic vs schema aprobată; `response.json()` |
| `table does not exist` | schema migrată/creată? URL spre DB corectă? |
| `connection refused 8545` | Anvil pornit de Dorian? `CHAIN_RPC_URL` corect? |
| Node signer timeout | Node instalat? script path corect? `stderr` pe server? |
| `hash mismatch` | octeți originali, Unicode, ordinea listelor, floats? |
| `no observations` | Crenguța a predat CSV și metadata? cale corectă? |

## 16. Definiție de DONE

- [ ] API rulează (`/health`, `/docs`) și CORS permite frontendul real.
- [ ] O singură schemă OpenAPI, actualizată la integrare.
- [ ] DB are constraints și snapshots canonice persistate.
- [ ] `plan_hash` e reproductibil pe octeții salvați; mutațiile sunt detectate.
- [ ] Confirmă tranzacții reale și respinge tx-uri străine.
- [ ] Rotațiile explică *de ce*, cu reguli sursate și avertismente.
- [ ] Open-Meteo e cache-uit cu model/sursă/date clare.
- [ ] Verificarea ML importă modulul Crenguței, fără duplicare.
- [ ] `inconclusive` ≠ `nonconform` ≠ eroare tehnică.
- [ ] Node signer funcționează fără private key în stdout.
- [ ] `SETUP.md` e testat dintr-o clonare nouă.

## 17. Prompt pentru asistentul AI

```text
Sunt Corina, începătoare cu FastAPI/SQLAlchemy.
Citește START_AICI.md, Agent.md, TerraCycle_Ghid_Integrare.md și Role_Corina.md.
Lucrează NUMAI la [TASK] în backend/. Explică întâi scopul, apoi dă
comenzile pentru PowerShell, fișierele exacte și un test pytest cu rezultat așteptat.
Respectă contractul API aprobat; nu adăuga endpointuri în tăcere.
Hash-uirea se face doar în Python pe octeți salvați, nu în JS.
Nu simula tranzacții confirmate și nu prezenta date mock ca reale.
Explică și ce predau Oanei / Dorian / Crenguței după fiecare pas.
```

**Documentație:** [FastAPI](https://fastapi.tiangolo.com/tutorial/), [SQLAlchemy](https://docs.sqlalchemy.org/en/20/), [Pydantic](https://docs.pydantic.dev/latest/), [Open-Meteo Historical](https://open-meteo.com/en/docs/historical-weather-api), [pytest](https://docs.pytest.org/).
