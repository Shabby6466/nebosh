import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { createSession, endSession, reportSessionEvent, WS_BASE_URL, type FrameEvalResult } from "../lib/api";
import { useCamera } from "../lib/useCamera";
import { useCandidateSession } from "../lib/candidateStore";
import Stepper from "../components/Stepper";
import { axiosMessage } from "./Register";

const CAPTURE_INTERVAL_MS = 2000;

interface LogEntry extends FrameEvalResult {
  at: string;
}

export default function Session() {
  const { candidateId: paramId } = useParams<{ candidateId: string }>();
  const { candidate } = useCandidateSession();
  const candidateId = paramId ?? candidate?.id;
  const { videoRef, start, captureFrame, ready } = useCamera();

  const [examCode, setExamCode] = useState("NEBOSH-IGC1");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "starting" | "active" | "ended">("idle");
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<FrameEvalResult | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    start();
    return () => {
      wsRef.current?.close();
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    };
  }, [start]);

  useEffect(() => {
    if (status !== "active" || !sessionId) return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        reportSessionEvent(sessionId, "tab_switched").catch(console.error);
        setLog((prev) => [{ violation: "tab_switched", at: new Date().toLocaleTimeString() } as any, ...prev].slice(0, 20));
      }
    };

    const handleBlur = () => {
      // Small timeout to prevent false positives when browser dialogs open (like camera permissions)
      setTimeout(() => {
        if (!document.hasFocus()) {
          reportSessionEvent(sessionId, "window_unfocused").catch(console.error);
          setLog((prev) => [{ violation: "window_unfocused", at: new Date().toLocaleTimeString() } as any, ...prev].slice(0, 20));
        }
      }, 500);
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("blur", handleBlur);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("blur", handleBlur);
    };
  }, [status, sessionId]);

  const beginSession = async () => {
    if (!candidateId) return;
    setStatus("starting");
    setError(null);
    try {
      const session = await createSession(candidateId, examCode);
      setSessionId(session.id);

      const ws = new WebSocket(`${WS_BASE_URL}/ws/v1/sessions/${session.id}`);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("active");
        intervalRef.current = window.setInterval(async () => {
          const blob = await captureFrame(480, 0.55);
          if (blob && ws.readyState === WebSocket.OPEN) {
            ws.send(await blob.arrayBuffer());
          }
        }, CAPTURE_INTERVAL_MS);
      };

      ws.onmessage = (evt) => {
        const result: FrameEvalResult = JSON.parse(evt.data);
        setLatest(result);
        if (result.violation) {
          setLog((prev) => [{ ...result, at: new Date().toLocaleTimeString() }, ...prev].slice(0, 20));
        }
      };

      ws.onerror = () => setError("Connection lost — frames are not being evaluated");
      ws.onclose = () => {
        if (intervalRef.current) window.clearInterval(intervalRef.current);
      };
    } catch (err) {
      setError(axiosMessage(err));
      setStatus("idle");
    }
  };

  const finishSession = async () => {
    if (!sessionId) return;
    wsRef.current?.close();
    if (intervalRef.current) window.clearInterval(intervalRef.current);
    await endSession(sessionId);
    setStatus("ended");
  };

  const live = status === "starting" || status === "active";

  if (!candidateId) {
    return <Navigate to="/" replace />;
  }
  if (candidate && candidate.kyc_status !== "verified") {
    return <Navigate to={`/kyc/${candidateId}`} replace />;
  }

  return (
    <div className="card wide">
      <Stepper current={3} />
      <h1>Exam Session</h1>

      <div className={live ? "session-live" : "form"}>
        <div className="camera-block">
          {/* Single persistent <video> across all statuses — remounting it would drop the
              already-attached getUserMedia stream and leave the preview black. */}
          <video ref={videoRef} className="video-preview" muted playsInline />
          {live && (
            <span className={`badge ${latest?.violation ? "badge-bad" : "badge-good"}`}>
              {status === "starting" ? "Connecting…" : latest?.violation ? latest.violation.replaceAll("_", " ") : "Monitoring"}
            </span>
          )}
        </div>

        {status === "idle" && (
          <>
            <label>
              Exam code
              <input value={examCode} onChange={(e) => setExamCode(e.target.value)} />
            </label>
            {error && <p className="error">{error}</p>}
            <button onClick={beginSession} disabled={!ready}>Start proctored session</button>
          </>
        )}

        {live && (
          <div className="status-panel">
            <ul className="kv">
              <li><span>Session</span><span>{sessionId}</span></li>
              <li><span>Persons detected</span><span>{latest?.person_count ?? "—"}</span></li>
              <li><span>Face match</span><span>{latest?.face_match === null || latest?.face_match === undefined ? "—" : latest.face_match ? "yes" : "no"}</span></li>
              <li><span>Similarity</span><span>{latest?.face_similarity?.toFixed(3) ?? "—"}</span></li>
              <li><span>Head yaw</span><span>{latest?.head_yaw != null ? `${latest.head_yaw}°` : "—"}</span></li>
              <li><span>Head pitch</span><span>{latest?.head_pitch != null ? `${latest.head_pitch}°` : "—"}</span></li>
              <li><span>Gaze X</span><span>{latest?.gaze_ratio_x != null ? latest.gaze_ratio_x.toFixed(3) : "—"}</span></li>
              <li><span>Gaze Y</span><span>{latest?.gaze_ratio_y != null ? latest.gaze_ratio_y.toFixed(3) : "—"}</span></li>
              <li><span>Processing</span><span>{latest?.processing_ms ? `${latest.processing_ms}ms` : "—"}</span></li>
            </ul>
            {error && <p className="error">{error}</p>}
            <button onClick={finishSession}>End session</button>

            <h3>Flag log</h3>
            {log.length === 0 ? (
              <p className="muted">No violations flagged yet.</p>
            ) : (
              <ul className="log">
                {log.map((entry, i) => (
                  <li key={i}>
                    <strong>{entry.at}</strong> — {entry.violation?.replaceAll("_", " ")}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {status === "ended" && (
        <div className="ended-panel">
          <p>Session ended. Thank you — your exam has been submitted for review.</p>
          <Link to="/">Back to home</Link>
        </div>
      )}
    </div>
  );
}
