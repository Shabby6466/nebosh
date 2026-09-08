import type { KYCResult } from "../lib/api";

interface KycResultViewProps {
  result: KYCResult;
  onProceed: () => void;
  onRetry: () => void;
}

export default function KycResultView({
  result,
  onProceed,
  onRetry,
}: KycResultViewProps) {
  return (
    <>
      <h1>{result.verified ? "Verification passed" : "Verification failed"}</h1>
      <ul className="kv">
        <li>
          <span>Match score</span>
          <span>{result.match_score.toFixed(3)}</span>
        </li>
        <li>
          <span>Liveness score</span>
          <span>{result.liveness_score.toFixed(3)}</span>
        </li>
        <li>
          <span>Liveness passed</span>
          <span>{result.liveness_passed ? "yes" : "no"}</span>
        </li>
        {result.reason && (
          <li>
            <span>Reason</span>
            <span>{result.reason}</span>
          </li>
        )}
      </ul>
      {result.verified ? (
        <button onClick={onProceed}>Start exam session</button>
      ) : (
        <button onClick={onRetry}>Try again</button>
      )}
    </>
  );
}
