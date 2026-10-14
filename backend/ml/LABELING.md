# Protocol de etichetare — TerraCycle Proof

## Scop

Acest document definește regulile pe care le urmează echipa
la etichetarea observațiilor satelitare. Etichetele servesc
ca referință independentă pentru evaluarea modelului ML.

## Sarcina de etichetare

**Întrebare:** „Într-o imagine Sentinel-2 suficient de clară,
se observă vegetație pe suprafața parcelei?"

Aceasta NU este aceeași întrebare cu „Parcela respectă
angajamentul de acoperire vegetală". Prima se referă la o
singură observație, a doua necesită mai multe observații +
reguli temporale + criterii de calitate.

## Etichete

| Valoare | Semnificație | Când o folosim |
|---------|-------------|---------------|
| `1`     | Vegetație vizibilă | Imagine suficient de clară, vegetație vizibilă pe parcelă |
| `0`     | Vegetație nevizibilă | Imagine clară, fără vegetație detectabilă vizual |
| _(gol)_ | Nu se poate decide | Nori, umbre, rezoluție insuficientă, ambiguitate |

## Reguli

1. **Evaluare vizuală independentă**: evaluatorul examinează
   imaginea (compoziție true color sau false color), NU
   valoarea NDVI calculată. Dacă se etichetează pe baza
   pragului NDVI, modelul ar învăța doar să imite pragul.

2. **Sursa imaginilor**: Copernicus Browser, folosind
   compoziție true color (B04/B03/B02) sau false color
   (B08/B04/B03). Se notează data, compoziția folosită și
   parcela.

3. **Ambiguitate**: dacă evaluatorul nu poate decide, rândul
   rămâne neetichetat. Nu se forțează o etichetă 0 pentru
   a echilibra clasele.

4. **Review dublu**: exemplele ambigue sau la limită se
   revizuiesc de cel puțin două persoane din echipă.

5. **Notare**: câmpul `notes` din CSV se folosește pentru
   a documenta motivul unei decizii dificile.

## Procedura (17 octombrie)

1. Fiecare membru etichetează 15–20 observații.
2. Se compară etichetele pentru aceleași exemple.
3. Dezacordurile se discută și se notează în `notes`.
4. Etichetele finale se salvează în `data/labels.csv`.

## Format CSV

```
parcel_id,acquired_at,label,annotator,source,notes
```

- `parcel_id`: identificatorul parcelei (ex: `parcel_01`)
- `acquired_at`: data achiziției Sentinel-2 (ISO-8601)
- `label`: `1`, `0`, sau gol
- `annotator`: inițialele persoanei (ex: `CC`, `CO`, `OA`, `DM`)
- `source`: compoziția folosită (ex: `true_color`, `false_color`)
- `notes`: observații suplimentare

## Limitări

- Etichetele vizuale nu pot confirma tipul de cultură,
  tratamentele aplicate sau respectarea unui angajament
  agronomic complet.
- Numărul mic de etichete (60–80) limitează puterea
  statistică a oricărui model antrenat pe ele.
- Pseudo-etichetele (generate automat din NDVI > prag)
  NU sunt etichete independente și nu trebuie prezentate
  ca validare.
