import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createCandidate } from "../lib/api";

export default function Register() {
  const navigate = useNavigate();
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
      navigate(`/kyc/${candidate.id}`);
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card">
      <h1>Candidate Registration</h1>
      <p className="muted">Step 1 of 2 — register, then complete ID + selfie verification.</p>
      <form onSubmit={submit} className="form">
        <label>
          Full name
          <input required value={form.full_name} onChange={update("full_name")} />
        </label>
        <label>
          Email
          <input required type="email" value={form.email} onChange={update("email")} />
        </label>
        <label>
          Phone
          <input value={form.phone} onChange={update("phone")} />
        </label>
        <label>
          CNIC / Passport No.
          <input required value={form.cnic_or_passport_no} onChange={update("cnic_or_passport_no")} />
        </label>
        <label>
          Exam booking reference
          <input value={form.exam_booking_ref} onChange={update("exam_booking_ref")} />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Registering…" : "Continue to verification"}
        </button>
      </form>
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
