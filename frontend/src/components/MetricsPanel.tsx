import type { FrameEvalResult } from "../lib/api";

interface MetricsPanelProps {
  sessionId: string | null;
  latest: FrameEvalResult | null;
  error: string | null;
  onFinishSession: () => void;
}

export default function MetricsPanel({
  sessionId,
  latest,
  error,
  onFinishSession,
}: MetricsPanelProps) {
  const faceMatchDisplay =
    latest?.face_match === null || latest?.face_match === undefined
      ? "—"
      : latest.face_match
      ? "yes"
      : "no";

  return (
    <div className="status-panel">
      <ul className="kv">
        <li>
          <span>Session</span>
          <span>{sessionId}</span>
        </li>
        <li>
          <span>Persons detected</span>
          <span>{latest?.person_count ?? "—"}</span>
        </li>
        <li>
          <span>Face match</span>
          <span>{faceMatchDisplay}</span>
        </li>
        <li>
          <span>Similarity</span>
          <span>{latest?.face_similarity?.toFixed(3) ?? "—"}</span>
        </li>
        <li>
          <span>Head yaw</span>
          <span>{latest?.head_yaw != null ? `${latest.head_yaw}°` : "—"}</span>
        </li>
        <li>
          <span>Head pitch</span>
          <span>{latest?.head_pitch != null ? `${latest.head_pitch}°` : "—"}</span>
        </li>
        <li>
          <span>Gaze X</span>
          <span>{latest?.gaze_ratio_x != null ? latest.gaze_ratio_x.toFixed(3) : "—"}</span>
        </li>
        <li>
          <span>Gaze Y</span>
          <span>{latest?.gaze_ratio_y != null ? latest.gaze_ratio_y.toFixed(3) : "—"}</span>
        </li>
        <li>
          <span>Processing</span>
          <span>{latest?.processing_ms ? `${latest.processing_ms}ms` : "—"}</span>
        </li>
      </ul>
      {error && <p className="error">{error}</p>}
      <button onClick={onFinishSession}>End session</button>
    </div>
  );
}
