import { CheckCircle2, FileSearch, ScanLine, TriangleAlert } from "lucide-react";
import { naira } from "../lib/format.js";
import { Badge, IconChip } from "./ui.jsx";

// The findings panel deliberately uses the `review` tone — the same one the app
// already uses for unmatched transfers, meaning "a human should look at this".
// It never uses `neg`, which is reserved for genuine failures (failed payouts,
// request errors). A flag is advice to the approver, not a blocked action, and
// the colour has to say so before the words do.
const severityLabel = {
  high: ["review", "worth checking"],
  medium: ["warn", "unusual"],
  low: ["neutral", "note"],
};

function Finding({ flag }) {
  const [tone, label] = severityLabel[flag.severity] || severityLabel.low;
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <Badge tone={tone} className="shrink-0">
        {label}
      </Badge>
      <span className="min-w-0 flex-1 text-[13px] leading-snug text-ink">{flag.message}</span>
    </li>
  );
}

// What the reader actually pulled off the document. Shown alongside the flags so
// the approver can sanity-check the machine rather than take its word for it.
function Extraction({ data }) {
  if (!data) return null;
  const rows = [
    ["Vendor", data.vendor],
    ["Document total", data.total_amount != null ? naira(data.total_amount) : null],
    ["Date", data.date],
  ].filter(([, v]) => v);
  if (!rows.length) return null;
  return (
    <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1.5 border-t border-line pt-3">
      {rows.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-[11px] uppercase tracking-wide text-muted">{k}</dt>
          <dd className="text-[13px] font-medium text-ink">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Result of the receipt check. `status` is one of:
 *   clean   — read successfully, nothing inconsistent
 *   flagged — findings a human should read before deciding
 *   error   — could not be read at all (never claims "clean")
 *   none    — no receipt checked
 */
export default function ReceiptCheck({ status, flags = [], extraction, className = "" }) {
  if (!status || status === "none") return null;

  if (status === "error") {
    return (
      <p
        role="status"
        className={`flex items-start gap-2 text-[13px] leading-snug text-muted ${className}`}
      >
        <ScanLine size={15} strokeWidth={2} className="mt-px shrink-0" />
        <span>
          The document couldn&rsquo;t be read automatically — check it by hand. This doesn&rsquo;t
          stop the request.
        </span>
      </p>
    );
  }

  if (status === "clean") {
    // Quiet on success. A large green panel for "nothing wrong" would out-shout
    // the actual findings state and train people to skim past it.
    return (
      <div role="status" className={className}>
        <p className="flex items-start gap-2 text-[13px] leading-snug text-pos-ink">
          <CheckCircle2 size={15} strokeWidth={2} className="mt-px shrink-0" />
          <span>Receipt read — the total matches, and it hasn&rsquo;t been submitted before.</span>
        </p>
        <Extraction data={extraction} />
      </div>
    );
  }

  const sorted = [...flags].sort((a, b) => {
    const order = { high: 0, medium: 1, low: 2 };
    return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
  });

  return (
    <section
      role="status"
      className={`rounded-xl bg-review-soft p-4 ${className}`}
      aria-label="Receipt check findings"
    >
      <div className="flex gap-3">
        <IconChip icon={flags.length > 1 ? FileSearch : TriangleAlert} tone="review" size="sm" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">
            {sorted.length === 1 ? "One thing to check" : `${sorted.length} things to check`}
          </p>
          <p className="mt-0.5 text-xs text-muted">
            Automated checks on the receipt. They don&rsquo;t block anything — the decision is
            still yours.
          </p>
          <ul className="mt-3 space-y-2">
            {sorted.map((f, i) => (
              <Finding key={`${f.code}-${i}`} flag={f} />
            ))}
          </ul>
          <Extraction data={extraction} />
        </div>
      </div>
    </section>
  );
}
