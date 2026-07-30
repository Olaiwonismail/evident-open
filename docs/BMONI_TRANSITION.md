# Nomba → BMoni transition plan

Everything here is verified against the live sandbox (`https://embedded-dev.bmoni.com`)
on 2026-07-30, not inferred from docs. Where a claim came from reading rather than
running, it says so.

---

## 1. Why this isn't a port

Nomba and BMoni disagree about what a "pay-in account" is, and that single
disagreement drives every decision below.

| | Nomba | BMoni |
| --- | --- | --- |
| Auth | OAuth2 `client_credentials`, token issue + refresh | one `x-api-key` header |
| Balance holder | implicit merchant wallet | an explicit per-user **smart wallet** (EVM account) |
| Pay-in account | **one NUBAN per collective and per member** | **one pooled NUBAN shared by everyone** |
| Attribution key | the account number that received the money | the wallet that received the money |
| Payout | one POST, `merchantTxRef` as idempotency key | verify → register → offramp → **sign** proposal |
| Currency | naira throughout | `CNGN` (naira-pegged) in the wallet |

### The finding that reshapes the product

`GET /v1/users/{id}/bank-accounts/deposit-accounts/NGN` returns the same row for
every user:

```json
{"accounts":[{"id":"pooled-vba-1","accountName":"Bkey Limited",
  "bankName":"9 Payment Service Bank","accountNumber":"6177463833",
  "bankCode":"XXXXXXX","targetCurrency":"EUR"}]}
```

Confirmed unchanged after completing the KYC profile, so it is by design and not
a pre-provisioning placeholder.

**Consequence:** Evident's original mechanic — *every member gets their own
account number, so a bank transfer identifies its sender with no guesswork* —
cannot be reproduced on BMoni's naira rail. Two people paying into
`6177463833` are indistinguishable at the bank level.

**What replaces it:** every member does get their own **smart wallet**, with a
unique EVM address. Contributions arrive as wallet-to-wallet transfers, and the
sending wallet identifies the member exactly as unambiguously as a NUBAN did.
The transparency guarantee is intact; the on-ramp is different.

---

## 2. Verified call sequence

Every step below returned success in the sandbox. This is the sequence
`provisioning.py` implements.

```
POST  /v1/users                                    201  → user.bmoniUserId
PATCH /v1/users/{id}/kyc                           200  → saved: personalInfo, address, identifications
POST  /v1/users/{id}/smart-wallets/owner-proof-challenges
                                                   201  → challengeId, message (10-min expiry)
      ── sign `message` locally, EIP-191 ──
POST  /v1/users/{id}/smart-wallets/create-managed  201  → id, walletAddress, isActive: true
POST  /v1/users/{id}/onboarding/start-nigeria      200  → hasBvn, hasLocalWallet
GET   /v1/users/{id}/smart-wallets/account/balances 200 → NGN "0"
```

Notes that cost time to discover:

- **`bmoniUserId`, not `id`.** The create-user response carries both; only
  `bmoniUserId` works as the `{userId}` path segment.
- **`CNGN` on the way in, `NGN` on the way out.** Wallet creation takes
  `currency: "CNGN"`; the response and the balances endpoint both say `"NGN"`.
- **The wallet deploys immediately.** `pendingDeployUserOperation: null`, so
  there's no second signing round at creation.
- **Sandbox BVN is `22222222222`.** Real BVNs are rejected outside production.
- **Unique email and phone per user.** The phone number is also the handle BMoni
  matches when crediting test funds.

### No mobile SDK required

BMoni's guide says to generate the owner key with their Flutter / React Native
SDK. Evident is a React web app, so that route doesn't exist — and it turns out
not to matter. `create-managed` only receives an address and a signature, and
validates by recovering the signer. A key derived server-side with `eth-account`
is indistinguishable from one held on a phone. **Verified working.**

Keys are derived, never stored:

```python
seed = hashlib.sha256(f"{SECRET_KEY}:{ref}".encode()).digest()
account = Account.from_key(seed)
```

Deterministic, so it survives a sandbox reset and needs no key table or
migration. The trade-off is stated plainly in §6.

---

## 3. What each Evident concept maps to

| Evident | BMoni |
| --- | --- |
| Collective | a user + a CNGN smart wallet (the treasury) |
| Member | a user + a CNGN smart wallet (their own funds) |
| Member pays dues | wallet-to-wallet send, member → collective |
| Collective balance | still computed from Evident's own append-only ledger |
| Expense payout | offramp from the collective wallet to a Nigerian bank |
| `source_transfer_id` | BMoni transaction id (still unique-constrained) |

Evident's ledger stays the source of truth for *what the group believes*, and
BMoni is the source of truth for *where the money actually is*. That separation
is deliberate: it's what lets the ledger survive a sandbox reset, and it's what
makes a mismatch between the two visible instead of silent.

---

## 4. Work breakdown

| # | Component | File | Status |
| --- | --- | --- | --- |
| 1 | API client — every verified endpoint | `services/bmoni_client.py` | built |
| 2 | Key derivation + EIP-191/712 signing | `services/signing.py` | built |
| 3 | End-to-end onboarding orchestration | `services/provisioning.py` | built |
| 4 | Provider seam now delegating to BMoni | `services/payments.py` | built |
| 5 | Contribution ingestion (poll + webhook) | `services/ingest.py`, `routers/webhooks.py` | built |
| 6 | New columns for BMoni identifiers | `models/{collective,member}.py` | built |
| 7 | Settings + dependency | `config.py`, `requirements.txt` | built |
| 8 | Demo seed script | `seed_demo.py` | built |

---

## 5. Money in, money out

### In — contributions

There is no per-member NUBAN to watch, so ingestion polls each collective's
wallet transactions and records new credits through the existing
`contributions.record_payment()`. The sender's wallet address maps back to a
member; anything unrecognised goes to the unmatched-review queue exactly as
before.

A webhook endpoint (`POST /webhooks/bmoni`) is also wired, because BMoni
supports `POST /v1/webhooks/config` with a real signing secret (`whsec_…`) — the
signature verification Nomba never allowed us to switch on. **The event payload
shape is undocumented and unverified**, so the handler parses defensively and
logs anything it doesn't recognise rather than guessing. Polling is the path
that is known to work; the webhook is the upgrade once a real delivery is seen.

### Out — expenses

```
GET  /v1/users/{id}/bank-accounts/nigerian-banks
POST /v1/users/{id}/bank-accounts/verify-nigerian-account   → account holder name
POST /v1/users/{id}/bank-accounts/withdrawal-accounts/nigeria → bankAccountId (get-or-create)
POST /v1/users/{id}/smart-wallets/{walletId}/offramp/nigeria  → proposalId, PENDING_APPROVALS
GET  /v1/users/{id}/smart-wallets/proposals/{id}/sign-payload
POST /v1/users/{id}/smart-wallets/proposals/{id}/sign
```

Two things worth knowing:

- **BMoni co-signs.** Managed wallets default to an approval threshold of 2 —
  the user owner plus BMoni's KMS custodian — and their docs state the backend
  appends its co-signature without a client request. So Evident produces exactly
  one signature, which its server can do.
- **There is no `merchantTxRef`.** Nomba's idempotency key has no equivalent, so
  double-payout protection is now Evident's job: `expenses.transfer_ref` records
  the proposal id, and an expense that already has one is never offramped again.

The ledger debit is still written and committed *before* the payout call, and a
failure still appends a compensating credit rather than deleting the debit.

---

## 6. Risks, stated plainly

| Risk | Detail |
| --- | --- |
| **Evident becomes custodial** | Deriving owner keys server-side means Evident holds the keys that can move members' money. Same trust posture as Nomba, but it sits awkwardly with a product whose pitch is "don't just trust the treasurer". The honest alternative — members signing on their own phones — needs the mobile app. |
| **`SECRET_KEY` is now key material** | Rotating it silently orphans every wallet, because the derivation changes. It must be treated as a backup-critical secret, not a session salt. |
| **Webhook payload unverified** | Shape unknown; polling carries ingestion until a real delivery is observed. |
| **Test funds are scarce and manual** | ₦1,000 per wallet, credited by hand against a phone number, ~1 business day, wiped on sandbox reset. Demo amounts must be small. |
| **No inbound bank-transfer simulation** | Sandbox cannot deliver a real bank transfer into the pooled account, so "pay from your bank app and watch it land" stays in demo mode. |
| **Column additions need a fresh DB** | `init_db` creates missing tables but never alters existing ones. |

---

## 7. Demo shape

What is genuinely real on stage:

1. Create a collective → a real BMoni user, wallet and treasury address.
2. Add members → each gets their own real wallet.
3. Fund one member (test tokens) → wallet-to-wallet send into the collective →
   the ledger attributes it to that member automatically.
4. Approve an expense → offramp → signed server-side → real payout.

What stays in demo mode: a member transferring from their own bank app. The
sandbox has no way to simulate it, and the pooled account couldn't attribute it
if it did.

**Set demo dues low** — ₦1,000 of test money spread across a few members means
dues in the low hundreds, not the ₦450,000 a real association would pool.
