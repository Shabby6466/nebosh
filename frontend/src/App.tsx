import { Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar";
import Register from "./pages/Register";
import Continue from "./pages/Continue";
import Kyc from "./pages/Kyc";
import Session from "./pages/Session";
import Admin from "./pages/Admin";

// Admin-only build (VITE_ADMIN_ONLY=true, used for admin.<domain>): just the
// compliance dashboard. The candidate flow pages are local test tools only.
const ADMIN_ONLY = import.meta.env.VITE_ADMIN_ONLY === "true";

export default function App() {
  if (ADMIN_ONLY) {
    return (
      <div className="app-shell">
        <Navbar adminOnly />
        <main>
          <Routes>
            <Route path="*" element={<Admin />} />
          </Routes>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Navbar />
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

