/**
 * Read-only client for the verified demonstration proof.
 *
 * Contract source: data/demo/latest_proof.json (schema "demo-proof-v1"),
 * produced by contracts/smoke_test_real_evidence.py and served by
 * scripts/serve_demo.py at GET /api/proof.
 *
 * The client is strictly read-only: it never sends a transaction and never
 * substitutes placeholder evidence. A missing, malformed or unreachable
 * document is reported as an error so the interface can show the real state.
 */
import { ApiError, readErrorPayload, readJsonBody } from './api';
import type {
  ProofBlockchain,
  ProofDocument,
  ProofEvent,
  ProofEvidence,
  ProofOnChain,
  ProofParcel,
  ProofRun,
  ProofVerification,
} from './types';

const PROOF_PATH = '/api/proof';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function buildProofUrl(): string {
  const configured = import.meta.env.VITE_PROOF_BASE_URL;

  // Without an explicit base URL the proof is requested from the same origin:
  // the Vite dev/preview server proxies /api/proof to the proof server.
  if (typeof configured !== 'string' || configured.trim() === '') {
    return PROOF_PATH;
  }

  return `${configured.trim().replace(/\/+$/, '')}${PROOF_PATH}`;
}

function requireSection(payload: Record<string, unknown>, key: string): Record<string, unknown> {
  const section = payload[key];
  if (!isRecord(section)) {
    throw new ApiError('INVALID_RESPONSE', `The proof document is missing the "${key}" section.`);
  }
  return section;
}

function requireString(source: Record<string, unknown>, key: string, section: string): string {
  const value = source[key];
  if (typeof value !== 'string' || value.length === 0) {
    throw new ApiError('INVALID_RESPONSE', `The proof document is missing "${key}" in ${section}.`);
  }
  return value;
}

function requireNumber(source: Record<string, unknown>, key: string, section: string): number {
  const value = source[key];
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ApiError('INVALID_RESPONSE', `The proof document has an invalid "${key}" in ${section}.`);
  }
  return value;
}

function optionalNumber(
  source: Record<string, unknown>,
  key: string,
  section: string,
): number | null {
  const value = source[key];
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ApiError('INVALID_RESPONSE', `The proof document has an invalid "${key}" in ${section}.`);
  }
  return value;
}

function requireBoolean(source: Record<string, unknown>, key: string, section: string): boolean {
  const value = source[key];
  if (typeof value !== 'boolean') {
    throw new ApiError('INVALID_RESPONSE', `The proof document has an invalid "${key}" in ${section}.`);
  }
  return value;
}

function requireStringArray(
  source: Record<string, unknown>,
  key: string,
  section: string,
): string[] {
  const value = source[key];
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new ApiError('INVALID_RESPONSE', `The proof document has an invalid "${key}" in ${section}.`);
  }
  return value as string[];
}

function parseRun(payload: Record<string, unknown>): ProofRun {
  const section = requireSection(payload, 'run');
  return {
    status: requireString(section, 'status', 'run'),
    local_only: requireBoolean(section, 'local_only', 'run'),
    network: requireString(section, 'network', 'run'),
    chain_id: requireNumber(section, 'chain_id', 'run'),
    rpc_url: requireString(section, 'rpc_url', 'run'),
  };
}

function parseParcel(payload: Record<string, unknown>): ProofParcel {
  const section = requireSection(payload, 'parcel');
  return {
    parcel_id: requireString(section, 'parcel_id', 'parcel'),
    season_id: requireString(section, 'season_id', 'parcel'),
    satellite_provider: requireString(section, 'satellite_provider', 'parcel'),
    satellite_dataset: requireString(section, 'satellite_dataset', 'parcel'),
    satellite_method: requireString(section, 'satellite_method', 'parcel'),
    source_csv: requireString(section, 'source_csv', 'parcel'),
    observations_total: requireNumber(section, 'observations_total', 'parcel'),
    observations_valid: requireNumber(section, 'observations_valid', 'parcel'),
    source_rows: requireNumber(section, 'source_rows', 'parcel'),
  };
}

function parseVerification(payload: Record<string, unknown>): ProofVerification {
  const section = requireSection(payload, 'verification');
  return {
    policy_version: requireString(section, 'policy_version', 'verification'),
    policy_type: requireString(section, 'policy_type', 'verification'),
    window_start: requireString(section, 'window_start', 'verification'),
    window_end: requireString(section, 'window_end', 'verification'),
    ndvi_threshold: requireNumber(section, 'ndvi_threshold', 'verification'),
    required_fraction: requireNumber(section, 'required_fraction', 'verification'),
    min_observations: requireNumber(section, 'min_observations', 'verification'),
    verdict: requireString(section, 'verdict', 'verification'),
    verdict_code: requireNumber(section, 'verdict_code', 'verification'),
    reason_code: requireString(section, 'reason_code', 'verification'),
    reason: requireString(section, 'reason', 'verification'),
    evidence_quality: requireString(section, 'evidence_quality', 'verification'),
    temporal_coverage: optionalNumber(section, 'temporal_coverage', 'verification'),
    evidence_quality_warnings: requireStringArray(
      section,
      'evidence_quality_warnings',
      'verification',
    ),
  };
}

function parseEvidence(payload: Record<string, unknown>): ProofEvidence {
  const section = requireSection(payload, 'evidence');
  return {
    schema_version: requireString(section, 'schema_version', 'evidence'),
    evidence_id: requireString(section, 'evidence_id', 'evidence'),
    commitment_id: requireString(section, 'commitment_id', 'evidence'),
    plan_id: requireString(section, 'plan_id', 'evidence'),
    plan_hash: requireString(section, 'plan_hash', 'evidence'),
    evidence_hash: requireString(section, 'evidence_hash', 'evidence'),
    evidence_hash_recomputed: requireString(section, 'evidence_hash_recomputed', 'evidence'),
    canonical_bytes_length: requireNumber(section, 'canonical_bytes_length', 'evidence'),
  };
}

function parseEvent(section: Record<string, unknown>): ProofEvent {
  return {
    name: requireString(section, 'name', 'blockchain.event'),
    commitment_id: requireString(section, 'commitment_id', 'blockchain.event'),
    evidence_hash: requireString(section, 'evidence_hash', 'blockchain.event'),
    verdict_code: requireNumber(section, 'verdict_code', 'blockchain.event'),
    recorder: requireString(section, 'recorder', 'blockchain.event'),
    recorded_at: requireNumber(section, 'recorded_at', 'blockchain.event'),
  };
}

function parseOnChain(section: Record<string, unknown>): ProofOnChain {
  return {
    commitment_id: requireString(section, 'commitment_id', 'blockchain.on_chain'),
    evidence_hash: requireString(section, 'evidence_hash', 'blockchain.on_chain'),
    verdict_code: requireNumber(section, 'verdict_code', 'blockchain.on_chain'),
    read_back_match: requireBoolean(section, 'read_back_match', 'blockchain.on_chain'),
  };
}

function parseBlockchain(payload: Record<string, unknown>): ProofBlockchain {
  const section = requireSection(payload, 'blockchain');
  const event = requireSection(section, 'event');
  const onChain = requireSection(section, 'on_chain');
  return {
    network: requireString(section, 'network', 'blockchain'),
    chain_id: requireNumber(section, 'chain_id', 'blockchain'),
    registry_address: requireString(section, 'registry_address', 'blockchain'),
    deploy_tx_hash: requireString(section, 'deploy_tx_hash', 'blockchain'),
    tx_hash: requireString(section, 'tx_hash', 'blockchain'),
    receipt_status: requireNumber(section, 'receipt_status', 'blockchain'),
    event: parseEvent(event),
    on_chain: parseOnChain(onChain),
  };
}

function parseIntegrity(payload: Record<string, unknown>): Record<string, boolean> {
  const section = requireSection(payload, 'integrity');
  const entries = Object.entries(section);
  if (entries.length === 0 || !entries.every(([, value]) => typeof value === 'boolean')) {
    throw new ApiError('INVALID_RESPONSE', 'The proof document has an invalid "integrity" section.');
  }
  return Object.fromEntries(entries) as Record<string, boolean>;
}

export function parseProof(payload: unknown): ProofDocument {
  if (!isRecord(payload)) {
    throw new ApiError('INVALID_RESPONSE', 'The proof document is not a JSON object.');
  }

  return {
    schema_version: requireString(payload, 'schema_version', 'proof'),
    generated_at: requireString(payload, 'generated_at', 'proof'),
    run: parseRun(payload),
    parcel: parseParcel(payload),
    verification: parseVerification(payload),
    evidence: parseEvidence(payload),
    blockchain: parseBlockchain(payload),
    integrity: parseIntegrity(payload),
    limitations: requireStringArray(payload, 'limitations', 'proof'),
  };
}

export async function getProof(): Promise<ProofDocument> {
  const url = buildProofUrl();

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
  } catch {
    throw new ApiError(
      'NETWORK_ERROR',
      'Could not reach the proof server. Start it with "python scripts/serve_demo.py" and reload.',
    );
  }

  const body = await readJsonBody(response);

  if (!response.ok) {
    const { code, message } = readErrorPayload(
      body.ok ? body.value : undefined,
      response.status,
    );
    if (code === 'HTTP_ERROR') {
      // The proof server answered without a structured error body.
      throw new ApiError(
        code,
        `The proof server did not return a proof document (HTTP ${response.status}).`,
        response.status,
      );
    }
    throw new ApiError(code, message, response.status);
  }

  if (!body.ok) {
    throw new ApiError(
      'INVALID_RESPONSE',
      'The proof server returned an empty or invalid JSON response.',
    );
  }

  return parseProof(body.value);
}
