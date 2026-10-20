from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Verdict

router = APIRouter(tags=["evidence"])


@router.get("/evidence/{evidence_id}/snapshot")
def get_evidence_snapshot(evidence_id: str, db: Session = Depends(get_db)):
    verdict = db.query(Verdict).filter(Verdict.evidence_id == evidence_id).first()
    if not verdict:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "EVIDENCE_NOT_FOUND", "message": f"Evidence '{evidence_id}' does not exist."}},
        )

    return Response(
        content=verdict.evidence_snapshot,
        media_type="application/octet-stream",
        headers={"X-Evidence-Hash": verdict.evidence_hash},
    )
