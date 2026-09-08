import { type RefObject } from "react";
import StatusBadge from "./StatusBadge";

interface CameraViewProps {
  videoRef: RefObject<HTMLVideoElement | null>;
  showBadge?: boolean;
  status?: "idle" | "starting" | "active" | "ended";
  violation?: string | null;
  cameraError?: string | null;
}

export default function CameraView({
  videoRef,
  showBadge = false,
  status = "idle",
  violation = null,
  cameraError = null,
}: CameraViewProps) {
  return (
    <div className="camera-block">
      {/* Single persistent <video> across all statuses — remounting it would drop the
          already-attached getUserMedia stream and leave the preview black. */}
      <video ref={videoRef} className="video-preview" muted playsInline />
      {showBadge && <StatusBadge status={status} violation={violation} />}
      {cameraError && <p className="error">{cameraError}</p>}
    </div>
  );
}
