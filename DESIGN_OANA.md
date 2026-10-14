# DESIGN BRIEF — TERRACYCLE PROOF
## Direcție vizuală completă pentru Oana: editorial, minimalist, matur, precis

**Obiectiv:** să pară un produs digital serios de climate intelligence / agritech, conceput intenționat de un designer, **nu** un dashboard generic generat de AI.  
**Culori cerute:** roșu profund, bleumarin închis, alb cald și negru. Nu folosi roz, violet, gradient neon, verde fosforescent ori glassmorphism.  
**Public:** juriu internațional (engleză), utilizator care trebuie să înțeleagă un angajament agricol și dovada sa.  
**Temperament:** calm, sobru, responsabil, precis, ușor editorial; fără aer de startup crypto speculativ.

---

## 1. Ideea de brand

**Numele vizibil:** `TERRACYCLE / PROOF` sau `TerraCycle Proof`, cu cuvântul *Proof* tratat ca un marcaj tipografic distinct. Nu e nevoie de logo AI. Propunerea este un **wordmark** realizat exclusiv prin tipografie: `TERRACYCLE` în uppercase, ușor letter-spaced, separat de `/ PROOF` printr-o linie verticală fină sau slash oblic mic. Singurul simbol posibil: un pătrat decupat cu o diagonală subțire ce amintește de o parcelă și de un document auditat; desenați-l din CSS/SVG simplu, fără frunze, globuri sau lanțuri în logo.

**Concept:** „From a claim to a traceable record.” Pe ecran, produsul **prezintă dovezi** în loc să strige „AI-Powered”. Culoarea, spațiul, alinierea și microcopy-ul inspiră rigoare. Elementele trebuie să arate mai degrabă ca un **dosar analitic foarte bine proiectat** decât ca o platformă crypto plină de efecte.

Cuvinte-cheie de design: `documentary`, `editorial`, `field report`, `quiet technology`, `precision`, `tactile restraint`, `architectural spacing`.

Nu folosi fotografii dramatice de peisaje la fiecare card. O singură fotografie agricolă reală, cu proveniență, poate apărea pe copertă. E mai bine să aveți **un grafic adevărat** și o hartă corectă decât 12 imagini stock cu fermieri zâmbind spre apus.

---

## 2. Paleta exactă de culori (tokens)

<details>
<summary>Principiul cromatic</summary>

Bleumarinul este fundalul autoritar, roșul este accentul selectiv, albul cald este pânza, negrul este textul. Aproximativ 70% spații deschise, 20% bleumarin, 8% tonuri neutre, 2% roșu. Nu îmbrăcați *totul* în roșu.

</details>

| Token | Hex | Rol | Unde se folosește |
|---|---|---|---|
| `--navy-950` | `#101E34` | bleumarin principal, profund | hero, header, footer, text accent |
| `--navy-800` | `#20334F` | suprafețe secundare | panouri dense, grafic întunecat |
| `--red-700` | `#8E2230` | burgundy / oxblood, accentul identitar | primary CTA, numere de secțiune, marker |
| `--red-600` | `#A8313E` | stare hover pe roșu | hover CTA, grafice selectate |
| `--red-100` | `#F5E9E9` | fond contextual pentru excepții | informații marcate, NU alerte globale |
| `--paper` | `#F8F7F4` | alb cald | background general |
| `--white` | `#FFFFFF` | suprafețe | formulare, carduri selectate |
| `--ink` | `#17191C` | negru/cărbune | titluri + text primar |
| `--muted` | `#5D6672` | gri neutru | explicații, metadata |
| `--line` | `#DDE1E3` | separatoare | borduri subțiri |
| `--green-700` | `#246457` | exclusiv verdict conform | status pozitiv, NU culorea brandului |
| `--amber-700` | `#8A6222` | exclusiv inconclusive | status incert |

**De ce verde/auriu dacă paleta e roșu/navy?** Pentru semnificația verdictelor. Culoarea de brand nu trebuie să însemne simultan „apasă aici” și „ai eșuat”. Verde și auriu apar doar ca semnale funcționale rare. `nonconform` folosește roșu profund, dar și un text explicit.

### CSS gata de copiat

`frontend/src/styles/tokens.css`:

```css
:root {
  --navy-950: #101E34;
  --navy-800: #20334F;
  --red-700: #8E2230;
  --red-600: #A8313E;
  --red-100: #F5E9E9;
  --paper: #F8F7F4;
  --white: #FFFFFF;
  --ink: #17191C;
  --muted: #5D6672;
  --line: #DDE1E3;
  --green-700: #246457;
  --amber-700: #8A6222;

  --container: 1224px;
  --rail: 228px;
  --header-height: 72px;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --shadow-soft: 0 8px 26px rgba(16,30,52,.055);
  --ease: cubic-bezier(.2,.7,.2,1);
}

* { box-sizing: border-box; }
html { color-scheme: light; scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
button, input, select, textarea { font: inherit; }
a { color: inherit; }
:focus-visible { outline: 3px solid var(--red-600); outline-offset: 3px; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
```

**Fonturi recomandate:** `IBM Plex Sans` pentru text, etichete, tabele și butoane; `Newsreader` sau `Georgia` (serif discret) doar pentru 1–2 headline-uri din hero ori titlul pașaportului. Dacă folosiți Google Fonts, includeți fallback local. Nu schimbați fontul la fiecare ecran. Dacă n-aveți timp, folosiți `Segoe UI` + `Georgia`: un design coerent bate orice font „special”.

```css
:root {
  --font-body: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
  --font-display: 'Newsreader', Georgia, serif;
}
.hero-title, .passport-title { font-family: var(--font-display); font-weight: 500; }
```

---

## 3. Grila, spațiile și proporțiile

### Desktop (1440px)

- **Container principal:** max-width 1224px, centrat, padding 40px lateral la ecrane largi.
- **Header:** 72px înălțime, bleumarin; logo stânga, navigare pe mijloc/dreapta, buton `Connect wallet` doar pe ecranele relevante.
- **Ecran flow:** rail stânga 228px și conținut flexibil dreapta, cu gap 48px. Fără meniu sidebar cu zece linkuri inexistente.
- **Content measure:** max-width 880px pentru pași, 1080px pentru grafice/pasaport.
- **Sistem spații:** 4, 8, 12, 16, 24, 32, 48, 64, 96 px. **Nimic aleatoriu**: 27px într-un card, 31px în altul, apoi 19px la al treilea arată improvizat.
- **Card radius:** 10px sau 14px maxim. Button radius 6px. Nu folosi 28–40px pentru orice card.
- **Borduri:** 1px `#DDE1E3`. Shadow foarte discret doar când cardul este ridicat; majoritatea componentelor pot sta fără shadow.
- **Separator:** o linie hairline orizontală cu 24–40px de aer.

### Tabletă (768–1024px)

Rail-ul devine o bară de progres orizontală cu 6 pași prescurtați. Gap la 24px, cards în 1–2 coloane. Niciun element important nu poate ieși din ecran.

### Mobil (375px)

Header 60–64px, margini de 20px, top progress `02 / 06`, un singur card pe rând, butoane principale full-width, input min 44px height, tabele cu scroll orizontal și etichete repetate vizibil. Graficul se redimensionează la lățime, fără text micro de 8px.

### Scară tipografică

| Element | Desktop | Mobile | Greutate |
|---|---:|---:|---|
| Display hero | 56–66px | 37–42px | serif regular / medium |
| Titlu pagină | 40–44px | 30–34px | 500–600 |
| Heading secțiune | 24–28px | 22–24px | 600 |
| Card title | 18–20px | 18px | 600 |
| Body | 15–16px | 15–16px | 400 |
| Metadata | 12–13px | 12–13px | 500 / tracking mic |
| Buton | 14–15px | 15px | 600 |

Line-height text body 1.6, titluri 1.12–1.2, metadata 1.3. **Maximum 2–3 mărimi per card.** Textul gri trebuie să rămână lizibil, nu `#AEB0B4` pe alb.

---

## 4. Anatomia aplicației: identitate vizuală repetabilă

### Header

Stânga: wordmark `TERRA / PROOF` pe fundal bleumarin, alb cald. La dreapta: `How it works`, `Evidence`, `View passport` (link doar dacă există ID), buton mic `Connect wallet` cu contur alb-cenușiu. Headerul **nu** trebuie să fie sticky dacă acoperă date importante. La scrolldown poate rămâne static.

### Navigation rail / jurnalul procesului

La stânga paginilor 01–05: câte un pas, indexat `01` `02` `03`... în font monospaced sau foarte bine aliniat; etapa actuală are o bară roșie de 3px și titlu navy bold; cele finalizate au un mic `✓` discret. Pe mobil: `STEP 02 OF 06` + segment progress, fără iconuri mari.

### Footer

Subțire, navy, cu `TerraCycle Proof / Demonstration prototype • 2026`; link către methodology, GitHub și un `Data limitation notice`. Fără animații sau jargon grandios.

### Status labels

Un badge sobru, cu bordură și text, nu capsule „gumoase” cu emoji. Variante: `REGISTERED` navy; `FUNDED` navy; `CONFORM` verde; `NONCONFORM` oxblood; `INCONCLUSIVE` ocru; `PAID` verde; `NEGATIVE` oxblood; `REFUNDED` gri închis. Include întotdeauna text, nu transmite stare doar prin culoare.

---

## 5. Scenografie de ecran: un wireframe în cuvinte pentru fiecare pagină

### 5.1 Landing / parcely selection (ecranul 01)

**Stil:** editorial, fără dashboard la prima vedere.

```text
┌──────────────────────────────────────────────────────────────────────┐
│ TERRA / PROOF                    METHODOLOGY       CONNECT WALLET    │
├──────────────────────────────────────────────────────────────────────┤
│ 01 / SELECT A FIELD                                                 │
│                                                                      │
│ A claim is not a proof.                                              │
│ A verifiable agricultural record, from field to evidence.           │
│                                                                      │
│ [ SELECT A FIELD ↓ ]                              ┌──────────────┐  │
│ 5 pre-defined fields • Historical season 2024     │ Subtle parcel│  │
│                                                   │ geometry/map │  │
│                                                   └──────────────┘  │
│ ──────────────────────────────────────────────────────────────────   │
│ FIELD 01         Dolj, Romania          Source: Sentinel-2 L2A       │
│ [SELECT THIS FIELD]  →                                               │
└──────────────────────────────────────────────────────────────────────┘
```

**Detalii:** hero pe navy într-o zonă de cca 360–430px înălțime, nu full-screen inutil; headline serif alb cu un cuvânt de accent roșu burgundy luminat rezonabil (sau un underline roșu scurt). Jos bandă paper cu parcele sub formă de rânduri bine delimitate, **nu** 5 carduri identice cu icon de frunză. Fiecare parcelă prezintă ID, regiune, thumbnail geometric de contur al parcelei dacă există, sezon și etichetă `Demo fixture`/`Real satellite evidence` conform datelor. Un CTA clar.

### 5.2 Istoricul câmpului (ecran 02)

**Fundal:** paper. Titlu `Start with the field’s history.`; subtitlu `The recommendation uses declared crops and treatments. Satellite verification checks vegetation cover only.`

Layout 2 coloane: 65% formular, 35% dreapta „Plan summary”/„What will be checked”. Istoric pe rânduri verticale de timeline, nu o formă uriașă fără structură:

```text
2022 ─ [ Crop ▼ wheat         ] [ Treatment tags              ] [ remove ]
2023 ─ [ Crop ▼ sunflower     ] [ No treatments declared     ] [ remove ]
       + Add year
Desired crop [maize ▼]

                         [ Back ]          [ Generate rotation options → ]
```

Inputurile au labels **deasupra**, help-text de 12–13px, focus ring roșu. Nu folosi placeholderul drept singura etichetă. Descrierea despre erbicide este discretă și clară: „Declared by the user; not verified by NDVI.”

### 5.3 Recomandări rotație (ecran 03)

Titlu `Three paths. One informed decision.` Rezultatele sub formă de **3 liste/carduri cu capete diferite**, nu 3 carduri clonă cu scor mare și gradient. Opțiunea recomandată poate avea bordură navy de 2px și mic header `PREFERRED UNDER CURRENT RULES`; celelalte au bordură simplă.

În fiecare card: `OPTION A / 01`, timeline cu an și cultură, motiv în limbaj normal, risc/limitare. Un `score 74/100` apare doar dacă există scor calculat, cu metodologie explicită. Selectarea unei variante arată check + border, nu un hover care face tot cardul să sară.

*Accesoriu distinctiv:* un mic „editorial aside” la dreapta: `Decision note / Why this is recommended`, text simplu, pe paper cu o linie verticală oxblood.

### 5.4 Commitment / Wallet (ecran 04)

**Cel mai important ecran de claritate.** Două blocuri verticale:

1. **Commitment summary** pe navy deschis: `Field 01`, `2024 historical season`, policy `Vegetation visible in at least 70% of eligible observations`, window `01 Apr–30 Jun 2024`, reward `0.001 test ETH` (calculează din wei corect, nu hardcoda).
2. **Transaction desk** pe alb: Connect wallet, `Network: Anvil / Sepolia`, `Beneficiary: 0x12…`, `Plan hash: 0x...` cu Copy. Buton `Register on testnet`. După receipt, un timeline `Prepared → Registered → Funded` cu TX links.

Microcopy vizibil: `Test network only. No real funds are exchanged.` Folosește un buton de confirmare separat pentru finanțator, cu instrucțiune „Switch to funding wallet” dacă rolurile sunt distincte. Nu arăta un singur buton magic „Commit & Pay & Verify” care ascunde 3 acte juridice diferite.

### 5.5 Verification / Satellite evidence (ecran 05)

**Semnătura vizuală a întregului proiect.** Grafic mare, sobru, ca într-un raport științific:

```text
FIELD EVIDENCE                                       SENTINEL-2 / L2A
2024 APR 01 — JUN 30                                  DATASET REF: …
──────────────────────────────────────────────────────────────────────
NDVI                                               [Valid ●] [Masked ×]
         0.75 ┤           ●   ●
              │      ●         ●
         0.35 ┤  ●         ○      ○   ← unitless indicator
              └───────────────────────── dates

Sample coverage       8 / 12 valid scenes       Valid pixels     83%
──────────────────────────────────────────────────────────────────────
VERDICT                                         [CONFORM / INCONCLUSIVE]
Reason in 1–3 sentences, no overclaim.
[Review evidence table ↓]                           [Settle on testnet]
```

Grafic pe alb cu linii de grid foarte fine; culoarea seriei: navy; punctele observate navy; cele eliminate contur roșu/gri, cu legendă. Nu colora fundalul întreg verde la `conform`. Un panel lateral slab colorat pentru `quality`, `policy`, `source`. `INCONCLUSIVE` are motiv specific: 3/5 observații sau acoperire sub prag, nu doar „AI uncertain”.

Un tabel dedesubt cu columne: `DATE`, `SCENE`, `NDVI`, `VALID PIXELS`, `INCLUDED`, `WHY`. Dacă sunt multe observații, un detaliu accordion „Review measurements”. Nu transforma dovezile într-un grafic imposibil de auditat.

### 5.6 Passport (ecranul 06)

**Aspect:** hârtie de certificat contemporan, nu NFT neon.

- Fundal paper, container alb 1080px cu margine subțire navy.
- Sus o bandă navy de 12px; sub ea `TERRA / PROOF`, `FIELD VERIFICATION RECORD`, ID scurt.
- Titlu serif `Digital Field Passport` 46px; sub el `Historical season 2024 • Dolj region`.
- În dreapta sus, QR **alb cu pixeli navy**, încadrare simplă, sub titlul `VERIFY THIS RECORD`.
- Secțiuni separate numeric `01 FIELD`, `02 COMMITMENT`, `03 OBSERVATION EVIDENCE`, `04 ATTESTATION`, `05 SETTLEMENT`.
- Footer: `This record documents a signed, limited-scope verification of vegetation cover. It is not an organic certificate.`

Raportul poate fi imprimabil fără efecte care dispar în PDF. Hashurile în text monospace mic dar lizibil, cu Copy. Tranzacțiile apar ca linkuri cu icon de external link discret. **Nicio hologramă de certificat** și nici sigiliu fals de autoritate.

---

## 6. Butoane și control states

### Buton principal

- background oxblood `#8E2230`, text alb, border-radius 6px, height 46–48px, padding 16px 22px;
- hover `#A8313E`, focus ring 3px; disabled pe gri cu atribut `disabled`, nu doar cu `opacity: 0.2`;
- text preferat `Generate options`, `Register commitment`, `Verify evidence`, `Settle commitment`; fără copy vag „Unleash AI”.

### Buton secundar

- fundal transparent/alb, bordură 1px `#BEC7D1`, text navy, hover border navy; `Back`, `Download evidence`, `View transaction`.

### Inputs

- height >= 44px, background alb, bordură line, padding 12px, label permanent; eroare explicită sub input, nu doar bordură roșie. `aria-describedby` asociat cu eroarea.

### Loading states

- Skeleton ca linii clare pentru pagina de plan, spinner discret DOAR în interiorul butonului pentru request scurt.
- Texte specifice: `Preparing the immutable record…`, `Waiting for wallet confirmation…`, `Verifying on-chain transaction…`, `Loading Sentinel-2 observations…`. Ultimul NU trebuie afișat dacă satelitul a fost deja procesat offline: preferabil `Loading cached observations…`.
- Un request eșuat oferă `Try again` doar dacă e idempotent; pentru tranzacții se verifică hash-ul existent înainte de retransmisie.

### Iconografie

Folosește `lucide-react` **cu parcimonie**: chevron, external-link, check, copy, info, alert, wallet, calendar. Dimensiuni 16–18px stroke 1.7px. Nu pune iconuri uriașe în fiecare card. Nu folosi 3D icons, emoji de grajd/planetă, pictograme stock în gradient.

---

## 7. Microcopy: diferența dintre un produs credibil și o prezentare AI

| Evitați | Afișați în produs |
|---|---|
| `Revolutionizing farming with blockchain intelligence` | `A field commitment, with evidence you can inspect.` |
| `AI VERIFIED SUSTAINABILITY` | `Vegetation-cover assessment from satellite observations.` |
| `Your eco score is 98.4%!` | `8 of 11 eligible observations indicate vegetation cover.` |
| `Smart contracts guarantee the truth` | `The contract verifies the signed result and controls the test reward.` |
| `Verification failed!` pentru neconcludent | `Insufficient evidence to reach a conclusion.` |
| `Transaction successful!` înainte de receipt | `Transaction submitted. Waiting for confirmation.` |
| `Wallet connected. You're secure!` | `Connected to Sepolia testnet` |

Titlurile paginilor, în ordinea flow-ului:

1. **Choose a field.** / `Start with a defined agricultural parcel.`
2. **Add the field history.** / `Describe what was cultivated and declared.`
3. **Review the rotation options.** / `Compare transparent recommendations, not black-box promises.`
4. **Register the commitment.** / `Lock the plan reference on a test network.`
5. **Inspect the evidence.** / `Satellite signals, quality checks and a signed result.`
6. **A record worth verifying.** / `The field passport links the claim, evidence and settlement.`

Interfața finală e **în engleză**, tutorialul poate rămâne în română. Folosiți diacritice în documentație, dar nu traduceri amestecate în aceleași butoane.

---

## 8. Accente vizuale proprii, controlate

Puteți folosi **maximum două** detalii distinctive repetate:

1. **„Document indexing”**: `01 / 06`, linii fine și marcaje editoriale `FIELD REPORT`, `SOURCE: COPERNICUS`. Dă consistență vizuală fără a fi decor gratuit.
2. **„Data stamp”**: un dreptunghi dreptunghiular tip „stamp” cu `VERIFIED RECORD • 2024`, dar *numai* dacă înseamnă „semnătură + hash verificabile”, nu validare independentă certificată.

Alt accent posibil: un contur de parcelă desenat din GeoJSON în SVG 1px, navy/oxblood, pe zone mici; asta este iconografie derivată din datele proiectului, nu ilustrație AI. **Nu inventați hartă reală dacă geometriile sunt demonstrative.**

---

## 9. Anti-„AI-looking” checklist

Interfața NU trebuie să conțină:

- fundal violet-albastru gradient pe toate secțiunile;
- glassmorphism, blur în carduri, halo/glow în spatele graficelor;
- 4–6 metric cards colorate din prima pagină doar ca să „umple dashboardul”;
- iconuri identice într-un cerc pastel pe fiecare rând;
- prea multe pilule cu margini 9999px, umbre foarte mari;
- un desen 3D cu glob, frunză, roboțel sau scut cu lacăt în hero;
- copy exagerat despre AI care „asigură” agricultura responsabilă;
- animații gratuite pentru verdict, numere fictive sau random progress;
- tot textul centrat; un raport bun folosește majoritar **aliniere la stânga**;
- 12 culori de accent, 6 fonts, 5 stiluri de colțuri rotunjite.

Interfața AR TREBUI să conțină:

- margini/aliniere impecabile, mult spațiu alb intenționat, heading-uri ferme;
- tipografie cu caracter și contrast funcțional, nu decorativ;
- grafice cu date reale și sursa lângă ele;
- informație progresivă: afișezi întâi ce contează, dar poți extinde tehnicul;
- stări empty/loading/error explicate, nu componente goale;
- UI pentru incertitudine, nu doar „verde/roșu”;
- design propriu al pașaportului cu secțiuni, QR și provenance;
- un stil repetat de etichete, butoane, formulare și tabele.

---

## 10. Accesibilitate și verificare vizuală

Testează manual:

- text de 16px se citește confortabil pe mobil 375px;
- ordine corectă Tab: nav → inputuri → select → submit → status;
- `label htmlFor` pentru fiecare input; `aria-live="polite"` pentru stări de tranzacție;
- nu comunica verdictul exclusiv cu roșu/verde;
- focusul este vizibil în browser, butoane >=44px pe mobil;
- închide overlayul MetaMask fără să pierzi formularul;
- butonul „copy hash” copiază hash-ul complet;
- graficul are și tabel de date lizibil pentru cine nu poate interpreta desenul;
- textul muted nu este prea pal; verifică contrastul cu un contrast checker.

### Teste de design pe care Oana le predă echipei

| Test | Ce demonstrează |
|---|---|
| Captură 1440×900, start flow | aspect editorial, claritatea conceptului |
| Captură 375×812, formular | mobile util, inputuri vizibile |
| Captură 1440×900, NDVI | grafic + sursă + legendă + quality |
| Captură pașaport | QR, hash, sursă, verdict, limitări |
| Ecran pe `inconclusive` | incertitudine clară, nu „failed” |
| Video de 30 sec cu Tab | accesibilitate de bază |

---

## 11. Cum lucrezi cu un asistent AI la design

### Prompt recomandat pentru fiecare componentă

```text
Lucrez în React + TypeScript + Tailwind v4 la TerraCycle Proof.
Citește Agent.md, Role_Oana.md și DESIGN_OANA.md integral.
Vreau să construiești [NUME ECRAN/COMPONENTĂ], fără să modifici restul fluxului.
Respectă EXACT paleta deep navy #101E34, oxblood #8E2230,
paper #F8F7F4, white #FFFFFF, ink #17191C.
Stil editorial modern, sobru, premium, minimalist, fără gradients,
fără glassmorphism, fără iconuri decorative, fără dashboard generic AI.
Folosește grid/spacing/tipografie din design brief, responsive 375/768/1440,
fără valori inventate. Fiecare buton trebuie să aibă acțiune reală.
Dă codul complet pentru fișierele modificate și cum testez cu npm run dev/build.
```

### Prompt de audit vizual

```text
Evaluează screenshotul acestui ecran față de DESIGN_OANA.md.
Nu-l lăuda gratuit. Notează probleme concrete la: ierarhie vizuală,
spațiere, contrast, aspect generic AI, microcopy, responsive și accesibilitate.
Propune schimbările în ordinea impactului; apoi implementează DOAR primele 3.
```

---

## 12. Definiția designului final

Ecranul trebuie să funcționeze ca o poveste în 6 pași: **parcelă → istoric → decizie → angajament → dovadă → pașaport**. Juriul trebuie să poată urmări fără explicație ce este afirmația fermierului, ce se poate verifica prin satelit, cine semnează și ce face contractul. Dacă poate face asta și UI-ul nu arată ca un șablon de 10 dolari, brief-ul și-a îndeplinit scopul.
