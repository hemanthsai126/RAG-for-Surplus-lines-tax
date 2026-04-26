import { NavLink, Outlet } from "react-router-dom";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    isActive
      ? "bg-teal-100 text-teal-900"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
  }`;

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col pb-16">
      <nav className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <NavLink to="/" className="group flex items-baseline gap-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-teal-700">Insurance</span>
            <span className="text-lg font-semibold tracking-tight text-slate-900 group-hover:text-teal-800">
              Insurance RAG
            </span>
          </NavLink>
          <div className="flex flex-wrap items-center justify-end gap-1">
            <NavLink to="/" end className={navClass}>
              Copilot
            </NavLink>
            <NavLink to="/compare" className={navClass}>
              Compare quotes
            </NavLink>
            <NavLink to="/risko" className={navClass}>
              Risko
            </NavLink>
            <NavLink to="/about" className={navClass}>
              About
            </NavLink>
          </div>
        </div>
      </nav>

      <div className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </div>

      <footer className="mx-auto mt-auto w-full max-w-6xl px-6 pb-8 pt-10 text-center text-xs text-slate-500">
        Educational demo — not insurance advice. Optional XGBoost retrain: place{" "}
        <code className="font-mono text-slate-700">training.csv</code> in{" "}
        <code className="font-mono text-slate-700">app/copilot/data/</code> with required feature columns.
      </footer>
    </div>
  );
}
