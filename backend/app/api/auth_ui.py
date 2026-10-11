from json import load
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth-ui"])

CONFIG_PATH = Path(__file__).resolve().parents[3] / "web" / "config" / "rss-kit-auth-ui.json"


def _load_auth_ui_config() -> dict:
    # The RSS KIT UI contract is data-driven so auth copy/logo can change
    # without modifying the Android authentication engine.
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return load(handle)



@router.get("/ui-config")
def auth_ui_config():
    return _load_auth_ui_config()
