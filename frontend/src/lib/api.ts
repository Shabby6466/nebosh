import axios from "axios";
import { clearAdminToken, getAdminToken } from "./adminAuth";

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export const WS_BASE_URL: string = API_BASE_URL.replace(/^http/, "ws");

export const api = axios.create({ baseURL: API_BASE_URL });

// Admin/vendor-management endpoints require an admin bearer token; attach it
// automatically so callers don't have to. A 401 back means the token expired
// or was never set — drop it so the Admin page falls back to the login form.
api.interceptors.request.use((config) => {
  if (config.url?.includes("/api/v1/admin/")) {
    const token = getAdminToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401 && err?.config?.url?.includes("/api/v1/admin/")) {
      clearAdminToken();
    }
    return Promise.reject(err);
  },
);

export interface Candidate {
  id: string;
  full_name: string;
  email: string;
  kyc_status: "pending" | "verified" | "rejected" | "expired";
  created_at: string;
}

export interface KYCResult {
  candidate_id: string;
  verified: boolean;
  match_score: number;
  liveness_score: number;
  liveness_passed: boolean;
  hold_id_match_score: number;
  hold_id_match_passed: boolean;
  reason: string | null;
}

export interface FaceCheckResult {
  verified: boolean;
  face_match: boolean | null;
  face_similarity: number | null;
  liveness_pass: boolean | null;
  liveness_score: number | null;
  reason: string | null;
}

export interface ExamSessionOut {
  id: string;
  candidate_id: string;
  exam_code: string;
  status: string;
  started_at: string;
}

export interface SessionSummary {
  id: string;
  candidate_id: string;
  candidate_name: string;
  exam_code: string;
  mode: "exam" | "interview";
  status: string;
  started_at: string;
  ended_at: string | null;
  trust_score: number | null;
  violation_count: number;
}

export interface Violation {
  id: string;
  session_id: string;
  type: string;
  confidence: number | null;
  detected_at: string;
  review_status: "unreviewed" | "confirmed" | "false_positive";
  snapshot_url: string | null; // null for browser events (no snapshot)
}

export interface FrameEvalResult {
  person_count: number;
  face_match: boolean | null;
  face_similarity: number | null;
  liveness_pass: boolean | null;
  liveness_score: number | null;
  head_yaw: number | null;
  head_pitch: number | null;
  gaze_ratio_x: number | null;
  gaze_ratio_y: number | null;
  violation: string | null;
  processing_ms: number;
}

export async function lookupCandidateByEmail(email: string): Promise<Candidate> {
  const { data } = await api.get<Candidate>("/api/v1/candidates/lookup", { params: { email } });
  return data;
}

export async function createCandidate(payload: {
  full_name: string;
  email: string;
  phone?: string;
  cnic_or_passport_no: string;
  exam_booking_ref?: string;
}): Promise<Candidate> {
  const { data } = await api.post<Candidate>("/api/v1/candidates", payload);
  return data;
}

export async function submitKyc(
  candidateId: string,
  idDocument: Blob,
  selfie: Blob,
  holdIdPhoto: Blob,
): Promise<KYCResult> {
  const form = new FormData();
  form.append("id_document", idDocument, "id_document.jpg");
  form.append("selfie", selfie, "selfie.jpg");
  form.append("hold_id_photo", holdIdPhoto, "hold_id_photo.jpg");
  const { data } = await api.post<KYCResult>(`/api/v1/kyc/verify`, form, {
    params: { candidate_id: candidateId },
  });
  return data;
}

export async function verifyFaceForSession(candidateId: string, frame: Blob): Promise<FaceCheckResult> {
  const form = new FormData();
  form.append("frame", frame, "frame.jpg");
  const { data } = await api.post<FaceCheckResult>(`/api/v1/candidates/${candidateId}/verify-face`, form);
  return data;
}

export async function createSession(candidateId: string, examCode: string): Promise<ExamSessionOut> {
  const { data } = await api.post<ExamSessionOut>("/api/v1/sessions", {
    candidate_id: candidateId,
    exam_code: examCode,
  });
  return data;
}

export async function endSession(sessionId: string): Promise<ExamSessionOut> {
  const { data } = await api.post<ExamSessionOut>(`/api/v1/sessions/${sessionId}/end`);
  return data;
}

export async function listCandidates(kycStatus?: string): Promise<Candidate[]> {
  const { data } = await api.get<Candidate[]>("/api/v1/admin/candidates", {
    params: kycStatus ? { kyc_status: kycStatus } : undefined,
  });
  return data;
}

export async function listSessions(): Promise<SessionSummary[]> {
  const { data } = await api.get<SessionSummary[]>("/api/v1/admin/sessions");
  return data;
}

export async function listViolations(sessionId: string): Promise<Violation[]> {
  const { data } = await api.get<Violation[]>(`/api/v1/admin/sessions/${sessionId}/violations`);
  return data;
}

export async function reviewViolation(
  violationId: string,
  reviewStatus: "confirmed" | "false_positive",
  notes?: string,
): Promise<void> {
  await api.post(`/api/v1/admin/violations/${violationId}/review`, null, {
    params: { review_status: reviewStatus, notes },
  });
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export async function adminLogin(email: string, password: string): Promise<TokenOut> {
  const { data } = await api.post<TokenOut>("/api/v1/auth/admin/login", { email, password });
  return data;
}

export interface Organization {
  id: string;
  name: string;
  allowed_origin: string | null;
  webhook_url: string | null;
  is_active: boolean;
  created_at: string;
  last_active_at: string | null;
  candidate_count: number;
  session_count: number;
  violation_count: number;
}

export interface OrganizationCreated extends Organization {
  api_key: string;
  webhook_secret: string; // HMAC key partners use to verify our webhooks — shown once
}

export async function listOrganizations(): Promise<Organization[]> {
  const { data } = await api.get<Organization[]>("/api/v1/admin/organizations");
  return data;
}

export async function createOrganization(payload: {
  name: string;
  allowed_origin?: string;
  webhook_url?: string;
}): Promise<OrganizationCreated> {
  const { data } = await api.post<OrganizationCreated>("/api/v1/admin/organizations", payload);
  return data;
}

export async function revokeOrganization(id: string): Promise<Organization> {
  const { data } = await api.post<Organization>(`/api/v1/admin/organizations/${id}/revoke`);
  return data;
}

export async function reactivateOrganization(id: string): Promise<Organization> {
  const { data } = await api.post<Organization>(`/api/v1/admin/organizations/${id}/reactivate`);
  return data;
}

export async function rotateOrganizationKey(id: string): Promise<{ id: string; api_key: string }> {
  const { data } = await api.post<{ id: string; api_key: string }>(
    `/api/v1/admin/organizations/${id}/rotate-key`,
  );
  return data;
}

export async function updateOrganization(
  id: string,
  payload: { allowed_origin?: string | null; webhook_url?: string | null },
): Promise<Organization> {
  const { data } = await api.patch<Organization>(`/api/v1/admin/organizations/${id}`, payload);
  return data;
}

export async function rotateWebhookSecret(id: string): Promise<{ id: string; webhook_secret: string }> {
  const { data } = await api.post<{ id: string; webhook_secret: string }>(
    `/api/v1/admin/organizations/${id}/rotate-webhook-secret`,
  );
  return data;
}

export async function reportSessionEvent(
  sessionId: string,
  eventType: string,
): Promise<void> {
  await api.post(`/api/v1/sessions/${sessionId}/events`, {
    type: eventType,
    confidence: 1.0,
  });
}
