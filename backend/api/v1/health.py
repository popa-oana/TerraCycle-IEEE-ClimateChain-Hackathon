from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "DB_UNAVAILABLE",
                    "message": "Database is not reachable.",
                }
            },
        )
    return {"status": "ok", "database": "ok"}
