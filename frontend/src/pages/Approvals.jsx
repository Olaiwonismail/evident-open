import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, CheckCircle2 } from "lucide-react";
import { api, ALLOW_SELF_APPROVAL } from "../api.js";
import { naira, formatTime } from "../lib/format.js";
import { Card, CardHeader, Button, Spinner, EmptyState, ErrorNote } from "../components/ui.jsx";

// The committee member's inbox. Approving here is what sets the real payout
// in motion — every decision carries the decider's name.
export default function Approvals() {
  const { collectiveId, me, isCommittee } = useOutletContext();
  const queryClient = useQueryClient();

  const expenses = useQuery({
    queryKey: ["expenses", collectiveId],
    queryFn: () => api.getExpenses(collectiveId),
    refetchInterval: 15_000,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["expenses", collectiveId] });
    queryClient.invalidateQueries({ queryKey: ["ledger", collectiveId] });
  };
  const approve = useMutation({
    mutationFn: (expenseId) => api.approveExpense(collectiveId, expenseId, me.id),
    onSuccess: refresh,
  });
  const reject = useMutation({
    mutationFn: ({ expenseId, reason }) => api.rejectExpense(collectiveId, expenseId, me.id, reason),
    onSuccess: refresh,
  });

  if (!isCommittee) {
    return (
      <Card>
        <EmptyState
          icon={ShieldCheck}
          tone="info"
          title="Committee only"
          subtitle="Only committee members can approve or reject expense requests."
        />
      </Card>
    );
  }

  const pending = (expenses.data || []).filter((e) => e.status === "pending");
  const decided = (expenses.data || []).filter((e) => e.status !== "pending").slice(0, 5);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title={`Awaiting your approval${pending.length ? ` (${pending.length})` : ""}`}
          subtitle="Approving disburses the money to the verified recipient immediately — your name goes on the ledger."
        />
        {expenses.isLoading ? (
          <Spinner />
        ) : pending.length === 0 ? (
          <EmptyState icon={CheckCircle2} tone="pos" title="Nothing pending" subtitle="New expense requests will land here." />
        ) : (
          <ul className="divide-y divide-line">
            {pending.map((e) => (
              <PendingRow
                key={e.id}
                expense={e}
                collectiveId={collectiveId}
                me={me}
                approve={approve}
                reject={reject}
              />
            ))}
          </ul>
        )}
        <div className="px-6 pb-4">
          <ErrorNote error={approve.error || reject.error} />
        </div>
      </Card>

      {decided.length > 0 && (
        <Card>
          <CardHeader title="Recently decided" subtitle="The last few calls the committee made." />
          <ul className="divide-y divide-line">
            {decided.map((e) => (
              <li key={e.id}>
                <Link
                  to={`/c/${collectiveId}/expenses/${e.id}`}
                  className="flex items-center justify-between gap-4 px-5 py-3 transition-colors hover:bg-surface-2 sm:px-6"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink">{e.reason}</p>
                    <p className="text-xs text-muted">
                      {e.status === "rejected" ? "rejected" : "approved"} by {e.decided_by_name}
                    </p>
                  </div>
                  <p className="font-mono text-sm font-semibold tabular-nums text-ink">{naira(e.amount)}</p>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function PendingRow({ expense, collectiveId, me, approve, reject }) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const busy = approve.isPending || reject.isPending;
  const isOwn = expense.requested_by === me.id && !ALLOW_SELF_APPROVAL;

  return (
    <li className="px-5 py-4 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to={`/c/${collectiveId}/expenses/${expense.id}`} className="min-w-0 flex-1">
          <p className="text-sm font-medium text-ink hover:underline">{expense.reason}</p>
          <p className="text-xs text-muted">
            to {expense.recipient_name} · requested by {expense.requested_by_name} ·{" "}
            {formatTime(expense.timestamp)}
          </p>
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <p className="font-mono text-sm font-semibold tabular-nums text-ink">{naira(expense.amount)}</p>
          {isOwn ? (
            <p className="text-xs italic text-muted">your own request — someone else decides</p>
          ) : (
            <>
              <Button className="min-h-9 px-3 text-xs" disabled={busy} onClick={() => approve.mutate(expense.id)}>
                {approve.isPending ? "Disbursing…" : "Approve & pay"}
              </Button>
              <Button variant="danger" className="min-h-9 px-3 text-xs" disabled={busy} onClick={() => setRejecting(!rejecting)}>
                Reject
              </Button>
            </>
          )}
        </div>
      </div>
      {rejecting && !isOwn && (
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            className="min-h-11 flex-1 rounded-xl border border-line-strong bg-surface px-3 text-sm text-ink outline-none placeholder:text-faint focus:border-brand focus:ring-2 focus:ring-brand/25"
            placeholder="Reason for rejection — goes on the public ledger"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <Button
            variant="danger"
            disabled={!reason || busy}
            onClick={() => reject.mutate({ expenseId: expense.id, reason })}
          >
            Confirm reject
          </Button>
        </div>
      )}
    </li>
  );
}
