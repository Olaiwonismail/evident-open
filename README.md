# Evident
An open financial tracking platform designed to eliminate corruption by showing members exactly where group money goes in real time.

**Highlights**
- Every collective **and every member** gets a dedicated pay-in account — so the bank account, not a treasurer, is the source of truth.
- Contributions land on a public, append-only ledger in real time, attributed automatically to the member who paid.
- Expenses require a stated reason, a receipt, and committee approval before Evident disburses them.
- Built-in demo mode simulates the full payment flow with no credentials.

> **Payment provider:** the Nomba integration has been removed and its replacement is not yet wired in. Provisioning, bank lookup and payouts currently return `503` — see `backend/app/services/payments.py`. Everything else (ledger, contributions, expenses, approvals, demo mode) runs as normal.

## Architecture & Security

Evident is built so that the **bank account is the source of truth**, not a person. Money flows through provider-issued virtual accounts, and Evident records every movement to a public, append-only ledger that members can read in real time. Every collective gets its own account, and **every member gets a personal pay-in account** — so an incoming transfer is attributed to exactly one person by the account it lands in, with no manual matching.

### Credentials

- **Nothing sensitive is committed.** Provider credentials live only in `backend/.env` (see `.env.example` for the shape) and are never exposed to the frontend. Unrecognised environment variables are ignored rather than crashing startup.

### Pay-in accounts

- **One account per collective, one per member.** Creating a collective provisions a dedicated account for the group's pooled funds, and every member invited to it is issued their **own** personal pay-in account.
- **Attribution without guesswork.** Because each member pays into an account that belongs only to them, an incoming transfer is matched to exactly one member by the account that received it — no reliance on sender names or reference codes. Anything that can't be matched falls through to the unmatched-review queue.

### Recording payments

- **Idempotency:** every payment carries a unique `source_transfer_id`, unique-constrained in the database. Any payment whose id was already recorded is skipped, so retries, duplicate deliveries and replays can never double-count money.
- **Classification is preserved, not overwritten:** payments are recorded `partial`, `exact` or `excess` against the expected dues, with the shortfall or overage spelled out on the ledger entry.

### Data handling

- **Append-only ledger.** Financial rows are never updated or deleted. Each contribution or expense writes a new `ledger_entries` row with the running `balance_after`, giving an immutable audit trail.
- **Payment matching & review queue.** Incoming transfers are matched to a member by the pay-in account that received them — a strong, unambiguous signal — before being credited. Anything that can't be matched (e.g. a transfer into the collective account itself) is filed in an unmatched-review queue rather than silently attached, so a human resolves it to a member.
- **Under/over-payment is preserved, not overwritten.** Payments are classified `partial`, `exact`, or `excess` against the expected dues, and the shortfall/overage is described on the ledger entry rather than being adjusted away.
- **Expenses require justification and approval.** A disbursement needs a stated reason and a receipt, and is only paid out after committee approval, with recipient bank-account validation before the payout.
- **Transport.** CORS is enforced at the API layer; production deployments should serve both frontend and backend over HTTPS so tokens and payloads are never sent in the clear.

## Getting Started (Running Locally)

### Prerequisites
* Node.js (v18 or higher)
* Python (3.10 or higher)
* Payment provider credentials (for real transactions, otherwise use Demo Mode)

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
* **Create a Collective:** Start by creating your group. Evident instantly provisions a dedicated virtual bank account solely for your collective's funds.
* **Invite Members:** Add your community members — each is automatically issued their own dedicated pay-in account — and optionally elevate trusted individuals to "Committee" status to help oversee spending.
* **Manage Unmatched Payments:** If a transfer arrives but cannot be automatically linked to a user, it enters a manual review queue where you can easily assign it to the correct member.

### 2. For Members
* **Pay Dues Seamlessly:** Log into your dashboard to view upcoming dues. Copy **your own** dedicated virtual account number and make a standard bank transfer from any Nigerian bank.
* **Instant, Automatic Attribution:** Because you pay into an account that's uniquely yours, the moment the transfer clears it is credited straight to you — your status turns green instantly, with no screenshots to a treasurer and no manual matching.
* **Track the Ledger:** At any time, check the live ledger to see the group's total balance, who has paid, and a permanent record of all incoming and outgoing funds.

### 3. Approving Expenses & Payouts
* **Submit an Expense:** When the group needs to spend money, the Treasurer drafts an expense by entering the recipient's bank details, a stated reason, and uploading a receipt.
* **Committee Approval:** The expense remains locked in a "Pending" state until the designated Committee Members review and approve it.
* **Automated Payout:** Once fully approved, Evident triggers a secure bank transfer to disburse the funds directly to the recipient, recording the approved expense permanently on the ledger.
