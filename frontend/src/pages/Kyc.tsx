import { useEffect, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { submitKyc, type KYCResult } from "../lib/api";
import { useCamera } from "../lib/useCamera";
import { useCandidateSession } from "../lib/candidateStore";
import Stepper from "../components/Stepper";
import { axiosMessage } from "./Register";

export default function Kyc() {
  const { candidateId: paramId } = useParams<{ candidateId: string }>();
  const { candidate, setCandidate } = useCandidateSession();
  const candidateId = paramId ?? candidate?.id;

  const navigate = useNavigate();
  const { videoRef, start, captureFrame, ready, error: cameraError } = useCamera();

  const [idFile, setIdFile] = useState<File | null>(null);
  const [selfieBlob, setSelfieBlob] = useState<Blob | null>(null);
  const [selfiePreview, setSelfiePreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<KYCResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    start();
  }, [start]);

  if (!candidateId) {
    return <Navigate to="/" replace />;
  }

  const captureSelfie = async () => {
    const blob = await captureFrame(720, 0.85);
    if (!blob) return;
    setSelfieBlob(blob);
    setSelfiePreview(URL.createObjectURL(blob));
  };

  const submit = async () => {
    if (!idFile || !selfieBlob) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitKyc(candidateId, idFile, selfieBlob);
      setResult(res);
      if (candidate) {
        setCandidate({ ...candidate, kyc_status: res.verified ? "verified" : "rejected" });
      }
    } catch (err) {
      setError(axiosMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    return (
      <div className="card">
        <Stepper current={result.verified ? 3 : 2} />
        <h1>{result.verified ? "Verification passed" : "Verification failed"}</h1>
        <ul className="kv">
          <li><span>Match score</span><span>{result.match_score.toFixed(3)}</span></li>
          <li><span>Liveness score</span><span>{result.liveness_score.toFixed(3)}</span></li>
          <li><span>Liveness passed</span><span>{result.liveness_passed ? "yes" : "no"}</span></li>
          {result.reason && <li><span>Reason</span><span>{result.reason}</span></li>}
        </ul>
        {result.verified ? (
          <button onClick={() => navigate(`/session/${candidateId}`)}>Start exam session</button>
        ) : (
          <button onClick={() => setResult(null)}>Try again</button>
        )}
      </div>
    );
  }

  return (
    <div className="card">
      <Stepper current={2} />
      <h1>Identity Verification (KYC)</h1>
      <p className="muted">Upload your government ID and capture a live selfie — both are matched automatically.</p>

      <label className="block">
        Government ID / Passport (photo or scan)
        <input type="file" accept="image/*" onChange={(e) => setIdFile(e.target.files?.[0] ?? null)} />
      </label>

      <div className="camera-block">
        <video ref={videoRef} className="video-preview" muted playsInline />
        {cameraError && <p className="error">{cameraError}</p>}
        <button type="button" onClick={captureSelfie} disabled={!ready}>
          Capture selfie
        </button>
      </div>

      {selfiePreview && (
        <div>
          <p className="muted">Captured selfie:</p>
          <img src={selfiePreview} alt="Captured selfie" className="thumb" />
        </div>
      )}

      {error && <p className="error">{error}</p>}

      <button onClick={submit} disabled={!idFile || !selfieBlob || submitting}>
        {submitting ? "Verifying…" : "Submit for verification"}
      </button>
    </div>
  );
}
