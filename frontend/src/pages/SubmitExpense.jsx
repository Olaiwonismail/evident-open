import { useRef, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, Paperclip, X } from "lucide-react";
import { api } from "../api.js";
import { Card, Button, Input, Select, EmptyState, ErrorNote } from "../components/ui.jsx";
import ReceiptCheck from "../components/ReceiptCheck.jsx";

const RECEIPT_TYPES = "image/png,image/jpeg,image/webp,image/heic,image/heif,application/pdf";

// The recipient's bank details captured here are what the payout actually
// goes to — hence the mandatory account verification before submitting.
export default function SubmitExpense() {
  const { collectiveId, me } = useOutletContext();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
    amount: "",
    reason: "",
    recipient_account: "",
    recipient_bank_code: "",
  });
  const [receiptFile, setReceiptFile] = useState(null);
  const fileInput = useRef(null);
  const set = (k) => (e) => {
    setForm({ ...form, [k]: e.target.value });
    if (k === "recipient_account" || k === "recipient_bank_code") lookup.reset();
    // the check compares the document against the amount, so a changed amount
    // invalidates the previous verdict rather than silently keeping a stale one
    if (k === "amount") receipt.reset();
  };

  const receipt = useMutation({
    mutationFn: (file) =>
      api.uploadReceipt(collectiveId, file, Number(form.amount) || 0, form.reason),
  });

  const clearReceipt = () => {
    setReceiptFile(null);
    receipt.reset();
    if (fileInput.current) fileInput.current.value = "";
  };

  const banks = useQuery({
    queryKey: ["banks", collectiveId],
    queryFn: () => api.getBanks(collectiveId),
    staleTime: Infinity,
  });

  const lookup = useMutation({
    mutationFn: () =>
      api.lookupAccount(collectiveId, form.recipient_account, form.recipient_bank_code),
  });

  const submit = useMutation({
    mutationFn: () =>
      api.submitExpense(collectiveId, {
        requested_by: me.id,
        amount: Number(form.amount),
        reason: form.reason,
        receipt_url: receipt.data?.receipt_url || null,
        recipient_account: form.recipient_account,
        recipient_bank_code: form.recipient_bank_code,
        recipient_name: lookup.data?.accountName,
        // carried through so the approver sees the same verdict, and so a
        // flagged-but-approved expense says so on the ledger
        receipt_sha256: receipt.data?.receipt_sha256 || null,
        receipt_fingerprint: receipt.data?.receipt_fingerprint || null,
        ai_status: receipt.data?.ai_status || null,
        ai_extraction: receipt.data?.ai_extraction || null,
        ai_flags: receipt.data?.ai_flags || null,
      }),
    onSuccess: (expense) => {
      queryClient.invalidateQueries({ queryKey: ["expenses", collectiveId] });
      navigate(`/c/${collectiveId}/expenses/${expense.id}`);
    },
  });

  if (!me) {
    return (
      <Card>
        <EmptyState
          icon={KeyRound}
          title="Open your personal link to request an expense"
          subtitle="Requests carry the requester's name — we need to know who you are."
        />
      </Card>
    );
  }

  const verified = lookup.isSuccess && lookup.data?.accountName;

  return (
    <Card className="mx-auto max-w-xl p-6 sm:p-8">
      <h1 className="mb-1 text-lg font-bold text-ink">Request an expense</h1>
      <p className="mb-6 text-sm text-muted">
        Your reason goes on the public ledger, and the committee's decision — with their name —
        follows it forever.
      </p>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
        <Input
          label="Amount (₦)"
          type="number"
          min="1"
          step="0.01"
          value={form.amount}
          onChange={set("amount")}
          required
        />
        <Input
          label="Reason — shown on the public ledger"
          placeholder="e.g. Generator fuel for July"
          value={form.reason}
          onChange={set("reason")}
          required
        />

        <div>
          <span className="mb-1.5 block text-sm font-medium text-ink">
            Receipt or invoice <span className="font-normal text-muted">(optional)</span>
          </span>
          <input
            ref={fileInput}
            type="file"
            accept={RECEIPT_TYPES}
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setReceiptFile(file);
              receipt.mutate(file);
            }}
          />

          {!receiptFile ? (
            <>
              <Button
                type="button"
                variant="secondary"
                onClick={() => fileInput.current?.click()}
              >
                <Paperclip size={15} strokeWidth={2} />
                Attach receipt
              </Button>
              <p className="mt-1.5 text-xs text-muted">
                A photo or PDF. We read it and check the total against your amount — it never
                blocks your request.
              </p>
            </>
          ) : (
            <div className="rounded-xl border border-line-strong bg-surface-2 p-3">
              <div className="flex items-center gap-2">
                <Paperclip size={15} strokeWidth={2} className="shrink-0 text-muted" />
                <span className="min-w-0 flex-1 truncate text-sm text-ink">{receiptFile.name}</span>
                <button
                  type="button"
                  onClick={clearReceipt}
                  aria-label={`Remove ${receiptFile.name}`}
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                >
                  <X size={15} strokeWidth={2} />
                </button>
              </div>

              {receipt.isPending && (
                <p
                  role="status"
                  className="mt-2.5 flex items-center gap-2 text-[13px] text-muted"
                >
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line-strong border-t-brand motion-reduce:animate-none" />
                  Reading the receipt…
                </p>
              )}

              {receipt.isError && (
                <p className="mt-2.5 text-[13px] leading-snug text-muted">
                  Couldn&rsquo;t check this receipt ({String(receipt.error.message)}). It&rsquo;s
                  still attached — you can submit as normal.
                </p>
              )}

              {receipt.isSuccess && (
                <ReceiptCheck
                  status={receipt.data.ai_status}
                  flags={receipt.data.ai_flags}
                  extraction={receipt.data.ai_extraction}
                  className="mt-3"
                />
              )}
            </div>
          )}
        </div>

        <hr className="border-line" />
        <p className="text-sm font-semibold text-ink">Where the money goes</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Recipient bank"
            value={form.recipient_bank_code}
            onChange={set("recipient_bank_code")}
            required
          >
            <option value="">{banks.isLoading ? "Loading banks…" : "Select bank"}</option>
            {(banks.data || []).map((b) => (
              <option key={b.bankCode || b.code} value={b.bankCode || b.code}>
                {b.bankName || b.name}
              </option>
            ))}
          </Select>
          <Input
            label="Recipient account number"
            value={form.recipient_account}
            onChange={set("recipient_account")}
            maxLength={10}
            required
          />
        </div>

        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="secondary"
            disabled={!form.recipient_account || !form.recipient_bank_code || lookup.isPending}
            onClick={() => lookup.mutate()}
          >
            {lookup.isPending ? "Verifying…" : "Verify account"}
          </Button>
          {verified && (
            <span className="inline-flex items-center gap-1 text-sm font-medium text-pos-ink">
              <Check size={15} strokeWidth={2.25} /> {lookup.data.accountName}
            </span>
          )}
        </div>
        <ErrorNote error={lookup.error} />
        <ErrorNote error={submit.error} />

        <div className="flex gap-3">
          <Button type="submit" disabled={!verified || submit.isPending}>
            {submit.isPending ? "Submitting…" : "Submit for approval"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => navigate(`/c/${collectiveId}/expenses`)}
          >
            Cancel
          </Button>
        </div>
        {!verified && (
          <p className="text-xs text-muted">
            Verify the recipient account before submitting — the payout goes exactly there.
          </p>
        )}
      </form>
    </Card>
  );
}
