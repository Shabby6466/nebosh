import { useEffect, useState } from "react";
import {
  listCandidates,
  listSessions,
  listViolations,
  reviewViolation,
  type Candidate,
  type SessionSummary,
  type Violation,
} from "../lib/api";

export default function Admin() {
  const [tab, setTab] = useState<"candidates" | "sessions">("sessions");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSession, setSelectedSession] = useState<SessionSummary | null>(null);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const [c, s] = await Promise.all([listCandidates(), listSessions()]);
      setCandidates(c);
      setSessions(s);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const openSession = async (session: SessionSummary) => {
    setSelectedSession(session);
    setViolations(await listViolations(session.id));
  };

  const review = async (violationId: string, status: "confirmed" | "false_positive") => {
    await reviewViolation(violationId, status);
    if (selectedSession) setViolations(await listViolations(selectedSession.id));
  };

  if (selectedSession) {
    return (
      <div className="card wide">
        <button className="link" onClick={() => setSelectedSession(null)}>&larr; Back to sessions</button>
        <h1>{selectedSession.candidate_name}</h1>
        <p className="muted">
          {selectedSession.exam_code} · {selectedSession.status} · started {new Date(selectedSession.started_at).toLocaleString()}
        </p>

        {violations.length === 0 ? (
          <p className="muted">No violations recorded for this session.</p>
        ) : (
          <div className="violation-grid">
            {violations.map((v) => (
              <div key={v.id} className="violation-card">
                <img src={v.snapshot_url} alt={v.type} />
                <div className="violation-meta">
                  <strong>{v.type.replaceAll("_", " ")}</strong>
                  <span className="muted">{new Date(v.detected_at).toLocaleTimeString()}</span>
                  {v.confidence != null && <span className="muted">confidence {v.confidence.toFixed(2)}</span>}
                  <span className={`badge badge-${v.review_status === "confirmed" ? "bad" : v.review_status === "false_positive" ? "good" : "neutral"}`}>
                    {v.review_status.replaceAll("_", " ")}
                  </span>
                  {v.review_status === "unreviewed" && (
                    <div className="review-actions">
                      <button onClick={() => review(v.id, "confirmed")}>Confirm</button>
                      <button onClick={() => review(v.id, "false_positive")}>False positive</button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="card wide">
      <h1>Compliance Dashboard</h1>
      <div className="tabs">
        <button className={tab === "sessions" ? "active" : ""} onClick={() => setTab("sessions")}>Sessions</button>
        <button className={tab === "candidates" ? "active" : ""} onClick={() => setTab("candidates")}>Candidates</button>
        <button className="link" onClick={refresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
      </div>

      {tab === "sessions" && (
        <table>
          <thead>
            <tr><th>Candidate</th><th>Exam</th><th>Status</th><th>Started</th><th>Violations</th></tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} className="clickable" onClick={() => openSession(s)}>
                <td>{s.candidate_name}</td>
                <td>{s.exam_code}</td>
                <td>{s.status}</td>
                <td>{new Date(s.started_at).toLocaleString()}</td>
                <td className={s.violation_count > 0 ? "flag-count" : ""}>{s.violation_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "candidates" && (
        <table>
          <thead>
            <tr><th>Name</th><th>Email</th><th>KYC status</th><th>Registered</th></tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.id}>
                <td>{c.full_name}</td>
                <td>{c.email}</td>
                <td><span className={`badge badge-${c.kyc_status === "verified" ? "good" : c.kyc_status === "rejected" ? "bad" : "neutral"}`}>{c.kyc_status}</span></td>
                <td>{new Date(c.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
