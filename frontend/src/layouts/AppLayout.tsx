import { Outlet } from "react-router-dom";

import { BrandMark } from "../components/operations/Icons";

export function AppLayout() {
  return (
    <div className="min-h-screen bg-[#071011] text-slate-100">
      <header className="sticky top-0 z-[1000] border-b border-slate-800/90 bg-[#071011]/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1560px] items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 text-emerald-300">
            <BrandMark />
            <div>
              <p className="text-sm font-semibold tracking-[0.16em] text-white">
                AIRVIEW AI
              </p>
              <p className="text-[10px] uppercase tracking-[0.12em] text-slate-500">
                Smart city intervention intelligence
              </p>
            </div>
          </div>
          <div className="hidden items-center gap-3 sm:flex">
            <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.7)]" />
            <span className="text-xs text-slate-400">Operational dashboard</span>
          </div>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
