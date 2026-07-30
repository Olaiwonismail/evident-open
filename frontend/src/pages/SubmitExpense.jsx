import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound } from "lucide-react";
import { api } from "../api.js";
import { Card, Button, Input, Select, EmptyState, ErrorNote } from "../components/ui.jsx";

// The recipient's bank details captured here are what the payout actually
// goes to — hence the mandatory account verification before submitting.
export default function SubmitExpense() {
  const { collectiveId, me } = useOutletContext();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
    amount: "",
    reason: "",
    receipt_url: "",
    recipient_account: "",
    recipient_bank_code: "",
  });
  const set = (k) => (e) => {
    setForm({ ...form, [k]: e.target.value });
    if (k === "recipient_account" || k === "recipient_bank_code") lookup.reset();
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
        receipt_url: form.receipt_url || null,
        recipient_account: form.recipient_account,
        recipient_bank_code: form.recipient_bank_code,
        recipient_name: lookup.data?.accountName,
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
        <div className="grid gap-4 sm:grid-cols-2">
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
            label="Receipt / invoice URL (optional)"
            placeholder="https://…"
            value={form.receipt_url}
            onChange={set("receipt_url")}
          />
        </div>
        <Input
          label="Reason — shown on the public ledger"
          placeholder="e.g. Generator fuel for July"
          value={form.reason}
          onChange={set("reason")}
          required
        />

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
