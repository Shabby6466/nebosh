import { Route, Routes } from "react-router-dom";
import Navbar from "./components/Navbar";
import Register from "./pages/Register";
import Continue from "./pages/Continue";
import Kyc from "./pages/Kyc";
import Session from "./pages/Session";
import Admin from "./pages/Admin";

export default function App() {
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

