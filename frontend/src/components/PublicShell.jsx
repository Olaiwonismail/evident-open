import { Link } from "react-router-dom";

// Layout for pages outside a collective: landing, auth, create, accept-invite.
export default function PublicShell({ children }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <Link to="/" className="text-lg font-bold tracking-tight text-ink">
            evident<span className="text-brand-ink">.</span>
          </Link>
          <span className="text-xs text-muted">Every naira in the open</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-12">{children}</main>
    </div>
  );
}
