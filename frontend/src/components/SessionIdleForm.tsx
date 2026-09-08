interface SessionIdleFormProps {
  examCode: string;
  onExamCodeChange: (value: string) => void;
  onBeginSession: () => void;
  ready: boolean;
  error: string | null;
}

export default function SessionIdleForm({
  examCode,
  onExamCodeChange,
  onBeginSession,
  ready,
  error,
}: SessionIdleFormProps) {
  return (
    <>
      <label>
        Exam code
        <input value={examCode} onChange={(e) => onExamCodeChange(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <button onClick={onBeginSession} disabled={!ready}>
        Start proctored session
      </button>
    </>
  );
}
