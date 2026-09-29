from conftest import send_frames, start_session


def test_health_and_readiness(client):
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok", "storage": "ok"}}


def test_readiness_reports_failed_dependency(client, monkeypatch):
    import app.main as main

    def broken():
        raise RuntimeError("bucket gone")

    monkeypatch.setattr(main, "check_bucket", broken)
    ready = client.get("/health/ready")
    assert ready.status_code == 503
    assert ready.json()["status"] == "degraded" and ready.json()["checks"]["storage"] == "error"


def test_docs_disabled(client):
    for path in ("/docs", "/redoc", "/openapi.json", "/docs/login"):
        assert client.get(path).status_code == 404
    client.app.openapi()  # spec still generates for export


def test_docs_open_without_password(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_docs_enabled", True)
    monkeypatch.setattr(settings, "api_docs_password", None)
    assert "swagger-ui" in client.get("/docs").text
    assert client.get("/openapi.json").json()["info"]["title"] == "Proctoring API"


def test_docs_password_gate(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_docs_enabled", True)
    monkeypatch.setattr(settings, "api_docs_password", "s3cret")
    client.cookies.clear()

    r = client.get("/docs", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/docs/login?next=/docs"
    assert client.get("/openapi.json").status_code == 401
    assert 'type="password"' in client.get("/docs/login").text

    bad = client.post("/docs/login", data={"password": "nope", "next": "/redoc"}, follow_redirects=False)
    assert bad.status_code == 401 and "Wrong password" in bad.text

    ok = client.post("/docs/login", data={"password": "s3cret", "next": "https://evil.test"},
                     follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/docs"  # no open redirect
    assert "swagger-ui" in client.get("/docs").text
    assert client.get("/openapi.json").status_code == 200

    monkeypatch.setattr(settings, "api_docs_password", "rotated")
    assert client.get("/openapi.json").status_code == 401  # rotating the password logs everyone out
    client.cookies.clear()


def test_docs_login_rate_limited(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "api_docs_enabled", True)
    monkeypatch.setattr(settings, "api_docs_password", "s3cret")
    codes = [client.post("/docs/login", data={"password": "x"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    # even the right password is refused while locked out
    assert client.post("/docs/login", data={"password": "s3cret"}, follow_redirects=False).status_code == 429


def test_metrics_exposed(client, learner):
    _, cand, headers = learner
    s = start_session(client, cand, headers)
    send_frames(client, s["id"], headers, 1)
    text = client.get("/metrics").text
    assert 'frames_evaluated_total{mode="exam",violation="none"}' in text
    assert 'route="/api/v1/sessions/{session_id}/frame"' in text  # templated, no raw UUIDs
    assert s["id"] not in text


def test_admin_pagination(client, admin_headers, make_org, make_candidate):
    org = make_org()
    for _ in range(3):
        make_candidate(org)
    page1 = client.get("/api/v1/admin/candidates?limit=2", headers=admin_headers).json()
    page2 = client.get("/api/v1/admin/candidates?limit=2&offset=2", headers=admin_headers).json()
    assert len(page1) == 2 and page1[0]["id"] != page2[0]["id"]
    assert client.get("/api/v1/admin/candidates?limit=5000", headers=admin_headers).status_code == 422
    assert len(client.get("/api/v1/admin/organizations?limit=1", headers=admin_headers).json()) == 1
