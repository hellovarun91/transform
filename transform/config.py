from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    pin: str
    secret: str
    data_dir: str
    vapid_private_key: str
    vapid_public_key: str
    vapid_claims_email: str
    tz: str = "Asia/Kolkata"
    port: int = 8000

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "transform.db")


def load_settings() -> Settings:
    data_dir = os.environ.get("TRANSFORM_DATA_DIR") or ("/data" if os.path.isdir("/data") else "./data")
    os.makedirs(data_dir, exist_ok=True)
    pin = os.environ.get("TRANSFORM_PIN", "")
    secret = os.environ.get("TRANSFORM_SECRET", "")
    if not pin or pin == "0000":
        raise RuntimeError("TRANSFORM_PIN must be set (and not 0000)")
    if not secret or secret == "change-me" or len(secret) < 16:
        raise RuntimeError("TRANSFORM_SECRET must be set to a random string of at least 16 characters")
    return Settings(
        pin=pin,
        secret=secret,
        data_dir=data_dir,
        vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY", ""),
        vapid_public_key=os.environ.get("VAPID_PUBLIC_KEY", ""),
        vapid_claims_email=os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@example.com"),
        tz=os.environ.get("TZ", "Asia/Kolkata"),
        port=int(os.environ.get("PORT", "8000")),
    )
