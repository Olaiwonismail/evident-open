import { Link, useParams } from "react-router-dom";
import { ArrowDownLeft, ArrowUpRight, Undo2, Ban, Circle, ScrollText } from "lucide-react";
import { naira, formatTime } from "../lib/format.js";
import { EmptyState, StatusBadge, IconChip } from "./ui.jsx";

// icon + tone per ledger entry type. Money direction reads instantly:
// down-left = in, up-right = out, undo = reversed, ban = rejected.
const entryStyle = {
  contribution: [ArrowDownLeft, "pos"],
  expense: [ArrowUpRight, "neg"],
  expense_failed: [Undo2, "info"],
  expense_refunded: [Undo2, "info"],
  expense_rejected: [Ban, "neutral"],
};

const amountColor = {
  contribution: "text-pos-ink",
  expense: "text-neg-ink",
  expense_failed: "text-info-ink",
  expense_refunded: "text-info-ink",
};

// One ledger row. Rejected requests carry no money — they show a status badge
// instead of a figure, but they stay on the record.
function Row({ entry }) {
  const { collectiveId } = useParams();
  const [Icon, tone] = entryStyle[entry.type] || [Circle, "neutral"];

  const body = (
    <>
      <IconChip icon={Icon} tone={tone} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-ink">{entry.description}</p>
        <p className="truncate text-xs text-muted">
          {entry.actor_name} · {formatTime(entry.timestamp)}
        </p>
      </div>
      <div className="shrink-0 text-right">
        {entry.type === "expense_rejected" ? (
          <StatusBadge status="rejected" />
        ) : (
          <>
            <p className={`font-mono text-sm font-semibold tabular-nums ${amountColor[entry.type] || "text-ink"}`}>
              {entry.amount >= 0 ? "+" : "−"}
              {naira(Math.abs(entry.amount))}
            </p>
            <p className="font-mono text-xs tabular-nums text-faint">bal {naira(entry.balance_after)}</p>
          </>
        )}
      </div>
    </>
  );

  if (entry.expense_id) {
    return (
      <Link
        to={`/c/${collectiveId}/expenses/${entry.expense_id}`}
        className="flex items-center gap-3.5 px-5 py-3.5 transition-colors hover:bg-surface-2 sm:px-6"
      >
        {body}
      </Link>
    );
  }
  return <div className="flex items-center gap-3.5 px-5 py-3.5 sm:px-6">{body}</div>;
}

export default function LedgerList({ entries, limit }) {
  if (!entries.length) {
    return (
      <EmptyState
        icon={ScrollText}
        title="No transactions yet"
        subtitle="The first transfer to the collective's account will appear here automatically."
      />
    );
  }
  const shown = limit ? entries.slice(0, limit) : entries;
  return (
    <ul className="divide-y divide-line">
      {shown.map((e) => (
        <li key={e.id}>
          <Row entry={e} />
        </li>
      ))}
    </ul>
  );
}
