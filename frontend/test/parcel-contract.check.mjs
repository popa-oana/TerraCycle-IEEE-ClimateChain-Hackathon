/**
 * frontend/test/parcel-contract.check.mjs — executes the real parcel validator
 * from src/lib/api.ts against a payload produced by the real backend.
 *
 * Plain Node, no test framework: it is run with
 *   node --experimental-strip-types frontend/test/parcel-contract.check.mjs <payload.json>
 * and exits non-zero when a check fails.
 */
import { readFileSync } from 'node:fs';
import { isParcel } from '../src/lib/api.ts';

const payloadPath = process.argv[2];
if (!payloadPath) {
  console.error('usage: node --experimental-strip-types parcel-contract.check.mjs <payload.json>');
  process.exit(2);
}

const failures = [];

function check(condition, message) {
  if (condition) {
    console.log(`  [ok]   ${message}`);
  } else {
    console.log(`  [FAIL] ${message}`);
    failures.push(message);
  }
}

const payload = JSON.parse(readFileSync(payloadPath, 'utf-8'));
const parcels = payload.parcels;

console.log('== parcel contract: the real backend payload ==');
check(Array.isArray(parcels) && parcels.length > 0, 'the payload contains a parcels array');
check(
  parcels.every((parcel) => isParcel(parcel)),
  'every real parcel is accepted by the frontend validator',
);
check(
  parcels.every((parcel) => typeof parcel.parcel_id === 'string' && parcel.parcel_id.length > 0),
  'parcel identifiers are preserved',
);
check(
  parcels.every(
    (parcel) =>
      parcel.latitude === undefined ||
      (typeof parcel.latitude === 'number' && Number.isFinite(parcel.latitude)),
  ),
  'no invalid coordinate is accepted',
);

console.log('== coordinate handling ==');
const withCoordinates = {
  ...parcels[0],
  latitude: 44.3302,
  longitude: 23.7949,
};
check(isParcel(withCoordinates), 'a parcel with valid coordinates is accepted');
check(
  isParcel(withCoordinates) && withCoordinates.latitude === 44.3302,
  'existing coordinates are preserved, not dropped or replaced',
);
check(
  isParcel({ ...parcels[0], latitude: 'north' }) === false,
  'a parcel with a non-numeric latitude is rejected',
);
check(
  isParcel({ ...parcels[0], longitude: Number.NaN }) === false,
  'a parcel with a NaN longitude is rejected',
);
check(
  isParcel({ ...parcels[0], latitude: null, longitude: null }),
  'a parcel with null coordinates is accepted as "no coordinates"',
);

console.log('== still required ==');
check(isParcel({ ...parcels[0], parcel_id: undefined }) === false, 'a missing parcel_id is rejected');
check(isParcel({ ...parcels[0], area_ha: 'many' }) === false, 'a non-numeric area_ha is rejected');
check(isParcel({ ...parcels[0], display_name: 5 }) === false, 'a non-string display_name is rejected');
check(isParcel({ ...parcels[0], geometry_url: undefined }) === false, 'a missing geometry_url is rejected');
check(isParcel(null) === false, 'a null parcel is rejected');
check(isParcel('parcel_01') === false, 'a non-object parcel is rejected');

console.log('== no invented values ==');
const serialised = JSON.stringify(parcels);
check(
  !/"(latitude|longitude)":\s*0(,|})/.test(serialised),
  'the backend payload contains no fabricated zero coordinates',
);

if (failures.length > 0) {
  console.error(`\n${failures.length} parcel contract check(s) failed`);
  process.exit(1);
}

console.log('\nall parcel contract checks passed');
