import { Users, Landmark, UserCheck, ArrowRight, Undo2 } from "lucide-react";
import { naira } from "../lib/format.js";

// A glanceable picture of the glass box: dues flow in from members, sit in
// one visible pool, and only leave to verified recipients via approvals.
// Every number is computed from the ledger itself, so the diagram can't lie.
export default function MoneyFlow({ entries, memberCount, balance }) {
  const totalIn = entries
    .filter((e) => e.type === "contribution")
    .reduce((s, e) => s + (e.amount || 0), 0);
  const payouts = entries.filter((e) => e.type === "expense");
  const totalOut = payouts.reduce((s, e) => s - (e.amount || 0), 0);
  const refunded = entries
    .filter((e) => e.type === "expense_refunded" || e.type === "expense_failed")
    .reduce((s, e) => s + (e.amount || 0), 0);
  const netOut = totalOut - refunded;

  return (
    <div className="rounded-2xl border border-line bg-surface p-5 shadow-sm shadow-black/[0.03] sm:p-6">
      <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-stretch">
        <FlowNode
          icon={Users}
          tone="pos"
          title="Members"
          big={`${memberCount}`}
          sub="pay dues from any bank"
        />
        <FlowArrow amount={totalIn} label="dues in" tone="text-pos-ink" />
        <FlowNode
          icon={Landmark}
          title="Collective pool"
          big={naira(balance ?? 0)}
          sub="held in the open — everyone sees this"
          highlight
        />
        <FlowArrow amount={netOut} label="approved payouts" tone="text-neg-ink" />
        <FlowNode
          icon={UserCheck}
          tone="info"
          title="Verified recipients"
          big={`${payouts.length} payout${payouts.length === 1 ? "" : "s"}`}
          sub="public reason + approver on each"
        />
      </div>
      {refunded > 0 && (
        <p className="mt-4 flex items-center justify-center gap-1.5 border-t border-line pt-3 text-xs text-muted">
          <Undo2 size={13} strokeWidth={1.75} />
          {naira(refunded)} returned after a failed transfer — money never disappears quietly.
        </p>
      )}
    </div>
  );
}

function FlowNode({ icon: Icon, tone = "brand", title, big, sub, highlight }) {
  if (highlight) {
    return (
      <div className="flex flex-1 flex-col items-center rounded-xl bg-panel p-4 text-center">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-on-panel">
          <Icon size={18} strokeWidth={1.75} />
        </span>
        <p className="mt-2 text-[11px] font-medium uppercase tracking-wide text-on-panel-dim">{title}</p>
        <p className="mt-0.5 text-lg font-bold tracking-tight text-on-panel">{big}</p>
        <p className="mt-0.5 text-[11px] text-on-panel-dim">{sub}</p>
      </div>
    );
  }
  const toneChip = {
    pos: "bg-pos-soft text-pos-ink",
    info: "bg-info-soft text-info-ink",
    brand: "bg-brand-soft text-brand-ink",
  };
  return (
    <div className="flex flex-1 flex-col items-center rounded-xl border border-line bg-surface-2 p-4 text-center">
      <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${toneChip[tone]}`}>
        <Icon size={18} strokeWidth={1.75} />
      </span>
      <p className="mt-2 text-[11px] font-medium uppercase tracking-wide text-muted">{title}</p>
      <p className="mt-0.5 text-lg font-bold tracking-tight text-ink">{big}</p>
      <p className="mt-0.5 text-[11px] text-muted">{sub}</p>
    </div>
  );
}

function FlowArrow({ amount, label, tone }) {
  return (
    <div className="flex shrink-0 flex-col items-center justify-center gap-0.5 px-1 py-1 sm:px-2">
      <p className={`font-mono text-sm font-semibold tabular-nums ${tone}`}>{naira(amount)}</p>
      <ArrowRight size={18} strokeWidth={2} className="hidden text-faint sm:block" />
      <ArrowRight size={16} strokeWidth={2} className="rotate-90 text-faint sm:hidden" />
      <p className="text-[10px] uppercase tracking-wide text-faint">{label}</p>
    </div>
  );
}
