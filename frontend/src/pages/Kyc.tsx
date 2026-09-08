import { useEffect, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { submitKyc, type KYCResult } from "../lib/api";
import { useCamera } from "../lib/useCamera";
import { useCandidateSession } from "../lib/candidateStore";
import Stepper from "../components/Stepper";
import KycCapture from "../components/KycCapture";
import KycResultView from "../components/KycResultView";
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
        <KycResultView
          result={result}
          onProceed={() => navigate(`/session/${candidateId}`)}
          onRetry={() => setResult(null)}
        />
      </div>
    );
  }

  return (
    <div className="card">
      <Stepper current={2} />
      <h1>Identity Verification (KYC)</h1>
      <p className="muted">Upload your government ID and capture a live selfie — both are matched automatically.</p>
      <KycCapture
        videoRef={videoRef}
        ready={ready}
        cameraError={cameraError}
        idFile={idFile}
        onIdFileChange={setIdFile}
        onCaptureSelfie={captureSelfie}
        selfiePreview={selfiePreview}
        onSubmit={submit}
        submitting={submitting}
        error={error}
      />
    </div>
  );
}
