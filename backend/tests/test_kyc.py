import json

from conftest import deliver_webhooks, kyc, start_session, token_for


def test_kyc_verified_enables_sessions_and_sends_webhook(client, make_org, make_candidate, sink):
    org = make_org()
    cand = make_candidate(org)
    headers = token_for(client, org, cand["id"])

    resp = kyc(client, cand["id"], headers)
    assert resp.status_code == 200 and resp.json()["verified"]
    assert client.get(f"/api/v1/candidates/{cand['id']}", headers=org["headers"]).json()["kyc_status"] == "verified"
    start_session(client, cand, headers)

    assert deliver_webhooks(client) == 1
    body = json.loads(sink.requests[0].content)
    assert body["event"] == "kyc.completed" and body["data"]["verified"] is True


def test_kyc_rejected_blocks_sessions(client, make_org, make_candidate, kyc_stub):
    org = make_org()
    cand = make_candidate(org)
    headers = token_for(client, org, cand["id"])
    kyc_stub.verified = False

    resp = kyc(client, cand["id"], headers).json()
    assert resp["verified"] is False and resp["reason"] == "liveness_check_failed"
    blocked = client.post("/api/v1/sessions", json={"candidate_id": cand["id"], "exam_code": "X"}, headers=headers)
    assert blocked.status_code == 403


def test_no_webhook_when_org_has_none(client, make_org, make_candidate):
    org = make_org(webhook_url=None)
    cand = make_candidate(org)
    kyc(client, cand["id"], token_for(client, org, cand["id"]))
    assert deliver_webhooks(client) == 0
