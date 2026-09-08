import { Link, useNavigate } from "react-router-dom";
import { useCandidateSession } from "../lib/candidateStore";

function CandidateNav() {
  const { candidate, clearCandidate } = useCandidateSession();
  const navigate = useNavigate();

  if (!candidate) {
    return (
      <div className="nav-links">
        <Link to="/continue">Continue registration</Link>
        <Link to="/admin">Admin</Link>
      </div>
    );
  }

  const resumeTo = candidate.kyc_status === "verified" ? `/session/${candidate.id}` : `/kyc/${candidate.id}`;
  const startOver = () => {
    clearCandidate();
    navigate("/");
  };

  return (
    <div className="nav-links">
      <span className="nav-greeting">Hi, {candidate.full_name.split(" ")[0]}</span>
      <Link to={resumeTo}>Resume</Link>
      <button className="link" onClick={startOver}>
        Start over
      </button>
      <Link to="/admin">Admin</Link>
    </div>
  );
}

export default function Navbar() {
  return (
    <nav className="nav">
      <Link to="/" className="brand">
        NEBOSH DEMO AI SYSTEM
      </Link>
      <CandidateNav />
    </nav>
  );
}
