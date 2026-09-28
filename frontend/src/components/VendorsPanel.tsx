import type React from "react";
import { useEffect, useState } from "react";
import {
  createOrganization,
  listOrganizations,
  reactivateOrganization,
  revokeOrganization,
  rotateOrganizationKey,
  type Organization,
} from "../lib/api";
import { axiosMessage } from "../pages/Register";

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

/** Shown exactly once, right after issue/rotation — the raw key is never
 * retrievable again after this closes, only its hash is stored server-side. */
function NewKeyReveal({ apiKey, onDismiss }: { apiKey: string; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(apiKey);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="key-reveal">
      <p>
        <strong>Copy this API key now</strong> — it will not be shown again. Only its hash is stored.
      </p>
      <div className="key-reveal-row">
        <code>{apiKey}</code>
        <button type="button" onClick={copy}>
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <button type="button" className="link" onClick={onDismiss}>
        I&apos;ve saved it — dismiss
      </button>
    </div>
  );
}

export default function VendorsPanel() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", allowed_origin: "", webhook_url: "" });
  const [submitting, setSubmitting] = useState(false);
  const [revealedKey, setRevealedKey] = useState<{ orgName: string; apiKey: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setOrgs(await listOrganizations());
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const submitNewVendor = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await createOrganization({
        name: form.name,
        allowed_origin: form.allowed_origin || undefined,
        webhook_url: form.webhook_url || undefined,
      });
      setRevealedKey({ orgName: created.name, apiKey: created.api_key });
      setForm({ name: "", allowed_origin: "", webhook_url: "" });
      setShowForm(false);
      await refresh();
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async (org: Organization) => {
    setBusyId(org.id);
    setError(null);
    try {
      if (org.is_active) await revokeOrganization(org.id);
      else await reactivateOrganization(org.id);
      await refresh();
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const rotate = async (org: Organization) => {
    if (!confirm(`Rotate the API key for "${org.name}"? Their current key will stop working immediately.`)) {
      return;
    }
    setBusyId(org.id);
    setError(null);
    try {
      const { api_key } = await rotateOrganizationKey(org.id);
      setRevealedKey({ orgName: org.name, apiKey: api_key });
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <div className="dashboard-header">
        <div>
          <p className="muted">API keys issued to integrating LMS partners, plus usage against each.</p>
        </div>
        <button className="link" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "+ New vendor"}
        </button>
      </div>

      {revealedKey && (
        <NewKeyReveal
          apiKey={revealedKey.apiKey}
          onDismiss={() => setRevealedKey(null)}
        />
      )}

      {showForm && (
        <form className="form" onSubmit={submitNewVendor} style={{ marginBottom: 24 }}>
          <label>
            Vendor name
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Savefast LMS"
            />
          </label>
          <label>
            Allowed origin (for CORS)
            <input
              value={form.allowed_origin}
              onChange={(e) => setForm({ ...form, allowed_origin: e.target.value })}
              placeholder="https://learn.savefast.example.com"
            />
          </label>
          <label>
            Webhook URL (optional)
            <input
              value={form.webhook_url}
              onChange={(e) => setForm({ ...form, webhook_url: e.target.value })}
              placeholder="https://savefast.example.com/kyc/callback"
            />
          </label>
          <button type="submit" disabled={submitting}>
            {submitting ? "Issuing key…" : "Issue API key"}
          </button>
        </form>
      )}

      {error && <p className="error">{error}</p>}

      {orgs.length === 0 ? (
        <div className="empty-state">
          <p>{loading ? "Loading vendors…" : "No vendors yet — issue the first API key above."}</p>
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Vendor</th>
              <th>Status</th>
              <th>Candidates</th>
              <th>Sessions</th>
              <th>Violations</th>
              <th>Last active</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {orgs.map((org) => (
              <tr key={org.id}>
                <td>
                  <div>{org.name}</div>
                  {org.allowed_origin && <div className="muted">{org.allowed_origin}</div>}
                </td>
                <td>
                  <span className={`badge badge-${org.is_active ? "good" : "bad"}`}>
                    {org.is_active ? "active" : "revoked"}
                  </span>
                </td>
                <td>{org.candidate_count}</td>
                <td>{org.session_count}</td>
                <td className={org.violation_count > 0 ? "flag-count" : ""}>{org.violation_count}</td>
                <td>{formatDate(org.last_active_at)}</td>
                <td>
                  <div className="review-actions">
                    <button type="button" disabled={busyId === org.id} onClick={() => rotate(org)}>
                      Rotate key
                    </button>
                    <button type="button" disabled={busyId === org.id} onClick={() => toggleActive(org)}>
                      {org.is_active ? "Revoke" : "Reactivate"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
