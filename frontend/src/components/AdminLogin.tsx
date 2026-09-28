import type React from "react";
import { useState } from "react";
import { adminLogin } from "../lib/api";
import { setAdminToken } from "../lib/adminAuth";
import { axiosMessage } from "../pages/Register";

export default function AdminLogin({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { access_token } = await adminLogin(email, password);
      setAdminToken(access_token);
      onLoggedIn();
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h1>Admin sign in</h1>
      <p className="muted">Reviewer, compliance officer or admin credentials.</p>
      <form className="form" onSubmit={submit}>
        <label>
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
