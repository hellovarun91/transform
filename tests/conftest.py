import pytest
from fastapi.testclient import TestClient

from transform.config import Settings
from transform.db import Store
from transform.plan import load_plan


@pytest.fixture(scope="session")
def plan():
    return load_plan()


@pytest.fixture
def settings(tmp_path):
    return Settings(pin="1234", secret="test-secret", data_dir=str(tmp_path), vapid_private_key="",
                    vapid_public_key="", vapid_claims_email="mailto:test@example.com", tz="Asia/Kolkata", port=8000)


@pytest.fixture
def store():
    return Store(":memory:")


@pytest.fixture
def client(settings, store, plan):
    from transform.app import create_app

    app = create_app(settings, store=store, plan=plan, start_scheduler=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    r = client.post("/api/auth", json={"pin": "1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}
