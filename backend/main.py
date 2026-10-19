from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1 import config, health
from backend.config import get_settings

settings = get_settings()

app = FastAPI(title="TerraCycle Proof API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(config.router, prefix="/api/v1")
