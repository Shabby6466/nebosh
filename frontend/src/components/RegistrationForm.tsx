import type React from "react";

export interface CandidateFormData {
  full_name: string;
  email: string;
  phone: string;
  cnic_or_passport_no: string;
  exam_booking_ref: string;
}

interface RegistrationFormProps {
  form: CandidateFormData;
  onChange: (key: keyof CandidateFormData) => (e: React.ChangeEvent<HTMLInputElement>) => void;
  onSubmit: (e: React.FormEvent) => void;
  submitting: boolean;
  error: string | null;
}

export default function RegistrationForm({
  form,
  onChange,
  onSubmit,
  submitting,
  error,
}: RegistrationFormProps) {
  return (
    <form onSubmit={onSubmit} className="form">
      <label>
        Full name
        <input
          required
          value={form.full_name}
          onChange={onChange("full_name")}
          placeholder="As shown on your ID"
        />
      </label>
      <label>
        Email
        <input
          required
          type="email"
          value={form.email}
          onChange={onChange("email")}
          placeholder="you@example.com"
        />
      </label>
      <label>
        Phone
        <input
          value={form.phone}
          onChange={onChange("phone")}
          placeholder="Optional"
        />
      </label>
      <label>
        CNIC / Passport No.
        <input
          required
          value={form.cnic_or_passport_no}
          onChange={onChange("cnic_or_passport_no")}
        />
      </label>
      <label>
        Exam booking reference
        <input
          value={form.exam_booking_ref}
          onChange={onChange("exam_booking_ref")}
          placeholder="Optional"
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Registering…" : "Continue to verification"}
      </button>
    </form>
  );
}
