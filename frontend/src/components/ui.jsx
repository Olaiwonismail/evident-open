import { useState } from "react";
import { Copy, Check } from "lucide-react";

export function Card({ children, className = "" }) {
  return (
    <div className={`rounded-2xl border border-line bg-surface shadow-sm shadow-black/[0.03] ${className}`}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
      <div className="min-w-0">
        <h2 className="font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-1 max-w-prose text-[13px] leading-snug text-muted">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

// tone → [soft background, ink text]. Money direction (pos/neg) is deliberately
// separate from the brand so "green" never means "brand", only "money in".
const badgeTones = {
  brand: "bg-brand-soft text-brand-ink",
  pos: "bg-pos-soft text-pos-ink",
  neg: "bg-neg-soft text-neg-ink",
  warn: "bg-warn-soft text-warn-ink",
  info: "bg-info-soft text-info-ink",
  review: "bg-review-soft text-review-ink",
  neutral: "bg-surface-2 text-muted",
};

export function Badge({ tone = "neutral", children, className = "" }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${badgeTones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

// [tone, label] for every status the ledger and expenses surface.
export const statusBadge = {
  exact: ["pos", "paid in full"],
  partial: ["warn", "partial"],
  excess: ["info", "overpaid — credited"],
  unmatched: ["review", "needs review"],
  pending: ["warn", "pending approval"],
  disbursing: ["info", "disbursing…"],
  paid: ["pos", "paid"],
  failed: ["neg", "failed"],
  rejected: ["neutral", "rejected"],
  manual_review: ["review", "manual review"],
};

export function StatusBadge({ status }) {
  const [tone, label] = statusBadge[status] || ["neutral", status];
  return <Badge tone={tone}>{label}</Badge>;
}

// Round tinted icon holder — used in empty states, ledger rows, hero moments.
export function IconChip({ icon: Icon, tone = "brand", size = "md", className = "" }) {
  const tones = {
    brand: "bg-brand-soft text-brand-ink",
    pos: "bg-pos-soft text-pos-ink",
    neg: "bg-neg-soft text-neg-ink",
    warn: "bg-warn-soft text-warn-ink",
    info: "bg-info-soft text-info-ink",
    review: "bg-review-soft text-review-ink",
    neutral: "bg-surface-2 text-muted",
  };
  const sizes = {
    sm: "h-8 w-8 rounded-lg [&>svg]:h-4 [&>svg]:w-4",
    md: "h-10 w-10 rounded-xl [&>svg]:h-5 [&>svg]:w-5",
    lg: "h-14 w-14 rounded-2xl [&>svg]:h-6 [&>svg]:w-6",
  };
  return (
    <span className={`inline-flex shrink-0 items-center justify-center ${tones[tone]} ${sizes[size]} ${className}`}>
      <Icon strokeWidth={1.75} />
    </span>
  );
}

const buttonVariants = {
  primary: "bg-brand text-on-brand hover:bg-brand-strong disabled:opacity-50",
  secondary: "bg-surface text-ink border border-line-strong hover:bg-surface-2 disabled:opacity-50",
  ghost: "text-brand-ink hover:bg-brand-soft disabled:opacity-50",
  danger: "bg-surface text-neg-ink border border-line-strong hover:bg-neg-soft disabled:opacity-50",
};

export function Button({ children, variant = "primary", className = "", ...props }) {
  return (
    <button
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition-[background-color,transform] duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-canvas active:scale-[0.98] disabled:cursor-not-allowed disabled:active:scale-100 ${buttonVariants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

const fieldClass =
  "w-full min-h-11 rounded-xl border border-line-strong bg-surface px-3 text-sm text-ink outline-none transition-colors placeholder:text-faint focus:border-brand focus:ring-2 focus:ring-brand/25";

export function Input({ label, hint, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>}
      <input className={`${fieldClass} py-2.5 ${className}`} {...props} />
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Textarea({ label, hint, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>}
      <textarea rows={3} className={`${fieldClass} py-2.5 ${className}`} {...props} />
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Select({ label, children, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>}
      <select className={`${fieldClass} bg-surface py-2.5 ${className}`} {...props}>
        {children}
      </select>
    </label>
  );
}

export function Spinner() {
  return (
    <div className="flex justify-center py-10">
      <div className="h-7 w-7 animate-spin rounded-full border-2 border-line-strong border-t-brand" />
    </div>
  );
}

export function EmptyState({ title, subtitle, icon: Icon, tone = "neutral" }) {
  return (
    <div className="px-6 py-14 text-center">
      {Icon && (
        <div className="mb-3 flex justify-center">
          <IconChip icon={Icon} tone={tone} size="md" />
        </div>
      )}
      <p className="text-sm font-semibold text-ink">{title}</p>
      {subtitle && <p className="mx-auto mt-1 max-w-xs text-[13px] leading-snug text-muted">{subtitle}</p>}
    </div>
  );
}

export function ErrorNote({ error }) {
  if (!error) return null;
  return (
    <p className="rounded-xl bg-neg-soft px-3 py-2 text-sm text-neg-ink">
      {String(error.message || error)}
    </p>
  );
}

export function CopyButton({ text, label = "Copy", variant = "secondary" }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant={variant}
      type="button"
      className="min-h-9 px-3 text-xs"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? <Check size={14} strokeWidth={2.25} /> : <Copy size={14} strokeWidth={2} />}
      {copied ? "Copied" : label}
    </Button>
  );
}
