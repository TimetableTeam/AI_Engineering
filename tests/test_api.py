"""FastAPI endpoint tests (in-process TestClient, fresh code)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["solver"]["sections"] == 12


def test_term_readiness_endpoint():
    response = client.get("/terms/1/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["term_id"] == 1
    assert body["ready"] is True
    assert body["errors"] == []


def test_solve_endpoint():
    response = client.post("/solve", json={"term_id": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert body["summary"]["solver_sessions"] == 12
    assert body["summary"]["scheduled"] == 12
    assert body["summary"]["unscheduled"] == 0


def test_solve_unknown_term_returns_422():
    response = client.post("/solve", json={"term_id": 88})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["ready"] is False
    assert detail["errors"] == [{"code": "TERM_NOT_FOUND", "term_id": 88}]


def test_solve_returns_422_when_term_not_ready(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(
        main_module,
        "validate_term_readiness",
        lambda term_id: {
            "ready": False,
            "errors": [
                {
                    "code": "MISSING_PRACTICAL_ENROLLMENT",
                    "registration_id": 15,
                    "student_id": 8,
                    "course_id": 2,
                }
            ],
        },
    )
    response = client.post("/solve", json={"term_id": 1})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["ready"] is False
    assert detail["errors"][0]["code"] == "MISSING_PRACTICAL_ENROLLMENT"


def test_validate_proposal_endpoint():
    response = client.post(
        "/validate-proposal",
        json={
            "section_id": 2,
            "instructor_id": 12,
            "room_id": 3,
            "slot_id": 3,
            "event_date": "2027-09-25",
        },
    )
    assert response.status_code == 200
    assert response.json()["primary_result"] == "FEASIBLE"
