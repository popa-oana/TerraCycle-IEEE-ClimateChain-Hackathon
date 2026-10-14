# START AICI — TerraCycle Proof (echipa complet începătoare)

**Data versiunii:** 14 octombrie 2026. **Cine citește:** toți, înainte de fișierul rolului.

## Ce livrăm, concret?

Un website demonstrabil care permite: `parcelă → introducere istoric → recomandare rotație → înregistrare angajament pe testnet → finanțare test → verificare istorică NDVI → semnătură digitală → plată/refund → pașaport QR`.

**O singură regulă de verificare în MVP:** parcelă cu acoperire vegetală într-o fereastră precizată. Recomandarea culturilor este separată de verdictul satelitar; nu putem verifica cu NDVI dacă fermierul chiar n-a folosit pesticide.

## 1. Instalații comune (Windows, varianta recomandată)

- [Git](https://git-scm.com/downloads), [VS Code](https://code.visualstudio.com/), [Node.js LTS](https://nodejs.org/en/download), [Python 3.11+](https://www.python.org/downloads/), [Docker Desktop](https://www.docker.com/products/docker-desktop/) **doar pe mașina Corinei** dacă PostgreSQL rulează acolo.
- Verifică în **PowerShell nou**, după instalare:

```powershell
git --version
node --version
npm --version
py --version
```

- Pentru un proiect Vite recent, **Node 20.19+ sau 22.12+** (sau versiune LTS compatibilă) este o alegere sigură; `node --version` trebuie să fie suficient de nou. Dacă comanda `py` nu există, încearcă `python --version` și verifică PATH.
- Pentru Foundry pe Windows: **WSL2/Ubuntu recomandat** (nu presupune că comenzile bash funcționează în PowerShell). Dorian urmează pașii separați din rolul său.
- Nu este necesar să instalați cu toții TOATE tehnologiile. Fiecare rol are propriile instrucțiuni.

## 2. Structura convenită

```text
terracycle-proof/
├── START_AICI.md / Agent.md / Role_*.md / DESIGN_OANA.md
├── TerraCycle_Ghid_Integrare.md
├── README.md / SETUP.md / CONTRIBUTING.md
├── .gitignore / .env.example
├── docs/
│   ├── api-contract.md / openapi.json / model.md / limitations.md
│   ├── decisions.md / demo-script.md
├── data/
│   ├── fixtures/ / parcels/ / ndvi/ / climate/ / labels.csv
├── backend/
│   ├── main.py / database.py / models.py / schemas.py / hashing.py
│   ├── rules/rotation.py / signer/sign_verdict.mjs
│   └── ml/{extract.py,features.py,train.py,predict.py,rules.py}
├── contracts/
│   ├── src/TerraCycleEscrow.sol / test/TerraCycleEscrow.t.sol
└── frontend/
    └── src/{pages,components,lib,styles}/
```

**Notă:** unele fișiere sunt planificate, nu există încă. Nu presupune că pot fi rulate până când colegul responsabil le creează. `docs/decisions.md` ține deciziile de schema și fixările importante.

## 3. Ziua zero: 90 de minute împreună

1. Dorian creează repository-ul și invitațiile GitHub; pune `Agent.md` și ghidurile în rădăcină.
2. Toți clonează: `git clone <URL-ul-real-al-repo-ului>` → `cd terracycle-proof`.
3. Alegeți împreună **o singură parcelă de referință** (din `data/fixtures/demo.json`, fără a inventa coordonate ale unei ferme reale), `season_id`, interval, `plan_id`, `policy_version`, `reward_wei` și o fereastră de verificare.
4. Corina + Dorian citesc toate obiectele JSON din `TerraCycle_Ghid_Integrare.md` și marchează într-un PR `SCHEMA V1 ACCEPTATĂ`.
5. Oana arată wireframe-ul și are aplicația React pornită.
6. Crenguța aduce o observație satelitară cu sursă reală, dacă este disponibilă, sau explică blocajul și fallback-ul.
7. Fiecare face un PR minimal care arată că Git-ul funcționează.

## 4. Ordinea implementării fără dependențe imposibile

| Zi | Minimul care trebuie să existe | Cum știm |
|---|---|---|
| 14 oct | schemă comună, UI inițial, test Forge, date NDVI sau plan de fallback | PR + captură + CSV/test |
| 15 oct | întreg fluxul clickable pe fixture, API minim, contract local | demo de 2 minute |
| 16–17 oct | rotații, date meteo, CSV satelitar, QR și pașaport | API + grafic |
| 18–19 oct | ML sau fallback declarat, EIP-712 și integrarea | test end-to-end |
| 20–22 oct | cazuri negative, teste, Sepolia și acces public | 5 scenarii și QR scanat |
| 23 oct | înghețare features | niciun feature nou |
| 24 oct | video/repo/documentație gata | clonare și replay demo |
| 25 oct | depunere, conform răspunsului organizatorilor | confirmare submit |

## 5. Scurt glosar

- **Frontend:** ce vede utilizatorul în browser (Oana).
- **Backend / API:** programul care primește cereri JSON și coordonează datele și logica (Corina).
- **Database:** unde salvăm planuri, snapshots, legături la tranzacții (Corina).
- **Fixture:** set mic de date *inventate și marcate ca demo* cu structură fixă, pentru a putea programa înaintea datelor reale.
- **Snapshot canonic:** versiunea exactă a planului/dovezii, serializată determinist și înghețată înainte de hash.
- **NDVI:** indice calculat din benzi satelitare roșu/infraroșu; măsoară un semnal de vegetație, nu conformitatea ecologică.
- **LightGBM:** un model pe date tabelare; e util doar dacă are etichete relevante și o evaluare corectă.
- **Smart contract:** cod rulat pe blockchain care menține starea și regulile de plată.
- **Escrow:** fonduri ținute într-un contract până la o condiție.
- **EIP-712:** standard pentru semnarea unui verdict structurat, diferit de o tranzacție MetaMask.
- **Testnet (Sepolia):** rețea de test cu ETH fără valoare monetară reală.

## 6. Ce să NU faceți

- Nu utilizați date satelitare fictive prezentate drept observații reale.
- Nu promiteți „AI garantează agricultura sustenabilă”.
- Nu folosiți toate tehnologiile doar de dragul lor. Cele 4 responsabilități sunt deja suficiente.
- Nu schimbați o interfață în propriul branch fără să actualizați ghidul comun.
- Nu pierdeți o zi întreagă pe o eroare de conectare Copernicus: există fallback și criteriu de oprire.
- Nu faceți deploy sau release pe baza unui singur happy path, fără teste negative.

## 7. Ce trebuie citit acum

- **Oana:** `Role_Oana.md` + `DESIGN_OANA.md`.
- **Corina:** `Role_Corina.md` + `TerraCycle_Ghid_Integrare.md`.
- **Dorian:** `Role_Dorian.md` + `TerraCycle_Ghid_Integrare.md`.
- **Crenguța:** `Role_Crenguta.md` + `TerraCycle_Ghid_Integrare.md` (schema observațiilor/evidence).

**Regula de echipă:** la checkpoint-ul zilnic, fiecare demonstrează ceva care rulează. „Am citit documentația” nu este un rezultat integrabil.
