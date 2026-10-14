# CRENGUȚA — Ghid extins: Copernicus, NDVI, etichete, ML, dovezi

> Citește `START_AICI.md`, `Agent.md` și `TerraCycle_Ghid_Integrare.md` înainte de acest fișier. Rolul tău: produci **dovezi satelitare reale, reproductibile**, o evaluare onestă a unui model simplu și o funcție Python utilizabilă direct de backendul Corinei. Nu ai de construit un server separat și nu trebuie să faci procesare satelitară în timpul demo-ului.

## 1. Înțelege exact ce verificăm

Proiectul urmărește un angajament de **acoperire vegetală a solului într-o fereastră temporală definită**, pe parcele fixe, într-un sezon istoric. Datele satelitare pot sugera prezența vegetației; **nu demonstrează** lipsa pesticidelor, absența erbicidelor, respectarea fertilizării sau certificarea bio. Blockchainul păstrează angajamentul și verdictul semnat, dar nu certifică adevărul observațiilor satelitare.

**MVP:** 5–10 parcele într-o singură regiune, un sezon istoric (de exemplu 2024), export CSV cu NDVI și calitate, regulă provizorie deterministă, apoi model LightGBM numai dacă există etichete independente și suficient de bune. Primul obiectiv este **un CSV real pentru o singură parcelă**, nu un model sofisticat.

## 2. Dicționar minimal

- **Sentinel-2 L2A**: produs satelitar cu reflectanță de suprafață; are benzi multispectrale.
- **B04**: lumina roșie; **B08**: infraroșu apropiat; plantele reflectă diferit cele două benzi.
- **NDVI**: `(B08 - B04) / (B08 + B04)`, aproximativ între -1 și 1. Valori mari pot indica vegetație viguroasă; nu sunt un verdict agronomic de sine stătător.
- **SCL**: Scene Classification Layer, clasificarea pixelilor. De exemplu 3 indică umbre de nori, 8–9 nori, 10 cirrus; 0, 1, 11 și alte clase problematice trebuie analizate explicit pentru mască.
- **GeoJSON**: fișier cu coordonatele poligonului parcelei; coordonatele sunt de regulă longitudine, latitudine în WGS84.
- **openEO**: interfață pentru cereri de procesare pe platforma Copernicus.
- **Etichetă (label)**: adevărul de referință oferit de o sursă/procedură independentă de predicția modelului.
- **Pseudo-etichetă**: etichetă generată dintr-o regulă sau alt model, nu adevăr independent.
- **Data leakage**: informație din test pătrunde în antrenare, umflând artificial performanța.
- **F1**: măsură care combină precizia și recall-ul; **confusion matrix** arată erorile fiecărei clase.

## 3. Pregătește mediul (Windows PowerShell)

Instalează Python 3.11 sau 3.12 și VS Code. Din rădăcina repo-ului:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install openeo requests pandas numpy scikit-learn lightgbm matplotlib joblib pytest
python -c "import openeo, pandas, lightgbm; print('OK')"
```

Dacă PowerShell blochează activarea, poți utiliza direct `.venv\Scripts\python.exe` și `.venv\Scripts\pip.exe`, fără a schimba politica globală de securitate. Pune dependențele într-un `requirements-ml.txt` cu versiuni fixate când primul flux funcționează.

Creează folderele:

```text
data/parcels/
data/ndvi/
data/labels/
data/features/
backend/ml/
docs/
scripts/
```

## 4. Parcela: primul fișier real

Creează `data/parcels/parcel_01.geojson` cu un `FeatureCollection` și un `Polygon` închis. **Nu inventa un teren agricol real doar pentru că punctele de pe hartă arată convenabil.** Alege o parcelă demonstrativă identificabilă pe hartă, fără a pretinde drept de proprietate, păstrează coordonatele, sursa și data selecției. Verifică manual conturul în [Copernicus Browser](https://browser.dataspace.copernicus.eu/).

Exemplu **strict pentru înțelegerea formatului, nu parcelă reală**:

```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature", "properties": {"parcel_id": "parcel_01"},
    "geometry": {"type": "Polygon", "coordinates": [[[0.0,0.0],[0.001,0.0],[0.001,0.001],[0.0,0.001],[0.0,0.0]]]}
  }]
}
```

Nu folosi exemplul de mai sus în demo: este un poligon artificial. Pentru un export real, folosește coordonate reale și confirmă că zona conține pixeli Sentinel-2 utilizabili.

## 5. Exportă un NDVI adevărat, pas cu pas

1. Intră în [Copernicus Data Space](https://dataspace.copernicus.eu/) și autentifică-te.
2. Deschide [notebook-ul oficial NDVI Timeseries](https://documentation.dataspace.copernicus.eu/notebook-samples/openeo/NDVI_Timeseries.html). Înainte să îl modifici, rulează exemplul oficial end-to-end.
3. Înlocuiește geometria demonstrativă cu GeoJSON-ul vostru și alege sezonul istoric convenit (`2024-03-01` până la `2024-10-31`, dacă rămâne acesta).
4. Cere colecția `SENTINEL2_L2A`, benzile `B04`, `B08` și `SCL`; **verifică semnătura API-ului și metadatele colecției** înainte să copiezi apelul. `spatial_extent` este uzual un bounding box, în timp ce un poligon complet se transmite prin operațiile care acceptă geometrii; nu presupune că `spatial_extent=geometry` merge.
5. Aplică o mască de calitate înainte de agregare. Cel puțin SCL 3, 8, 9, 10 nu intră în NDVI; decideți explicit și restul claselor nevalide și scrieți alegerea în raport.
6. Calculează `NDVI=(NIR-RED)/(NIR+RED)` doar pe pixeli valizi, cu protecție pentru numitor nul.
7. Agregă spațial în poligon pentru fiecare dată. **Calculează separat fracția de pixeli valizi**, nu doar media NDVI: `număr_pixeli_valizi / număr_pixeli_totali_din_parcelă`.
8. Exportă într-un CSV local și păstrează ID-ul scenei/data achiziției dacă interfața disponibilă le oferă. Uneori exportul agregat nu le oferă direct: atunci păstrează un manifest separat; nu inventa `scene_id`.

Schema de livrat Corinei:

```csv
parcel_id,acquired_at,scene_id,ndvi_mean,valid_pixel_fraction
parcel_01,2024-04-10T00:00:00Z,<id_din_sursa>,0.54,0.93
```

**Rândul e numai un exemplu de structură, nu un rezultat observat.** Pentru fiecare rând real: `ndvi_mean` trebuie să fie în [-1,1], `valid_pixel_fraction` în [0,1], dată validă, parcelă existentă, sursă documentată. Eliminați duplicatele pentru aceeași parcelă/scenă/dată printr-o regulă reproductibilă.

### Poarta de decizie: 14 octombrie, ora 20:00

Trebuie să aveți: un fișier NDVI real inspectabil și o strategie scrisă pentru etichete. Dacă openEO e blocat de autentificare/joburi/limitări, nu pierdeți restul hackathonului: export manual pentru 1–2 parcele din Copernicus Browser sau folosiți [Sentinel Hub Statistical API](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Statistical.html) conform documentației. Faceți fallback după un interval prestabilit, nu după două zile.

## 6. Controlează calitatea datelor

O medie NDVI pe doi pixeli vizibili nu reprezintă întreaga parcelă. Reguli inițiale propuse în plan:

- Exclude o observație dacă fracția pixelilor valizi este sub **0.50**.
- Dacă într-o fereastră sunt mai puțin de **5 observații valide**, rezultatul este `inconclusive`.
- Acoperirea temporală sub **0.50** produce `inconclusive`.

**Definiți concret acoperirea temporală:** împarteți fereastra în intervale fixe (de exemplu săptămâni calendaristice), apoi `intervale_cu_cel_putin_o_observatie_valida / numar_total_intervale`. Salvați dimensiunea intervalului în configurația politicii. Un interval cu 10 observații nu compensează automat 4 intervale fără date.

Stocați în evidență câte scene au fost consultate, câte au fost excluse, fracția validă și regulile folosite. `inconclusive` nu înseamnă `nonconform`.

## 7. Etichetele: cea mai mare capcană științifică

**Sentinel-2 nu oferă etichete „fermă conformă”.** Pentru un prototip simplu puteți defini o sarcină separată: *vegetație vizibilă vs. sol predominant descoperit* într-o observație sau fereastră. Atunci:

1. Scrieți protocolul într-un `docs/labeling_protocol.md`: ce imagini/benzi vă uitați, ce înseamnă 0/1 și când exemplul e ambiguu.
2. Pregătește o foaie cu `observation_id`, `parcel_id`, `date`, `source`, `label`, `reviewer_id`, `confidence`, `notes`.
3. Pe 17 octombrie fiecare dintre cei patru etichetează 15–20 exemple. Exemplele discutabile se revizuiesc de două persoane.
4. Nu cere evaluatorului să se uite la valoarea NDVI dacă scopul e o etichetă vizuală independentă de pragul NDVI.
5. Păstrează separat `unknown/ambiguous`; nu forța eticheta 0 ca să iasă balanța claselor.

Dacă generați `label = int(ndvi_mean > 0.35)`, sunt **pseudo-etichete**. Modelul poate învăța doar să imite pragul; nu trebuie prezentat ca validare independentă și nu furnizează dovada unei practici agricole.

## 8. Construiește features fără scurgeri de date

Fișier `backend/ml/features.py` cu funcție unică, reutilizată la train și predicție. Posibile features pe fereastra de verificare: `ndvi_mean`, `ndvi_min`, `ndvi_max`, număr observații, panta NDVI în timp, fracție intervale acoperite, zile/observații peste prag; opțional precipitații cumulate și temperatură medie din fișierele Corinei. **Nu adăuga în inferență features care nu au existat la train.**

Datele trebuie să respecte timpul: dacă verdictul este pentru o fereastră terminată la 31 mai, nu introduce valori obținute în iulie. Normalizează datele/datele lipsă cu logică fixată pe datele de antrenare.

Păstrează `data/features.csv`, plus `model_metadata.json` cu `feature_names` în ordine, versiunea algoritmului de creare a features, sursa datelor și politica de verificare.

## 9. Întâi baseline, apoi LightGBM

- **Baseline A:** o regulă simplă bazată pe NDVI, care operează pe aceeași sarcină ca etichetele.
- **Baseline B:** `LogisticRegression`.
- **Model candidat:** `LightGBM LGBMClassifier` (cu parametri inițiali simpli, fără tuning agresiv pe eșantion minuscul).

Dacă sunt 60–80 etichete și doar 5–10 parcele, puterea statistică este foarte redusă. Nu promite acuratețe generalizabilă. De asemenea, multe observații de pe aceeași parcelă sunt corelate; **nu folosi split aleator pe rânduri**. Aplică un split pe grup `parcel_id` și păstrează un test final nefolosit la alegerea hiperparametrilor. `GroupKFold` cere suficiente grupuri; dacă nu sunt suficiente, raportează exact limitarea.

Exemplu orientativ:

```python
from sklearn.model_selection import GroupKFold
from sklearn.metrics import classification_report, confusion_matrix
from lightgbm import LGBMClassifier

cv = GroupKFold(n_splits=3)  # doar dacă există cel puțin 3 parcele distincte
for train_idx, val_idx in cv.split(X, y, groups=parcel_ids):
    model = LGBMClassifier(n_estimators=100, learning_rate=0.05,
                           max_depth=4, random_state=42)
    model.fit(X.iloc[train_idx], y.iloc[train_idx])
    pred = model.predict(X.iloc[val_idx])
    print(confusion_matrix(y.iloc[val_idx], pred))
    print(classification_report(y.iloc[val_idx], pred, zero_division=0))
```

**Atenție:** codul arată doar validarea încrucișată; pentru o evaluare finală corectă rezervă un grup/set de test independent înainte de selectarea modelului. Nu compara scoruri pe seturi diferite.

## 10. Separă predicția ML de verdictul de angajament

Dacă clasificatorul prezice **vegetație prezentă**, asta NU este automat verdictul unei politici „acoperire vegetală suficientă în fiecare perioadă”. Scrie `backend/ml/rules.py` cu o funcție unică `verify_parcel(parcel_id, policy, evidence_directory)`. Ea:

1. Încarcă fișierele reale, nu inventează observații.
2. Filtrează datele în fereastra angajamentului.
3. Calculează calitatea și acoperirea; la date insuficiente returnează `inconclusive`.
4. Aplică politica de agregare acceptată de echipă la observațiile/estimările valide.
5. Returnează verdictul (`conform`, `nonconform`, `inconclusive`) plus explicație, observații folosite, observații excluse, indicatori de calitate, versiune model/reguli și surse.

Corina importă direct această funcție. Nu se scrie un al doilea algoritm de verificare în FastAPI. Nu afișa scorul de probabilitate al clasei „vegetație” ca probabilitate de agricultură conformă.

## 11. `evidence_document`: dovada care poate fi hash-uită

Schema exactă este comună și trebuie validată în `TerraCycle_Ghid_Integrare.md`. Furnizează Corinei un obiect structurat care include: `parcel_id`, `window_start/end`, sursele satelitare identificabile, observațiile și ordinea lor, criteriile de mască, fracția pixelilor valizi, regulile de excludere, datele climatice folosite dacă există, `model_version`, `feature_version`, pragurile și `verdict` cu explicație. Corina îl transformă în snapshot canonic și calculează hash-ul; **tu nu implementezi hashing separat**.

Test de reproductibilitate: pe aceleași fișiere și aceeași configurație, funcția întoarce aceleași observații, aceeași ordine și același verdict. Dacă datasetul sau politica se schimbă, versiunea trebuie actualizată.

## 12. Teste obligatorii

- CSV valid: valori NDVI/fractie în intervalele corecte, fără date neparsabile.
- Fără fișier NDVI: eroare explicită, nu verdict fabricat.
- 4 observații valide: `inconclusive`.
- Acoperire temporală 40%: `inconclusive`.
- Fracție validă 0.49: observație exclusă.
- Intrări nesortate: aceeași ieșire după sortare deterministă.
- Acelasi dataset + model + policy: același verdict și aceleași dovezi.
- Train/test: `set(train_parcel_ids).isdisjoint(test_parcel_ids)` este adevărat.
- Raportul nu susține certificare bio/pesticide pe baza NDVI.

## 13. Calendar 14–25 octombrie

| Zi | Livrabil și test de acceptare |
|---|---|
| 14 | CSV NDVI **real** dintr-o parcelă; protocol etichete; decizie la 20:00 |
| 15 | Verificator provizoriu cu prag clar documentat |
| 16 | Mască nori, fracție pixeli valizi, acoperire temporală implementate |
| 17 | Etichetare cu echipa, `labels.csv`, `features.csv`, split pe parcelă |
| 18 | Baseline + LightGBM dacă etichetele justifică; F1/confusion matrix |
| 19 | `verify_parcel()` returnează trei verdicte și dovezi explicabile |
| 20 | Evaluare fără leakage, verificare cu Corina |
| 21 | Date reale pentru scenariile disponibile; scenariile artificiale marcate fixture |
| 22 | Dataset/model/policy înghețate cu metadate și hash-uri Corina |
| 23 | `docs/model.md` și `docs/limitations.md`; fără features noi |
| 24 | Explicație satelit/ML și grafice pentru video-ul Oanei |
| 25 | Verifică formulările științifice ale prezentării înainte de submit |

## 14. Ce înseamnă „gata”

Există minimum un export real verificabil, README cu proveniență și reproducere, `backend/ml/` importabil, funcție de verificare unică, teste pentru `inconclusive`, manifest dovezi, raport de evaluare cu baseline și limitări. Dacă nu aveți etichete credibile, **livrați explicit un verificator bazat pe reguli** și prezentați ML ca experiment, nu ca certificare.

## 15. Prompt pentru asistentul AI

> Citește `Agent.md`, `TerraCycle_Ghid_Integrare.md` și `Role_Crenguta.md`. Sunt începător cu Copernicus/openEO. Mai întâi explică scopul datelor și operațiunea, apoi scrie un singur script minimal cu fișier de intrare, comandă de rulare, verificare automată și mesaj de eroare. Nu inventa date sau rezultate. Verifică parametrii openEO în documentația actuală înainte de a-mi da cod executabil; păstrează diferența dintre predicția vegetației și conformitatea agronomică.
