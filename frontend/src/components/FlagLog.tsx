import type { FrameEvalResult } from "../lib/api";

export interface LogEntry extends Partial<FrameEvalResult> {
  at: string;
  violation?: string | null;
}

interface FlagLogProps {
  log: LogEntry[];
}

export default function FlagLog({ log }: FlagLogProps) {
  return (
    <div className="log-container">
      <h3>Flag log</h3>
      {log.length === 0 ? (
        <p className="muted">No violations flagged yet.</p>
      ) : (
        <ul className="log">
          {log.map((entry, i) => (
            <li key={i} className="log-violation">
              <strong>{entry.at}</strong>
              <span>{entry.violation?.replaceAll("_", " ")}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
