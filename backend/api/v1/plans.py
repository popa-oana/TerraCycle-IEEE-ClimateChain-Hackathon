from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Plan
from backend.rules.rotation import compute_plan_id, generate_rotations
from backend.schemas import PlanRequest, PlanResponse

router = APIRouter(tags=["plans"])


@router.post("/plans", response_model=PlanResponse)
def create_plan(request: PlanRequest, db: Session = Depends(get_db)):
    history_years = [h.year for h in request.crop_history]
    if len(history_years) != len(set(history_years)):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "Duplicate years in crop history."}},
        )

    previous_crop = request.crop_history[-1].crop_id
    rotations = generate_rotations(request.requested_crop_id, previous_crop)

    req_dict = request.model_dump()
    plan_id = compute_plan_id(req_dict)

    existing = db.get(Plan, plan_id)
    if existing:
        return PlanResponse(
            plan_id=existing.plan_id,
            parcel_id=existing.parcel_id,
            season_id=existing.season_id,
            rotations=existing.rotations,
        )

    plan = Plan(
        plan_id=plan_id,
        parcel_id=request.parcel_id,
        season_id=request.season_id,
        crop_history=[h.model_dump() for h in request.crop_history],
        treatments=request.treatments,
        requested_crop_id=request.requested_crop_id,
        rotations=[r for r in rotations],
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return PlanResponse(
        plan_id=plan.plan_id,
        parcel_id=plan.parcel_id,
        season_id=plan.season_id,
        rotations=plan.rotations,
    )
