# Evident
An open financial tracking platform designed to eliminate corruption by showing members exactly where group money goes in real time.

**Highlights**
- Every collective **and every member** gets their own wallet — so the ledger, not a treasurer, is the record of truth.
- Contributions land on a public, append-only ledger in real time, attributed automatically by the wallet that sent them.
- Expenses require a stated reason, a receipt, and committee approval before Evident disburses them.
- Uploaded receipts are read by an AI check that flags duplicates and mismatched totals — advisory, never blocking.
- Built-in demo mode simulates the full payment flow with no credentials.

> **Payments run on [BMoni](https://embedded-dev.bmoni.com), against the sandbox.** Wallet provisioning, bank verification and payouts all call the live sandbox API — see `backend/app/services/payments.py`. Set `BMONI_API_KEY` to enable them; without it those routes return `503` and everything else still works.

## Architecture & Security

Evident is built so that the **ledger is the record of truth**, not a person. Every collective and every member is provisioned a BMoni smart wallet; money moves wallet-to-wallet, and Evident appends every movement to a public, append-only ledger that members can read in real time. An incoming transfer is attributed to exactly one person by the wallet that sent it, with no manual matching.

### Credentials

- **Nothing sensitive is committed.** Provider credentials live only in `backend/.env` (see `.env.example` for the shape) and are never exposed to the frontend. Unrecognised environment variables are ignored rather than crashing startup.
- **`SECRET_KEY` is key material.** Smart-wallet owner keys are derived from it, so rotating it orphans every wallet already provisioned. Back it up like a private key.

### Wallets and attribution

- **One wallet per collective, one per member.** Creating a collective provisions a treasury wallet for the group's pooled funds, and every member invited to it is issued their **own** wallet. Provisioning the treasury is mandatory — if it fails, the collective is rolled back rather than created with nowhere to hold money.
- **Attribution by sending wallet.** A wallet-to-wallet transfer carries the sender's address, and that address maps to exactly one member — no reliance on sender names or reference codes. Anything arriving from an address Evident doesn't recognise falls through to the unmatched-review queue rather than being silently attached.
- **The naira deposit account is pooled, and is never used for attribution.** BMoni issues one shared NGN account across all users, so it cannot identify who paid. Evident displays it, but the wallet address is the pay-in identity that actually matters — see `backend/app/services/ingest.py`.
- **Detection is by polling, not webhooks.** A scheduler sweeps each treasury wallet's transactions every 20 seconds. The webhook endpoint accepts deliveries and funnels them through the same recording path, but BMoni's payload shape is undocumented, so the ledger relies on polling rather than trusting it.

### Recording payments

- **Idempotency:** every payment carries a unique `source_transfer_id`, unique-constrained in the database. Any payment whose id was already recorded is skipped, so retries, duplicate deliveries and replays can never double-count money.
- **Classification is preserved, not overwritten:** payments are recorded `partial`, `exact` or `excess` against the expected dues, with the shortfall or overage spelled out on the ledger entry.

### Paying out

- **Four steps, not one.** A payout verifies the destination account, registers it as a withdrawal account, creates an offramp *proposal*, and then signs it. Evident produces exactly one EIP-191 signature over the proposal; BMoni co-signs server-side.
- **Never twice.** BMoni's offramp carries no client-supplied idempotency key, so Evident refuses to offramp an expense that already holds a `transfer_ref`.
- **Recipient names are re-verified, not trusted.** The holder name registered against a withdrawal account comes from a fresh verification call, not from whatever the submitter typed.
- **Statement descriptor.** The offramp takes only a bank account and an amount, so the recipient's statement shows BMoni's descriptor rather than the collective's name.

### Receipt checks

- **The receipt is read, not just stored.** An uploaded receipt or invoice is passed to Gemini, which extracts the vendor, total and date; the total is compared against the amount being requested.
- **Duplicate detection on two fingerprints.** A sha256 over the file bytes catches the identical file; a content fingerprint over vendor + total + date catches the same receipt re-photographed, cropped or re-compressed. Matching is scoped to the collective, so one group's expenses are never revealed to another.
- **Advisory, never blocking.** A flag never prevents a submission or an approval — it is shown to the approver, and an expense approved despite a flag records that fact. Leaving `GEMINI_API_KEY` unset disables only the document reading; duplicate and unusual-amount detection still run.

### Data handling

- **Append-only ledger.** Financial rows are never updated or deleted. Each contribution or expense writes a new `ledger_entries` row with the running `balance_after`, giving an immutable audit trail.
- **Payment matching & review queue.** Incoming transfers are matched to a member by the wallet that sent them — a strong, unambiguous signal — before being credited. Anything that can't be matched is filed in an unmatched-review queue rather than silently attached, so a human resolves it to a member. The treasury paying itself is recognised and skipped.
- **Under/over-payment is preserved, not overwritten.** Payments are classified `partial`, `exact`, or `excess` against the expected dues, and the shortfall/overage is described on the ledger entry rather than being adjusted away.
- **Expenses require justification and approval.** A disbursement needs a stated reason and a receipt, and is only paid out after committee approval, with recipient bank-account validation before the payout.
- **Transport.** Deployments should serve both frontend and backend over HTTPS so payloads are never sent in the clear.

### Known limitations

This is a demonstration build running against BMoni's sandbox. Two gaps are worth stating plainly:

- **There is no authentication yet.** Member identity is carried in the request rather than a verified session, so the role checks guarding approvals are not yet enforceable. Don't put real money through this build.
- **Funding a member wallet happens outside Evident.** BMoni's transfer API originates from a *personal* wallet, which only the BMoni app can create — a server-provisioned wallet can't originate one. Members move funds from the BMoni app; Evident detects the arrival and records it.

## Getting Started (Running Locally)

### Prerequisites
* Node.js (v18 or higher)
* Python (3.10 or higher)
* A BMoni sandbox API key (for real transactions, otherwise use Demo Mode)
* A Gemini API key (optional — enables reading uploaded receipts)

### Backend Setup
1. Navigate to the backend directory: `cd backend`
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `source venv/bin/activate` (or `venv\Scripts\activate` on Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Configure your environment: Copy `.env.example` to `.env` and fill it in.
6. Start the server: `uvicorn app.main:app --reload`

### Frontend Setup
1. Navigate to the frontend directory: `cd frontend`
2. Install dependencies: `npm install`
3. Start the dev server: `npm run dev`

## Testing & Demo Mode

The quickest way to evaluate the platform without deploying the full backend is via the built-in **Demo Mode**.

- **Interactive Demo:** Navigate to `https://evident-rose.vercel.app/c/demo?m=m1` (or click "Explore the live demo" on the landing page) to interact with a seeded, in-memory dataset.
- **Simulated Transfers:** Within the demo collective, navigate to the "Pay Dues" page and click the simulation button. This mimics the server-side payment webhook flow, allowing you to watch the ledger update in real-time.
- **Role Switching:** Use the demo widget to seamlessly toggle your view between an ordinary Member, the Treasurer, or a Committee Member to verify permission constraints and UI changes.

## How to Use Evident (User Guide)

### 1. For Organizers & Treasurers
* **Create a Collective:** Start by creating your group. Evident instantly provisions a treasury wallet that holds your collective's funds and nothing else.
* **Invite Members:** Add your community members — each is automatically issued their own wallet — and optionally elevate trusted individuals to "Committee" status to help oversee spending.
* **Manage Unmatched Payments:** If a transfer arrives but cannot be automatically linked to a user, it enters a manual review queue where you can easily assign it to the correct member.

### 2. For Members
* **Pay Dues:** Log into your dashboard to view upcoming dues, then send your contribution from your own wallet to the collective's treasury.
* **Instant, Automatic Attribution:** Because the transfer carries your wallet's address, the moment it clears it is credited straight to you — your status turns green, with no screenshots to a treasurer and no manual matching.
* **Track the Ledger:** At any time, check the live ledger to see the group's total balance, who has paid, and a permanent record of all incoming and outgoing funds.

### 3. Approving Expenses & Payouts
* **Submit an Expense:** When the group needs to spend money, the Treasurer drafts an expense by entering the recipient's bank details, a stated reason, and uploading a receipt. The receipt is read and checked before the request reaches the committee.
* **Committee Approval:** The expense remains locked in a "Pending" state until the designated Committee Members review and approve it.
* **Automated Payout:** Once fully approved, Evident triggers a secure bank transfer to disburse the funds directly to the recipient, recording the approved expense permanently on the ledger.

## Further Documentation

* [`docs/BMONI_TRANSITION.md`](docs/BMONI_TRANSITION.md) — how the payment provider works, endpoint by endpoint, and what the migration changed.
* [`docs/RECEIPT_VERIFICATION.md`](docs/RECEIPT_VERIFICATION.md) — the receipt check in detail, including the fraud signals that were tried and rejected.
* [`docs/archive/`](docs/archive/) — superseded references, kept for history. Nothing there describes the current codebase.
