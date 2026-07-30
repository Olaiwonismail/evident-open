import { demoApi, DEMO_ID } from "./demo/store.js";
import { getSessionToken } from "./lib/session.js";

// The demo collective lives entirely in the in-memory store; every other
// collective hits the real backend. Dispatch happens per call, so the demo
// stays available alongside real usage.
export { DEMO_ID };
export const isDemoCollective = (id) => id === DEMO_ID;

// "No solo spending": the member who requests an expense can never be the one
// who approves it. Flipping this to true lets a solo tester drive the whole loop
// in one browser, at the cost of disabling the control — so it stays false, and
// testing uses two member links instead.
export const ALLOW_SELF_APPROVAL = false;

// Vite sets import.meta.env.DEV=true under `vite dev`, false in a production
// build — so local dev hits the local backend and the deployed UI hits Render,
// with no manual toggling. (The old `A || B` always picked A, so the deployed
// UI was silently calling localhost.)
const API = import.meta.env.DEV
  ? "http://127.0.0.1:8000"
  : "https://evident-z4te.onrender.com";

// Receipts are stored on the backend and referenced by a path, not an absolute
// URL — resolve against the API origin so the link works from the deployed UI.
// Demo receipts are never fetchable; they exist only in memory.
export const resolveReceiptUrl = (url) => {
  if (!url) return null;
  if (url.startsWith("demo://")) return null;
  return url.startsWith("/") ? `${API}${url}` : url;
};

// The member's credential, pulled from the session rather than threaded through
// every call site. Absent for a public visitor, which is fine — reads don't need
// it, and writes are meant to fail without it.
const auth = (collectiveId) => {
  const token = getSessionToken(collectiveId);
  return token ? { "X-Member-Token": token } : {};
};

async function request(path, options = {}) {
  const { headers, ...rest } = options;
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...headers },
    ...rest,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

// Multipart needs its own path: setting Content-Type by hand strips the
// boundary the browser generates, so the upload arrives unparseable.
async function upload(path, formData, headers = {}) {
  const res = await fetch(`${API}${path}`, { method: "POST", body: formData, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Upload failed (${res.status})`);
  return body;
}

const realApi = {
  createCollective: (data) =>
    request("/collectives", { method: "POST", body: JSON.stringify(data) }),
  getCollective: (id) => request(`/collectives/${id}`),
  getLedger: (id) => request(`/collectives/${id}/ledger`),
  // sent with the token when there is one: the roster is public by name and
  // role, and contact details come back only for a committee member
  getMembers: (id) => request(`/collectives/${id}/members`, { headers: auth(id) }),
  getMe: (id) => request(`/collectives/${id}/me`, { headers: auth(id) }),
  inviteMember: (id, data) =>
    request(`/collectives/${id}/members`, {
      method: "POST",
      headers: auth(id),
      body: JSON.stringify(data),
    }),
  setMemberRole: (id, memberId, role) =>
    request(`/collectives/${id}/members/${memberId}/role`, {
      method: "POST",
      headers: auth(id),
      body: JSON.stringify({ role }),
    }),
  getContributions: (id, memberId) =>
    request(`/collectives/${id}/members/${memberId}/contributions`),
  getExpenses: (id) => request(`/collectives/${id}/expenses`),
  getExpense: (id, expenseId) => request(`/collectives/${id}/expenses/${expenseId}`),
  submitExpense: (id, data) =>
    request(`/collectives/${id}/expenses`, {
      method: "POST",
      headers: auth(id),
      body: JSON.stringify(data),
    }),
  // No approver in the body any more — the server reads it off the token, so
  // there is nothing here to forge.
  approveExpense: (id, expenseId) =>
    request(`/collectives/${id}/expenses/${expenseId}/approve`, {
      method: "POST",
      headers: auth(id),
    }),
  rejectExpense: (id, expenseId, _approverId, reason) =>
    request(`/collectives/${id}/expenses/${expenseId}/reject`, {
      method: "POST",
      headers: auth(id),
      body: JSON.stringify({ reason }),
    }),
  getUnmatched: (id) => request(`/collectives/${id}/unmatched`),
  resolveUnmatched: (id, unmatchedId, memberId) =>
    request(`/collectives/${id}/unmatched/${unmatchedId}/resolve`, {
      method: "POST",
      headers: auth(id),
      body: JSON.stringify({ member_id: memberId }),
    }),
  uploadReceipt: (id, file, amount, reason) => {
    const form = new FormData();
    form.append("file", file);
    form.append("amount", String(amount || 0));
    form.append("reason", reason || "");
    return upload(`/collectives/${id}/receipts`, form, auth(id));
  },
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
  // real collectives only — the demo resolves identity from its in-memory roster
  getMe: (id) => realApi.getMe(id),
  inviteMember: (id, data) => forId(id).inviteMember(id, data),
  setMemberRole: (id, memberId, role) => forId(id).setMemberRole(id, memberId, role),
  getContributions: (id, memberId) => forId(id).getContributions(id, memberId),
  uploadReceipt: (id, file, amount, reason) =>
    forId(id).uploadReceipt(id, file, amount, reason),
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
