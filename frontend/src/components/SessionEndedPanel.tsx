import { Link } from "react-router-dom";

export default function SessionEndedPanel() {
  return (
    <div className="ended-panel">
      <p>Session ended. Thank you — your exam has been submitted for review.</p>
      <Link to="/">Back to home</Link>
    </div>
  );
}
