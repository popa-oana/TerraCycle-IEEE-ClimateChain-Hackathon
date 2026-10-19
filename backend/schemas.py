from pydantic import BaseModel, Field, model_validator


class HistoryItem(BaseModel):
    year: int = Field(ge=1990, le=2026)
    crop_id: str = Field(min_length=2, max_length=60)


class PlanRequest(BaseModel):
    parcel_id: str = Field(min_length=1, max_length=64)
    season_id: str = Field(min_length=1, max_length=64)
    crop_history: list[HistoryItem] = Field(min_length=1)
    treatments: list[str] = []
    requested_crop_id: str = Field(min_length=2, max_length=64)


class RotationCrop(BaseModel):
    year: int
    crop_id: str


class RotationOption(BaseModel):
    rotation_id: str
    crops: list[RotationCrop]
    score: float
    explanations: list[str]
    risks: list[str]


class PlanResponse(BaseModel):
    plan_id: str
    parcel_id: str
    season_id: str
    rotations: list[RotationOption]
    climate_source: str = "fixture"


class PrepareRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64)
    rotation_id: str = Field(min_length=1, max_length=64)
    beneficiary_address: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    verification_policy_id: str = Field(min_length=1, max_length=64)


class PrepareResponse(BaseModel):
    commitment_id: str
    plan_hash: str
    parcel_id: str
    season_id: str
    beneficiary_address: str
    settle_deadline: str
    snapshot_url: str
    state: str


class ConfigResponse(BaseModel):
    chain_id: int
    network_name: str
    contract_address: str | None = None
    abi_url: str
    abi_version: str
    verifier_address: str | None = None
    app_url: str | None = None


class ObservationsSummary(BaseModel):
    total_observations: int
    valid_observations: int
    vegetated_count: int
    vegetated_fraction: float


class DataProvenance(BaseModel):
    provider: str
    dataset: str
    bands: list[str]
    method: str


class TxHashes(BaseModel):
    register: str | None = None
    fund: str | None = None
    settle: str | None = None
    refund: str | None = None


class PassportResponse(BaseModel):
    commitment_id: str
    parcel_display_name: str
    region: str
    season_id: str
    practice_type: str
    plan_hash: str
    evidence_hash: str | None = None
    verdict: str | None = None
    contract_state: str | None = None
    contract_address: str | None = None
    chain_id: int | None = None
    observations_summary: ObservationsSummary | None = None
    data_provenance: DataProvenance | None = None
    tx_hashes: TxHashes | None = None
    limitations: list[str] = []


class Attestation(BaseModel):
    commitmentId: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    planHash: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    evidenceHash: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    verdict: int = Field(ge=0, le=2)
    validUntil: int = Field(gt=0)


class EvidenceDocument(BaseModel):
    commitment_id: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    evidence_id: str = Field(min_length=1, max_length=64)
    verdict: str = Field(pattern=r"^(conform|nonconform|inconclusive)$")
    verdict_code: int = Field(ge=0, le=2)
    reason_codes: list[str] = []
    model_version: str = Field(min_length=1, max_length=64)
    policy_version: str = Field(min_length=1, max_length=64)
    parcel_id: str
    season_id: str
    observations: ObservationsSummary | None = None
    data_provenance: DataProvenance | None = None
    valid_until: int = Field(gt=0)

    @model_validator(mode="after")
    def check_verdict_mapping(self):
        mapping = {"conform": 0, "nonconform": 1, "inconclusive": 2}
        expected = mapping.get(self.verdict)
        if expected is None or self.verdict_code != expected:
            raise ValueError(f"verdict '{self.verdict}' does not match verdict_code {self.verdict_code}")
        return self


class VerifyResponse(BaseModel):
    commitment_id: str
    evidence_id: str
    evidence_hash: str
    verdict: str
    verdict_code: int
    attestation: Attestation
    signature: str | None = None
    reason_codes: list[str] = []
    snapshot_url: str


class ErrorResponse(BaseModel):
    error: dict[str, str]
