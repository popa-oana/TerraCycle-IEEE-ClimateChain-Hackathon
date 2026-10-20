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

/**
 * Plan types for POST /api/v1/plans.
 * Contract source: backend/schemas.py and backend/api/v1/plans.py.
 */

export interface HistoryItem {
  year: number;
  crop_id: string;
}

export interface PlanRequest {
  parcel_id: string;
  season_id: string;
  crop_history: HistoryItem[];
  treatments?: string[];
  requested_crop_id: string;
}

export interface RotationCrop {
  year: number;
  crop_id: string;
}

export interface RotationOption {
  rotation_id: string;
  crops: RotationCrop[];
  score: number;
  explanations: string[];
  risks: string[];
}

export interface PlanResponse {
  plan_id: string;
  parcel_id: string;
  season_id: string;
  rotations: RotationOption[];
  climate_source: string;
}
