# OANA — GHID COMPLET: FRONTEND, DESIGN, WALLET ȘI VIDEO

**Rol:** construiești experiența utilizatorului în React + TypeScript + Tailwind CSS și coordonezi demonstrația video.  
**Perioadă:** 14–25 octombrie 2026.  
**Nivel presupus:** zero experiență cu React, blockchain și procesul echipei. Nu trebuie să știi Solidity.  
**Citește înainte:** `START_AICI.md`, `Agent.md`, `TerraCycle_Ghid_Integrare.md` și **obligatoriu** `DESIGN_OANA.md`.

## 1. Ce trebuie să reușească aplicația TA

Un utilizator trebuie să poată, fără explicații orale:

1. vedea o parcelă predefinită și sursa datelor;
2. introduce un istoric de culturi și tratamente;
3. cere/alege o recomandare de rotație pe trei ani;
4. înțelege ce practică se va verifica (acoperire vegetală, NU „eco”);
5. conecta MetaMask și înregistra angajamentul cu ETH de test;
6. vedea starea contractului, finanțarea și rezultatul verificării;
7. inspecta graficul NDVI și dovezile (inclusiv observații excluse și motivul);
8. face settle, observa plata sau refundul confirmat, apoi deschide pașaportul prin QR.

**Nu implementezi** backend, model AI, logică de semnătură privată, clasificări satelitare sau scor agronomic. Nu „inventezi” date și endpoint-uri ca să arate frumos; folosești mock-uri etichetate până la integrarea reală.

## 2. Cele șase concepte pe care trebuie să le înțelegi

| Termen | În limbaj normal | Exemplu concret |
|---|---|---|
| Componentă React | bloc reutilizabil care desenează o parte din ecran | `StatusPill` arată `Funded` |
| Props | date transmise unei componente | `<StatusPill status="Funded" />` |
| State | informație care se schimbă când dai click/completezi formularul | parcela selectată |
| API / fetch | trimiți request HTTP backendului Corinei | `POST /plans` cu istoric |
| TypeScript | verifică forma datelor înainte să ruleze codul | `plan_id: string` |
| Wallet / ethers | MetaMask permite utilizatorului să semneze o tranzacție | `registerCommitment(...)` |

**De reținut:** semnarea verdictului EIP-712 o face **serverul Dorian + Corina**, nu MetaMask-ul fermierului. MetaMask-ul din UI trimite **tranzacția de înregistrare/finanțare/settle**, dacă walletul utilizatorului are rolul corect.

## 3. Setup exact, Windows / PowerShell

### 3.1 Verifică instalările

Deschide VS Code, `Terminal → New Terminal`, selectează PowerShell:

```powershell
node --version
npm --version
git --version
```

Dacă Node nu există, instalează Node LTS; redeschide terminalul. Dacă Vite refuză versiunea Node, actualizează la versiunea cerută de eroare (versiunile actuale de Vite cer Node recent).

### 3.2 Creează proiectul React o singură dată

Din **rădăcina repo-ului** (unde se află `Agent.md`):

```powershell
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install tailwindcss @tailwindcss/vite ethers recharts qrcode.react react-router-dom lucide-react
npm run dev
```

Deschide adresa indicată în terminal (de obicei `http://localhost:5173`). Dacă repo-ul conține deja `frontend/`, **NU mai rula `npm create`**: folosește doar `cd frontend; npm install; npm run dev`.

### 3.3 Activează Tailwind CSS v4

În `frontend/vite.config.ts` (păstrează și pluginul React):

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({ plugins: [react(), tailwindcss()] });
```

În `frontend/src/index.css`:

```css
@import "tailwindcss";
@import "./styles/tokens.css";
```

**Nu urma din greșeală tutoriale Tailwind v3** care cer neapărat `tailwind.config.js` + `@tailwind base`; pachetul `@tailwindcss/vite` folosește setup v4.

### 3.4 Fișier de configurare local

`frontend/.env.example`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Copiază-l în `frontend/.env.local` (ignorat de Git):

```powershell
Copy-Item .env.example .env.local
```

**NU pune `VERIFIER_PRIVATE_KEY` / `DEV_PRIVATE_KEY` / secrete în variabile `VITE_`**. Browserul le expune oricui.

## 4. Structura clară a codului tău

```text
frontend/
├── .env.example
├── package.json
├── vite.config.ts
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css
    ├── styles/tokens.css
    ├── lib/api.ts              # fetch tipizat, DOAR API Corina
    ├── lib/types.ts            # tipuri care reproduc contractul comun
    ├── lib/wallet.ts           # ethers + MetaMask; fără chei private
    ├── components/
    │   ├── AppShell.tsx
    │   ├── SectionHeading.tsx
    │   ├── FormField.tsx
    │   ├── StatusPill.tsx
    │   ├── ErrorNotice.tsx
    │   ├── SourceLabel.tsx
    │   ├── NdviChart.tsx
    │   └── EvidenceTable.tsx
    └── pages/
        ├── ParcelsPage.tsx
        ├── HistoryPage.tsx
        ├── PlanPage.tsx
        ├── CommitmentPage.tsx
        ├── VerificationPage.tsx
        └── PassportPage.tsx
```

**Sfat:** 6 pagini vizuale pot fi grupate inițial într-un wizard, dar URL-ul pașaportului **trebuie să funcționeze direct**, inclusiv după refresh: `/passport/:commitmentId`.

## 5. Ziua 1: construiește un ecran care chiar merge

### 5.1 Primele tipuri TS

`src/lib/types.ts`:

```ts
export type Verdict = 'conform' | 'nonconform' | 'inconclusive';
export type ChainStatus = 'Registered' | 'Funded' | 'Paid' | 'Negative' | 'Refunded';

export interface Parcel {
  parcel_id: string;
  parcel_id_bytes32: string;
  display_name: string;
  region: string;
  area_ha: number | null;
  geometry_url: string;
  data_origin: 'fixture' | 'real';
}

export interface CropHistoryEntry {
  year: number;
  crop: string;
  treatments: string[];
}

export interface PlanRequest {
  parcel_id: string;
  season_id: string;
  history: CropHistoryEntry[];
  desired_crop: string;
}

export interface AppConfig {
  chain_id: number;
  contract_address: string;
  contract_abi: unknown[];
  explorer_base_url: string | null;
  public_app_url: string;
}
```

Când Corina îngheață `docs/api-contract.md`, tipurile trebuie comparate câmp cu câmp; nu atribui `any` doar ca să dispară eroarea TypeScript.

### 5.2 Funcția unică de fetch

`src/lib/api.ts`:

```ts
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  const raw = await response.text();
  let payload: unknown = null;
  try { payload = raw ? JSON.parse(raw) : null; } catch { /* non-JSON error */ }

  if (!response.ok) {
    const body = payload as { error?: { code?: string; message?: string } } | null;
    throw new ApiError(body?.error?.code ?? 'API_ERROR',
      body?.error?.message ?? `Request failed (${response.status})`, response.status);
  }
  return payload as T;
}
```

Testează în `ParcelsPage` un `GET /parcels` și afișează mesaj clar dacă API-ul Corinei nu pornește. Pentru început, fallback temporar din `src/mocks/parcels.ts` cu banner **`Demo fixture, not satellite-verified`**. Nu ascunde mock-ul în `api.ts`.

### 5.3 Formularul trebuie să aibă validare reală

Input-uri: alegerea parcelei, anul fiecărei culturi, cultura, tratamente declarate, cultura dorită. Reguli minime:

- Nu trimite formular fără parcelă selectată.
- Nu accepta ani duplicați în istoric.
- Nu accepta ani viitori ca „istoric”.
- Trimite valorile din listă, nu text de tip „2023: grâu; 2024: ...”.
- Arată un mesaj prietenos în interfață pentru 422 (validation error).
- Dezactivează butonul DOAR cât așteaptă requestul, nu definitiv.

Ordinea în cod: `useState` pentru date -> validare -> `api<PlanResponse>('/plans', {...})` -> salvează `plan_id` -> navighează spre recomandări.

## 6. Design și navigare: ce arată FIECARE ecran

Instrucțiunile tipografice, culorile, gridul, spațierile, hover/focus și anti-AI sunt în `DESIGN_OANA.md`. Mai jos este **conținutul funcțional**:

| Ecran | Conținut obligatoriu | Buton principal | Ce afișezi în cazul unei probleme |
|---|---|---|---|
| 01 / Parcel selection | 5–10 parcele, regiune, sursa datelor, status demo/real | `Select this field` | `No fields available` |
| 02 / Field history | Istoric pe ani, culturi, tratamente, cultură dorită | `Generate rotation options` | eroare câmp + păstrează inputurile |
| 03 / Rotation options | 2–3 opțiuni trei ani, motive, trade-off, disclaimer agronomic | `Continue with this plan` | `Plan generation unavailable` |
| 04 / Commitment | politică exactă, snapshot hash, sumă test, wallet, `register`, `fund` | `Register commitment` | wallet refuzat/rețea greșită/tx pending |
| 05 / Verification | grafic NDVI, tabel scene/date, nori, verdict motivat, attestation și tx | `Verify evidence` / `Settle` | `Inconclusive` ≠ eșec tehnic |
| 06 / Passport | pașaport lizibil, timeline, hash-uri scurtate cu Copy, link explorer, QR | `Copy passport link` | `Passport not found` |

### Stări vizuale, DOAR dacă reflectă realitatea API

`Not started`, `Loading`, `Prepared`, `Registered`, `Funded`, `Verifying`, `Conform`, `Nonconform`, `Inconclusive`, `Paid`, `Negative`, `Refunded`. Nu pune „Reward transferred” până la receipt verificat de backend. `Prepared` este stare off-chain.

## 7. Integrare wallet real: fără să expui chei

### 7.1 Ideea

`window.ethereum` este obiectul introdus de MetaMask în browser. `ethers.BrowserProvider(...)` comunică cu el. Semnatarul de browser este fermierul sau finanțatorul. Semnatarul verdictelor rămâne pe server.

`src/lib/wallet.ts`:

```ts
import { BrowserProvider, Contract } from 'ethers';
import type { AppConfig } from './types';

type EthereumWindow = Window & { ethereum?: any }; // doar la marginea API-ului extern

export async function connectWallet(config: AppConfig) {
  const ethereum = (window as EthereumWindow).ethereum;
  if (!ethereum) throw new Error('Install MetaMask to continue.');
  const provider = new BrowserProvider(ethereum);
  await provider.send('eth_requestAccounts', []);
  const network = await provider.getNetwork();
  if (network.chainId !== BigInt(config.chain_id)) {
    throw new Error(`Wrong network. Please switch to chain ${config.chain_id}.`);
  }
  const signer = await provider.getSigner();
  return { provider, signer, address: await signer.getAddress() };
}

export async function getContract(config: AppConfig) {
  const { signer } = await connectWallet(config);
  return new Contract(config.contract_address, config.contract_abi, signer);
}
```

Aici `any` apare **strict** la tipizarea extensiei injectate; nu îl propaga prin restul aplicației. Producția poate folosi declarație TypeScript dedicată pentru providerul EIP-1193.

### 7.2 Registration: pașii exacți din UI

1. `GET /config` din API (chainId, ABI, contract).
2. `POST /commitments/prepare` → primești `plan_hash`, două IDs `bytes32`, `commitment_id`, deadline.
3. `getContract(config)`, apelezi `registerCommitment(parcelIdBytes32, seasonIdBytes32, planHash, settleDeadline)`.
4. `const receipt = await tx.wait()`; verifici că receipt există și `status === 1`.
5. `POST /commitments/{id}/transactions` cu `{action:'register',tx_hash:tx.hash}`.
6. **Abia după confirmarea API** afișezi `Registered`.

Fragment orientativ:

```ts
const contract = await getContract(config);
const tx = await contract.registerCommitment(
  prepared.parcel_id_bytes32,
  prepared.season_id_bytes32,
  prepared.plan_hash,
  prepared.settle_deadline
);
const receipt = await tx.wait();
if (!receipt || receipt.status !== 1) throw new Error('Transaction failed');
await api(`/commitments/${prepared.commitment_id}/transactions`, {
  method: 'POST',
  body: JSON.stringify({ action: 'register', tx_hash: tx.hash }),
});
```

**Roluri wallet:** la `register`, walletul conectat devine beneficiarul (`msg.sender`), deci trebuie să corespundă cu `beneficiary_wallet` pregătit. Pentru `fund`, folosește portofel de finanțator distinct și `fundCommitment(id, {value: BigInt(reward_wei)})`. Pentru `settle`, contractul primește `attestation` și `signature` deja validate de server. **Nu muta fonduri reale.**

### 7.3 Greșeli frecvente

| Simptom | Cauză probabilă | Ce faci |
|---|---|---|
| `window.ethereum undefined` | MetaMask lipsește sau browserul nu are extensia | instalează și reîncarcă pagina |
| `wrong network` | wallet pe Sepolia, API pe Anvil sau invers | arată chainId cerut din `/config`, nu hardcoda |
| `CALL_EXCEPTION` | ABI sau contract greșit, revert în contract | cere adresa+ABI reale de la Dorian, citește revert |
| `user rejected action` | omul a apăsat Reject | mesaj normal; păstrezi datele |
| `insufficient funds` | wallet test fără ETH sau gas | faucet/test account, nu plăti bani reali |
| `tx pending` | încă neconfirmat | „Transaction pending”, nu „Paid” |
| `failed to fetch` | API/CORS/URL greșit | testează `/health` în browser, vorbește cu Corina |

## 8. Graficul NDVI trebuie să fie informativ, nu doar decor

Instalat deja `recharts`. Graficul conține X=data observației, Y=NDVI (`-1…1` posibil; pentru câmpuri folosește interval pe date, NU taia valori fără să explici), linie reală sau puncte, punctele filtrate afișate separat ori explicate, fereastra politicii, legendă și unitate „NDVI (unitless)”.

Datele vin numai prin `GET /passports/{id}` sau răspunsul de verificare, nu din valori inventate direct în componentă. Fiecare punct are `acquired_at`, `ndvi_mean`, `scene_id`, `valid_pixel_fraction` și `is_valid`. Pentru valori lipsă NU interpola artistic; arată gap. În tabelul de sub grafic se vede de ce o scenă este exclusă (`clouds / invalid pixels / missing data`).

**Text de explicat sub grafic:** „NDVI is a satellite vegetation indicator. It does not confirm pesticide use, organic certification, or farm ownership.”

## 9. QR și pașaport

`qrcode.react` poate genera un QR local dintr-un URL pregătit de API. Folosește:

```tsx
import { QRCodeSVG } from 'qrcode.react';

const url = `${config.public_app_url.replace(/\/$/, '')}/passport/${commitmentId}`;
<QRCodeSVG value={url} size={180} bgColor="#FFFFFF" fgColor="#101E34" />
```

- **Niciodată `localhost` pentru telefon** decât dacă site-ul rulează pe același telefon, ceea ce nu e cazul. Folosește URL HTTPS public ori IP LAN accesibil, setat în `GET /config`.
- Pagina `/passport/:id` face `GET /passports/{id}` la fiecare refresh, nu depinde de state-ul wizardului anterior.
- Hashurile afișate cu `0x1234…89ab`, dar se copiază **întregi**.
- Link-ul explorer se afișează doar dacă `explorer_base_url` există și rețeaua corespunde.
- Test cu telefon real: scanare → rețea accesibilă → pagină corectă → reload.

## 10. Calendarul zilnic, foarte explicit

| Dată | Ce faci, în ordinea exactă | Livrabil / dovadă | De la cine depinzi |
|---|---|---|---|
| **14 oct** | setup → tokens design → AppShell → select parcelă → formular istoricului | screenshot + `npm run dev` + POST/mock | schema JSON de la Corina |
| **15 oct** | completează cele 6 pagini cu fixture etichetat → navigare completă → fără butoane moarte | walkthrough 2 minute, 6 ecrane | fixture comun |
| **16 oct** | opțiuni rotație, justificări, skeleton/error/empty | 2–3 variante cu explicații | `POST /plans` Corina |
| **17 oct** | construiește `NdviChart`, `EvidenceTable`, pașaport dummy, QR preliminar | grafic/tabel + route direct | CSV Crenguța, API Corina |
| **18 oct** | `GET /config`, wallet connect, `register` și `fund`, receipts | tx local confirmat, nu mock | ABI + contract Dorian, API Corina |
| **19 oct** | verificare reală, mapping trei verdicte, evidențe, `settle`, negative/refund | minimum happy path real | model Crenguța + Dorian signer |
| **20 oct** | testează MetaMask reject, network, tx pending, API absent, date neconcludente | tabel de teste + capturi | toți |
| **21 oct** | walkthrough complet + pașaport public + QR scanat pe telefon | video brut cu scanare | URL public + backend |
| **22 oct** | testează browser curat + mobile/tablet/desktop + dark? NU necesar | 3 viewporturi + build trecut | deploy backend |
| **23 oct** | polish și bug-uri critice; nu noi funcționalități | UI stabil, zero console errors | nimeni |
| **24 oct** | montează video 3–5 min, voiceover/subtitrări, verifică în browser | MP4 + poster + capturi | toți furnizează scenele |
| **25 oct** | verifică linkurile și fișierele încărcate; fără schimbări după submit | checklist final | Dorian |

**Checkpoint zilnic:** demonstrează în call URL-ul, clickurile și eroarea posibilă, nu doar un screenshot al codului.

## 11. Scenariu video: ritm 3–5 minute, fără montaj artificial

- **0:00–0:20:** problema: „A sustainability claim is not evidence.” Cadru curat cu parcela / pașaport.
- **0:20–0:55:** introduci istoricul; compari rotațiile și explici politica verificabilă.
- **0:55–1:35:** conectezi MetaMask; arăți register + fund cu tranzacții TEST, fără seed phrases.
- **1:35–2:20:** deschizi verificarea satelitară; graficul NDVI, mascare nori, verdict + motiv.
- **2:20–3:10:** settle conform, reward; QR → telefon → pașaport și link explorer.
- **3:10–4:15:** negative cases: istoric schimbat, nonconform, dublă revendicare, neconcludent. Etichete `Demo scenario` pentru fixture.
- **4:15–4:40:** limite științifice + valoare: hash verificabil, verificator autorizat, surse transparente.

Dacă durata reală cere comprimare, taie animațiile și ecranul static, **nu** demonstrațiile cu verificări. În OBS capturează 1920×1080, ascunde notificările și taburile personale, nu arăta wallet key, adaugă subtitrări lizibile. Export MP4 H.264. Test final: sunetul, rezoluția, linkul public, limbă engleză.

## 12. Criterii de „DONE” care nu se negociază

- [ ] `npm run build` trece fără erori TS.
- [ ] `GET /parcels`, `POST /plans`, `GET /config` sunt reale ori marcate clar mock.
- [ ] Nu există butoane decorative care pretind că fac tranzacții.
- [ ] Refuzul MetaMask, chain greșit și API offline se văd clar.
- [ ] `Registered/Paid` se afișează **după confirmarea backendului**.
- [ ] Graficul are sursă reală sau badge clar `Demo data`, nu cifre inventate.
- [ ] Pașaportul se deschide din URL lipit într-un browser gol.
- [ ] QR-ul scanează din telefon real.
- [ ] Responsive la 375px, 768px și desktop; navigare cu tastatura.
- [ ] Video demonstrează datele și limitele fără a afirma certificare eco.

## 13. Cum îi ceri ajutor asistentului AI

```text
Sunt Oana și fac frontendul proiectului TerraCycle Proof, ca începătoare.
Citește Agent.md, TerraCycle_Ghid_Integrare.md, Role_Oana.md și DESIGN_OANA.md.
Te rog să implementezi DOAR taskul de azi în frontend/, pe fișiere numite explicit.
Vreau: ce înseamnă fiecare pas, comenzile pentru PowerShell, cod complet pentru
fișierele afectate, cum verific în browser, ce erori apar des și ce îi predau Corinei
sau lui Dorian. Folosește DOAR endpointurile aprobate, fără a inventa date.
Respectă palette/typography/layout din DESIGN_OANA.md; evită dashboard-ul generic AI.
Nu trece la pasul următor până nu există testul minimal descris.
```

**Documentație oficială:** [React Learn](https://react.dev/learn), [Vite](https://vite.dev/guide/), [Tailwind/Vite](https://tailwindcss.com/docs/installation/using-vite), [ethers v6](https://docs.ethers.org/v6/), [Recharts](https://recharts.org/).
