import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, isDemoCollective } from "../api.js";
import { getSessionMember, setSessionMember } from "../lib/session.js";
import { Badge, Spinner, CopyButton } from "../components/ui.jsx";

const roleTone = { organizer: "review", committee: "info", member: "neutral" };

export default function CollectiveShell() {
  const { collectiveId } = useParams();
  const [params] = useSearchParams();

  // identity: a personal ?m= link wins and is remembered for the session
  const [memberId, setMemberIdState] = useState(
    () => params.get("m") || getSessionMember(collectiveId)
  );
  const setMemberId = (id) => {
    setMemberIdState(id);
    setSessionMember(collectiveId, id);
  };
  // a ?m= link identifies the member; keep it in the URL so this stays a durable,
  // bookmarkable personal link. Internal nav drops the query but falls back to the
  // saved session identity, so who-you-are survives moving between tabs.
  useEffect(() => {
    const m = params.get("m");
    if (m) {
      setSessionMember(collectiveId, m);
      setMemberIdState(m);
    }
  }, [collectiveId, params]);

  const collective = useQuery({
    queryKey: ["collective", collectiveId],
    queryFn: () => api.getCollective(collectiveId),
  });
  const members = useQuery({
    queryKey: ["members", collectiveId],
    queryFn: () => api.getMembers(collectiveId),
  });

  const me = (members.data || []).find((m) => m.id === memberId) || null;
  const role = me?.role || "public";
  const isCommittee = role === "committee" || role === "organizer";
  const isOrganizer = role === "organizer";

  // badge counts for the nav — what's waiting on a committee member
  const expenses = useQuery({
    queryKey: ["expenses", collectiveId],
    queryFn: () => api.getExpenses(collectiveId),
    enabled: isCommittee,
    refetchInterval: 15_000,
  });
  const unmatched = useQuery({
    queryKey: ["unmatched", collectiveId],
    queryFn: () => api.getUnmatched(collectiveId),
    enabled: isCommittee,
    refetchInterval: 30_000,
  });
  const pendingCount = (expenses.data || []).filter((e) => e.status === "pending").length;
  const reviewCount = (unmatched.data || []).filter((u) => u.status !== "resolved").length;

  if (collective.isLoading || members.isLoading) return <Spinner />;
  if (collective.isError)
    return (
      <div className="py-20 text-center text-sm text-muted">
        Collective not found.{" "}
        <Link className="text-brand-ink underline" to="/">
          Create one?
        </Link>
      </div>
    );

  const nav = [
    { to: ".", end: true, label: "Home", show: true },
    { to: "ledger", label: "Ledger", show: true },
    { to: "me", label: "My record", show: !!me },
    { to: "expenses", label: "Expenses", show: true },
    { to: "approvals", label: "Approvals", show: isCommittee, count: pendingCount },
    { to: "review", label: "Needs review", show: isCommittee, count: reviewCount },
    { to: "members", label: "Members", show: true },
  ].filter((t) => t.show);

  const publicLink = `${window.location.origin}/c/${collectiveId}`;
  const ctx = {
    collectiveId,
    collective: collective.data,
    members: members.data || [],
    me,
    role,
    isCommittee,
    isOrganizer,
    setMemberId,
  };

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur-md">
        <div className="mx-auto max-w-5xl px-4 pt-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <Link to="/" className="text-sm font-bold tracking-tight text-ink">
                evident<span className="text-brand-ink">.</span>
              </Link>
              <h1 className="mt-1 truncate text-xl font-bold tracking-tight text-ink sm:text-2xl">
                {collective.data.name}
              </h1>
              <p className="mt-0.5 truncate text-sm text-muted">{collective.data.purpose}</p>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-2 pt-1">
              {me ? (
                <div className="text-right">
                  <p className="text-sm font-medium text-ink">{me.name}</p>
                  <Badge tone={roleTone[role] || "neutral"}>{role}</Badge>
                </div>
              ) : (
                <Badge tone="neutral">public view</Badge>
              )}
              <div className="flex items-center gap-2">
                {isDemoCollective(collectiveId) && (
                  <RoleSwitcher members={members.data || []} me={me} setMemberId={setMemberId} />
                )}
                <CopyButton text={publicLink} label="Share ledger" />
              </div>
            </div>
          </div>

          <nav className="-mb-px mt-4 flex gap-1 overflow-x-auto pb-2" aria-label="Sections">
            {nav.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.end}
                className={({ isActive }) =>
                  `flex min-h-9 items-center gap-1.5 whitespace-nowrap rounded-full px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ${
                    isActive ? "bg-brand text-on-brand" : "text-muted hover:bg-surface-2 hover:text-ink"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {t.label}
                    {t.count > 0 && (
                      <span
                        className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold leading-none ${
                          isActive ? "bg-white/20 text-on-brand" : "bg-warn-soft text-warn-ink"
                        }`}
                      >
                        {t.count}
                      </span>
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet context={ctx} />
      </main>
    </div>
  );
}

// Demo-only: preview any screen as any member without re-logging in.
function RoleSwitcher({ members, me, setMemberId }) {
  return (
    <select
      value={me?.id || ""}
      onChange={(e) => setMemberId(e.target.value || null)}
      className="min-h-9 rounded-xl border border-dashed border-warn bg-warn-soft px-2 text-xs font-medium text-warn-ink outline-none focus-visible:ring-2 focus-visible:ring-brand"
      title="Demo: switch who you're viewing as"
    >
      <option value="">👀 Public view</option>
      {members.map((m) => (
        <option key={m.id} value={m.id}>
          {m.name} ({m.role})
        </option>
      ))}
    </select>
  );
}
