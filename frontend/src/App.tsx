import { Link, Route, Routes, useNavigate } from "react-router-dom";
import Register from "./pages/Register";
import Continue from "./pages/Continue";
import Kyc from "./pages/Kyc";
import Session from "./pages/Session";
import Admin from "./pages/Admin";
import { useCandidateSession } from "./lib/candidateStore";

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
      <button className="link" onClick={startOver}>Start over</button>
      <Link to="/admin">Admin</Link>
    </div>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <nav className="nav">
        <Link to="/" className="brand">NEBOSH/IOSH Proctoring</Link>
        <CandidateNav />
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Register />} />
          <Route path="/continue" element={<Continue />} />
          <Route path="/kyc/:candidateId" element={<Kyc />} />
          <Route path="/session/:candidateId" element={<Session />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
    </div>
  );
}
