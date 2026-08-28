import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createCandidate } from "../lib/api";
import { useCandidateSession } from "../lib/candidateStore";
import Stepper from "../components/Stepper";

export default function Register() {
  const navigate = useNavigate();
  const { setCandidate } = useCandidateSession();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    phone: "",
    cnic_or_passport_no: "",
    exam_booking_ref: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const update = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const candidate = await createCandidate(form);
      setCandidate({
        id: candidate.id,
        full_name: candidate.full_name,
        email: candidate.email,
        kyc_status: candidate.kyc_status,
      });
      navigate(`/kyc/${candidate.id}`);
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card">
      <Stepper current={1} />
      <h1>Candidate Registration</h1>
      <p className="muted">Register once, then verify your identity to unlock your exam session.</p>
      <form onSubmit={submit} className="form">
        <label>
          Full name
          <input required value={form.full_name} onChange={update("full_name")} placeholder="As shown on your ID" />
        </label>
        <label>
          Email
          <input required type="email" value={form.email} onChange={update("email")} placeholder="you@example.com" />
        </label>
        <label>
          Phone
          <input value={form.phone} onChange={update("phone")} placeholder="Optional" />
        </label>
        <label>
          CNIC / Passport No.
          <input required value={form.cnic_or_passport_no} onChange={update("cnic_or_passport_no")} />
        </label>
        <label>
          Exam booking reference
          <input value={form.exam_booking_ref} onChange={update("exam_booking_ref")} placeholder="Optional" />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Registering…" : "Continue to verification"}
        </button>
      </form>
      <p className="muted footnote">
        Already registered? <Link to="/continue">Continue with your email</Link>
      </p>
    </div>
  );
}

export function axiosMessage(err: unknown): string {
  if (typeof err === "object" && err !== null && "response" in err) {
    const response = (err as { response?: { data?: { detail?: string } } }).response;
    if (response?.data?.detail) return response.data.detail;
  }
  return err instanceof Error ? err.message : "Something went wrong";
}
