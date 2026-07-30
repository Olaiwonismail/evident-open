import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, CircleDollarSign, Link2 } from "lucide-react";
import { api } from "../api.js";
import { naira, formatTime } from "../lib/format.js";
import { Card, CardHeader, Button, CopyButton, IconChip, Spinner, EmptyState, StatusBadge } from "../components/ui.jsx";

// A member's personal view: what they've paid, what they still owe, and
// their full contribution history.
export default function MyRecord() {
  const { collectiveId, me } = useOutletContext();

  const q = useQuery({
    queryKey: ["contributions", collectiveId, me?.id],
    queryFn: () => api.getContributions(collectiveId, me.id),
    enabled: !!me,
    refetchInterval: 15_000,
  });

  if (!me) {
    return (
      <Card>
        <EmptyState
          icon={KeyRound}
          title="Open your personal link to see your record"
          subtitle="Your contribution history is tied to who you are in the collective."
        />
      </Card>
    );
  }

  if (q.isLoading) return <Spinner />;
  const { dues_amount, dues_frequency, total_paid = 0, contributions = [] } = q.data || {};
  const pct = dues_amount ? Math.min(100, Math.round((total_paid / dues_amount) * 100)) : null;
  const owed = dues_amount ? Math.max(0, dues_amount - total_paid) : null;
  const personalLink = `${window.location.origin}/c/${collectiveId}?m=${me.id}`;

  return (
    <div className="space-y-6">
      {/* One record panel, not three stat cards: paid leads with a progress
          meter; owed and count trail as supporting facts. */}
      <Card className="p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Total paid</p>
            <p className="font-mono text-3xl font-bold tabular-nums text-pos-ink">{naira(total_paid)}</p>
          </div>
          <div className="text-right">
            <p className="text-xs uppercase tracking-wide text-muted">
              {owed === 0 ? "Status" : "Still owed"}
            </p>
            <p className={`font-mono text-xl font-semibold tabular-nums ${owed ? "text-warn-ink" : "text-pos-ink"}`}>
              {owed === null ? "—" : owed === 0 ? "up to date" : naira(owed)}
            </p>
          </div>
        </div>
        {pct !== null && (
          <div className="mt-4">
            <div className="h-2 overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full bg-pos transition-[width] duration-500 ease-out"
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="mt-1.5 flex items-center justify-between text-xs text-muted">
              <span>
                {pct >= 100 ? "Dues covered" : `${pct}% of ${naira(dues_amount)} ${dues_frequency || ""}`}
              </span>
              <span>
                {contributions.length} payment{contributions.length === 1 ? "" : "s"}
              </span>
            </div>
          </div>
        )}
        {owed > 0 && (
          <Link to={`/c/${collectiveId}/pay`} className="mt-5 block sm:inline-block">
            <Button className="w-full sm:w-auto">Pay now</Button>
          </Link>
        )}
      </Card>

      <Card className="p-5">
        <div className="flex items-start gap-3">
          <IconChip icon={Link2} tone="brand" />
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-ink">Your personal link</p>
            <p className="mt-0.5 text-sm text-muted">
              Save this — it's how you get back to your account and pay dues from any device.
              Keep it private: anyone with it can act as you.
            </p>
            <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-line p-3">
              <p className="truncate font-mono text-xs text-muted">{personalLink}</p>
              <CopyButton text={personalLink} label="Copy link" />
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Your contributions"
          subtitle="Every transfer into your personal pay-in account is credited to you and shows up here automatically."
        />
        {contributions.length === 0 ? (
          <EmptyState
            icon={CircleDollarSign}
            title="No contributions yet"
            subtitle="Transfers you make will show up here."
          />
        ) : (
          <ul className="divide-y divide-line">
            {contributions.map((c) => (
              <li key={c.id} className="flex items-center justify-between px-5 py-4 sm:px-6">
                <div>
                  <p className="font-mono text-sm font-semibold tabular-nums text-ink">{naira(c.amount)}</p>
                  <p className="text-xs text-muted">{formatTime(c.timestamp)}</p>
                </div>
                <StatusBadge status={c.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
