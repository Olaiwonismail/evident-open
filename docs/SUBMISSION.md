# Evident — NITHUB Innovation Fair Hackathon 2026

**Challenge:** How might AI and BMONI's financial infrastructure create better and
more inclusive ways for people to interact with money?

---

## 1. The problem: payment systems confirm, they do not account

A payment system tells you a transaction succeeded. It does not tell you what
happened to the money afterward — who authorised the next movement, on what
grounds, or whether the stated reason matches the document behind it. That
record exists, but it is private to whoever holds the funds, and everyone else
is asked to take it on trust.

**So transparency today is a report somebody produces, not a property of the
rail.** A report can be delayed, summarised, or written to match a story. The
people it concerns most are the least able to check it.

That gap is invisible when you are the only person your money belongs to. It
becomes the whole problem the moment money is **held on someone else's behalf**
— which describes most of how money actually moves in Nigeria: pooled savings,
cooperative funds, association dues, project budgets, community levies, church
and mosque collections, market-union contributions. In every case the person who
put the money in has no independent way to see where it went.

**Who is left out:** not people without accounts. People without *visibility* —
anyone whose money is held, pooled, or spent by someone else, and whose only
instrument for checking is asking that person and believing the answer.

**What Evident changes:** it makes accountability a property of the payment
system rather than a document produced afterward.

- The ledger is built from **BMoni's own transaction data**, not typed in by an
  administrator — so it cannot be edited to match a story.
- It is **append-only and public**: entries are never rewritten or deleted, and
  every stakeholder reads the same record in real time.
- Every outbound payment carries a stated reason, a receipt, and a **named
  approver**, permanently attached.
- **AI verifies the justification, not just the arithmetic** — the document
  behind a payment is read and checked before a human commits the funds.

A Nigerian community collective is the first instance we have built, because it
is where the absence bites hardest and where the whole loop can be demonstrated
end to end. The mechanism — transparency enforced by the payment rail itself —
is not specific to it.

---

## 2. Architecture: how AI and BMONI connect

```
MEMBER                    EVIDENT                        BMONI SANDBOX
  │                          │                                │
  │ create collective        │                                │
  ├─────────────────────────>│  POST /v1/users                │
  │                          ├───────────────────────────────>│
  │                          │  POST /v1/wallets/create-managed
  │                          ├───────────────────────────────>│
  │                          │  <── smart wallet + NGN rail ───┤
  │  <── treasury wallet ────┤                                │
  │                          │                                │
  │ contribute               │                                │
  ├──── wallet transfer ─────┼───────────────────────────────>│
  │                          │  GET /wallets/{id}/transactions │  (20s poll)
  │                          ├───────────────────────────────>│
  │                          │  match sender address → member  │
  │                          │  append to ledger (idempotent)  │
  │                          │                                │
  │ request expense          │                                │
  ├── amount + reason + ─────>│                                │
  │   receipt image          │                                │
  │                          │        ┌──────────────┐        │
  │                          ├───────>│ GEMINI 3.6   │        │
  │                          │        │ reads the doc │        │
  │                          │<───────┤ vendor/total/ │        │
  │                          │        │ date/items    │        │
  │                          │        └──────────────┘        │
  │                          │  compare total vs claim         │
  │                          │  fingerprint vs past receipts   │
  │  <── advisory findings ──┤  (never blocks)                 │
  │                          │                                │
COMMITTEE approves           │  verify account → register →    │
  ├─────────────────────────>│  offramp proposal → EIP-191 sign│
  │                          ├───────────────────────────────>│
  │                          │  debit ledger BEFORE transfer,  │
  │                          │  reverse on failure             │
```

**Where AI sits:** on the money path, between "I want ₦214,462" and a human
committing the funds. Not a chatbot bolted to the side.

**Where BMONI sits:** it *is* the money. Wallets, balances, the naira rail, and
the payout. Remove it and there is no product — only a spreadsheet.

### BMONI endpoints used

| Endpoint | Purpose | Status |
|---|---|---|
| `POST /v1/users` | one BMoni user per collective and per member | **working** |
| `GET /v1/users` | idempotent re-adoption after a 409 | **working** |
| `POST /v1/wallets/create-managed` | smart wallet, server-side, no mobile SDK | **working** — 4 provisioned |
| `GET /v1/users/{id}/wallets` | recover an existing wallet on 409 | **working** |
| `GET /v1/wallets/{id}/transactions` | contribution ingest (20s poll) | **working** |
| `GET /v1/users/{id}/banks` | Nigerian bank list | **working** |
| `POST /v1/users/{id}/accounts/verify` | recipient name verification | **returns `E101`, unresolved** |
| `POST /v1/users/{id}/offramp` + proposal signing | payout to a bank account | implemented, **never executed live** |

### Key technical decisions

- **Attribution by sending wallet, not by account number.** BMoni's naira deposit
  account is pooled across users, so it cannot identify a payer. Each member has
  their own smart wallet, and a wallet-to-wallet transfer carries the sender
  address — one address, one member, no name matching.
- **Polling, not webhooks.** BMoni's webhook payload shape is undocumented. The
  endpoint exists and funnels into the same recording path, but the ledger relies
  on polling rather than trusting an unverified shape.
- **Ledger debit is written *before* the transfer call,** and reversed with a new
  append-only entry if the transfer fails. Intent is always on the record.
- **Idempotency:** every payment carries a unique `source_transfer_id` under a
  database unique constraint. BMoni's offramp has no client idempotency key, so
  Evident refuses to offramp an expense that already holds a payout reference.

---

## 3. The AI, and why it is not decoration

**One capability, on the critical path:** when a member attaches a receipt or
invoice, Gemini reads it and returns structured fields (vendor, grand total,
currency, date, line items, legibility). Evident then runs three checks:

1. **Amount vs document.** Claimed ₦X against a document totalling ₦Y, with a 1%
   tolerance for rounding and fees.
2. **Receipt reuse.** Two fingerprints: SHA-256 over the bytes catches the
   identical file; a content fingerprint over vendor + total + date catches the
   same receipt re-photographed, cropped or recompressed.
3. **Unusual amount.** Only when a request is *both* beyond three standard
   deviations of the group's history *and* larger than anything it has ever paid.

### Responsible-AI note

- **It flags. It never blocks.** No AI output can prevent a submission or a
  payout. In a transparency product a false positive is expensive: wrongly
  flagging an honest member damages exactly the trust the tool exists to build.
- **Every failure degrades to "no opinion", never to "rejected"** — missing API
  key, unreadable image, model error, unsupported file type.
- **The verdict is published.** Flags are written onto the expense and appear on
  the public ledger beside the human decision: *"AI flagged a ₦45,000 gap —
  approved anyway by <name>."* The model is held to the same transparency rule as
  the committee rather than acting as an invisible oracle.
- **The human decides, and is named.** Approval always carries a person's name.
- **The model is told today's date.** Without it, it judged a two-day-old invoice
  as post-dated and wrote that onto the record — a false accusation against a
  legitimate expense. Found and fixed during this build.
- **What is sent:** the receipt image and the prompt. No member names, no bank
  details, no ledger history. Extraction is stored as JSON on the expense.
- **A clean result is not a guarantee.** A well-forged receipt read correctly
  reads as clean. This narrows the gap; it does not close it.

---

## 4. Privacy, security and financial safety

- **Authentication is a signed capability token.** A member's personal link
  carries their id plus an HMAC keyed by the server secret. Previously identity
  was `?m=<member_id>` — and the member list *publishes every id*, so anyone
  could read the roster and approve a payout as the organizer. Ids stay public
  and harmless now; a token cannot be derived from one.
- **Writes are authenticated, reads are not — deliberately.** The public ledger
  is the product. Locking it down would remove the transparency the group needs.
  All 8 money-and-authority routes require a token; verified by test.
- **The requester and approver come from the token, never the request body.**
- **No solo spending, enforced server-side.** The member who requests an expense
  cannot approve it. This previously existed only as a UI flag.
- **Role changes are the organizer's alone** — a committee member cannot recruit
  their own quorum.
- **The roster no longer leaks contact details.** It returned whole ORM rows,
  publishing every member's email, phone and wallet ids to any visitor. It now
  returns name and role publicly; contact details only to a committee member.
- **Recipient names come from the bank, never from user input** — and are
  re-verified at payout time rather than trusted from submission.
- **Sessions end with the tab.** Credentials go in `sessionStorage`, not
  `localStorage`, so a treasury credential is not left on a shared laptop.
- **Test data only.** Sandbox keys, no live funds, no real personal financial
  data. Credentials live in `backend/.env`, never committed, never exposed to
  the frontend.

**Known limitation, stated plainly:** the capability-URL model means the link
*is* the credential — forwarding a personal link hands over that member's
authority. That trade is deliberate for a group reached by a WhatsApp link and
needing no passwords or email delivery. Production would add device-bound
sessions and rotation.

---

## 5. Declarations

**Built during the official build period (29–30 July):**
- The entire BMONI integration — provisioning, wallets, ingest, bank lookup,
  offramp and proposal signing.
- The AI receipt verification feature — Gemini integration, extraction schema,
  duplicate detection, anomaly baseline, and its UI.
- The authentication and authorization layer described in §4.

**Pre-existing (declared):** Evident's core ledger, contribution, expense and
approval model, its React frontend, and its demo mode predate the build window.
They were built against a different payment provider, which was removed and
replaced by BMONI during this hackathon.

**Third-party dependencies:**

| Dependency | Use |
|---|---|
| BMONI Embedded API (sandbox) | wallets, naira rail, bank data, payouts |
| Google Gemini `gemini-3.6-flash` | receipt and invoice reading |
| FastAPI, SQLAlchemy, asyncpg, APScheduler | backend |
| `eth-account` | EIP-191 signing of offramp proposals |
| React, Vite, Tailwind CSS, TanStack Query | frontend |
| PostgreSQL (Render), SQLite | storage |

AI coding assistance (Claude) was used during development. All architectural and
product decisions, and this submission, are the entrant's own.

---

## 6. What is proven, and what is not

Stated directly, because a claim we cannot demonstrate is worth less than an
honest gap.

**Demonstrated working:**
- Server-side BMoni user and smart-wallet provisioning — 4 wallets created, and
  re-adoption reproduces identical wallets after a database wipe.
- Live Gemini extraction on a real invoice: vendor, ₦214,462.50 grand total
  correctly chosen over the ₦199,500 subtotal, four line items, VAT handled.
- Duplicate detection, amount comparison, and the full advisory UI.
- The complete authentication model, verified by an end-to-end test suite.
- The full member journey in demo mode.

**Not proven:**
- **Account verification returns `E101`** for every account number tried in
  sandbox. Unresolved.
- **No live payout has executed.** The offramp path is implemented against the
  documented shape but has never moved money.
- **No live contribution has landed** — wallets hold no test funds, so the
  ingest field mapping is written against documentation, not an observed payload.

**A negative result worth reporting:** perceptual image hashing (dHash) was
implemented first for duplicate detection and then removed. Receipts downsample
to near-uniform pale rectangles, so unrelated documents collided at *smaller*
Hamming distances than a genuine re-photographed duplicate (measured 5 and 7
between different receipts, 8 between true duplicates, on a 256-bit hash). No
threshold separates those populations. It was removed rather than shipped with a
threshold that cannot work, and replaced with the content fingerprint.
