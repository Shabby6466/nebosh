const STEPS = ["Register", "Verify identity", "Exam session"] as const;

export default function Stepper({ current }: { current: 1 | 2 | 3 }) {
  return (
    <ol className="stepper">
      {STEPS.map((label, i) => {
        const step = i + 1;
        const state = step < current ? "done" : step === current ? "active" : "upcoming";
        return (
          <li key={label} className={`step step-${state}`}>
            <span className="step-dot">{state === "done" ? "✓" : step}</span>
            <span className="step-label">{label}</span>
            {step < STEPS.length && <span className="step-connector" />}
          </li>
        );
      })}
    </ol>
  );
}
