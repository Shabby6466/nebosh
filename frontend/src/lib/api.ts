import axios from "axios";

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export const WS_BASE_URL: string = API_BASE_URL.replace(/^http/, "ws");

export const api = axios.create({ baseURL: API_BASE_URL });

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
  status: string;
  started_at: string;
  ended_at: string | null;
  violation_count: number;
}

export interface Violation {
  id: string;
  session_id: string;
  type: string;
  confidence: number | null;
  detected_at: string;
  review_status: "unreviewed" | "confirmed" | "false_positive";
  snapshot_url: string;
}

export interface FrameEvalResult {
  person_count: number;
  face_match: boolean | null;
  face_similarity: number | null;
  liveness_pass: boolean | null;
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

export async function submitKyc(candidateId: string, idDocument: Blob, selfie: Blob): Promise<KYCResult> {
  const form = new FormData();
  form.append("id_document", idDocument, "id_document.jpg");
  form.append("selfie", selfie, "selfie.jpg");
  const { data } = await api.post<KYCResult>(`/api/v1/kyc/verify`, form, {
    params: { candidate_id: candidateId },
  });
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

export async function reportSessionEvent(
  sessionId: string,
  eventType: string,
): Promise<void> {
  await api.post(`/api/v1/sessions/${sessionId}/events`, {
    type: eventType,
    confidence: 1.0,
  });
}
