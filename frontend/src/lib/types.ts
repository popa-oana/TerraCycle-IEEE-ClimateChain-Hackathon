/**
 * Parcel types for GET /api/v1/parcels.
 * Contract source: backend/api/v1/parcels.py and data/fixtures/demo.json.
 * The endpoint returns the fixture records unchanged.
 */

export interface Parcel {
  parcel_id: string;
  parcel_id_bytes32: string;
  display_name: string;
  region: string;
  area_ha: number;
  latitude: number;
  longitude: number;
  geometry_url: string;
  data_origin: string;
}

export interface ParcelsResponse {
  parcels: Parcel[];
}
