import type {
  Parcel,
  ParcelsResponse,
  PlanRequest,
  PlanResponse,
  RotationOption,
} from './types';

const API_PREFIX = '/api/v1';

export class ApiError extends Error {
  readonly code: string;
  readonly status?: number;

  constructor(code: string, message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function buildApiUrl(path: string): string {
  const configured = import.meta.env.VITE_API_BASE_URL;

  if (typeof configured !== 'string' || configured.trim() === '') {
    throw new ApiError(
      'CONFIG_ERROR',
      'VITE_API_BASE_URL is not configured. Set it to the backend origin, for example http://localhost:8000.',
    );
  }

  const origin = configured
    .trim()
    .replace(/\/+$/, '')
    .replace(/\/api\/v1$/, '');

  return `${origin}${API_PREFIX}${path}`;
}

export function readErrorObject(value: unknown): { code: string; message: string } | null {
  if (!isRecord(value)) {
    return null;
  }
  if (typeof value.code !== 'string' || typeof value.message !== 'string') {
    return null;
  }
  return { code: value.code, message: value.message };
}

export function readErrorPayload(payload: unknown, status: number): { code: string; message: string } {
  if (isRecord(payload)) {
    const direct = readErrorObject(payload.error);
    if (direct) {
      return direct;
    }

    if (isRecord(payload.detail)) {
      const nested = readErrorObject(payload.detail.error);
      if (nested) {
        return nested;
      }
      if (typeof payload.detail.message === 'string') {
        return {
          code:
            typeof payload.detail.code === 'string' ? payload.detail.code : 'HTTP_ERROR',
          message: payload.detail.message,
        };
      }
    }

    if (Array.isArray(payload.detail)) {
      const first = payload.detail[0];
      return {
        code: 'VALIDATION_ERROR',
        message:
          isRecord(first) && typeof first.msg === 'string'
            ? first.msg
            : 'The request failed validation.',
      };
    }
  }

  return {
    code: 'HTTP_ERROR',
    message: `The API request failed with status ${status}.`,
  };
}

export async function readJsonBody(
  response: Response,
): Promise<{ ok: true; value: unknown } | { ok: false }> {
  try {
    const text = await response.text();
    if (text.trim() === '') {
      return { ok: false };
    }
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false };
  }
}

/**
 * A parcel may or may not carry coordinates. When they are present they must
 * be finite numbers; when they are absent the parcel is still valid, because
 * the backend does not guarantee a position for every parcel.
 */
function hasOptionalNumber(value: unknown): boolean {
  return (
    value === undefined ||
    value === null ||
    (typeof value === 'number' && Number.isFinite(value))
  );
}

export function isParcel(value: unknown): value is Parcel {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.parcel_id === 'string' &&
    typeof value.parcel_id_bytes32 === 'string' &&
    typeof value.display_name === 'string' &&
    typeof value.region === 'string' &&
    typeof value.area_ha === 'number' &&
    Number.isFinite(value.area_ha) &&
    hasOptionalNumber(value.latitude) &&
    hasOptionalNumber(value.longitude) &&
    typeof value.geometry_url === 'string' &&
    typeof value.data_origin === 'string'
  );
}

function parseParcelsResponse(payload: unknown, status: number): ParcelsResponse {
  if (!isRecord(payload) || !Array.isArray(payload.parcels)) {
    throw new ApiError(
      'INVALID_RESPONSE',
      'The API response does not contain a parcels array.',
      status,
    );
  }

  const parcels = payload.parcels;
  if (!parcels.every(isParcel)) {
    throw new ApiError(
      'INVALID_RESPONSE',
      'The API returned a parcel with an unexpected structure.',
      status,
    );
  }

  return { parcels };
}

export async function getParcels(): Promise<ParcelsResponse> {
  const url = buildApiUrl('/parcels');

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
  } catch {
    throw new ApiError(
      'NETWORK_ERROR',
      'Could not reach the API. Check that the backend is running and that CORS allows this origin.',
    );
  }

  const body = await readJsonBody(response);

  if (!response.ok) {
    const { code, message } = readErrorPayload(
      body.ok ? body.value : undefined,
      response.status,
    );
    throw new ApiError(code, message, response.status);
  }

  if (!body.ok) {
    throw new ApiError(
      'INVALID_RESPONSE',
      'The API returned an empty or invalid JSON response.',
      response.status,
    );
  }

  return parseParcelsResponse(body.value, response.status);
}

function isRotationCrop(value: unknown): value is { year: number; crop_id: string } {
  if (!isRecord(value)) {
    return false;
  }
  return typeof value.year === 'number' && Number.isFinite(value.year) && typeof value.crop_id === 'string';
}

function isRotationOption(value: unknown): value is RotationOption {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.rotation_id === 'string' &&
    Array.isArray(value.crops) &&
    value.crops.every(isRotationCrop) &&
    typeof value.score === 'number' &&
    Number.isFinite(value.score) &&
    Array.isArray(value.explanations) &&
    value.explanations.every((item) => typeof item === 'string') &&
    Array.isArray(value.risks) &&
    value.risks.every((item) => typeof item === 'string')
  );
}

function isPlanResponse(value: unknown): value is PlanResponse {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.plan_id === 'string' &&
    typeof value.parcel_id === 'string' &&
    typeof value.season_id === 'string' &&
    Array.isArray(value.rotations) &&
    value.rotations.every(isRotationOption) &&
    typeof value.climate_source === 'string'
  );
}

export async function createPlan(request: PlanRequest): Promise<PlanResponse> {
  const url = buildApiUrl('/plans');

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
  } catch {
    throw new ApiError(
      'NETWORK_ERROR',
      'Could not reach the API. Check that the backend is running and that CORS allows this origin.',
    );
  }

  const body = await readJsonBody(response);

  if (!response.ok) {
    const { code, message } = readErrorPayload(
      body.ok ? body.value : undefined,
      response.status,
    );
    throw new ApiError(code, message, response.status);
  }

  if (!body.ok) {
    throw new ApiError(
      'INVALID_RESPONSE',
      'The API returned an empty or invalid JSON response.',
      response.status,
    );
  }

  if (!isPlanResponse(body.value)) {
    throw new ApiError(
      'INVALID_RESPONSE',
      'The API returned a plan response with an unexpected structure.',
      response.status,
    );
  }

  return body.value;
}
