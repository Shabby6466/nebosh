import { useEffect, useRef, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { createSession, endSession, reportSessionEvent, WS_BASE_URL, type FrameEvalResult } from "../lib/api";
import { useCamera } from "../lib/useCamera";
import { useCandidateSession } from "../lib/candidateStore";
import Stepper from "../components/Stepper";
import CameraView from "../components/CameraView";
import MetricsPanel from "../components/MetricsPanel";
import FlagLog, { type LogEntry } from "../components/FlagLog";
import SessionIdleForm from "../components/SessionIdleForm";
import SessionEndedPanel from "../components/SessionEndedPanel";
import { axiosMessage } from "./Register";

const CAPTURE_INTERVAL_MS = 2000;

export default function Session() {
  const { candidateId: paramId } = useParams<{ candidateId: string }>();
  const { candidate } = useCandidateSession();
  const candidateId = paramId ?? candidate?.id;
  const { videoRef, start, captureFrame, ready, error: cameraError } = useCamera();

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
        setLog((prev) => [{ violation: "tab_switched", at: new Date().toLocaleTimeString() }, ...prev].slice(0, 20));
      }
    };

    const handleBlur = () => {
      // Small timeout to prevent false positives when browser dialogs open (like camera permissions)
      setTimeout(() => {
        if (!document.hasFocus()) {
          reportSessionEvent(sessionId, "window_unfocused").catch(console.error);
          setLog((prev) => [{ violation: "window_unfocused", at: new Date().toLocaleTimeString() }, ...prev].slice(0, 20));
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
        <CameraView
          videoRef={videoRef}
          showBadge={live}
          status={status}
          violation={latest?.violation}
          cameraError={cameraError}
        />

        {status === "idle" && (
          <SessionIdleForm
            examCode={examCode}
            onExamCodeChange={setExamCode}
            onBeginSession={beginSession}
            ready={ready}
            error={error}
          />
        )}

        {live && (
          <div>
            <MetricsPanel
              sessionId={sessionId}
              latest={latest}
              error={error}
              onFinishSession={finishSession}
            />
            <FlagLog log={log} />
          </div>
        )}
      </div>

      {status === "ended" && <SessionEndedPanel />}
    </div>
  );
}

