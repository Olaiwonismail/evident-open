import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api.js";
import { setSessionMember, setSessionToken } from "../lib/session.js";
import { Check, PartyPopper } from "lucide-react";
import { Card, Button, Input, Select, ErrorNote, CopyButton, IconChip } from "../components/ui.jsx";
import PublicShell from "../components/PublicShell.jsx";

// Three steps: group details → light identity check on the organizer →
// account number reveal. Finishing step 2 is what provisions the
// virtual account behind the scenes.
export default function CreateCollective() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    name: "",
    purpose: "",
    dues_amount: "",
    dues_frequency: "monthly",
    organizer_name: "",
    organizer_phone: "",
    organizer_email: "",
    id_number: "",
  });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const identity = useMutation({
    mutationFn: () => api.verifyIdentity({ id_number: form.id_number }),
  });

  const create = useMutation({
    mutationFn: () =>
      api.createCollective({
        ...form,
        dues_amount: form.dues_amount ? Number(form.dues_amount) : null,
        organizer_email: form.organizer_email || null,
        organizer_phone: form.organizer_phone || null,
      }),
    onSuccess: (c) => {
      setSessionMember(c.id, c.organizer_id);
      // Returned once and only here. Without keeping it, the organizer would be
      // locked out of the collective they just created.
      setSessionToken(c.id, c.organizer_token);
    },
  });

  if (create.isSuccess) {
    const c = create.data;
    const publicLink = `${window.location.origin}/c/${c.id}`;
    return (
      <PublicShell>
        <Card className="mx-auto max-w-xl p-8">
          <div className="mb-6 text-center">
            <div className="mb-3 flex justify-center">
              <IconChip icon={PartyPopper} tone="pos" size="lg" />
            </div>
            <h2 className="text-xl font-bold text-ink">{c.name} is live</h2>
            <p className="mt-1 text-sm text-muted">
              Invite your members and each gets their own dedicated pay-in account — every transfer
              lands on the public ledger, credited to the right person automatically.
            </p>
          </div>

          <div className="rounded-2xl bg-panel p-6 text-center">
            <p className="text-xs uppercase tracking-wide text-on-panel-dim">Next step</p>
            <p className="mt-2 text-lg font-semibold text-on-panel">Invite your members</p>
            <p className="mt-1 text-sm text-on-panel-dim">
              Each member gets their own dedicated pay-in account, so every payment is credited to
              them automatically.
            </p>
          </div>

          <div className="mt-6 flex items-center justify-between gap-3 rounded-xl border border-line p-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">Public ledger link — share with everyone</p>
              <p className="truncate font-mono text-xs text-muted">{publicLink}</p>
            </div>
            <CopyButton text={publicLink} />
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <Button onClick={() => navigate(`/c/${c.id}/members`)}>Invite members →</Button>
            <Button variant="secondary" onClick={() => navigate(`/c/${c.id}`)}>
              Open dashboard
            </Button>
          </div>
        </Card>
      </PublicShell>
    );
  }

  return (
    <PublicShell>
      <div className="mx-auto max-w-xl">
        <StepTracker step={step} />

        {step === 1 && (
          <Card className="p-8">
            <h1 className="mb-1 text-lg font-bold text-ink">Set up your collective</h1>
            <p className="mb-6 text-sm text-muted">
              Name the group, state its purpose, and set the dues. This is what members will see.
            </p>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                setStep(2);
              }}
            >
              <Input
                label="Collective name"
                placeholder="e.g. Ikeja GRA Estate Levy Fund"
                value={form.name}
                onChange={set("name")}
                required
              />
              <Input
                label="Purpose"
                placeholder="What is this group raising money for?"
                value={form.purpose}
                onChange={set("purpose")}
                required
              />
              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="Dues amount (₦, optional)"
                  type="number"
                  min="0"
                  placeholder="5000"
                  value={form.dues_amount}
                  onChange={set("dues_amount")}
                />
                <Select label="Frequency" value={form.dues_frequency} onChange={set("dues_frequency")}>
                  <option value="monthly">Monthly</option>
                  <option value="quarterly">Quarterly</option>
                  <option value="annual">Annual</option>
                </Select>
              </div>

              <hr className="border-line" />
              <p className="text-sm font-semibold text-ink">You (the organizer)</p>
              <Input label="Your name" value={form.organizer_name} onChange={set("organizer_name")} required />
              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="Phone"
                  hint="Used to match your own transfers to you"
                  value={form.organizer_phone}
                  onChange={set("organizer_phone")}
                  required
                />
                <Input
                  label="Email (optional)"
                  type="email"
                  value={form.organizer_email}
                  onChange={set("organizer_email")}
                />
              </div>
              <Button type="submit" className="w-full">
                Continue to identity check
              </Button>
            </form>
          </Card>
        )}

        {step === 2 && (
          <Card className="p-8">
            <h1 className="mb-1 text-lg font-bold text-ink">Verify your identity</h1>
            <p className="mb-6 text-sm text-muted">
              A light check on you as the organizer — the collective's bank account inherits
              verification underneath, so this stays quick.
            </p>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                if (identity.isSuccess) create.mutate();
                else identity.mutate();
              }}
            >
              <Input
                label="BVN or NIN"
                inputMode="numeric"
                maxLength={11}
                placeholder="11 digits"
                value={form.id_number}
                onChange={(e) => {
                  setForm({ ...form, id_number: e.target.value.replace(/\D/g, "") });
                  identity.reset();
                }}
                hint="Only used to confirm you are who you say — never shown to members."
                required
              />
              {!identity.isSuccess && (
                <p className="rounded-xl bg-warn-soft px-3 py-2 text-xs text-warn-ink">
                  MVP: verification is instant — any 11 digits pass. Manual review backs it up in
                  production.
                </p>
              )}
              {identity.isSuccess && (
                <p className="flex items-center gap-1.5 rounded-xl bg-pos-soft px-3 py-2 text-sm font-medium text-pos-ink">
                  <Check size={15} strokeWidth={2.25} /> Identity verified — you're good to go.
                </p>
              )}
              <ErrorNote error={identity.error || create.error} />
              <Button
                type="submit"
                className="w-full"
                disabled={identity.isPending || create.isPending || form.id_number.length !== 11}
              >
                {identity.isPending
                  ? "Verifying…"
                  : create.isPending
                    ? "Creating your account…"
                    : identity.isSuccess
                      ? "Create collective"
                      : "Verify identity"}
              </Button>
              {!identity.isSuccess && (
                <button
                  type="button"
                  onClick={() => create.mutate()}
                  disabled={create.isPending}
                  className="w-full text-center text-xs text-muted underline-offset-2 hover:text-ink hover:underline"
                >
                  Can't verify right now? Continue — we'll review manually.
                </button>
              )}
              <button
                type="button"
                onClick={() => setStep(1)}
                className="w-full text-center text-xs text-muted hover:text-ink"
              >
                ← Back to details
              </button>
            </form>
          </Card>
        )}

        <p className="mt-6 text-center text-xs text-muted">
          Already in a collective?{" "}
          <Link to="/login" className="font-medium text-brand-ink hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </PublicShell>
  );
}

function StepTracker({ step }) {
  const steps = ["Group details", "Identity check", "Account ready"];
  return (
    <ol className="mb-6 flex items-center justify-center gap-2">
      {steps.map((label, i) => {
        const n = i + 1;
        const state = n < step ? "done" : n === step ? "active" : "todo";
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full font-mono text-xs font-bold ${
                state === "done"
                  ? "bg-brand text-on-brand"
                  : state === "active"
                    ? "bg-brand-soft text-brand-ink ring-2 ring-brand"
                    : "bg-surface-2 text-faint"
              }`}
            >
              {state === "done" ? <Check size={13} strokeWidth={2.5} /> : n}
            </span>
            <span
              className={`text-xs font-medium ${state === "active" ? "text-ink" : "text-muted"}`}
            >
              {label}
            </span>
            {n < steps.length && <span className="h-px w-6 bg-line-strong" />}
          </li>
        );
      })}
    </ol>
  );
}
