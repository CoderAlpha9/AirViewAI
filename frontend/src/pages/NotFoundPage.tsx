import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="mx-auto flex min-h-[70vh] max-w-7xl flex-col justify-center px-6 lg:px-10">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-air">404</p>
      <h1 className="mt-4 text-4xl font-semibold">Page not found</h1>
      <p className="mt-3 text-mist">This route is not part of the current platform foundation.</p>
      <Link className="mt-8 w-fit border-b border-air pb-1 text-sm text-air" to="/">
        Return to overview
      </Link>
    </section>
  );
}

