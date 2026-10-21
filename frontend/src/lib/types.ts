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

/**
 * Proof types for the verified demonstration document.
 * Contract source: data/demo/latest_proof.json (schema "demo-proof-v1"),
 * produced by contracts/smoke_test_real_evidence.py and served by
 * scripts/serve_demo.py at GET /api/proof.
 */

export interface ProofRun {
  status: string;
  local_only: boolean;
  network: string;
  chain_id: number;
  rpc_url: string;
}

export interface ProofParcel {
  parcel_id: string;
  season_id: string;
  satellite_provider: string;
  satellite_dataset: string;
  satellite_method: string;
  source_csv: string;
  observations_total: number;
  observations_valid: number;
  source_rows: number;
}

export interface ProofVerification {
  policy_version: string;
  policy_type: string;
  window_start: string;
  window_end: string;
  ndvi_threshold: number;
  required_fraction: number;
  min_observations: number;
  verdict: string;
  verdict_code: number;
  reason_code: string;
  reason: string;
  evidence_quality: string;
  temporal_coverage: number | null;
  evidence_quality_warnings: string[];
}

export interface ProofEvidence {
  schema_version: string;
  evidence_id: string;
  commitment_id: string;
  plan_id: string;
  plan_hash: string;
  evidence_hash: string;
  evidence_hash_recomputed: string;
  canonical_bytes_length: number;
}

export interface ProofEvent {
  name: string;
  commitment_id: string;
  evidence_hash: string;
  verdict_code: number;
  recorder: string;
  recorded_at: number;
}

export interface ProofOnChain {
  commitment_id: string;
  evidence_hash: string;
  verdict_code: number;
  read_back_match: boolean;
}

export interface ProofBlockchain {
  network: string;
  chain_id: number;
  registry_address: string;
  deploy_tx_hash: string;
  tx_hash: string;
  receipt_status: number;
  event: ProofEvent;
  on_chain: ProofOnChain;
}

export interface ProofDocument {
  schema_version: string;
  generated_at: string;
  run: ProofRun;
  parcel: ProofParcel;
  verification: ProofVerification;
  evidence: ProofEvidence;
  blockchain: ProofBlockchain;
  integrity: Record<string, boolean>;
  limitations: string[];
}
