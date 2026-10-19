from fastapi import APIRouter

router = APIRouter(tags=["config"])


@router.get("/config")
def get_config():
    return {
        "chain_id": 11155111,
        "network_name": "sepolia",
        "contract_address": None,
        "abi_url": "/api/v1/config/abi",
        "abi_version": "2026-10-22-v1",
        "verifier_address": None,
        "app_url": "http://localhost:5173",
    }
