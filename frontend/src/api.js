import { demoApi, DEMO_ID } from "./demo/store.js";

// The demo collective lives entirely in the in-memory store; every other
// collective hits the real backend. Dispatch happens per call, so the demo
// stays available alongside real usage.
export { DEMO_ID };
export const isDemoCollective = (id) => id === DEMO_ID;

// TESTING: lets an organizer approve/reject their own expense request so a
// solo tester can run the whole loop. Set back to false to restore the
// "no solo spending" guard for the real demo.
export const ALLOW_SELF_APPROVAL = true;

// Vite sets import.meta.env.DEV=true under `vite dev`, false in a production
// build — so local dev hits the local backend and the deployed UI hits Render,
// with no manual toggling. (The old `A || B` always picked A, so the deployed
// UI was silently calling localhost.)
const API = import.meta.env.DEV
  ? "http://127.0.0.1:8000"
  : "https://evident-z4te.onrender.com";

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

const realApi = {
  createCollective: (data) =>
    request("/collectives", { method: "POST", body: JSON.stringify(data) }),
  getCollective: (id) => request(`/collectives/${id}`),
  getLedger: (id) => request(`/collectives/${id}/ledger`),
  getMembers: (id) => request(`/collectives/${id}/members`),
  inviteMember: (id, data) =>
    request(`/collectives/${id}/members`, { method: "POST", body: JSON.stringify(data) }),
  setMemberRole: (id, memberId, role) =>
    request(`/collectives/${id}/members/${memberId}/role`, {
      method: "POST",
      body: JSON.stringify({ role }),
    }),
  getContributions: (id, memberId) =>
    request(`/collectives/${id}/members/${memberId}/contributions`),
  getExpenses: (id) => request(`/collectives/${id}/expenses`),
  getExpense: (id, expenseId) => request(`/collectives/${id}/expenses/${expenseId}`),
  submitExpense: (id, data) =>
    request(`/collectives/${id}/expenses`, { method: "POST", body: JSON.stringify(data) }),
  approveExpense: (id, expenseId, approverId) =>
    request(`/collectives/${id}/expenses/${expenseId}/approve`, {
      method: "POST",
      body: JSON.stringify({ approver_id: approverId }),
    }),
  rejectExpense: (id, expenseId, approverId, reason) =>
    request(`/collectives/${id}/expenses/${expenseId}/reject`, {
      method: "POST",
      body: JSON.stringify({ approver_id: approverId, reason }),
    }),
  getUnmatched: (id) => request(`/collectives/${id}/unmatched`),
  resolveUnmatched: (id, unmatchedId, memberId) =>
    request(`/collectives/${id}/unmatched/${unmatchedId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ member_id: memberId }),
    }),
  getBanks: () => request("/banks"),
  lookupAccount: (accountNumber, bankCode) =>
    request(`/banks/lookup?account_number=${accountNumber}&bank_code=${bankCode}`, {
      method: "POST",
    }),
};

const forId = (id) => (isDemoCollective(id) ? demoApi : realApi);

export const api = {
  // auth + identity are demo stubs until the backend grows these endpoints
  requestOtp: (data) => demoApi.requestOtp(data),
  verifyOtp: (data) => demoApi.verifyOtp(data),
  verifyIdentity: (data) => demoApi.verifyIdentity(data),

  // always creates a real collective (the demo one already exists)
  createCollective: (data) => realApi.createCollective(data),

  getCollective: (id) => forId(id).getCollective(id),
  getLedger: (id) => forId(id).getLedger(id),
  getMembers: (id) => forId(id).getMembers(id),
  inviteMember: (id, data) => forId(id).inviteMember(id, data),
  setMemberRole: (id, memberId, role) => forId(id).setMemberRole(id, memberId, role),
  getContributions: (id, memberId) => forId(id).getContributions(id, memberId),
  getExpenses: (id) => forId(id).getExpenses(id),
  getExpense: (id, expenseId) => forId(id).getExpense(id, expenseId),
  submitExpense: (id, data) => forId(id).submitExpense(id, data),
  approveExpense: (id, expenseId, approverId) => forId(id).approveExpense(id, expenseId, approverId),
  rejectExpense: (id, expenseId, approverId, reason) =>
    forId(id).rejectExpense(id, expenseId, approverId, reason),
  getUnmatched: (id) => forId(id).getUnmatched(id),
  resolveUnmatched: (id, unmatchedId, memberId) =>
    forId(id).resolveUnmatched(id, unmatchedId, memberId),

  // bank calls carry the collective id purely to pick demo vs real
  getBanks: (id) => (isDemoCollective(id) ? demoApi.getBanks() : realApi.getBanks()),
  lookupAccount: (id, accountNumber, bankCode) =>
    isDemoCollective(id)
      ? demoApi.lookupAccount(accountNumber)
      : realApi.lookupAccount(accountNumber, bankCode),

  simulateIncomingTransfer: (id, memberId, amount) => {
    if (!isDemoCollective(id)) throw new Error("Simulated transfers are demo-only");
    return demoApi.simulateIncomingTransfer(id, memberId, amount);
  },
};
