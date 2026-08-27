import { Link, Route, Routes } from "react-router-dom";
import Register from "./pages/Register";
import Kyc from "./pages/Kyc";
import Session from "./pages/Session";
import Admin from "./pages/Admin";

export default function App() {
  return (
    <div className="app-shell">
      <nav className="nav">
        <span className="brand">NEBOSH/IOSH Proctoring</span>
        <div className="nav-links">
          <Link to="/">Register</Link>
          <Link to="/admin">Admin</Link>
        </div>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Register />} />
          <Route path="/kyc/:candidateId" element={<Kyc />} />
          <Route path="/session/:candidateId" element={<Session />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
    </div>
  );
}
