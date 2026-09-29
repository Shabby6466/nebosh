"""Frame evaluation pipeline: debounce, interview mode, client events, WS."""
import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import JPEG, send_frames, start_session


def _report(client, org, session_id):
    return client.get(f"/api/v1/sessions/{session_id}/report", headers=org["headers"]).json()


def test_clean_frames_record_no_violations(client, learner):
    org, cand, headers = learner
    s = start_session(client, cand, headers)
    assert send_frames(client, s["id"], headers, 3)["violation"] is None
    rep = _report(client, org, s["id"])
    assert rep["frames_evaluated"] == 3 and rep["violations"] == []


def test_violation_debounced_across_consecutive_frames(client, learner, frame_stub):
    org, cand, headers = learner
    s = start_session(client, cand, headers)
    frame_stub.violation = "multiple_people"
    send_frames(client, s["id"], headers, 1)
    assert _report(client, org, s["id"])["violation_counts"] == {}  # 1 frame: below debounce
    send_frames(client, s["id"], headers, 2)
    assert _report(client, org, s["id"])["violation_counts"] == {"multiple_people": 2}


def test_clean_frame_resets_streak(client, learner, frame_stub):
    org, cand, headers = learner
    s = start_session(client, cand, headers)
    for v in ("face_mismatch", None, "face_mismatch", None):
        frame_stub.violation = v
        send_frames(client, s["id"], headers, 1)
    assert _report(client, org, s["id"])["violation_counts"] == {}


def test_interview_mode_never_flags_looking_away(client, learner, frame_stub):
    org, cand, headers = learner
    exam = start_session(client, cand, headers, mode="exam")
    viva = start_session(client, cand, headers, mode="interview")
    frame_stub.violation = "looking_away"
    assert send_frames(client, exam["id"], headers, 2)["violation"] == "looking_away"
    assert send_frames(client, viva["id"], headers, 2)["violation"] is None
    assert frame_stub.flags == [True, True, False, False]
    assert _report(client, org, viva["id"])["violation_counts"] == {}


def test_client_events_validated_and_recorded(client, learner):
    org, cand, headers = learner
    s = start_session(client, cand, headers)
    url = f"/api/v1/sessions/{s['id']}/events"
    assert client.post(url, json={"type": "rm -rf"}, headers=headers).status_code == 422
    assert client.post(url, json={"type": "tab_switched", "confidence": 2}, headers=headers).status_code == 422
    assert client.post(url, json={"type": "tab_switched"}, headers=headers).status_code == 200
    v = _report(client, org, s["id"])["violations"][0]
    assert v["type"] == "tab_switched" and v["snapshot_url"] is None


def test_frames_rejected_after_session_end(client, learner):
    _, cand, headers = learner
    s = start_session(client, cand, headers)
    client.post(f"/api/v1/sessions/{s['id']}/end", headers=headers)
    resp = client.post(f"/api/v1/sessions/{s['id']}/frame", files={"frame": ("f.jpg", JPEG, "image/jpeg")},
                       headers=headers)
    assert resp.status_code == 404


def test_websocket_evaluates_then_closes_after_end(client, learner):
    _, cand, headers = learner
    s = start_session(client, cand, headers)
    token = headers["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/v1/sessions/{s['id']}?token={token}") as ws:
        ws.send_bytes(JPEG)
        assert ws.receive_json()["person_count"] == 1
        client.post(f"/api/v1/sessions/{s['id']}/end", headers=headers)
        ws.send_bytes(JPEG)
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4410


def test_websocket_rejects_bad_token(client, learner):
    _, cand, headers = learner
    s = start_session(client, cand, headers)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/v1/sessions/{s['id']}?token=garbage") as ws:
            ws.receive_json()
    assert exc.value.code == 4401
