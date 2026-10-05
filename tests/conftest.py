import pytest
from fastapi.testclient import TestClient

from transform.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        pin="1234",
        secret="test-secret",
        data_dir=str(tmp_path),
        vapid_private_key="",
        vapid_public_key="",
        vapid_claims_email="mailto:test@example.com",
        tz="Asia/Kolkata",
        port=8000,
    )


@pytest.fixture
def client(settings):
    from transform.app import create_app

    app = create_app(settings, start_scheduler=False)
    with TestClient(app) as c:
        yield c
