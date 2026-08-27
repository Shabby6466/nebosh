import { useCallback, useEffect, useRef, useState } from "react";

export function useCamera() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setReady(true);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not access camera");
    }
  }, []);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setReady(false);
  }, []);

  useEffect(() => stop, [stop]);

  /** Downscales the current video frame to maxDim on the long edge and encodes as JPEG. */
  const captureFrame = useCallback((maxDim = 480, quality = 0.6): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return Promise.resolve(null);

    const scale = Math.min(1, maxDim / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return Promise.resolve(null);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), "image/jpeg", quality));
  }, []);

  return { videoRef, start, stop, captureFrame, ready, error };
}
