import { type RefObject, useState } from "react";
import CameraView from "./CameraView";

type Stage = "id" | "selfie" | "hold" | "review";

const SUBSTEPS: { key: Stage; label: string }[] = [
  { key: "id", label: "ID document" },
  { key: "selfie", label: "Selfie" },
  { key: "hold", label: "Hold CNIC" },
  { key: "review", label: "Review" },
];

interface KycCaptureProps {
  videoRef: RefObject<HTMLVideoElement | null>;
  ready: boolean;
  cameraError: string | null;
  idFile: File | null;
  idPreview: string | null;
  onIdFileChange: (file: File | null) => void;
  onCaptureSelfie: () => Promise<boolean>;
  selfiePreview: string | null;
  onCaptureHoldId: () => Promise<boolean>;
  holdIdPreview: string | null;
  onSubmit: () => void;
  submitting: boolean;
  error: string | null;
}

export default function KycCapture({
  videoRef,
  ready,
  cameraError,
  idFile,
  idPreview,
  onIdFileChange,
  onCaptureSelfie,
  selfiePreview,
  onCaptureHoldId,
  holdIdPreview,
  onSubmit,
  submitting,
  error,
}: KycCaptureProps) {
  const [stage, setStage] = useState<Stage>("id");
  // Whether each camera-based stage is showing the live feed (about to shoot)
  // or a just-captured still. Kept separate from "does a preview exist" so
  // that pressing Retake shows the live feed again for repositioning instead
  // of silently re-shooting whatever the camera happened to be pointed at.
  const [selfieMode, setSelfieMode] = useState<"camera" | "preview">("camera");
  const [holdMode, setHoldMode] = useState<"camera" | "preview">("camera");

  const reachedIndex = Math.max(
    idFile ? 1 : 0,
    selfiePreview ? 2 : 0,
    holdIdPreview ? 3 : 0,
  );

  const goTo = (target: Stage, index: number) => {
    if (index <= reachedIndex) setStage(target);
  };

  const takeSelfie = async () => {
    if (await onCaptureSelfie()) setSelfieMode("preview");
  };
  const takeHoldId = async () => {
    if (await onCaptureHoldId()) setHoldMode("preview");
  };

  const capturingSelfie = stage === "selfie" && selfieMode === "camera";
  const capturingHold = stage === "hold" && holdMode === "camera";
  // The <video> element must stay mounted for the whole flow — remounting it
  // would drop the already-attached getUserMedia stream and leave a black
  // preview when the user comes back to a capture stage. So we keep
  // CameraView permanently in the tree and only toggle its visibility.
  const showCamera = capturingSelfie || capturingHold;

  return (
    <>
      <ol className="substeps">
        {SUBSTEPS.map((s, i) => {
          // "done" (checkmark) only once that step's own capture exists — not
          // merely reachable — so we never show a false-positive checkmark on
          // a step the candidate hasn't actually completed yet.
          const isDone = [idFile, selfiePreview, holdIdPreview, null][i] != null && s.key !== "review";
          const state = s.key === stage ? "active" : isDone ? "done" : "upcoming";
          return (
            <li key={s.key} className={`substep substep-${state}`}>
              <button
                type="button"
                className="substep-btn"
                disabled={i > reachedIndex}
                onClick={() => goTo(s.key, i)}
              >
                <span className="substep-dot">{state === "done" ? "✓" : i + 1}</span>
                <span className="substep-label">{s.label}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <div className={showCamera ? "camera-wrap" : "camera-wrap hidden"}>
        <CameraView videoRef={videoRef} cameraError={cameraError} />
      </div>

      {stage === "id" && (
        <div className="capture-stage">
          <p className="hint">Upload a clear photo or scan of your government-issued ID (CNIC/passport).</p>
          <label className="block">
            Government ID / Passport
            <input
              type="file"
              accept="image/*"
              onChange={(e) => onIdFileChange(e.target.files?.[0] ?? null)}
            />
          </label>
          {idPreview && <img src={idPreview} alt="Uploaded ID" className="thumb" />}
          <div className="capture-actions">
            <button type="button" onClick={() => setStage("selfie")} disabled={!idFile}>
              Continue
            </button>
          </div>
        </div>
      )}

      {stage === "selfie" && (
        <div className="capture-stage">
          <p className="hint hint-warn">
            Set your CNIC aside for this shot — only your face should be visible, looking straight at the camera.
          </p>
          {capturingSelfie ? (
            <div className="capture-actions">
              <button type="button" onClick={takeSelfie} disabled={!ready}>
                Capture selfie
              </button>
            </div>
          ) : (
            <>
              <img src={selfiePreview ?? undefined} alt="Captured selfie" className="thumb" />
              <div className="capture-actions">
                <button type="button" className="ghost" onClick={() => setSelfieMode("camera")}>
                  Retake
                </button>
                <button type="button" onClick={() => setStage("hold")}>
                  Continue
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {stage === "hold" && (
        <div className="capture-stage">
          <p className="hint hint-warn">
            Hold your original CNIC in your hand, facing the camera, next to your face — both your face and the
            photo on the card must be clearly visible in one shot.
          </p>
          {capturingHold ? (
            <div className="capture-actions">
              <button type="button" onClick={takeHoldId} disabled={!ready}>
                Capture CNIC + face
              </button>
            </div>
          ) : (
            <>
              <img src={holdIdPreview ?? undefined} alt="Captured CNIC held next to face" className="thumb" />
              <div className="capture-actions">
                <button type="button" className="ghost" onClick={() => setHoldMode("camera")}>
                  Retake
                </button>
                <button type="button" onClick={() => setStage("review")}>
                  Continue
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {stage === "review" && (
        <div className="capture-stage">
          <p className="hint">Review your captures, then submit for verification.</p>
          <div className="review-grid">
            <div className="review-item">
              <img src={idPreview ?? undefined} alt="ID document" className="thumb" />
              <span className="muted">ID document</span>
              <button type="button" className="link" onClick={() => setStage("id")}>
                Retake
              </button>
            </div>
            <div className="review-item">
              <img src={selfiePreview ?? undefined} alt="Selfie" className="thumb" />
              <span className="muted">Selfie</span>
              <button type="button" className="link" onClick={() => setStage("selfie")}>
                Retake
              </button>
            </div>
            <div className="review-item">
              <img src={holdIdPreview ?? undefined} alt="CNIC held next to face" className="thumb" />
              <span className="muted">CNIC + face</span>
              <button type="button" className="link" onClick={() => setStage("hold")}>
                Retake
              </button>
            </div>
          </div>

          {error && <p className="error">{error}</p>}

          <button
            onClick={onSubmit}
            disabled={!idFile || !selfiePreview || !holdIdPreview || submitting}
          >
            {submitting ? "Verifying…" : "Submit for verification"}
          </button>
        </div>
      )}
    </>
  );
}
