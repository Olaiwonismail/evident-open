// Seeded in-memory dataset + an api-compatible facade (demoApi), so every
// screen can be designed and demoed before the backend is wired in.
// Flip DEMO_MODE in src/api.js to switch the whole app to the real API.

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));
const clone = (x) => (x === undefined ? x : JSON.parse(JSON.stringify(x)));

let seq = 1000;
const uid = (p) => `${p}${seq++}`;

// a plausible 10-digit NUBAN for demo member pay-in accounts
const fakeNuban = () => "80" + String(Math.floor(10000000 + Math.random() * 89999999));
const DEMO_BANK = "Amucha MFB";

const ago = (days, h = 10, m = 0) => {
  const t = new Date();
  t.setDate(t.getDate() - days);
  t.setHours(h, m, 0, 0);
  return t.toISOString();
};

export const DEMO_ID = "demo";

const db = { collectives: {} };

const col = (id) => {
  const c = db.collectives[id];
  if (!c) throw new Error("Collective not found");
  return c;
};

const findMember = (c, memberId) => {
  const m = c.members.find((m) => m.id === memberId);
  if (!m) throw new Error("Member not found");
  return m;
};

function addEntry(c, e) {
  c.balance += e.amount || 0;
  const entry = { id: uid("le"), balance_after: c.balance, ...e };
  c.ledger.push(entry);
  return entry;
}

function contributionStatus(c, amount) {
  if (!c.dues_amount) return "exact";
  if (amount === c.dues_amount) return "exact";
  return amount > c.dues_amount ? "excess" : "partial";
}

function addContribution(c, { member_id, amount, timestamp, status }) {
  const member = findMember(c, member_id);
  const contribution = {
    id: uid("ct"),
    member_id,
    amount,
    status: status || contributionStatus(c, amount),
    timestamp,
  };
  c.contributions.push(contribution);
  const entry = addEntry(c, {
    type: "contribution",
    amount,
    description: `Dues payment — ${member.name}`,
    actor_name: member.name,
    timestamp,
    member_id,
  });
  contribution.ledger_entry_id = entry.id;
  return contribution;
}

function newCollective(data) {
  const id = data.id || uid("c");
  const organizerId = uid("m");
  const c = {
    id,
    name: data.name,
    purpose: data.purpose,
    dues_amount: data.dues_amount || null,
    dues_frequency: data.dues_frequency || "monthly",
    bank_account_number:
      data.bank_account_number ||
      "90" + String(Math.floor(10000000 + Math.random() * 89999999)),
    bank_name: "Amucha MFB",
    organizer_id: organizerId,
    created_at: new Date().toISOString(),
    balance: 0,
    members: [
      {
        id: organizerId,
        name: data.organizer_name,
        phone: data.organizer_phone || null,
        email: data.organizer_email || null,
        role: "organizer",
        bank_account_number: fakeNuban(),
        bank_name: DEMO_BANK,
        joined_at: new Date().toISOString(),
      },
    ],
    ledger: [],
    expenses: [],
    contributions: [],
    unmatched: [],
  };
  db.collectives[id] = c;
  return c;
}

// ---------------------------------------------------------------- seed data

function seed() {
  const c = newCollective({
    id: DEMO_ID,
    name: "Harmony Close Residents Association",
    purpose: "Estate security & maintenance levy",
    dues_amount: 5000,
    dues_frequency: "monthly",
    bank_account_number: "9012345678",
    organizer_name: "Adaeze Okonkwo",
    organizer_phone: "08031234567",
    organizer_email: "adaeze@harmonyclose.ng",
  });
  // stable, readable ids for the seeded cast
  c.organizer_id = "m1";
  c.members[0].id = "m1";

  const cast = [
    ["m2", "Tunde Bakare", "08052345678", "committee"],
    ["m3", "Ngozi Eze", "08163456789", "committee"],
    ["m4", "Emeka Obi", "07034567890", "member"],
    ["m5", "Fatima Aliyu", "08085678901", "member"],
    ["m6", "Yusuf Adamu", "09016789012", "member"],
    ["m7", "Bisi Adeyemi", "08147890123", "member"],
    ["m8", "Chinedu Okafor", "07068901234", "member"],
  ];
  for (const [id, name, phone, role] of cast) {
    c.members.push({
      id, name, phone, email: null, role,
      bank_account_number: fakeNuban(),
      bank_name: DEMO_BANK,
      joined_at: ago(40),
    });
  }

  // --- May dues: everyone paid
  const may = [
    ["m1", 36], ["m2", 35, 9], ["m3", 35, 14], ["m4", 34],
    ["m5", 33, 16], ["m6", 33, 19], ["m7", 32], ["m8", 32, 11],
  ];
  for (const [mid, d, h = 10] of may) {
    addContribution(c, { member_id: mid, amount: 5000, timestamp: ago(d, h) });
  }

  // --- June dues: Yusuf missed, Chinedu paid half
  const june = [
    ["m1", 16], ["m2", 15, 9], ["m3", 15, 13], ["m4", 14], ["m5", 13, 17], ["m7", 12],
  ];
  for (const [mid, d, h = 10] of june) {
    addContribution(c, { member_id: mid, amount: 5000, timestamp: ago(d, h) });
  }
  addContribution(c, { member_id: "m8", amount: 2500, timestamp: ago(12, 15) });

  // --- Expense 1: approved & paid
  const e1 = {
    id: "e1",
    amount: 45000,
    reason: "Replace security lights at the estate gate",
    receipt_url: "https://receipts.evident.ng/demo/security-lights.pdf",
    status: "paid",
    requested_by: "m4",
    requested_by_name: "Emeka Obi",
    recipient_name: "ADEBAYO ELECTRICAL SUPPLIES",
    recipient_account: "0123456789",
    recipient_bank_code: "058",
    recipient_bank_name: "GTBank",
    timestamp: ago(13, 11),
    decided_by: "m2",
    decided_by_name: "Tunde Bakare",
    decided_at: ago(12, 12),
    decision_reason: null,
    paid_at: ago(12, 12, 4),
  };
  c.expenses.push(e1);
  addEntry(c, {
    type: "expense",
    amount: -e1.amount,
    description: `Payout: ${e1.reason}`,
    actor_name: `to ${e1.recipient_name} · approved by Tunde Bakare`,
    timestamp: e1.paid_at,
    expense_id: e1.id,
  });

  // --- Expense 2: rejected (zero-money marker on the ledger — honesty on record)
  const e2 = {
    id: "e2",
    amount: 60000,
    reason: "New office chairs for the chairman's office",
    receipt_url: null,
    status: "rejected",
    requested_by: "m6",
    requested_by_name: "Yusuf Adamu",
    recipient_name: "CHUKWU & SONS FURNITURE",
    recipient_account: "0234567891",
    recipient_bank_code: "044",
    recipient_bank_name: "Access Bank",
    timestamp: ago(11, 10),
    decided_by: "m3",
    decided_by_name: "Ngozi Eze",
    decided_at: ago(11, 16),
    decision_reason: "Not in this quarter's budget — raise it at the next meeting.",
    paid_at: null,
  };
  c.expenses.push(e2);
  addEntry(c, {
    type: "expense_rejected",
    amount: null,
    description: `Rejected: ${e2.reason}`,
    actor_name: `rejected by Ngozi Eze — "${e2.decision_reason}"`,
    timestamp: e2.decided_at,
    expense_id: e2.id,
  });

  // --- Expense 3: approved but the payout failed; money returned
  const e3 = {
    id: "e3",
    amount: 25000,
    reason: "Borehole water pump repair",
    receipt_url: "https://receipts.evident.ng/demo/pump-quote.jpg",
    status: "failed",
    requested_by: "m5",
    requested_by_name: "Fatima Aliyu",
    recipient_name: "BLESSED WATERS NIG LTD",
    recipient_account: "0345678912",
    recipient_bank_code: "057",
    recipient_bank_name: "Zenith Bank",
    timestamp: ago(7, 9),
    decided_by: "m2",
    decided_by_name: "Tunde Bakare",
    decided_at: ago(6, 10),
    decision_reason: null,
    paid_at: null,
    failure_reason: "Recipient account could not be credited — transfer reversed.",
  };
  c.expenses.push(e3);
  addEntry(c, {
    type: "expense",
    amount: -e3.amount,
    description: `Payout: ${e3.reason}`,
    actor_name: `to ${e3.recipient_name} · approved by Tunde Bakare`,
    timestamp: ago(6, 10, 2),
    expense_id: e3.id,
  });
  addEntry(c, {
    type: "expense_refunded",
    amount: e3.amount,
    description: `Refund: transfer for "${e3.reason}" failed`,
    actor_name: e3.failure_reason,
    timestamp: ago(5, 8),
    expense_id: e3.id,
  });

  // --- July dues so far
  addContribution(c, { member_id: "m1", amount: 5000, timestamp: ago(3, 8) });
  addContribution(c, { member_id: "m2", amount: 5000, timestamp: ago(2, 12) });
  addContribution(c, { member_id: "m5", amount: 5000, timestamp: ago(2, 18) });

  // --- an unmatched transfer waiting in the needs-review queue.
  // Mirrors the backend: the money stays OFF the ledger until someone
  // attributes it to a member.
  c.unmatched.push({
    id: "u1",
    amount: 5000,
    sender_name: "KOLAWOLE ADEBAYO",
    sender_account: "0456789123",
    sender_bank: "OPay",
    status: "needs_review",
    timestamp: ago(3, 14),
  });

  // --- Expense 4: pending — the live demo approval target
  c.expenses.push({
    id: "e4",
    amount: 18000,
    reason: "Generator diesel for July",
    receipt_url: "https://receipts.evident.ng/demo/diesel-invoice.pdf",
    status: "pending",
    requested_by: "m5",
    requested_by_name: "Fatima Aliyu",
    recipient_name: "GREENFIELD DIESEL CO",
    recipient_account: "0567891234",
    recipient_bank_code: "50515",
    recipient_bank_name: "Moniepoint MFB",
    timestamp: ago(1, 9),
    decided_by: null,
    decided_by_name: null,
    decided_at: null,
    decision_reason: null,
    paid_at: null,
  });
}
seed();

// ------------------------------------------------------------------- banks

const BANKS = [
  { bankCode: "044", bankName: "Access Bank" },
  { bankCode: "058", bankName: "GTBank" },
  { bankCode: "057", bankName: "Zenith Bank" },
  { bankCode: "011", bankName: "First Bank" },
  { bankCode: "033", bankName: "UBA" },
  { bankCode: "50211", bankName: "Kuda MFB" },
  { bankCode: "999992", bankName: "OPay" },
  { bankCode: "999991", bankName: "PalmPay" },
  { bankCode: "50515", bankName: "Moniepoint MFB" },
  { bankCode: "221", bankName: "Stanbic IBTC" },
];

const FAKE_ACCOUNT_NAMES = [
  "ADEBAYO ELECTRICAL SUPPLIES",
  "BLESSED WATERS NIG LTD",
  "CHUKWU & SONS HARDWARE",
  "GREENFIELD DIESEL CO",
  "OLUWASEUN CATERING SERVICES",
  "DE-PRESTIGE PRINTING PRESS",
  "MAMA NKECHI FOODSTUFF",
  "FIRSTCHOICE PLUMBING WORKS",
  "ROYAL EVENTS & RENTALS",
  "SUNRISE CLEANING AGENCY",
];

// --------------------------------------------------------------- demo api

export const demoApi = {
  // --- auth (fake: any contact works, any 4–6 digit code passes)
  requestOtp: async ({ contact }) => {
    await delay(700);
    if (!contact) throw new Error("Enter your phone number or email");
    return { ok: true };
  },
  verifyOtp: async ({ code }) => {
    await delay(600);
    if (!/^\d{4,6}$/.test(code || "")) throw new Error("That code doesn't look right");
    return { collective_id: DEMO_ID, member_id: "m1", name: "Adaeze Okonkwo" };
  },
  verifyIdentity: async () => {
    await delay(1200);
    return { verified: true };
  },

  createCollective: async (data) => {
    await delay(900);
    const c = newCollective(data);
    return clone({
      id: c.id,
      name: c.name,
      purpose: c.purpose,
      dues_amount: c.dues_amount,
      dues_frequency: c.dues_frequency,
      bank_account_number: c.bank_account_number,
      bank_name: c.bank_name,
      organizer_id: c.organizer_id,
    });
  },

  getCollective: async (id) => {
    await delay();
    const c = col(id);
    return clone({
      id: c.id,
      name: c.name,
      purpose: c.purpose,
      dues_amount: c.dues_amount,
      dues_frequency: c.dues_frequency,
      bank_account_number: c.bank_account_number,
      bank_name: c.bank_name,
      organizer_id: c.organizer_id,
    });
  },

  getLedger: async (id) => {
    await delay();
    const c = col(id);
    return clone({ balance: c.balance, entries: [...c.ledger].reverse() });
  },

  getMembers: async (id) => {
    await delay();
    return clone(col(id).members);
  },

  inviteMember: async (id, data) => {
    await delay(500);
    const c = col(id);
    const member = {
      id: uid("m"),
      name: data.name,
      phone: data.phone || null,
      email: data.email || null,
      role: data.role === "committee" ? "committee" : "member",
      bank_account_number: fakeNuban(),
      bank_name: DEMO_BANK,
      joined_at: new Date().toISOString(),
    };
    c.members.push(member);
    return clone(member);
  },

  setMemberRole: async (id, memberId, role) => {
    await delay(400);
    const m = findMember(col(id), memberId);
    if (m.role === "organizer") throw new Error("The organizer's role can't be changed");
    m.role = role;
    return clone(m);
  },

  getContributions: async (id, memberId) => {
    await delay();
    const c = col(id);
    const mine = c.contributions.filter((x) => x.member_id === memberId);
    return clone({
      dues_amount: c.dues_amount,
      dues_frequency: c.dues_frequency,
      total_paid: mine.reduce((s, x) => s + x.amount, 0),
      contributions: [...mine].reverse(),
    });
  },

  getExpenses: async (id) => {
    await delay();
    return clone([...col(id).expenses].reverse());
  },

  getExpense: async (id, expenseId) => {
    await delay();
    const e = col(id).expenses.find((x) => x.id === expenseId);
    if (!e) throw new Error("Expense not found");
    return clone(e);
  },

  submitExpense: async (id, data) => {
    await delay(700);
    const c = col(id);
    const requester = findMember(c, data.requested_by);
    const bank = BANKS.find((b) => b.bankCode === data.recipient_bank_code);
    const expense = {
      id: uid("e"),
      amount: Number(data.amount),
      reason: data.reason,
      receipt_url: data.receipt_url || null,
      status: "pending",
      requested_by: requester.id,
      requested_by_name: requester.name,
      recipient_name: data.recipient_name || "VERIFIED RECIPIENT",
      recipient_account: data.recipient_account,
      recipient_bank_code: data.recipient_bank_code,
      recipient_bank_name: bank ? bank.bankName : "Bank",
      timestamp: new Date().toISOString(),
      decided_by: null,
      decided_by_name: null,
      decided_at: null,
      decision_reason: null,
      paid_at: null,
    };
    c.expenses.push(expense);
    return clone(expense);
  },

  approveExpense: async (id, expenseId, approverId) => {
    await delay(900);
    const c = col(id);
    const e = c.expenses.find((x) => x.id === expenseId);
    if (!e) throw new Error("Expense not found");
    if (e.status !== "pending") throw new Error("This request has already been decided");
    if (e.amount > c.balance) throw new Error("Not enough in the pool to cover this payout");
    const approver = findMember(c, approverId);
    e.status = "paid";
    e.decided_by = approver.id;
    e.decided_by_name = approver.name;
    e.decided_at = new Date().toISOString();
    e.paid_at = e.decided_at;
    addEntry(c, {
      type: "expense",
      amount: -e.amount,
      description: `Payout: ${e.reason}`,
      actor_name: `to ${e.recipient_name} · approved by ${approver.name}`,
      timestamp: e.paid_at,
      expense_id: e.id,
    });
    return clone(e);
  },

  rejectExpense: async (id, expenseId, approverId, reason) => {
    await delay(600);
    const c = col(id);
    const e = c.expenses.find((x) => x.id === expenseId);
    if (!e) throw new Error("Expense not found");
    if (e.status !== "pending") throw new Error("This request has already been decided");
    const approver = findMember(c, approverId);
    e.status = "rejected";
    e.decided_by = approver.id;
    e.decided_by_name = approver.name;
    e.decided_at = new Date().toISOString();
    e.decision_reason = reason;
    addEntry(c, {
      type: "expense_rejected",
      amount: null,
      description: `Rejected: ${e.reason}`,
      actor_name: `rejected by ${approver.name} — "${reason}"`,
      timestamp: e.decided_at,
      expense_id: e.id,
    });
    return clone(e);
  },

  getBanks: async () => {
    await delay();
    return clone(BANKS);
  },

  lookupAccount: async (accountNumber) => {
    await delay(800);
    if (!/^\d{10}$/.test(accountNumber || ""))
      throw new Error("Account number must be 10 digits");
    const name = FAKE_ACCOUNT_NAMES[Number(accountNumber[9]) % FAKE_ACCOUNT_NAMES.length];
    return { accountName: name };
  },

  getUnmatched: async (id) => {
    await delay();
    return clone([...col(id).unmatched].reverse());
  },

  resolveUnmatched: async (id, unmatchedId, memberId) => {
    await delay(600);
    const c = col(id);
    const u = c.unmatched.find((x) => x.id === unmatchedId);
    if (!u || u.status !== "needs_review")
      throw new Error("Transfer not found or already resolved");
    const member = findMember(c, memberId);
    const contribution = {
      id: uid("ct"),
      member_id: member.id,
      amount: u.amount,
      status: contributionStatus(c, u.amount),
      timestamp: new Date().toISOString(),
    };
    c.contributions.push(contribution);
    addEntry(c, {
      type: "contribution",
      amount: u.amount,
      description: `Dues payment — ${member.name} (attributed from ${u.sender_name})`,
      actor_name: member.name,
      timestamp: contribution.timestamp,
      member_id: member.id,
    });
    u.status = "resolved";
    u.resolved_by = member.id;
    return clone(contribution);
  },

  // demo-only: stands in for the provider webhook that fires when a real
  // transfer lands. Pay-dues screen calls this to complete the loop.
  simulateIncomingTransfer: async (id, memberId, amount) => {
    await delay(400);
    const c = col(id);
    return clone(
      addContribution(c, {
        member_id: memberId,
        amount,
        timestamp: new Date().toISOString(),
      })
    );
  },
};
