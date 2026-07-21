import { Link, Outlet } from "react-router-dom";

export function AppLayout() {
  return (
    <div className="min-h-screen bg-ink text-white">
      <header className="border-b border-line/70">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5 lg:px-10">
          <Link className="flex items-center gap-3" to="/" aria-label="AirView AI home">
            <span className="grid h-9 w-9 place-items-center rounded-lg border border-air/40 bg-air/10">
              <span className="h-3 w-3 rounded-full bg-air shadow-[0_0_16px_rgba(83,214,162,0.8)]" />
            </span>
            <span className="text-sm font-semibold tracking-[0.16em]">AIRVIEW AI</span>
          </Link>
          <nav className="flex items-center gap-5 text-xs font-medium uppercase tracking-[0.14em] text-mist">
            <Link className="transition hover:text-air" to="/data-readiness">Data readiness</Link>
            <span className="hidden sm:block">Smart city intelligence platform</span>
          </nav>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="border-t border-line/70">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-6 py-6 text-xs text-mist sm:flex-row sm:items-center sm:justify-between lg:px-10">
          <span>Team Dextron · ET AI Hackathon 2.0</span>
          <span>Foundation stage · No live environmental data connected</span>
        </div>
      </footer>
    </div>
  );
}
