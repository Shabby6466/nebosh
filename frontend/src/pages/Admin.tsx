import { useEffect, useMemo, useState } from "react";
import {
  listCandidates,
  listSessions,
  listViolations,
  reviewViolation,
  type Candidate,
  type SessionSummary,
  type Violation,
} from "../lib/api";
import { axiosMessage } from "./Register";

const AUTO_REFRESH_MS = 15000;

export default function Admin() {
  const [tab, setTab] = useState<"sessions" | "candidates">("sessions");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSession, setSelectedSession] = useState<SessionSummary | null>(null);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = async (opts: { silent?: boolean } = {}) => {
    if (!opts.silent) setLoading(true);
    setError(null);
    try {
      const [c, s] = await Promise.all([listCandidates(), listSessions()]);
      setCandidates(c);
      setSessions(s);
      setLastUpdated(new Date());
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      if (!opts.silent) setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const id = window.setInterval(() => refresh({ silent: true }), AUTO_REFRESH_MS);
    return () => window.clearInterval(id);
  }, []);

  const openSession = async (session: SessionSummary) => {
    setSelectedSession(session);
    setViolations(await listViolations(session.id));
  };

  const review = async (violationId: string, status: "confirmed" | "false_positive") => {
    await reviewViolation(violationId, status);
    if (selectedSession) setViolations(await listViolations(selectedSession.id));
  };

  const filteredSessions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter(
      (s) => s.candidate_name.toLowerCase().includes(q) || s.exam_code.toLowerCase().includes(q),
    );
  }, [sessions, query]);

  const filteredCandidates = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return candidates;
    return candidates.filter(
      (c) => c.full_name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q),
    );
  }, [candidates, query]);

  if (selectedSession) {
    return (
      <div className="card wide">
        <button className="link" onClick={() => setSelectedSession(null)}>&larr; Back to sessions</button>
        <h1>{selectedSession.candidate_name}</h1>
        <p className="muted">
          {selectedSession.exam_code} · {selectedSession.status} · started {new Date(selectedSession.started_at).toLocaleString()}
        </p>

        {violations.length === 0 ? (
          <div className="empty-state">
            <p>No violations recorded for this session.</p>
          </div>
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
      <div className="dashboard-header">
        <div>
          <h1>Compliance Dashboard</h1>
          <p className="muted">
            {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()} · auto-refreshes every 15s` : "Loading…"}
          </p>
        </div>
        <button className="link" onClick={() => refresh()} disabled={loading}>{loading ? "Refreshing…" : "Refresh now"}</button>
      </div>

      <div className="tabs">
        <button className={tab === "sessions" ? "active" : ""} onClick={() => setTab("sessions")}>
          Sessions {sessions.length > 0 && <span className="tab-count">{sessions.length}</span>}
        </button>
        <button className={tab === "candidates" ? "active" : ""} onClick={() => setTab("candidates")}>
          Candidates {candidates.length > 0 && <span className="tab-count">{candidates.length}</span>}
        </button>
        <input
          className="search"
          placeholder={tab === "sessions" ? "Search by candidate or exam code…" : "Search by name or email…"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {error && <p className="error">{error}</p>}

      {tab === "sessions" && (
        filteredSessions.length === 0 ? (
          <div className="empty-state">
            <p>{loading ? "Loading sessions…" : sessions.length === 0 ? "No exam sessions yet." : "No sessions match your search."}</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr><th>Candidate</th><th>Exam</th><th>Status</th><th>Started</th><th>Violations</th></tr>
            </thead>
            <tbody>
              {filteredSessions.map((s) => (
                <tr key={s.id} className="clickable" onClick={() => openSession(s)}>
                  <td>{s.candidate_name}</td>
                  <td>{s.exam_code}</td>
                  <td><span className={`badge badge-${s.status === "active" ? "good" : "neutral"}`}>{s.status}</span></td>
                  <td>{new Date(s.started_at).toLocaleString()}</td>
                  <td className={s.violation_count > 0 ? "flag-count" : ""}>{s.violation_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      {tab === "candidates" && (
        filteredCandidates.length === 0 ? (
          <div className="empty-state">
            <p>{loading ? "Loading candidates…" : candidates.length === 0 ? "No candidates registered yet." : "No candidates match your search."}</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr><th>Name</th><th>Email</th><th>KYC status</th><th>Registered</th></tr>
            </thead>
            <tbody>
              {filteredCandidates.map((c) => (
                <tr key={c.id}>
                  <td>{c.full_name}</td>
                  <td>{c.email}</td>
                  <td><span className={`badge badge-${c.kyc_status === "verified" ? "good" : c.kyc_status === "rejected" ? "bad" : "neutral"}`}>{c.kyc_status}</span></td>
                  <td>{new Date(c.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
