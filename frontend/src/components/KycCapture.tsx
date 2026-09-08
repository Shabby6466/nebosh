import { type RefObject } from "react";
import CameraView from "./CameraView";

interface KycCaptureProps {
  videoRef: RefObject<HTMLVideoElement | null>;
  ready: boolean;
  cameraError: string | null;
  idFile: File | null;
  onIdFileChange: (file: File | null) => void;
  onCaptureSelfie: () => void;
  selfiePreview: string | null;
  onSubmit: () => void;
  submitting: boolean;
  error: string | null;
}

export default function KycCapture({
  videoRef,
  ready,
  cameraError,
  idFile,
  onIdFileChange,
  onCaptureSelfie,
  selfiePreview,
  onSubmit,
  submitting,
  error,
}: KycCaptureProps) {
  return (
    <>
      <label className="block">
        Government ID / Passport (photo or scan)
        <input
          type="file"
          accept="image/*"
          onChange={(e) => onIdFileChange(e.target.files?.[0] ?? null)}
        />
      </label>

      <div className="camera-block">
        <CameraView videoRef={videoRef} cameraError={cameraError} />
        <button type="button" onClick={onCaptureSelfie} disabled={!ready}>
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

      <button
        onClick={onSubmit}
        disabled={!idFile || !selfiePreview || submitting}
      >
        {submitting ? "Verifying…" : "Submit for verification"}
      </button>
    </>
  );
}
