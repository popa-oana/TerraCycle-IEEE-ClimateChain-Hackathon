from pydantic import BaseModel, Field


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


class ErrorResponse(BaseModel):
    error: dict[str, str]
