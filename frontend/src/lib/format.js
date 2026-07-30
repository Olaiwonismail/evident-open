// display-only grouping (e.g. 792 546 1234) — always copy the raw digits
export const groupDigits = (s) =>
  s ? String(s).replace(/^(\d{3})(\d{3})(\d+)$/, "$1 $2 $3") : s;

export const naira = (n) =>
  new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: Number(n) % 1 === 0 ? 0 : 2,
  }).format(n);

// backend timestamps are naive UTC — pin them to UTC before display
export const formatTime = (iso) => {
  if (!iso) return "";
  const date = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return date.toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" });
};
