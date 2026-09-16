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
  const [idPreview, setIdPreview] = useState<string | null>(null);
  const [selfieBlob, setSelfieBlob] = useState<Blob | null>(null);
  const [selfiePreview, setSelfiePreview] = useState<string | null>(null);
  const [holdIdBlob, setHoldIdBlob] = useState<Blob | null>(null);
  const [holdIdPreview, setHoldIdPreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<KYCResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    start();
  }, [start]);

  if (!candidateId) {
    return <Navigate to="/" replace />;
  }

  const setIdDocument = (file: File | null) => {
    setIdFile(file);
    setIdPreview(file ? URL.createObjectURL(file) : null);
  };

  const captureSelfie = async (): Promise<boolean> => {
    const blob = await captureFrame(720, 0.85);
    if (!blob) return false;
    setSelfieBlob(blob);
    setSelfiePreview(URL.createObjectURL(blob));
    return true;
  };

  const captureHoldId = async (): Promise<boolean> => {
    const blob = await captureFrame(1280, 0.85);
    if (!blob) return false;
    setHoldIdBlob(blob);
    setHoldIdPreview(URL.createObjectURL(blob));
    return true;
  };

  const submit = async () => {
    if (!idFile || !selfieBlob || !holdIdBlob) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitKyc(candidateId, idFile, selfieBlob, holdIdBlob);
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

  // KycCapture (and the <video> element inside it) must stay mounted for the
  // whole page lifetime — the camera's getUserMedia stream is only attached
  // to that one DOM node once, on first mount. Unmounting it (e.g. by
  // conditionally returning a different tree for the result view) would
  // destroy that node; remounting later creates a fresh <video> with no
  // stream attached, showing a black box until a full page refresh reruns
  // `start()`. So we always render KycCapture and just hide it with CSS
  // while a result is shown.
  return (
    <div className="card">
      <Stepper current={result ? (result.verified ? 3 : 2) : 2} />
      {result && (
        <KycResultView
          result={result}
          onProceed={() => navigate(`/session/${candidateId}`)}
          onRetry={() => setResult(null)}
        />
      )}
      <div hidden={!!result}>
        <h1>Identity Verification (KYC)</h1>
        <p className="muted">
          Three quick steps: upload your ID, take a selfie, then hold your CNIC up to the camera.
        </p>
        <KycCapture
          videoRef={videoRef}
          ready={ready}
          cameraError={cameraError}
          idFile={idFile}
          idPreview={idPreview}
          onIdFileChange={setIdDocument}
          onCaptureSelfie={captureSelfie}
          selfiePreview={selfiePreview}
          onCaptureHoldId={captureHoldId}
          holdIdPreview={holdIdPreview}
          onSubmit={submit}
          submitting={submitting}
          error={error}
        />
      </div>
    </div>
  );
}
