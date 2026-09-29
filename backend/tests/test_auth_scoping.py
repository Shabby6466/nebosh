"""Tenant isolation and token scoping — the guarantees partners rely on."""
from conftest import kyc, start_session, token_for


def test_api_key_required(client):
    assert client.post("/api/v1/candidates", json={}).status_code == 422  # missing header
    assert client.get("/api/v1/candidates/lookup?email=a@b.c", headers={"X-API-Key": "nope"}).status_code == 401


def test_revoked_key_rejected(client, make_org, admin_headers):
    org = make_org()
    client.post(f"/api/v1/admin/organizations/{org['id']}/revoke", headers=admin_headers)
    assert client.get("/api/v1/candidates/lookup?email=a@b.c", headers=org["headers"]).status_code == 401


def test_email_unique_per_org_case_insensitive(client, make_org, make_candidate):
    a, b = make_org(), make_org()
    cand = make_candidate(a, "Learner@Mail.com")
    assert cand["email"] == "learner@mail.com"
    dup = client.post("/api/v1/candidates", json={"full_name": "x", "email": "LEARNER@mail.com",
                                                  "cnic_or_passport_no": "1"}, headers=a["headers"])
    assert dup.status_code == 409
    make_candidate(b, "learner@mail.com")  # other org: allowed
    found = client.get("/api/v1/candidates/lookup", params={"email": "LEARNER@MAIL.COM"}, headers=a["headers"])
    assert found.json()["id"] == cand["id"]


def test_org_cannot_touch_other_orgs_data(client, learner, make_org):
    org, cand, headers = learner
    other = make_org()
    session = start_session(client, cand, headers)
    assert client.post("/api/v1/auth/token", json={"candidate_id": cand["id"]}, headers=other["headers"]).status_code == 404
    assert client.get(f"/api/v1/candidates/{cand['id']}", headers=other["headers"]).status_code == 404
    assert client.get(f"/api/v1/candidates/{cand['id']}/sessions", headers=other["headers"]).status_code == 404
    assert client.get(f"/api/v1/sessions/{session['id']}/report", headers=other["headers"]).status_code == 404
    assert client.post(f"/api/v1/sessions/{session['id']}/terminate", headers=other["headers"]).status_code == 404
    assert client.get(f"/api/v1/sessions/{session['id']}/report", headers=org["headers"]).status_code == 200


def test_session_token_scoped_to_its_candidate(client, learner, make_candidate):
    org, cand, headers = learner
    other = make_candidate(org)
    other_headers = token_for(client, org, other["id"])
    session = start_session(client, cand, headers)
    # Another learner's token can't KYC, start sessions, or send frames for this learner
    assert kyc(client, cand["id"], other_headers).status_code == 403
    assert client.post("/api/v1/sessions", json={"candidate_id": cand["id"], "exam_code": "X"},
                       headers=other_headers).status_code == 403
    assert client.post(f"/api/v1/sessions/{session['id']}/end", headers=other_headers).status_code == 403


def test_token_lifetime_capped(client, learner):
    org, cand, _ = learner
    resp = client.post("/api/v1/auth/token", json={"candidate_id": cand["id"], "expires_minutes": 100_000},
                       headers=org["headers"])
    assert resp.status_code == 422


def test_admin_token_not_accepted_as_session_token(client, learner, admin_headers):
    _, cand, _ = learner
    assert kyc(client, cand["id"], admin_headers).status_code == 403


def test_session_token_not_accepted_on_admin_routes(client, learner):
    _, _, headers = learner
    assert client.get("/api/v1/admin/candidates", headers=headers).status_code == 403


def test_admin_login_throttled_after_failures(client, admin_headers):
    bad = {"email": "admin@example.com", "password": "wrong"}
    codes = [client.post("/api/v1/auth/admin/login", json=bad).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    # the right password is refused too while locked out
    good = client.post("/api/v1/auth/admin/login", json={"email": "admin@example.com", "password": "pw"})
    assert good.status_code == 429


def test_api_key_rate_limit(client, make_org, monkeypatch):
    from app.core.config import settings

    org = make_org()
    monkeypatch.setattr(settings, "api_key_rate_limit_per_minute", 3)
    codes = [client.get("/api/v1/candidates/lookup?email=x@y.z", headers=org["headers"]).status_code for _ in range(4)]
    assert codes == [404, 404, 404, 429]
