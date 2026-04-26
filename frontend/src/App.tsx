import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import About from "./pages/About";
import Home from "./pages/Home";
import PremiumCompare from "./pages/PremiumCompare";
import Risko from "./pages/Risko";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="about" element={<About />} />
          <Route path="compare" element={<PremiumCompare />} />
          <Route path="risko" element={<Risko />} />
          <Route path="rag" element={<Navigate to="/risko" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
