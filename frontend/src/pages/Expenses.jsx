import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus, ReceiptText } from "lucide-react";
import { api } from "../api.js";
import { naira, formatTime } from "../lib/format.js";
import { Card, CardHeader, Button, Spinner, EmptyState, StatusBadge } from "../components/ui.jsx";

export default function Expenses() {
  const { collectiveId, me } = useOutletContext();
  const expenses = useQuery({
    queryKey: ["expenses", collectiveId],
    queryFn: () => api.getExpenses(collectiveId),
    refetchInterval: 15_000,
  });

  return (
    <Card>
      <CardHeader
        title="Expense requests"
        subtitle="Money only leaves the pool with a public reason and committee approval."
        action={
          me ? (
            <Link to={`/c/${collectiveId}/expenses/new`}>
              <Button className="min-h-9 px-3 text-xs">
                <Plus size={15} strokeWidth={2.25} />
                New request
              </Button>
            </Link>
          ) : null
        }
      />
      {expenses.isLoading ? (
        <Spinner />
      ) : (expenses.data || []).length === 0 ? (
        <EmptyState
          icon={ReceiptText}
          title="No expenses yet"
          subtitle="Requests submitted by members appear here."
        />
      ) : (
        <ul className="divide-y divide-line">
          {expenses.data.map((e) => (
            <li key={e.id}>
              <Link
                to={`/c/${collectiveId}/expenses/${e.id}`}
                className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-surface-2 sm:px-6"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">{e.reason}</p>
                  <p className="truncate text-xs text-muted">
                    to {e.recipient_name} · requested by {e.requested_by_name} ·{" "}
                    {formatTime(e.timestamp)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <p className="font-mono text-sm font-semibold tabular-nums text-ink">{naira(e.amount)}</p>
                  <StatusBadge status={e.status} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
