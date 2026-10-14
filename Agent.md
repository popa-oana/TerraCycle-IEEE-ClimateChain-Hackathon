# AGENT.md — regulile proiectului TerraCycle Proof

> **Citește înainte de orice cod.** Valabil pentru echipă și pentru asistenții AI din VS Code/Cursor/Copilot. Versiune de lucru: **14 octombrie 2026**.
>
> Acest pachet extinde planul și cele cinci fișiere furnizate. Fișierul `TerraCycle_Ghid_Integrare.md` menționat în sursele inițiale **nu a fost încărcat**; versiunea inclusă aici este o **propunere concretă de contract de integrare**, ce trebuie confirmată împreună de cele patru persoane înainte de a o trata ca fiind definitivă.

## 1. Proiectul în 60 de secunde

**Problemă:** afirmațiile de sustenabilitate dintr-un lanț de aprovizionare agricol sunt greu de verificat din exterior. O simplă înregistrare într-un blockchain nu dovedește că o afirmație este adevărată.

**MVP:** un fermier selectează una dintre 5–10 parcele agricole predefinite, introduce istoricul și solicită o recomandare de rotație a culturilor. Alege un angajament limitat și verificabil: **acoperire vegetală în intervalul ales**. Planul este păstrat integral în backend și hash-ul său este înregistrat într-un contract escrow pe o rețea Ethereum de test. Datele Sentinel-2 istorice furnizează măsurători NDVI; un modul Python aplică verificarea și returnează `conform`, `nonconform` sau `inconclusive`. Un verificator autorizat semnează verdictul EIP-712. Contractul plătește recompensa doar la `conform`. Pașaportul digital arată dovada și linkurile on-chain.

**Ce NU înseamnă:** certificare ecologică, verificare a erbicidelor sau a fertilizării, finanțare cu bani reali, dovadă absolută că datele inițiale sunt adevărate, validare automată on-chain a imaginilor, detectarea tuturor fraudei funciare.

## 2. Cine deține ce

| Persoană | Responsabilitate unică | Livrabil transmis altora |
|---|---|---|
| **Oana** | UX/UI, React + TypeScript + Tailwind, wallet în browser, video | `frontend/`, machete, demo înregistrat |
| **Corina** | FastAPI, PostgreSQL, planuri + climă, serializare/hash, verificarea tranzacțiilor, integrarea ML | API documentat, DB, `SETUP.md`, snapshots |
| **Dorian** | Solidity + Foundry, semnătură EIP-712 în Node, testare contract, deploy, QR/link, Git/Devpost | ABI, script semnare, contract, teste și adresa deployată |
| **Crenguța** | GeoJSON, Sentinel-2, mascare nori, etichete, features, baseline + LightGBM, verdict și raport științific | CSV + metadata reale, `backend/ml/`, `docs/model.md` |

**Graniță:** Oana nu definește API de capul ei. Dorian nu generează alte documente JSON canonice. Corina nu rescrie feature-urile modelului. Crenguța nu schimbă schema REST ori EIP-712 fără discuție.

## 3. Arhitectura comună

```text
Browser — React/TypeScript/Tailwind (Oana)
    | REST/JSON                        | tranzacții ETH de test
    v                                  v
FastAPI (Corina) <---confirmare---> Contract Solidity (Dorian)
    |                                    ^
    +--> PostgreSQL (Corina)             | EIP-712 verificat on-chain
    +--> backend/ml/* (Crenguța)         |
    +--> Node signer (Dorian) -----------+
    +--> data/ndvi/*.csv (cache offline)
    +--> data/climate/*.json (cache offline)

QR -> URL public /passport/{commitment_id} -> aceeași aplicație React
```

- **Datele satelitare se procesează offline**. Nu lansăm un job openEO atunci când juriul apasă pe „Verify”.
- **Un singur repo**, o singură ramură `main`; fiecare persoană are branch personal, PR și review de la alt coleg.
- Backendul este **singura autoritate de serializare și SHA-256** pentru `plan_snapshot` și `evidence_document`. Clientul primește hash-ul gata calculat; nimeni nu face `JSON.stringify()` și nu pretinde că obține aceiași octeți.
- On-chain se păstrează `bytes32 planHash` și referințe/stări, nu tot istoricul agricol și nu date personale.
- Tranzacția MetaMask este trimisă de utilizator; **backendul verifică receipt-ul, contractul, chainId-ul, metoda, parametrii și evenimentele**, nu are încredere în un `tx_hash` tastat arbitrar.
- Planul istoric trebuie descris ca **demonstrație retrospectivă**, nu angajament real făcut în 2024.

## 4. Convențiile care nu se negociază

### Verdict

| JSON | Număr în EIP-712/Solidity | Semnificație |
|---|---:|---|
| `conform` | 0 | Observațiile îndeplinesc politica înghețată |
| `nonconform` | 1 | Observații suficiente, condiția nu este îndeplinită |
| `inconclusive` | 2 | Date insuficiente; nu afirmăm eșecul practicii |

**Atenție:** eticheta clasificatorului `vegetation_present = 1/0` este cu totul altceva decât codul verdictului final `0/1/2`.

### Stări escrow

`Registered → Funded → Paid | Negative → Refunded`; alternativ `Funded → Refunded` numai după deadline. `Paid` și `Refunded` sunt terminale. `Negative` păstrează fondurile până la refund, inclusiv pentru verdict neconcludent.

### Tipuri de date

- Hash și IDs de contract: șir `0x` + 64 hex; wallet: adresă Ethereum validă.
- Sumă: **string decimal de wei** în API (`"1000000000000000"`), `bigint` în frontend.
- Timp API: ISO-8601 cu zonă UTC (de ex. `2024-06-01T00:00:00Z`); Solidity: secunde Unix.
- GeoJSON: **[longitudine, latitudine]**, nu invers; CRS WGS84 / EPSG:4326.
- Erori: `{ "error": { "code": "PLAN_HASH_MISMATCH", "message": "..." } }`; mesaj util în engleză pentru UI; cod stabil pentru teste.
- Limba interfeței: **engleză** pentru juriul internațional; ghidurile și comentariile echipei pot fi în română.
- CSV/JSON/fixtures: UTF-8; date reale cu sursă + dată export; date demo marcate `fixture`.

### Semnătura unică, exactă

```text
EIP712Domain:
  name: TerraCycleEscrow
  version: "1"
  chainId: rețeaua efectivă
  verifyingContract: adresa contractului efectiv

VerificationResult:
  bytes32 commitmentId
  bytes32 planHash
  bytes32 evidenceHash
  uint8 verdict
  uint64 validUntil
```

`commitmentId = keccak256(abi.encode(parcelId, seasonId))`, unde **ambii parametri sunt `bytes32`** în propunerea de contract atașată. Regula de conversie a identificatorilor în `bytes32` se stabilește într-un singur fixture comun, nu separat de fiecare persoană.

## 5. Ordinea corectă de lucru

1. **Citiți `START_AICI.md`, apoi `Agent.md` și fișierul rolului.**
2. **14 octombrie:** Corina + Dorian îngheață numele câmpurilor, schema EIP-712, stările, ABI-ul și fixture-ul comun. Oana începe wireframe și UI cu fixture. Crenguța obține un CSV real și alege modul de etichetare.
3. **15 octombrie:** prima demonstrație cap-coadă pe fixture; tot ce lipsește de la date externe poate fi încă simulare, dar **marcat vizibil**.
4. **16–20 octombrie:** înlocuiți piesele simulate cu integrare reală, teste, date satelitare, semnare, model și contract.
5. **21–22 octombrie:** demo complet, QR scanat, Sepolia, reproductibilitate.
6. **23 octombrie:** feature freeze; doar remedieri.
7. **24 octombrie:** video, Devpost, verificare dintr-o clonă nouă.
8. **25 octombrie:** submit după clarificarea ferestrei oficiale de depunere. **Nu contați pe ultimul minut.**

**Atenție la termen:** materialele încărcate consemnează **o contradicție între două pagini Devpost** privind fereastra de depunere. Trebuie contactați organizatorii. Termenul operațional intern este **24 octombrie seara**, nu presupunerea că se poate trimite oricând pe 25.

### Două verificări obligatorii pe 14 octombrie, ora 20:00 (România)

- **Poarta date:** Crenguța are CSV NDVI **real**, cu sursa identificabilă, plus o decizie de etichetare. Fără acestea, restrângeți public pretențiile ML.
- **Poarta contract:** Dorian + Corina au contract compilat + cel puțin un test Forge verde + fixture EIP-712 stabilit. Dacă nu, mențineți UI cu fixture și prioritizați contractul local.

## 6. Cum lucrăm cu Git fără să stricăm munca colegilor

```bash
git switch main
git pull --ff-only
git switch -c feat/oana-parcel-form
# faci modificări
git status
git add frontend/
git commit -m "feat(frontend): add parcel intake form"
git push -u origin feat/oana-parcel-form
# deschizi Pull Request; un coleg face review și apoi merge
```

Reguli: nu commit pe `main`, nu urcați `.env`, seed, chei, adrese RPC cu token, parole DB reale, date ale unor fermieri reali. `git status` și `git diff --staged` înainte de commit. Dacă accidental intră un secret în Git, **revocați-l/rotați-l**, nu doar ștergeți linia.

**PR obligatoriu:** ce fișiere ai modificat, ce teste ai rulat (comandă + rezultat), captură/screenshot dacă e UI, ce așteaptă alt coleg, ce rămâne TODO. Reviewer diferit de autor; PR-urile lui Dorian sunt reviewate de Oana/Corina/Crenguța.

## 7. „Done” înseamnă dovadă, nu impresie

- **UI:** se vede în browser, se poate naviga, mesajele de eroare sunt inteligibile, `npm run build` trece.
- **API:** `/docs` funcționează, `pytest` trece, există request și response de exemplu.
- **Contract:** `forge test -vvv` trece, există hash de tranzacție testabil, nu doar output de compilare.
- **ML:** există rânduri reale cu proveniență, report reproducibil, split fără leakage, limitări declarate.
- **Integrare:** fiecare click are un traseu observabil de la UI până la API/chain și înapoi.

## 8. Ce face fiecare când se blochează

1. Copiază **comanda exactă** și **eroarea exactă** în mesajul echipei.
2. Spune ce te așteptai să se întâmple și ce s-a întâmplat de fapt.
3. Verifică versiunea toolului și directorul curent (`pwd` / `Get-Location`).
4. Încearcă întâi un test minimal, nu rescrie toată componenta.
5. Dacă depinde de alt coleg, folosește fixture-ul comun și scrie `BLOCKED_BY: ...` în PR.
6. Dacă un API lipsește, modificarea se propune în `TerraCycle_Ghid_Integrare.md` și `docs/api-contract.md` prin PR, înainte de implementare.

## 9. Prompts pentru asistentul AI al fiecăruia

```text
Lucrez la TerraCycle Proof. Citește integral Agent.md, START_AICI.md,
TerraCycle_Ghid_Integrare.md și fișierul rolului meu înainte să scrii cod.
Sunt începător cu stack-ul. Explică întâi scopul pasului și apoi dă-mi
COMENZI EXACTE pentru sistemul meu de operare, fișiere exacte, cod minim
și modul de verificare. Nu modifica interfețe, fixture sau alte roluri
fără să explici conflictul. Nu inventa teste trecute, date satelitare,
metrici, tranzacții sau endpointuri. Dă-mi întâi un pas mic verificabil,
nu 30 de fișiere generate într-un singur răspuns.
```

## 10. Ordinea documentelor

1. `START_AICI.md` — lansare rapidă și dependențe.
2. `Agent.md` — reguli și limite.
3. `TerraCycle_Ghid_Integrare.md` — JSON, API, hash, EIP-712, contract.
4. `Role_Oana.md`, `Role_Corina.md`, `Role_Dorian.md`, `Role_Crenguta.md` — implementare detaliată, pas cu pas.
5. `DESIGN_OANA.md` — brief vizual profund, complement pentru rolul Oanei.

**Referințe oficiale:** [React](https://react.dev/learn), [FastAPI](https://fastapi.tiangolo.com/tutorial/), [Foundry](https://getfoundry.sh/), [openEO Copernicus](https://documentation.dataspace.copernicus.eu/notebook-samples/openeo/NDVI_Timeseries.html), [Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api), [ethers](https://docs.ethers.org/v6/), [Tailwind/Vite](https://tailwindcss.com/docs/installation/using-vite).
