# DORIAN — Ghid extins pentru blockchain, EIP-712, QR, Git și predare

> Citește în această ordine: `START_AICI.md`, `Agent.md`, `TerraCycle_Ghid_Integrare.md`, apoi acest document. Ești responsabil pentru contractul Solidity, semnarea verdictelor în Node, testele de securitate și procesul de integrare Git. Nu implementa pe cont propriu alt contract API.

## 1. Ce construiești și de ce

Aplicația promite un reward pentru o practică verificabilă. Un **smart contract** este un program care rulează pe blockchain și ține ETH de test într-un **escrow**: banii nu ajung imediat la fermier. Backendul verifică dovezile satelitare; apoi un **verificator autorizat** semnează verdictul digital. Contractul acceptă doar semnătura acestui verificator. Dacă verdictul e `conform`, trimite recompensa beneficiarului. Pentru `nonconform` sau `inconclusive`, nu plătește beneficiarul; finanțatorul poate solicita refund conform regulilor stabilite.

**Nu dovedești că satelitul are dreptate prin blockchain.** Dovedești cine a semnat verdictul, că datele angajamentului nu au fost schimbate și că regulile de plată au fost executate. În demo folosești ETH de test, niciodată bani reali.

## 2. Glosar pentru începători

- **EVM**: mediul unde se execută programele Ethereum.
- **Solidity**: limbajul în care scrii contractul.
- **Foundry**: set de unelte pentru compilare, testare și deploy. `forge` compilează/testează, `anvil` pornește un blockchain local, `cast` inspectează și trimite apeluri.
- **RPC URL**: adresa unui server prin care interacționezi cu un blockchain.
- **Wallet**: adresă publică plus cheie privată. Cheia privată nu se publică.
- **ABI**: descrierea funcțiilor și a evenimentelor contractului, citită de frontend.
- **EIP-712**: metodă standard de semnare a unui obiect structurat; include identificatorul rețelei și adresa contractului.
- **Hash**: amprentă digitală; `planHash` este produs numai de backendul Corinei.
- **Replay attack**: încercarea de a reutiliza o semnătură într-un context nepermis.

## 3. Instalare și verificare inițială

Pe Windows, folosește **WSL2 Ubuntu** pentru Foundry; Node.js și Git pot fi instalate și pe Windows. În terminalul Ubuntu:

```bash
sudo apt update
sudo apt install -y git curl build-essential
curl -L https://foundry.paradigm.xyz | bash
source ~/.bashrc
foundryup
forge --version
anvil --version
```

Din rădăcina repo-ului, **doar dacă directorul `contracts/` nu există deja**:

```bash
forge init contracts --no-git
cd contracts
forge build
forge test
```

Dacă proiectul este deja creat de un coleg, nu rula `forge init` peste el. Instalează `ethers` în directorul Node stabilit de echipă și fixează versiunea în lockfile. Păstrează într-un `.env` ignorat de Git: `DEV_PRIVATE_KEY`, `VERIFIER_PRIVATE_KEY`, `SEPOLIA_RPC_URL`. Nu pune niciodată valori reale în README, screenshoturi, loguri sau frontend (`VITE_*`).

## 4. Înainte de a scrie contractul: decideți exact interfața

Cu Corina, validați și consemnați în `TerraCycle_Ghid_Integrare.md`:

1. Modul de calcul al `commitmentId` (conform Agent: `keccak256(abi.encode(parcelId, seasonId))`). Precizați tipul Solidity al ambelor argumente; altfel hash-urile diferă.
2. Câmpurile EIP-712, cu nume, tipuri și ordine identice în Python/Node/Solidity: `bytes32 commitmentId`, `bytes32 planHash`, `bytes32 evidenceHash`, `uint8 verdict`, `uint64 validUntil`.
3. Domeniul: `name=TerraCycleEscrow`, `version=1`, `chainId` real, `verifyingContract` adresa reală.
4. Funcțiile, parametrii și evenimentele pentru `registerCommitment`, `fundCommitment`, `settle`, `refund`.
5. Cine este beneficiarul, cine finanțează, când expiră angajamentul și cine poate solicita refund.

**Important:** Acestea sunt decizii de integrare, nu presupuneri pe care le poți ascunde în cod. Dacă lipsește ceva, deschide un PR de documentație înainte să programezi.

## 5. Construirea contractului în pași mici

### Pasul A: definirea datelor și a constructorului

Creează `contracts/src/TerraCycleEscrow.sol`. Definește o structură `Commitment` pentru ID, `planHash`, fermier/beneficiar, finanțator, sumă, expirare și stare. Definește enumul `Registered`, `Funded`, `Paid`, `Negative`, `Refunded` sau maparea agreată exact de echipă. Primește/verifică adresa verificatorului autorizat în constructor. Folosește biblioteci OpenZeppelin EIP712/ECDSA pentru semnături și protecție de reentrancy la plăți.

### Pasul B: registration

`registerCommitment(...)` trebuie să respingă un ID deja înregistrat și să lege fermierul/beneficiarul de `planHash`. Test: o înregistrare nouă reușește; a doua înregistrare pentru aceeași parcelă-sezon e respinsă.

### Pasul C: funding

`fundCommitment(...) payable` acceptă numai starea `Registered` și un reward pozitiv. Setează finanțatorul și suma, trece în `Funded`. Testează finanțarea dublă și sume zero. Nu folosi un transfer automat către fermier în acest pas.

### Pasul D: settle

Primește verdictul și semnătura. Calculează digestul EIP-712 **în contract**, recuperează semnatarul și compară cu `verifier`. Compară `commitmentId`, `planHash`, `validUntil` și starea curentă. Verdicturile au codurile `0=conform`, `1=nonconform`, `2=inconclusive`. Pentru conform: schimbă starea înainte de transfer, plătește o singură dată, emite eveniment. Pentru celelalte: intră în `Negative`, banii rămân pentru refund. Tratează explicit semnăturile expirate și datele modificate.

### Pasul E: refund

Numai finanțatorul eligibil poate recupera fondurile, în condițiile convenite: verdict negativ/neconcludent ori expirare fără verdict. Schimbă starea înaintea transferului. Testează că un străin nu poate retrage și că refund-ul repetat e imposibil.

## 6. Semnarea EIP-712 în Node

Fișier: `backend/signer/sign_verdict.mjs`. Intrare: un JSON pe `stdin` cu **mesajul de semnat și domeniul**, fără cheia privată. Procesul citește cheia din `process.env.VERIFIER_PRIVATE_KEY`. Folosește `ethers.Wallet.signTypedData(domain, types, value)`; outputul `stdout` conține numai JSON cu `signature` și, dacă e util, `digest`. Toate mesajele de eroare merg pe `stderr`; procesul iese cu cod diferit de zero dacă nu poate semna.

Exemplu de structură logică, nu valori de producție:

```js
const types = {
  VerificationResult: [
    {name: 'commitmentId', type: 'bytes32'},
    {name: 'planHash', type: 'bytes32'},
    {name: 'evidenceHash', type: 'bytes32'},
    {name: 'verdict', type: 'uint8'},
    {name: 'validUntil', type: 'uint64'},
  ]
};
```

Testează întâi cu un exemplu fix de la Corina: aceeași adresă recuperată local cu `ethers.verifyTypedData(...)` și în contractul rulat pe `anvil`. Semnătura pentru altă rețea sau alt contract trebuie să eșueze.

## 7. Testare Foundry: lista minimă

Scrie `contracts/test/TerraCycleEscrow.t.sol` și rulează `forge test -vvv` după fiecare modificare. **Testele obligatorii:** înregistrare+finanțare+plată conform; neconform păstrează fondurile; alt semnatar respins; settle repetat respins; aceeași parcelă-sezon respinsă; semnătură expirată respinsă; refund după verdict negativ; refund după expirare; `planHash` schimbat respins. Mai testează reentrancy, funder greșit, sumă zero, domeniu chainId greșit și refuzul unei semnături pentru alt `evidenceHash`.

Pentru fiecare test notează: **precondiție**, **acțiune**, **rezultat așteptat**, **rezultat observat**. Nu declara contractul sigur doar fiindcă a compilat.

## 8. Integrare cu frontend și backend

- **De la Corina primești:** ID, `planHash`, `evidenceHash`, politica, adresa verificatorului, regulile de expirare și contractul API.
- **Oanei îi dai:** `GET /config` cu `chainId`, adresa contractului, ABI-ul exact, funcțiile chemate și exemplele de stări.
- **Corinei îi dai:** utilitarul Node verificabil, evenimentele emise de contract și regulile prin care backendul confirmă tranzacția.
- **Nu accepta drept dovadă doar un `txHash` trimis de browser.** Backendul verifică rețea, adresă contract, eveniment, parametri, fonduri și statusul tranzacției.

## 9. QR și pașaport

QR-ul este **doar un link** către pagina publică `PUBLIC_APP_URL/passport/{commitment_id}`. Poți genera QR prin `qrcode` sau colabora cu Oana pentru `qrcode.react`. Linkul trebuie testat de pe telefon cu conexiune separată. Un QR cu `localhost` arată spectaculos până când îl scanează juriul și nu se întâmplă nimic.

Pașaportul trebuie să permită verificarea ID-ului, statusului contractului, dovezilor și tranzacției, fără a pretinde că blockchainul certifică informațiile agronomice.

## 10. Git și Pull Requests

Creează `CONTRIBUTING.md` cu reguli: branch per task, `main` protejat, PR cu reviewer diferit de autor, fără chei/loguri sensibile. Comenzi tipice:

```bash
git checkout main
git pull --rebase origin main
git switch -c feat/eip712-signing
# editezi + testezi
git add contracts backend/signer
git commit -m "Implement EIP-712 verdict signing"
git push -u origin feat/eip712-signing
```

Deschide PR și atașează comandă de test, output și ce alte module sunt afectate. Pentru PR-urile tale, reviewer este Oana sau Corina.

## 11. Calendar realist 14–25 octombrie

| Dată | Rezultat verificabil |
|---|---|
| 14 oct | Foundry funcționează; schema EIP-712 și interfața escrow agreate cu Corina |
| 15 oct | Register/fund/settle/refund local pe Anvil, cu teste simple |
| 16 oct | `sign_verdict.mjs` semnează exemplul fix și contractul îl acceptă |
| 17 oct | QR pentru pașaport + manifest dovezi împreună cu Corina |
| 18 oct | Teste semnătură greșită, domeniu greșit și replay |
| 19 oct | Verdictul real ajunge backend → semnare → contract |
| 20 oct | Setul de teste de securitate și refund trece |
| 21 oct | Demo local stabil, evenimente vizibile în explorer local |
| 22 oct | Deploy pe Sepolia doar dacă e stabil; ABI și adresă prin `/config` |
| 23 oct | Feature freeze, PR-uri închise, doar bug-uri critice |
| 24 oct | Devpost, repo public, demo video și limitări verificate |
| 25 oct | Submit și verificarea linkurilor; fără modificări după depunere |

## 12. Cum arată predarea ta finală

Există `contracts/src/TerraCycleEscrow.sol`, teste `forge test -vvv` trecute, `backend/signer/sign_verdict.mjs`, `CONTRIBUTING.md`, ABI + adresă accesibile din `/config`, QR scanat fizic, instrucțiuni de deploy și limitări în README. Păstrează capturi ori outputuri ale testelor fără secrete.

## 13. Prompt bun pentru asistentul de cod

> Citește `Agent.md`, `TerraCycle_Ghid_Integrare.md` și `Role_Dorian.md`. Lucrăm cu Solidity/Foundry și ethers v6. Sunt începător. Explică-mi mai întâi scopul funcției și datele de intrare/ieșire, apoi implementează UN singur pas cu fișier complet, comenzile de rulare și cel puțin un test negativ. Nu modifica schema agreată, nu inventa endpointuri și nu pune chei private în frontend sau Git.
