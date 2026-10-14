# TERRACYCLE PROOF — GHIDUL COMUN DE INTEGRARE

**Versiune:** propunere V1, 14 octombrie 2026  
**Citește:** toate cele patru persoane, înainte să lege două module.  
**Statut IMPORTANT:** documentul cu acest nume era menționat în planul încărcat, **dar nu era inclus între fișierele furnizate**. Acest document **nu pretinde că reproduce un contract API oficial existent**. Este o SPECIFICAȚIE NOUĂ PROPUSĂ pe baza arhitecturii și convențiilor din `Agent.md`, ce se aprobă prin PR comun Corina + Dorian + Oana + Crenguța.

## 0. Decizie de luat împreună ÎNAINTE de implementare

Parcurgeți acest ghid în call și completați `docs/decisions.md` cu `SCHEMA V1 ACCEPTATĂ`, data, persoanele și orice schimbare față de exemple. După aprobare, **acest document devine sursa unică pentru nume de endpointuri, tipuri JSON și apeluri contract**. Nu lăsați o copie alternativă în mesaje.

| Decizie | Propunere V1 | Aprobare necesară |
|---|---|---|
| Format ID parcelă/sezon on-chain | câte un `bytes32` stabil, stocat în fișierul demo | Corina + Dorian |
| Calcul `commitmentId` | `keccak256(abi.encode(parcelId, seasonId))` | Corina + Dorian |
| Hash JSON plan/dovezi | `SHA-256` peste octeții JSON canonici, produși și stocați doar în Python | Corina |
| Verdict EIP-712 | `0=conform`, `1=nonconform`, `2=inconclusive` | toți |
| Fereastra verificării | 2024; fereastră explicită, nu întregul sezon implicit | Crenguța + Corina |
| Pragul agronomic demonstrativ | minimum 70% observații clasificate vegetație, numai dacă există observații suficiente | Crenguța |
| Un sistem de rulare pentru demo | contract local + Sepolia dacă deploymentul reușește | Dorian |

## 1. Diagrama de proces, în limbaj normal

```text
[Oana] UI: alege parcela (parcel_id) + completează istoricul
      | POST /plans
      v
[Corina] API: recomandă rotații și returnează un plan ales
      | POST /commitments/prepare
      v
[Corina] îngheață plan_snapshot -> canonical_bytes -> SHA-256(plan_hash)
      | generează parcel_id_bytes32, season_id_bytes32, commitment_id
      v
[Oana] MetaMask: registerCommitment(...) -> hash tranzacție
      | POST /commitments/{id}/transactions (action=register)
      v
[Corina] verifică receipt on-chain -> salvează Registered
      v
[Oana] alt wallet (finanțator): fundCommitment(...), ETH de test
      | POST .../transactions (action=fund)
      v
[Corina] confirmă Funded -> poate începe verificarea
      | POST /commitments/{id}/verify
      v
[Crenguța] modul Python: observații CSV -> control calitate -> predicții/regelă -> verdict
      | evidence_document (complet, cu versiuni și observații)
      v
[Corina] canonical SHA-256 evidence -> Node signer Dorian (EIP-712)
      | attestation + signature
      v
[Oana] settle(attestation, signature) via MetaMask
      | POST .../transactions (action=settle)
      v
[Corina] receipt + evenimente: Paid SAU Negative; Negative poate fi refunded
      v
[Oana] /passport/{commitment_id} + QR -> API GET /passports/{id}
```

**Cheia conceptuală:** blockchain-ul garantează condițiile de plată și protejează *hash-urile* împotriva modificării nedetectate; **nu confirmă singur realitatea datelor agricole**. Un verificator semnează un raport verificabil și își asumă calitatea dovezilor.

## 2. Datele unice folosite peste tot

În `data/fixtures/demo.json` păstrați un obiect central, de tip:

```json
{
  "fixture_version": "demo-v1",
  "parcel_id": "parcel-demo-01",
  "parcel_id_bytes32": "0x1111111111111111111111111111111111111111111111111111111111111111",
  "season_id": "season-2024",
  "season_id_bytes32": "0x2222222222222222222222222222222222222222222222222222222222222222",
  "policy_version": "cover-v1",
  "window_start": "2024-04-01",
  "window_end": "2024-06-30",
  "reward_wei": "1000000000000000",
  "source_type": "fixture",
  "notes": "IDs on-chain demonstrative fixe, nu sunt ID-uri cadastrale reale"
}
```

Acești octeți repetați sunt **identificatori demonstrativi**, nu rezultați dintr-un calcul magic. Contractul primește `bytes32`, backendul și frontendul folosesc aceleași valori returnate de API. **Nu hash-uiți separat slugul** `parcel-demo-01` în browser. Înainte de testul E2E, Dorian verifică în Foundry și ethers aceeași valoare de `commitmentId`.

Un singur fixture este folosit de toată echipa; dacă vreți încă patru parcele pentru demo, adăugați în același loc identificatori distincți și descrieri pentru fiecare. **GeoJSON-ul fiecărei parcele trebuie să conțină coordonate reale sau demonstrative etichetate corect și sursa geometriei.**

### Conveții serializare

- JSON primit/returnat: snake_case; timp UTC ISO-8601; numere financiare `reward_wei` ca string.
- Hash SHA-256 și Ethereum `bytes32`: `0x` + 64 caractere hex; **SHA-256 ≠ Keccak-256**, nu se substituie unul altuia.
- `commitmentId`: keccak al celor două `bytes32` ABI-encodate, nu SHA-256 de JSON.
- Nu există date de contact sau chei private on-chain.
- `funder`, `beneficiary`, `verifier`: trei roluri logice; pot fi portofele DEV distincte. Cheia verificatorului **nu intră niciodată în Vite/React**.

## 3. API propus V1: lista exactă

| Endpoint | Responsabil | Scop | Începe cu mock? |
|---|---|---|---|
| `GET /health` | Corina | probă că API rulează | nu |
| `GET /config` | Corina + Dorian | chainId, contract, ABI, explorer, URL public | da |
| `GET /parcels` | Corina + Crenguța | listă parcele predefinite | da |
| `POST /plans` | Corina | recomandă rotațiile pe trei ani | da |
| `POST /commitments/prepare` | Corina | creează snapshot & hash înainte de registrare | da |
| `POST /commitments/{id}/transactions` | Corina + Dorian | verifică o tranzacție `register`, `fund`, `settle` sau `refund` | da |
| `GET /commitments/{id}` | Corina | stare reală și date publice | da |
| `POST /commitments/{id}/verify` | Corina + Crenguța + Dorian | generează raportul cu verdict și semnătură | da, dar eticheta MOCK explicită |
| `GET /passports/{id}` | Corina | afișarea verificabilă de Oana | da |
| `GET /commitments/{id}/snapshot` | Corina | returnează **octeții originali** ai snapshotului | nu |

**Interfață propusă, nu existentă deja:** dacă vreți alte rute, modificați întâi această masă și fișierul `docs/api-contract.md`, apoi implementați.

### `GET /health`

```json
{"status":"ok"}
```

### `GET /config`

```json
{
  "chain_id": 31337,
  "rpc_network_name": "Anvil local",
  "contract_address": "0x0000000000000000000000000000000000000001",
  "contract_abi": [],
  "explorer_base_url": null,
  "public_app_url": "http://localhost:5173",
  "is_demo_network": true
}
```

`contract_abi` de mai sus este **placeholder**, frontendul nu poate interacționa cu el până când Dorian exportă ABI-ul real din `contracts/out/TerraCycleEscrow.sol/TerraCycleEscrow.json`. `contract_address` este **placeholder**, NU adresă de deployment. Corina va înlocui configul numai cu valori validate pe rețeaua efectivă. Când utilizatorul e pe Sepolia, `chain_id` trebuie să fie 11155111 (verificat și în wallet).

### `GET /parcels` → obiectul folosit de Oana

```json
{
  "parcels": [
    {
      "parcel_id": "parcel-demo-01",
      "parcel_id_bytes32": "0x1111111111111111111111111111111111111111111111111111111111111111",
      "display_name": "Field 01",
      "region": "Dolj, Romania",
      "area_ha": null,
      "geometry_url": "/assets/parcels/parcel-demo-01.geojson",
      "data_origin": "fixture"
    }
  ]
}
```

Nu inventați numele proprietarilor și nu afișați hectarele dacă nu le calculați corect (GeoJSON în EPSG:4326 nu permite o arie corectă prin simpla înmulțire de grade).

### `POST /plans`

Request:

```json
{
  "parcel_id": "parcel-demo-01",
  "season_id": "season-2024",
  "history": [
    {"year": 2022, "crop": "wheat", "treatments": ["herbicide_declared"]},
    {"year": 2023, "crop": "sunflower", "treatments": []}
  ],
  "desired_crop": "maize"
}
```

Response orientativ:

```json
{
  "plan_id": "plan-demo-01",
  "parcel_id": "parcel-demo-01",
  "recommendations": [
    {
      "option_id": "rotation-a",
      "crops_by_year": [{"year": 2024, "crop": "maize"}, {"year": 2025, "crop": "wheat"}, {"year": 2026, "crop": "peas"}],
      "score": 74,
      "reasons": ["Crop family alternation is preferred in this rule-based demo."],
      "warnings": ["This is educational planning support, not agronomic certification."]
    }
  ],
  "climate_source": "Open-Meteo ERA5-Land",
  "rules_version": "rotation-v1",
  "data_origin": "fixture"
}
```

Scorul `74` este strict **valoare ilustrativă**, nu rezultat calculat. În cod, Corina va calcula deterministic sau va elimina scorul; Oana nu afișează o notă ca fiind științifică dacă încă e mock.

### `POST /commitments/prepare`

Request:

```json
{
  "parcel_id": "parcel-demo-01",
  "season_id": "season-2024",
  "plan_id": "plan-demo-01",
  "selected_option_id": "rotation-a",
  "beneficiary_wallet": "0x3333333333333333333333333333333333333333",
  "verification_policy": {
    "policy_version": "cover-v1",
    "type": "vegetation_cover",
    "window_start": "2024-04-01",
    "window_end": "2024-06-30",
    "min_observations": 5,
    "min_valid_pixel_fraction": 0.5,
    "min_temporal_coverage": 0.5,
    "min_positive_fraction": 0.7
  },
  "reward_wei": "1000000000000000"
}
```

Response (notă: hash-urile sunt valori calculate, **nu** substituiți literal un `0xaaaa...`):

```text
{
  "commitment_id": "0x<64-hexdigits-computed>",
  "parcel_id_bytes32": "0x<64-hexdigits-from-fixture>",
  "season_id_bytes32": "0x<64-hexdigits-from-fixture>",
  "plan_hash": "0x<sha256-hex-of-saved-canonical-bytes>",
  "settle_deadline": 1764547200,
  "state": "Prepared",
  "snapshot_url": "/commitments/{id}/snapshot"
}
```

**`Prepared` este doar stare OFF-CHAIN** în DB; contractul nu are această stare. `settle_deadline` din exemplu trebuie generat din configurație; nu copiați timestamp-ul fără verificarea datei și a modelului de expirare pentru scenariul 2024 retrospective.

### `POST /commitments/{id}/transactions`

Request după `registerCommitment`:

```json
{"action":"register","tx_hash":"0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

Pe același endpoint, `action` poate fi `fund`, `settle`, `refund`, corespunzător metodei contractului. Response:

```json
{"commitment_id":"0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","action":"register","confirmation":"confirmed","state":"Registered"}
```

**Câmpuri demonstrative:** cheia din URL este calculată; `tx_hash` din JSON trebuie să provină din tranzacția reală, nu din exemple. Serverul trebuie să respingă o tranzacție care are altă adresă de contract, alt ID, alt sender unde rolul contează, parametri diferiți sau care a eșuat (`receipt.status != 1`). Dacă receipt-ul încă lipsește, răspundeți `PENDING_CONFIRMATION`, nu `confirmed`.

### `GET /commitments/{id}`

```json
{
  "commitment_id": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "parcel_id": "parcel-demo-01",
  "season_id": "season-2024",
  "plan_hash": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "beneficiary_wallet": "0x3333333333333333333333333333333333333333",
  "state": "Funded",
  "tx_hashes": {"register": null, "fund": null, "settle": null, "refund": null},
  "data_origin": "fixture"
}
```

În backend real câmpurile de tip `tx_hashes` conțin hash-uri numai după confirmare; la început sunt `null`.

### `POST /commitments/{id}/verify`

Fără corp în MVP. Corina verifică: starea e `Funded`, hash-ul planului e încă același, snapshot-ul e înghețat, fișierele satelitare sunt pregătite. Crenguța întoarce o decizie **bazată pe dovezile reale disponibile** sau marchează explicit lipsa acestora. Backendul construiește `evidence_document`, îl canonizează și îl hash-uiește; Dorian semnează.

Response propus:

```text
{
  "verdict": "inconclusive",
  "verdict_code": 2,
  "reason": "Insufficient cloud-free observations",
  "evidence_hash": "0x<sha256-over-immutable-evidence-document>",
  "attestation": {
    "commitmentId": "0x<...>",
    "planHash": "0x<...>",
    "evidenceHash": "0x<...>",
    "verdict": 2,
    "validUntil": 1799999999
  },
  "signature": "0x<65-byte-ecdsa-signature>",
  "data_origin": "satellite_observations"
}
```

**Atenție:** verificarea retrospective din 2024 este permisă ca demo; `validUntil` al atestării trebuie să fie în viitorul momentului de settle demonstrativ, nu la finele sezonului 2024. Semnătura nu reprezintă automat un audit extern independent.

### `GET /passports/{id}`

```text
{
  "commitment_id": "0x<...>",
  "parcel_display_name": "Field 01",
  "season_id": "season-2024",
  "plan_hash": "0x<...>",
  "evidence_hash": "0x<...>",
  "policy_version": "cover-v1",
  "verdict": "inconclusive",
  "contract_state": "Negative",
  "observations": [
    {"acquired_at":"2024-05-11", "ndvi_mean":0.43,"valid_pixel_fraction":0.92,"scene_id":"source-id"}
  ],
  "data_provenance": {"provider":"Copernicus Data Space", "dataset":"Sentinel-2 L2A", "method":"cloud-masked NDVI", "origin":"real_or_explicit_fixture"},
  "tx_hashes": {"register":null,"fund":null,"settle":null,"refund":null},
  "limitations": ["NDVI cannot verify pesticide use or organic certification."]
}
```

`observations` are date orientative; nu le prezentați ca observații reale dacă nu au fost exportate. La un `GET` public, nu expuneți istoricul complet al tratamentelor fără acord explicit; păstrați doar elementele necesare verificării și dovezile publicabile.

## 4. Snapshot-uri canonice și hashing

**Responsabil unic: Corina.** Algoritmul V1 este o convenție locală de echipă, NU implementare completă RFC 8785. Pentru că JSON conține numere și Unicode, evitați aproximări. Reguli V1:

1. JSON include *numai* tipuri obiect/listă/string/int/bool/null; **nu** include `float` în obiectele înghețate. Pragurile se păstrează ca string-uri zecimale exacte sau ca întregi (`min_positive_percent: 70`). Dacă schema API folosește `0.7`, convertiți înainte de snapshot într-un format stabil documentat.
2. Ordenați cheile dicționarelor recursiv; listele își păstrează ordinea deliberată. `ensure_ascii=False`, fără spații (`separators=(",", ":")`), UTF-8.
3. Serializați **o singură dată**, salvați exact acei octeți `snapshot_bytes` în DB/disc imutabil, faceți SHA-256 pe ei; nu calculați din nou hash-ul unui obiect reconstituit din altă sursă fără a compara cu snapshotul original.
4. Dacă datele sunt modificate, creați **altă versiune**; nu rescrieți snapshotul legat de hash-ul on-chain.

Cod minimal de pornire (nu înlocuiește teste):

```python
# backend/hashing.py
import hashlib
import json


def canonical_bytes(payload: dict) -> bytes:
    def reject_float(value):
        if isinstance(value, float):
            raise TypeError("Floats are forbidden in canonical snapshots")
        if isinstance(value, dict):
            for child in value.values():
                reject_float(child)
        elif isinstance(value, list):
            for child in value:
                reject_float(child)

    reject_float(payload)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def hash_snapshot(payload: dict) -> tuple[bytes, str]:
    content = canonical_bytes(payload)
    return content, "0x" + hashlib.sha256(content).hexdigest()
```

Test minim:

```python
def test_hash_does_not_depend_on_key_order():
    a = {"parcel": "Câmp", "policy": {"v": 1, "active": True}}
    b = {"policy": {"active": True, "v": 1}, "parcel": "Câmp"}
    assert hash_snapshot(a) == hash_snapshot(b)
```

Pentru demo „istoric modificat”: comparați **snapshotul declarat acum** cu snapshotul imutabil legat de `planHash`; dacă diferă, API returnează `PLAN_HASH_MISMATCH` și nu semnează. Schimbarea bazei de date „în loc” nu trebuie să modifice dovada înghețată. **Nu transmiteți direct un `planHash` ales de utilizator drept adevăr de referință.**

## 5. `evidence_document`: CE hash-uim efectiv

Acesta este **raportul înghețat** pe care îl semnează verificatorul prin `evidenceHash`; nu este un simplu scor:

```text
{
  "schema_version": "evidence-v1",
  "commitment_id": "0x<...>",
  "plan_hash": "0x<...>",
  "parcel_id": "parcel-demo-01",
  "policy": {"policy_version":"cover-v1", "window_start":"2024-04-01",
             "window_end":"2024-06-30", "minimum_observations":5,
             "minimum_coverage_percent":50, "minimum_positive_percent":70},
  "observations": [
    {"acquired_at":"2024-05-11", "scene_id":"...", "ndvi_milli":430,
     "valid_pixel_percent":92, "is_valid":true, "vegetation_class":1}
  ],
  "quality": {"valid_count":1, "coverage_percent":10,
              "excluded_count":0, "inconclusive_reason":"INSUFFICIENT_OBSERVATIONS"},
  "dataset": {"dataset_version":"...", "source":"Copernicus Sentinel-2 L2A",
              "export_time":"...", "csv_sha256":"..."},
  "model": {"model_version":"...", "features_version":"...", "source":"ML_OR_RULE_BASED",
            "model_file_sha256":"..."},
  "verdict": "inconclusive",
  "verdict_code": 2
}
```

Acesta este **model de structură**, nu un raport autentic. Pentru reproducibilitate, în snapshot se folosesc câmpuri întregi sau string-uri cu precizie fixă (`ndvi_milli`, procente), nu floats JSON instabile. Observațiile sortate după `(acquired_at, scene_id)`. Crenguța transmite observațiile brute/metadatele; Corina creează documentul canonic și păstrează fișierul/modelul/metadatele necesare reproducerii. `evidence_hash` este SHA-256 și se pune în struct EIP-712.

## 6. Contract Solidity: interfață PROPUSĂ, invariabile și coduri

### Interfață agreată

```solidity
struct VerificationResult {
    bytes32 commitmentId;
    bytes32 planHash;
    bytes32 evidenceHash;
    uint8 verdict;       // 0 conform, 1 nonconform, 2 inconclusive
    uint64 validUntil;   // UNIX seconds
}

function registerCommitment(
    bytes32 parcelId,
    bytes32 seasonId,
    bytes32 planHash,
    uint64 settleDeadline
) external returns (bytes32 commitmentId);

function fundCommitment(bytes32 commitmentId) external payable;
function settle(VerificationResult calldata attestation, bytes calldata signature) external;
function refund(bytes32 commitmentId) external;
```

Constructor propus: `constructor(address verifier)`, verificator diferit de adresa zero. Cheia autorizată este publică doar ca adresă, niciodată ca private key. ABI-ul rezultat din compilare, NU codul de mai sus, este furnizat frontendului prin `/config`.

### Tranziții (on-chain)

| Din | Apel valid | Condiție | În |
|---|---|---|---|
| absent | `registerCommitment` | ID parcelă-sezon nu există, hash nenul | Registered |
| Registered | `fundCommitment` | `msg.value > 0`, o singură finanțare | Funded |
| Funded | `settle` | atestare validă, verdict 0, `planHash` corespunde | Paid |
| Funded | `settle` | atestare validă, verdict 1 sau 2 | Negative |
| Negative | `refund` | `msg.sender == funder` | Refunded |
| Funded, deadline expirat | `refund` | `msg.sender == funder` | Refunded |

**Invariabile:** același ID parcelă+sezon nu se poate înregistra de două ori; `settle` poate reuși o singură dată; e imposibil `Paid` dacă verdictul !=0; reentrancy guard și Checks-Effects-Interactions la transferuri; `settle` numai înainte/în termenul fixat de contract conform deciziei voastre; EIP-712 domain cu chainId și verifyingContract real. **Stocarea `Negative` nu trebuie să permită alt `settle`.**

### Model minimal de evenimente și verificare

Propuneți evenimente cu ID: `CommitmentRegistered`, `CommitmentFunded`, `CommitmentSettled`, `CommitmentRefunded`. În fiecare, includeți `commitmentId`. Corina confirmă receipt-ul prin adresă, topic + parametri decodați, plus starea curentă din contract; nu acceptă `tx_hash` inventat ca dovadă.

### EIP-712: struct și domain exacte

```javascript
const domain = {
  name: "TerraCycleEscrow",
  version: "1",
  chainId: Number(config.chain_id),
  verifyingContract: config.contract_address,
};
const types = {
  VerificationResult: [
    { name: "commitmentId", type: "bytes32" },
    { name: "planHash", type: "bytes32" },
    { name: "evidenceHash", type: "bytes32" },
    { name: "verdict", type: "uint8" },
    { name: "validUntil", type: "uint64" },
  ],
};
```

**Securitate demonstrativă:** numai `VERIFIER_PRIVATE_KEY` de pe backend semnează verdictul. În timpul demo-ului, butonul `Verify` din UI determină API-ul să ruleze pipeline-ul *pe date deja exportate*, nu permite utilizatorului să introducă `verdict=0`.

## 7. Protocolul API ↔ ML

Crenguța livrează interfața Python unică:

```python
# backend/ml/rules.py
from typing import Any

def verify_parcel(parcel_id: str, policy: dict[str, Any],
                  evidence_directory: str) -> dict[str, Any]:
    """Returnează verdict, motiv, observații și metadate; nu semnează și nu hash-uiește."""
    ...
```

Minimum return:

```text
{
  "verdict": "inconclusive",           # conform | nonconform | inconclusive
  "reason_code": "INSUFFICIENT_OBSERVATIONS",
  "observations": [...],             # scene_id, acquired_at, ndvi_mean, valid_pixel_fraction
  "quality": {...},                  # număr observații, acoperire temporală, excluse
  "model": {...},                    # versiune, model utilizat, clase + metadate
  "source": {...}                    # furnizor, CSV/dataset/hash
}
```

Corina NU recalculează features ori praguri; modulul Crenguței NU semnează și NU construiește SHA-256 de snapshot. **Nu permiteți ca `inconclusive` să fie tratat drept `nonconform`.**

## 8. Cazuri de eroare pe care toți le afișează consecvent

```json
{"error":{"code":"PLAN_HASH_MISMATCH","message":"The stored commitment does not match the original plan."}}
```

Coduri propuse: `INVALID_INPUT`, `PARCEL_NOT_FOUND`, `PLAN_NOT_FOUND`, `ALREADY_COMMITTED`, `WRONG_NETWORK`, `TX_NOT_FOUND`, `TX_FAILED`, `TX_MISMATCH`, `PENDING_CONFIRMATION`, `MISSING_EVIDENCE`, `INSUFFICIENT_OBSERVATIONS`, `MODEL_UNAVAILABLE`, `SIGNER_UNAVAILABLE`, `INVALID_SIGNATURE`, `EXPIRED_ATTESTATION`, `NOT_FUNDED`, `PLAN_HASH_MISMATCH`, `INTERNAL_ERROR`.

Clientul nu presupune că toate răspunsurile HTTP au `json()` valid; la eșec afișează un mesaj util și un buton Retry unde retry-ul e sigur. **Refuzul MetaMask** este eroare controlată; utilizatorul nu pierde datele formularului.

## 9. Teste de integrare ÎNTRE persoane

1. **Corina ↔ Oana**: formular React trimite JSON și primește răspuns, fără CORS; `GET /health`, `GET /parcels`, `POST /plans`.
2. **Dorian ↔ Oana**: `/config` trimite ABI și adresă reală; wallet se conectează pe același chain; `registerCommitment` apare în receipt.
3. **Dorian ↔ Corina**: contractul calculează ID identic cu ethers; planHash exact; Node semnează un verdict, Foundry îl validează; `wrong signer` e respins.
4. **Crenguța ↔ Corina**: `verify_parcel(...)` pe CSV fixture și apoi pe CSV real; aceeași ordine de coloane; `inconclusive` pentru insuficiență; backend poate serializa dovezile.
5. **Toți**: `register → fund → verify → settle conform → passport`; apoi `nonconform → Negative → refund`, `inconclusive → Negative`, dublă revendicare, istoric alterat.
6. **Test din clonare**: `README` + `SETUP.md` reconstruiesc sistemul pe laptopul altcuiva fără chei secrete commit-uite.

### Checklist de predare între colegi

La fiecare handoff, cel care predă pune într-un PR: **cale fișier, commit SHA, comandă de pornire, intrare exemplu, ieșire exemplu, comandă de test, starea mock/real, persoana care îl preia**. Dacă unul lipsește, nu este gata pentru integrare.

## 10. Cum demonstrați cele cinci scenarii fără înșelătorie

- **Happy path:** o parcelă cu date reale suficiente și verdict justificat conform. Dacă n-o aveți, demo pe fixture se poate arăta, dar suprapuneți `DEMO DATA`.
- **Istoric modificat:** generați o versiune nouă a istoricului; backend compară cu snapshotul vechi și refuză. Nu pretindeți că blockchain-ul a detectat conținutul agronomic independent.
- **Nonconform:** e nevoie de dovezi negative sau de un fixture evident marcat. Nu selectați arbitrar un verdict nonconform pentru aceeași serie pozitivă.
- **Dublă revendicare:** pe același parcel/season, al doilea register sau settle este refuzat de contract. Distingeți aceste două variante în prezentare.
- **Neconcludent:** date insuficiente sau acoperire slabă, explicate numeric; verdict 2 → Negative, finanțatorul face refund.

## 11. Documente oficiale pentru pași dubioși

- [Copernicus openEO NDVI Timeseries](https://documentation.dataspace.copernicus.eu/notebook-samples/openeo/NDVI_Timeseries.html)
- [Open-Meteo Historical Archive API](https://open-meteo.com/en/docs/historical-weather-api)
- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/)
- [ethers.js v6](https://docs.ethers.org/v6/)
- [Foundry](https://getfoundry.sh/)
- [OpenZeppelin cryptography](https://docs.openzeppelin.com/contracts/5.x/api/utils/cryptography)
- [scikit-learn GroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html)

**STOP:** dacă planul-sursă și implementarea actuală nu coincid, rezolvați conflictul printr-un PR explicit. Nu faceți patru variante care „par aproape identice”.
