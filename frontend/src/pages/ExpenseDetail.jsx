import { useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { api, ALLOW_SELF_APPROVAL } from "../api.js";
import { naira, formatTime, groupDigits } from "../lib/format.js";
import { Card, Button, Input, Spinner, StatusBadge, ErrorNote } from "../components/ui.jsx";

// The full story of one request: who asked, who decided (and why), and
// whether the money actually moved. This is where members follow an expense.
export default function ExpenseDetail() {
  const { collectiveId, me, isCommittee } = useOutletContext();
  const { expenseId } = useParams();
  const queryClient = useQueryClient();

  const q = useQuery({
    queryKey: ["expense", collectiveId, expenseId],
    queryFn: () => api.getExpense(collectiveId, expenseId),
    refetchInterval: 15_000,
  });
  // the backend stores only the bank code — resolve its display name
  const banks = useQuery({
    queryKey: ["banks", collectiveId],
    queryFn: () => api.getBanks(collectiveId),
    staleTime: Infinity,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["expense", collectiveId, expenseId] });
    queryClient.invalidateQueries({ queryKey: ["expenses", collectiveId] });
    queryClient.invalidateQueries({ queryKey: ["ledger", collectiveId] });
  };
  const approve = useMutation({
    mutationFn: () => api.approveExpense(collectiveId, expenseId, me.id),
    onSuccess: refresh,
  });
  const reject = useMutation({
    mutationFn: (reason) => api.rejectExpense(collectiveId, expenseId, me.id, reason),
    onSuccess: refresh,
  });

  if (q.isLoading) return <Spinner />;
  if (q.isError)
    return (
      <div className="py-20 text-center text-sm text-muted">
        Expense not found.{" "}
        <Link className="text-brand-ink underline" to={`/c/${collectiveId}/expenses`}>
          Back to expenses
        </Link>
      </div>
    );

  const e = q.data;
  const bank = (banks.data || []).find(
    (b) => (b.bankCode || b.code) === e.recipient_bank_code
  );
  const bankName = e.recipient_bank_name || bank?.bankName || bank?.name || e.recipient_bank_code;
  const canDecide =
    isCommittee && e.status === "pending" && (ALLOW_SELF_APPROVAL || me?.id !== e.requested_by);

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <Link
        to={`/c/${collectiveId}/expenses`}
        className="inline-flex items-center gap-1 text-sm text-muted transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} strokeWidth={2} />
        All expenses
      </Link>

      <Card className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-mono text-3xl font-bold tracking-tight text-ink">{naira(e.amount)}</p>
            <p className="mt-1 text-sm font-medium text-ink">{e.reason}</p>
          </div>
          <StatusBadge status={e.status} />
        </div>

        <dl className="mt-6 grid gap-4 border-t border-line pt-5 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">Recipient</dt>
            <dd className="mt-1 text-sm font-medium text-ink">{e.recipient_name}</dd>
            <dd className="font-mono text-xs text-muted">
              {groupDigits(e.recipient_account)} · {bankName}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">Receipt</dt>
            <dd className="mt-1 text-sm">
              {e.receipt_url ? (
                <a
                  href={e.receipt_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-medium text-brand-ink hover:underline"
                >
                  View receipt
                  <ExternalLink size={13} strokeWidth={2} />
                </a>
              ) : (
                <span className="text-muted">None attached</span>
              )}
            </dd>
          </div>
        </dl>
      </Card>

      <Card className="p-6">
        <h2 className="mb-4 text-sm font-semibold text-ink">History</h2>
        <Timeline expense={e} />
      </Card>

      {canDecide && (
        <Card className="border-warn/40 p-6">
          <h2 className="text-sm font-semibold text-ink">Your decision</h2>
          <p className="mt-1 text-xs text-muted">
            Approving disburses {naira(e.amount)} to {e.recipient_name} immediately, with your name
            on the ledger.
          </p>
          <DecisionControls approve={approve} reject={reject} />
        </Card>
      )}
    </div>
  );
}

function Timeline({ expense: e }) {
  const steps = [
    {
      tone: "bg-pos",
      title: `Requested by ${e.requested_by_name}`,
      when: e.timestamp,
    },
  ];

  if (e.status === "pending") {
    steps.push({
      tone: "bg-warn animate-pulse",
      title: "Waiting on the committee",
      sub: "Any committee member can approve or reject.",
    });
  } else if (e.status === "rejected") {
    steps.push({
      tone: "bg-neg",
      title: `Rejected by ${e.decided_by_name}`,
      sub: e.decision_reason ? `"${e.decision_reason}"` : null,
      when: e.decided_at,
    });
  } else {
    steps.push({
      tone: "bg-pos",
      title: `Approved by ${e.decided_by_name}`,
      when: e.decided_at,
    });
    if (e.status === "failed") {
      steps.push({
        tone: "bg-neg",
        title: "Payout failed — money returned to the pool",
        sub: e.failure_reason,
      });
    } else if (e.status === "manual_review") {
      steps.push({
        tone: "bg-review",
        title: "Transfer status unclear — flagged for manual review",
        sub: "The payout is being confirmed with the bank before the ledger is updated.",
      });
    } else if (e.status === "disbursing") {
      steps.push({
        tone: "bg-info animate-pulse",
        title: "Disbursing…",
        sub: `Sending to ${e.recipient_name}.`,
      });
    } else {
      steps.push({
        tone: "bg-pos",
        title: `Paid to ${e.recipient_name}`,
        when: e.paid_at,
      });
    }
  }

  return (
    <ol className="space-y-0">
      {steps.map((s, i) => (
        <li key={i} className="relative flex gap-3 pb-5 last:pb-0">
          {i < steps.length - 1 && (
            <span className="absolute left-[5px] top-4 h-full w-px bg-line-strong" />
          )}
          <span className={`relative mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full ${s.tone}`} />
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">{s.title}</p>
            {s.sub && <p className="mt-0.5 text-xs text-muted">{s.sub}</p>}
            {s.when && <p className="mt-0.5 font-mono text-xs text-faint">{formatTime(s.when)}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function DecisionControls({ approve, reject }) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const busy = approve.isPending || reject.isPending;

  return (
    <div className="mt-4 space-y-3">
      <div className="flex gap-3">
        <Button disabled={busy} onClick={() => approve.mutate()}>
          {approve.isPending ? "Disbursing…" : "Approve & pay"}
        </Button>
        <Button variant="danger" disabled={busy} onClick={() => setRejecting(!rejecting)}>
          Reject
        </Button>
      </div>
      {rejecting && (
        <div className="flex gap-2">
          <div className="flex-1">
            <Input
              placeholder="Reason for rejection — goes on the public ledger"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <Button variant="danger" disabled={!reason || busy} onClick={() => reject.mutate(reason)}>
            Confirm reject
          </Button>
        </div>
      )}
      <ErrorNote error={approve.error || reject.error} />
    </div>
  );
}
