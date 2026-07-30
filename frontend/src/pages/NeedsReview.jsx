import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Target } from "lucide-react";
import { api } from "../api.js";
import { naira, formatTime } from "../lib/format.js";
import { Card, CardHeader, Button, Spinner, EmptyState, ErrorNote, Badge } from "../components/ui.jsx";

// Money that arrived but couldn't be matched to a member lands here, so
// nothing is ever quietly absorbed. Attributing it to the right member is
// what moves the naira onto the ledger, under their name.
export default function NeedsReview() {
  const { collectiveId, members, isCommittee } = useOutletContext();
  const queryClient = useQueryClient();

  const unmatched = useQuery({
    queryKey: ["unmatched", collectiveId],
    queryFn: () => api.getUnmatched(collectiveId),
    refetchInterval: 30_000,
  });

  const resolve = useMutation({
    mutationFn: ({ unmatchedId, memberId }) =>
      api.resolveUnmatched(collectiveId, unmatchedId, memberId),
    onSuccess: (_, { memberId }) => {
      queryClient.invalidateQueries({ queryKey: ["unmatched", collectiveId] });
      queryClient.invalidateQueries({ queryKey: ["ledger", collectiveId] });
      queryClient.invalidateQueries({ queryKey: ["contributions", collectiveId, memberId] });
    },
  });

  if (!isCommittee) {
    return (
      <Card>
        <EmptyState
          icon={ShieldCheck}
          tone="info"
          title="Committee only"
          subtitle="Only the organizer and committee can attribute unmatched payments."
        />
      </Card>
    );
  }

  const items = (unmatched.data || []).filter((u) => u.status !== "resolved");

  return (
    <Card>
      <CardHeader
        title={`Needs review${items.length ? ` (${items.length})` : ""}`}
        subtitle="Transfers we couldn't match to a member. Attributing one puts the money on the ledger under the right member's name."
      />
      {unmatched.isLoading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Target}
          tone="pos"
          title="All clear"
          subtitle="Every transfer has been matched to a member."
        />
      ) : (
        <ul className="divide-y divide-line">
          {items.map((u) => (
            <ReviewRow key={u.id} item={u} members={members} resolve={resolve} />
          ))}
        </ul>
      )}
      <div className="px-6 pb-4">
        <ErrorNote error={resolve.error} />
      </div>
    </Card>
  );
}

function ReviewRow({ item, members, resolve }) {
  const [memberId, setMemberId] = useState("");
  const busy = resolve.isPending && resolve.variables?.unmatchedId === item.id;

  return (
    <li className="px-5 py-4 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">
            {item.sender_name || "Unknown sender"}{" "}
            <span className="font-mono text-muted">
              ({item.sender_account || "no account"}
              {item.sender_bank ? ` · ${item.sender_bank}` : ""})
            </span>
          </p>
          <p className="font-mono text-xs text-muted">{formatTime(item.timestamp)}</p>
        </div>
        <div className="flex items-center gap-3">
          <p className="font-mono text-sm font-semibold tabular-nums text-ink">{naira(item.amount)}</p>
          <Badge tone="review">needs review</Badge>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={memberId}
          onChange={(e) => setMemberId(e.target.value)}
          className="min-h-11 flex-1 rounded-xl border border-line-strong bg-surface px-3 text-sm text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/25"
        >
          <option value="">Who sent this payment?</option>
          {members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
        <Button
          disabled={!memberId || busy}
          onClick={() => resolve.mutate({ unmatchedId: item.id, memberId })}
        >
          {busy ? "Attributing…" : "Attribute payment"}
        </Button>
      </div>
    </li>
  );
}
