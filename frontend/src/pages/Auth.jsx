import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api.js";
import { setSessionMember } from "../lib/session.js";
import { Card, Button, Input, ErrorNote } from "../components/ui.jsx";
import PublicShell from "../components/PublicShell.jsx";

// One screen handles both sign up and log in: enter a phone or email, get a
// one-time code. New contacts become accounts automatically — no password.
export default function Auth() {
  const navigate = useNavigate();
  const [channel, setChannel] = useState("phone");
  const [contact, setContact] = useState("");
  const [code, setCode] = useState("");

  const send = useMutation({
    mutationFn: () => api.requestOtp({ contact, channel }),
  });
  const verify = useMutation({
    mutationFn: () => api.verifyOtp({ contact, code }),
    onSuccess: (data) => {
      setSessionMember(data.collective_id, data.member_id);
      navigate(`/c/${data.collective_id}`);
    },
  });

  return (
    <PublicShell>
      <Card className="mx-auto max-w-md p-8">
        <div className="mb-6 text-center">
          <h1 className="text-xl font-bold text-ink">Welcome to Evident</h1>
          <p className="mt-1 text-sm text-muted">
            Log in or create your account — we'll text you a one-time code.
          </p>
        </div>

        {!send.isSuccess ? (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              send.mutate();
            }}
          >
            <div className="grid grid-cols-2 gap-1 rounded-xl bg-surface-2 p-1">
              {["phone", "email"].map((ch) => (
                <button
                  key={ch}
                  type="button"
                  onClick={() => setChannel(ch)}
                  className={`min-h-9 rounded-lg text-sm font-medium capitalize transition-colors ${
                    channel === ch ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
                  }`}
                >
                  {ch}
                </button>
              ))}
            </div>
            <Input
              label={channel === "phone" ? "Phone number" : "Email address"}
              type={channel === "phone" ? "tel" : "email"}
              placeholder={channel === "phone" ? "0803 123 4567" : "you@example.com"}
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              required
              autoFocus
            />
            <ErrorNote error={send.error} />
            <Button type="submit" className="w-full" disabled={send.isPending}>
              {send.isPending ? "Sending code…" : "Continue"}
            </Button>
          </form>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              verify.mutate();
            }}
          >
            <p className="text-center text-sm text-muted">
              Enter the 6-digit code sent to <span className="font-medium text-ink">{contact}</span>
            </p>
            <Input
              label="One-time code"
              inputMode="numeric"
              maxLength={6}
              placeholder="123456"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              required
              autoFocus
            />
            <p className="rounded-xl bg-warn-soft px-3 py-2 text-xs text-warn-ink">
              MVP preview: any 6-digit code works — it logs you into the demo collective as the
              organizer. Real accounts use the personal link from your invite.
            </p>
            <ErrorNote error={verify.error} />
            <Button type="submit" className="w-full" disabled={verify.isPending || code.length < 4}>
              {verify.isPending ? "Verifying…" : "Log in"}
            </Button>
            <button
              type="button"
              onClick={() => {
                send.reset();
                setCode("");
              }}
              className="w-full text-center text-xs text-muted hover:text-ink"
            >
              Use a different {channel === "phone" ? "number" : "email"}
            </button>
          </form>
        )}

        <p className="mt-6 border-t border-line pt-4 text-center text-xs text-muted">
          Starting a new group?{" "}
          <Link to="/create" className="font-medium text-brand-ink hover:underline">
            Create a collective
          </Link>
        </p>
      </Card>
    </PublicShell>
  );
}
