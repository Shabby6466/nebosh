import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { lookupCandidateByEmail } from "../lib/api";
import { useCandidateSession } from "../lib/candidateStore";
import { axiosMessage } from "./Register";

export default function Continue() {
  const navigate = useNavigate();
  const { setCandidate } = useCandidateSession();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const candidate = await lookupCandidateByEmail(email);
      setCandidate({
        id: candidate.id,
        full_name: candidate.full_name,
        email: candidate.email,
        kyc_status: candidate.kyc_status,
      });
      navigate(candidate.kyc_status === "verified" ? `/session/${candidate.id}` : `/kyc/${candidate.id}`);
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card">
      <h1>Continue your registration</h1>
      <p className="muted">Enter the email you registered with to pick up where you left off.</p>
      <form onSubmit={submit} className="form">
        <label>
          Email
          <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Looking up…" : "Continue"}
        </button>
      </form>
    </div>
  );
}
