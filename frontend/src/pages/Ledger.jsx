import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api.js";
import { naira } from "../lib/format.js";
import { Card, CardHeader, Spinner } from "../components/ui.jsx";
import LedgerList from "../components/LedgerList.jsx";
import MoneyFlow from "../components/MoneyFlow.jsx";

const FILTERS = [
  { id: "all", label: "Everything" },
  { id: "in", label: "Money in" },
  { id: "out", label: "Money out" },
  { id: "flagged", label: "Rejected & failed" },
];

const matches = {
  all: () => true,
  in: (e) => e.type === "contribution" || e.type === "expense_refunded" || e.type === "expense_failed",
  out: (e) => e.type === "expense",
  flagged: (e) =>
    e.type === "expense_rejected" || e.type === "expense_refunded" || e.type === "expense_failed",
};

// The permanent record. Append-only — rejected and failed items stay visible
// alongside the wins, because that's the honesty claim.
export default function Ledger() {
  const { collectiveId, members } = useOutletContext();
  const [filter, setFilter] = useState("all");

  const ledger = useQuery({
    queryKey: ["ledger", collectiveId],
    queryFn: () => api.getLedger(collectiveId),
    refetchInterval: 10_000,
  });

  if (ledger.isLoading) return <Spinner />;
  const { balance, entries = [] } = ledger.data || {};
  const shown = entries.filter(matches[filter]);

  const totalIn = entries.filter((e) => (e.amount || 0) > 0).reduce((s, e) => s + e.amount, 0);
  const totalOut = entries.filter((e) => (e.amount || 0) < 0).reduce((s, e) => s - e.amount, 0);

  return (
    <div className="space-y-6">
      <MoneyFlow entries={entries} memberCount={members.length} balance={balance} />

      {/* One summary bar, not three identical cards: balance leads, in/out trail. */}
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-2xl border border-line bg-surface px-6 py-4 shadow-sm shadow-black/[0.03]">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted">Balance</p>
          <p className="font-mono text-2xl font-bold tabular-nums text-ink">{naira(balance ?? 0)}</p>
        </div>
        <div className="h-8 w-px bg-line" />
        <div>
          <p className="text-xs uppercase tracking-wide text-muted">Total in</p>
          <p className="font-mono text-lg font-semibold tabular-nums text-pos-ink">{naira(totalIn)}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-muted">Total out</p>
          <p className="font-mono text-lg font-semibold tabular-nums text-neg-ink">{naira(totalOut)}</p>
        </div>
      </div>

      <Card>
        <CardHeader
          title="Public ledger"
          subtitle="Append-only. Every naira in and out — including rejected and failed items — visible to every member, forever."
          action={
            <div className="flex flex-wrap gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  onClick={() => setFilter(f.id)}
                  className={`min-h-9 whitespace-nowrap rounded-full px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ${
                    filter === f.id ? "bg-ink text-canvas" : "text-muted hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          }
        />
        <LedgerList entries={shown} />
      </Card>
    </div>
  );
}
