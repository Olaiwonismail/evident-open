import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Clock, ArrowRight } from "lucide-react";
import { api } from "../api.js";
import { naira, groupDigits } from "../lib/format.js";
import { Card, CardHeader, Button, Spinner, CopyButton, StatusBadge } from "../components/ui.jsx";
import LedgerList from "../components/LedgerList.jsx";

// The screen everyone opens to: live balance, what's pending, recent
// activity, and one obvious way to pay in. The glass box at a glance.
export default function Home() {
  const { collectiveId, me, isCommittee } = useOutletContext();

  const ledger = useQuery({
    queryKey: ["ledger", collectiveId],
    queryFn: () => api.getLedger(collectiveId),
    refetchInterval: 10_000, // live: payments appear without a refresh
  });
  const expenses = useQuery({
    queryKey: ["expenses", collectiveId],
    queryFn: () => api.getExpenses(collectiveId),
    refetchInterval: 15_000,
  });

  if (ledger.isLoading) return <Spinner />;
  const { balance, entries = [] } = ledger.data || {};
  const pending = (expenses.data || []).filter((e) => e.status === "pending");
  // every payment goes to a member's OWN dedicated pay-in account — there's no
  // collective-wide account surfaced in the UI.
  const personalAccount = !!me?.bank_account_number;

  return (
    <div className="space-y-6">
      {/* Balance + account: the balance leads as a dark "vault" panel; the
          account number sits beside it, no side-stripe gimmick. */}
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="flex flex-col justify-between rounded-2xl bg-panel p-6 lg:col-span-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-on-panel-dim">
              Collective balance
            </p>
            <p className="mt-2 font-mono text-4xl font-bold tracking-tight text-on-panel sm:text-5xl">
              {naira(balance ?? 0)}
            </p>
            <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-on-panel-dim">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-pos opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-pos" />
              </span>
              Live — updates automatically
            </p>
          </div>
          {me && (
            <Link to={`/c/${collectiveId}/pay`} className="mt-6">
              <Button className="w-full sm:w-auto">Pay my dues</Button>
            </Link>
          )}
        </div>

        <Card className="flex flex-col justify-center p-6 lg:col-span-2">
          {personalAccount ? (
            <>
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                Your pay-in account
              </p>
              <p className="mt-2 font-mono text-2xl font-semibold tracking-wide text-ink">
                {groupDigits(me.bank_account_number)}
              </p>
              <p className="mt-1 text-sm text-muted">{me.bank_name}</p>
              <div className="mt-4 flex items-center justify-between gap-3 border-t border-line pt-4">
                <p className="text-xs text-muted">Dues here are credited to you</p>
                <CopyButton text={me.bank_account_number} label="Copy" />
              </div>
            </>
          ) : (
            <>
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                Pay-in account
              </p>
              <p className="mt-2 text-sm text-ink">
                Each member pays into their own dedicated account.
              </p>
              <p className="mt-1 text-xs text-muted">
                Open your personal invite link to see yours.
              </p>
            </>
          )}
        </Card>
      </div>

      {pending.length > 0 && (
        <Card>
          <CardHeader
            title={`Pending approval (${pending.length})`}
            subtitle={
              isCommittee
                ? "These requests are waiting on the committee — including you."
                : "Money that can't move until the committee decides."
            }
            action={
              isCommittee ? (
                <Link to={`/c/${collectiveId}/approvals`}>
                  <Button className="min-h-9 px-3 text-xs">Review now</Button>
                </Link>
              ) : null
            }
          />
          <ul className="divide-y divide-line">
            {pending.map((e) => (
              <li key={e.id}>
                <Link
                  to={`/c/${collectiveId}/expenses/${e.id}`}
                  className="flex items-center justify-between gap-4 px-5 py-3 transition-colors hover:bg-surface-2 sm:px-6"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-warn-soft text-warn-ink">
                      <Clock size={16} strokeWidth={1.75} />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink">{e.reason}</p>
                      <p className="text-xs text-muted">requested by {e.requested_by_name}</p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <p className="font-mono text-sm font-semibold tabular-nums text-ink">{naira(e.amount)}</p>
                    <StatusBadge status={e.status} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <CardHeader
          title="Recent activity"
          subtitle="The last few movements — the full history is one tap away."
          action={
            <Link
              to={`/c/${collectiveId}/ledger`}
              className="inline-flex min-h-9 items-center gap-1 rounded-lg px-2 text-sm font-semibold text-brand-ink hover:bg-brand-soft"
            >
              Full ledger
              <ArrowRight size={15} strokeWidth={2} />
            </Link>
          }
        />
        <LedgerList entries={entries} limit={5} />
      </Card>
    </div>
  );
}
