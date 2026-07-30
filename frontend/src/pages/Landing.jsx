import { Link } from "react-router-dom";
import { Landmark, ScrollText, ShieldCheck, ArrowRight } from "lucide-react";
import { DEMO_ID } from "../api.js";
import { Button } from "../components/ui.jsx";
import PublicShell from "../components/PublicShell.jsx";

const features = [
  [Landmark, "Dedicated account", "One real NUBAN per group"],
  [ScrollText, "Live public ledger", "Every transfer visible"],
  [ShieldCheck, "Committee approvals", "No solo spending"],
];

const steps = [
  "Create your collective — a dedicated bank account is provisioned instantly.",
  "Members transfer dues from any Nigerian bank; each payment lands on the public ledger automatically.",
  "Spending needs a public reason and a committee approval — then the payout goes straight to the verified recipient.",
];

export default function Landing() {
  return (
    <PublicShell>
      <div className="mx-auto max-w-2xl">
        {/* Hero: the claim on a dark "vault" panel — the same surface the
            balance lives on inside the app, so the brand reads as one object. */}
        <div className="overflow-hidden rounded-3xl bg-panel px-6 py-12 text-center sm:px-10 sm:py-14">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-on-panel-dim">
            Transparent collective treasury
          </p>
          <h1 className="mt-4 text-4xl font-bold leading-[1.05] tracking-tight text-on-panel text-balance sm:text-5xl">
            Every naira <span className="text-brand">in the open.</span>
          </h1>
          <p className="mx-auto mt-4 max-w-md text-sm leading-relaxed text-on-panel-dim">
            A dedicated bank account with a live public ledger for your association, co-op or alumni
            group. No more "trust the treasurer" — trust the ledger.
          </p>
          <div className="mx-auto mt-7 flex max-w-xs flex-col gap-2.5">
            <Link to="/create">
              <Button className="w-full">Create a collective</Button>
            </Link>
            <Link
              to={`/c/${DEMO_ID}?m=m1`}
              className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl px-4 text-sm font-semibold text-on-panel transition-colors hover:bg-white/10"
            >
              Explore the live demo
              <ArrowRight size={16} strokeWidth={2} />
            </Link>
          </div>
          <p className="mt-4 text-xs text-on-panel-dim">
            Already a member?{" "}
            <Link to="/login" className="font-medium text-on-panel underline-offset-2 hover:underline">
              Log in
            </Link>
          </p>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {features.map(([Icon, title, sub]) => (
            <div key={title} className="rounded-2xl border border-line bg-surface p-5">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft text-brand-ink">
                <Icon size={18} strokeWidth={1.75} />
              </span>
              <p className="mt-3 text-sm font-semibold text-ink">{title}</p>
              <p className="mt-0.5 text-xs text-muted">{sub}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 rounded-2xl border border-line bg-surface p-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">How it works</p>
          <ol className="mt-4 space-y-4">
            {steps.map((step, i) => (
              <li key={i} className="flex gap-3.5">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-panel font-mono text-xs font-semibold text-on-panel">
                  {i + 1}
                </span>
                <p className="text-sm leading-relaxed text-ink">{step}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </PublicShell>
  );
}
