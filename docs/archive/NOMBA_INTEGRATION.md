# Nomba Integration — Complete Reference

> **Archived — describes an integration that no longer exists.** Nomba was
> removed from Evident and replaced by BMoni; see `docs/BMONI_TRANSITION.md` for
> the migration and the README for how the system works now. Nothing below
> reflects the current codebase. Kept only as a record of what the per-member
> NUBAN model did, and why the pooled-account model that replaced it needed a
> different attribution mechanism.

Everything in Evident that touches Nomba: configuration, auth, the API surface,
money-in, money-out, reconciliation, failure modes, and the accumulated list of
Nomba quirks the code works around.

Evident's core claim is that **the bank account is the source of truth, not a
treasurer**. Nomba is what makes that literally true: every collective and every
member holds a real NUBAN, so money movement is observed rather than asserted.

---

## 1. Map of the integration

| Concern | File |
| --- | --- |
| Credentials / settings | [config.py:20-26](backend/app/config.py#L20-L26) |
| HTTP client, auth, all endpoint wrappers | [nomba_client.py](backend/app/services/nomba_client.py) |
| Inbound webhook endpoint | [webhooks.py](backend/app/routers/webhooks.py) |
| Signature check + payment processing | [webhook.py](backend/app/services/webhook.py) |
| Virtual-account provisioning | [collectives.py:18-35](backend/app/routers/collectives.py#L18-L35) |
| Bank list + account name lookup | [banks.py](backend/app/routers/banks.py) |
| Payouts (transfer + status polling) | [disbursement.py](backend/app/services/disbursement.py) |
| Reconciliation sweep + startup token | [main.py:17-141](backend/app/main.py#L17-L141) |
| Live diagnostics CLI | [find_transfer.py](backend/find_transfer.py) |
| Offline webhook test harness | [test_webhook_flow.py](backend/test_webhook_flow.py) |
| Deploy-time env wiring | [render.yaml:18-29](render.yaml#L18-L29) |

Dependency: plain [`httpx`](backend/requirements.txt) — there is no Nomba SDK.
Every call is hand-rolled against the REST API.

---

## 2. Configuration

Defined in [config.py:20-26](backend/app/config.py#L20-L26), loaded from
`backend/.env` (see [.env.example](backend/.env.example)).

| Env var | Required | Used by | Notes |
| --- | --- | --- | --- |
| `NOMBA_BASE_URL` | no (defaults to `https://sandbox.nomba.com`) | every request | Render overrides this to the **live** host |
| `NOMBA_CLIENT_ID` | **yes** | token issue | |
| `NOMBA_PRIVATE_KEY` | **yes** | token issue | sent as `client_secret` |
| `NOMBA_ACCOUNT_ID` | **yes** | `accountId` header on *every* request incl. token issue/refresh | |
| `NOMBA_SUB_ACCOUNT_ID` | **yes** by schema | **nothing** | declared and required at startup but never read by any code path — a missing value blocks boot for no functional reason |
| `NOMBA_SIGNATURE_KEY` | no (defaults `""`) | webhook signature verification | **empty on purpose in production** — see §5.2 |
| `APP_BASE_URL` | **yes** | builds the `callbackUrl` registered on each virtual account | must be publicly reachable |

`Evident_Nomba_API_Reference.pdf` is gitignored ([.gitignore:4](.gitignore#L4)) —
the vendor spec is deliberately not in the repo.

**Deploy note:** [render.yaml](render.yaml) pins `NOMBA_BASE_URL` to sandbox and
`NOMBA_SIGNATURE_KEY` to `""`, but the Render dashboard's env values take
precedence over the blueprint, and the deployed service runs against **live**
Nomba. Treat the dashboard, not `render.yaml`, as authoritative.

---

## 3. Auth & transport

### 3.1 Token lifecycle — [nomba_client.py:37-98](backend/app/services/nomba_client.py#L37-L98)

OAuth2 `client_credentials`, held in a module-level singleton (`_token`) guarded
by an `asyncio.Lock`.

```
POST /v1/auth/token/issue    body: {grant_type, client_id, client_secret}   header: accountId
POST /v1/auth/token/refresh  body: {refresh_token}                          header: accountId
```

- A token is issued at startup in the lifespan hook
  ([main.py:123-125](backend/app/main.py#L123-L125)); failure there is logged,
  not fatal — the first API call retries.
- `get_token()` re-issues or refreshes lazily whenever `utcnow() >= expires_at`.
- If refresh returns non-200, it silently falls back to a fresh issue
  ([nomba_client.py:73-76](backend/app/services/nomba_client.py#L73-L76)).
- Expiry is parsed from Nomba's ISO `expiresAt` (e.g. `2026-07-03T00:54:40.287Z`),
  converted to **naive UTC** to match `datetime.utcnow()` comparisons, and
  **backdated 60 s** so a token is never used in its last minute
  ([nomba_client.py:30-34](backend/app/services/nomba_client.py#L30-L34)).

⚠️ The token is process-local. Multiple workers/instances each hold their own —
fine, but it means token count scales with replicas.

### 3.2 Request headers — [nomba_client.py:94-98](backend/app/services/nomba_client.py#L94-L98)

```python
{"Authorization": <access_token>, "accountId": <NOMBA_ACCOUNT_ID>}
```

Note there is **no `Bearer ` prefix** — Nomba takes the raw token. All calls use
a 30 s timeout.

### 3.3 Error handling — the important part

Two Nomba behaviours break naive `raise_for_status()` handling, and both are
explicitly worked around:

**(a) Errors arrive as HTTP 200.** Validation failures come back `200 OK` with
`{"status": false, "code": ..., "description": ..., "message": ...}` and **no
`data` key**. Callers doing `data["data"]` used to hit an opaque `KeyError`
instead of the real reason. `_raise_for_nomba_error()`
([nomba_client.py:17-27](backend/app/services/nomba_client.py#L17-L27)) raises
`NombaAPIError` with the real message.

**(b) `status: false` is not reliable.** Nomba sends `status: false` on some
*successful* responses (the transactions endpoint does this). So the check keys
off the **error code**, treating `"00"`/`"0"`/absent as success — never on
`status` alone, or successful reads would look like failures.

**(c) `raise_for_status()` discards the body.** `_checked()`
([nomba_client.py:101-108](backend/app/services/nomba_client.py#L101-L108))
keeps the first 300 chars of the response text on HTTP ≥ 400, because that's
where `"account not found"` / `"Insufficient fund"` actually live.

`NombaAPIError` surfaces to users as a real message rather than a bare 500 in
two places: [banks.py:22-28](backend/app/routers/banks.py#L22-L28) (→ 400 "check
the account number and bank") and
[expenses.py:132-136](backend/app/routers/expenses.py#L132-L136) (→ 502 "Payout
failed: …").

---

## 4. API surface

Every Nomba endpoint Evident calls, all wrapped in
[nomba_client.py](backend/app/services/nomba_client.py):

| Wrapper | Method + path | Purpose |
| --- | --- | --- |
| `_issue_token` | `POST /v1/auth/token/issue` | get access + refresh token |
| `_refresh_token` | `POST /v1/auth/token/refresh` | extend session |
| `create_virtual_account` | `POST /v1/accounts/virtual` | collective pay-in NUBAN |
| `create_member_virtual_account` | `POST /v1/accounts/virtual` | per-member pay-in NUBAN |
| `fetch_virtual_account` | `GET /v1/accounts/virtual/{ref}` | read VA by `accountRef` (NUBAN backfill) |
| `fetch_virtual_account_transactions` | `GET /v1/accounts/virtual/{acct}/transactions` | per-account history (diagnostics only — 404s on the shared wallet) |
| `lookup_bank_account` | `POST /v1/transfers/bank/lookup` | resolve account number + bank code → account name |
| `fetch_banks` | `GET /v1/transfers/banks` | bank code list |
| `transfer_to_bank` | `POST /v2/transfers/bank` | payout (note: **v2**, everything else is v1) |
| `fetch_account_transactions` | `GET /v1/transactions/accounts` | wallet-wide feed, cursor-paginated |
| `requery_transaction` | `POST /v1/transactions/accounts` | poll a transfer's terminal status |

**Amounts are in naira**, not kobo, on both `transfer_to_bank` and inbound
`transactionAmount` ([nomba_client.py:210](backend/app/services/nomba_client.py#L210),
[webhook.py:134-135](backend/app/services/webhook.py#L134-L135)).

---

## 5. Money in

### 5.1 Virtual account provisioning

Two flavours, both `POST /v1/accounts/virtual`:

| | Collective | Member |
| --- | --- | --- |
| `accountRef` | the collective UUID | `mbr_<member_uuid>` |
| `accountName` | collective name, cleaned | `"<member name> <collective name>"`, cleaned |
| `callbackUrl` | `{APP_BASE_URL}/webhooks/nomba` | same |
| `currency` | `NGN` | `NGN` |

The `mbr_` prefix is the discriminator the webhook uses to tell a member account
from a collective account
([webhook.py:86-87](backend/app/services/webhook.py#L86-L87)).

`expectedAmount` is **deliberately not set**
([nomba_client.py:148](backend/app/services/nomba_client.py#L148)) — Evident does
its own partial/exact/excess reconciliation rather than letting Nomba reject
off-amount transfers.

#### Two hard-won gotchas

**Account names reject special characters.** Nomba rejects even a hyphen.
`_clean_account_name()`
([nomba_client.py:135-139](backend/app/services/nomba_client.py#L135-L139)) strips
to alphanumerics + spaces, collapses whitespace, caps at 50 chars, and falls back
to `"Evident Account"` if nothing survives. This is why the member account name
joins with a space, not `" - "`.

**The create response often omits the NUBAN.** `_extract_nuban()`
([collectives.py:18-20](backend/app/routers/collectives.py#L18-L20)) tries
`bankAccountNumber` → `accountNumber` → `bankAccountNo`; if all are missing the
code re-reads the account via `fetch_virtual_account(ref)`, which does return it
([collectives.py:90-93](backend/app/routers/collectives.py#L90-L93)). Sandbox VA
responses also carry no `accountId`/`walletId`, so `virtual_account_id` falls back
to the NUBAN itself ([collectives.py:95](backend/app/routers/collectives.py#L95)).
`GET /collectives/{id}` additionally **backfills** the NUBAN for collectives
created before this fallback existed
([collectives.py:128-140](backend/app/routers/collectives.py#L128-L140)).

#### Failure policy differs by caller — intentionally

- **Collective creation**: VA failure → full `db.rollback()` + `502`. A collective
  with no account is useless.
- **Organizer's personal account**: best-effort. The collective's own account
  already exists, so a hiccup is logged loudly but doesn't fail creation
  ([collectives.py:107-110](backend/app/routers/collectives.py#L107-L110)).
- **Invited member**: VA failure → the uncommitted member row rolls back and the
  caller gets a `502` with Nomba's real reason. `_provision_member_account`
  never swallows exceptions — that's exactly how the "special characters" bug
  once hid ([collectives.py:23-26](backend/app/routers/collectives.py#L23-L26)).

### 5.2 The webhook — `POST /webhooks/nomba`

[webhooks.py](backend/app/routers/webhooks.py)

**Signature verification** is HMAC-SHA256, base64-encoded, over the colon-joined
fields:

```
event_type : requestId : merchant.userId : merchant.walletId :
transaction.transactionId : transaction.type : transaction.time :
transaction.responseCode : <nomba-timestamp header>
```

compared against the `nomba-signature` header
([webhook.py:18-43](backend/app/services/webhook.py#L18-L43)). A `responseCode`
of `None` or the string `"null"` normalises to `""`.

> **Verification is off in the deployed environment on purpose.** It only runs
> when `NOMBA_SIGNATURE_KEY` is non-empty, and the hackathon account issues no
> signing key — Nomba sends unsigned webhooks. Setting the key would reject
> every real delivery with a 401. The code path is correct and round-trip tested
> ([test_webhook_flow.py:48-71](backend/test_webhook_flow.py#L48-L71)); it's the
> key that's absent, not the implementation.

**Event filtering:** anything that isn't `event_type == "payment_success"` is
acknowledged and ignored.

**Retry semantics:** a processing exception returns **HTTP 500**, not 200
([webhooks.py:32-41](backend/app/routers/webhooks.py#L32-L41)). Nomba only
retries on non-2xx. The earlier behaviour — 200 on failure — told Nomba the event
was handled even when a transient DB blip meant nothing was saved, so a payment
could silently vanish until reconciliation. Idempotency on `source_transfer_id`
makes the retry safe.

### 5.3 Matching cascade — [webhook.py:129-234](backend/app/services/webhook.py#L129-L234)

```
1. Idempotency guard
   Has source_transfer_id already been recorded as a Contribution
   OR as an UnmatchedTransfer?  → return, do nothing.

2. Strong signal: which account RECEIVED the money
   _match_member_by_receiving_account() collects every identifier the payload
   might carry — aliasAccountNumber, aliasAccountReference, accountNumber,
   bankAccountNumber, transaction.accountRef, order.accountRef — and matches
   against Member.virtual_account_id / Member.bank_account_number, plus
   Member.id for refs shaped "mbr_<uuid>".
   → a hit pins the member unambiguously. Collective is read from the member.

3. Otherwise: _find_collective() runs the same candidate set against
   Collective.virtual_account_id / bank_account_number / id, plus
   merchant.walletId.
   → no collective matched = log and drop (someone else's account).

4. Weak fallback: _match_member() by sender phone == Member.phone.

5. Classify against collective.dues_amount:
   no member          → "unmatched"    → UnmatchedTransfer row, NO ledger entry
   no dues configured → "exact"
   amount <  expected → "partial"
   amount >  expected → "excess"
   amount == expected → "exact"

6. Write Contribution + append-only LedgerEntry with running balance_after.
   Partial/excess shortfall or overage is spelled out in the description,
   never adjusted away.
```

**Why the candidate-set shotgun:** Nomba's create-VA response exposes no
`walletId`, only `accountRef` and `bankAccountNumber`, and the webhook payload
shape varies by event source. Matching against every identifier the payload could
plausibly carry is the only reliable approach
([webhook.py:99-100](backend/app/services/webhook.py#L99-L100)).

Unmatched transfers are resolved by a human via
`POST /collectives/{id}/unmatched/{uid}/resolve`
([ledger.py:86-162](backend/app/routers/ledger.py#L86-L162)), which promotes them
into a real `Contribution` + ledger entry so money is never quietly absorbed.

### 5.4 Reconciliation sweep — the *actual* real-time path

[main.py:44-135](backend/app/main.py#L44-L135)

**This is not a backstop. It is the primary way money reaches the ledger in the
deployed environment**, because Nomba does not deliver webhooks to Evident on the
shared hackathon account.

Two APScheduler jobs, both `max_instances=1, coalesce=True`:

| Job | Interval | Pages | Role |
| --- | --- | --- | --- |
| shallow | **15 s** | 1 (newest) | de-facto real-time ingestion |
| deep | **15 min** | 10 | catches anything older / missed |

Mechanism:

1. Window = yesterday → today (`timedelta(days=1)`, so midnight rollover is covered).
2. Page the **wallet-wide** feed `GET /v1/transactions/accounts` with a cursor —
   the per-NUBAN endpoint 404s on the shared wallet
   ([main.py:78](backend/app/main.py#L78)).
3. Skip anything where `entryType != "CREDIT"` — money in only.
4. Skip transaction ids already present in `Contribution` or `UnmatchedTransfer`.
5. Keep only rows that belong to Evident: `virtualAccountReference` starting
   `mbr_` with a known member id, **or** equal to a known collective id, **or**
   `recipientAccountNumber` in the set of known Evident NUBANs. Everything else
   is another team's traffic on the shared wallet.
6. `_tx_to_webhook_payload()` ([main.py:17-41](backend/app/main.py#L17-L41))
   rebuilds a synthetic `payment_success` envelope (`requestId` = `recon-<txid>`)
   so the healed payment runs through **the exact same** `process_payment_success`
   logic — one code path, no divergence.

The in-loop `seen.add(tx_id)` guards against the same transaction appearing twice
within a single sweep. A feed-fetch failure aborts the sweep and logs; page count
is capped so a busy shared wallet can't run away.

⚠️ Both sweeps scan the same window, so on a quiet wallet the shallow job hits
Nomba ~5,760×/day. That is intentional for demo latency, not a general-purpose
default.

---

## 6. Money out

### 6.1 Recipient validation

Before an expense row is even saved, `POST /v1/transfers/bank/lookup` resolves the
account number + bank code to an account name
([expenses.py:69-77](backend/app/routers/expenses.py#L69-L77)). No name back →
`422`. The resolved name is stored on the expense and is what appears on the
payout — so the recipient shown in the UI is Nomba's answer, not user input.

`GET /banks` serves the bank-code list, cached in a module-level list after the
first fetch ([banks.py:7-15](backend/app/routers/banks.py#L7-L15)) — process-local,
never invalidated.

### 6.2 Disbursement — [disbursement.py:48-119](backend/app/services/disbursement.py#L48-L119)

Guarded by: expense must be `pending`, approver must be `committee`/`organizer`,
and balance must cover the amount.

```
status → "disbursing"
write the DEBIT ledger entry and COMMIT        ← before the transfer call,
                                                 so intent is always recorded
POST /v2/transfers/bank
  amount        = naira, rounded to 2dp
  merchantTxRef = expense.id (UUID)  ← idempotency key
  senderName    = collective name, truncated to 50  ← recipient's statement
  narration     = "<collective> — <reason[:50]>"
```

Outcome handling:

| Nomba `status` | Result |
| --- | --- |
| `SUCCESS` | expense → `paid` |
| `FAILED` | expense → `failed`, reversing credit entry `expense_failed` |
| `REFUND` | expense → `failed`, reversing credit entry `expense_refunded` |
| anything else / exception during the call | expense stays `disbursing`, background poll starts |

Because the ledger is **append-only**, a failed payout is never corrected by
deleting the debit — `_reverse_expense_debit()`
([disbursement.py:29-45](backend/app/services/disbursement.py#L29-L45)) appends a
compensating credit ("Reversal — transfer for '…' did not complete") by `system`.

### 6.3 Status polling — [disbursement.py:122-164](backend/app/services/disbursement.py#L122-L164)

A fire-and-forget `asyncio.create_task` polls `POST /v1/transactions/accounts`
with the transfer ref: **10 attempts, 30 s apart** (~5 min total), opening its own
DB session per attempt. Terminal status → `paid` or `failed` + reversal. Exhausted
→ expense flagged `manual_review` and logged as an error.

⚠️ The poller lives only in process memory. A restart or deploy mid-flight loses
it and the expense is stranded in `disbursing` — nothing re-adopts it, and the
reconciliation sweep only covers **inbound** credits.

---

## 7. Nomba data on Evident's models

| Model | Field | Source |
| --- | --- | --- |
| `Collective` | `virtual_account_id` | VA `accountId`/`walletId`, falls back to NUBAN |
| | `bank_account_number` | VA NUBAN — where members transfer to |
| | `bank_name` | VA `bankName` |
| `Member` | `virtual_account_id`, `bank_account_number`, `bank_name` | personal VA, same fallbacks |
| `Contribution` | `source_transfer_id` | Nomba `transactionId` — **`unique=True`, the idempotency anchor** |
| | `sender_name`, `sender_account` | `customer.senderName` / `customer.accountNumber` |
| `UnmatchedTransfer` | `source_transfer_id` | same, also `unique=True` |
| `Expense` | `nomba_transfer_id` | transfer response `id`, used as the requery ref |
| | `recipient_name` | **resolved by Nomba lookup**, not user-entered |

The two `unique=True` constraints are what make webhook retries, duplicate
deliveries, and reconciliation replays all safe.

---

## 8. Frontend touchpoints

The frontend never talks to Nomba. It only renders what the backend recorded:

- [Landing.jsx:14](frontend/src/pages/Landing.jsx#L14) — "a dedicated Nomba account is provisioned instantly"
- [PublicShell.jsx:12](frontend/src/components/PublicShell.jsx#L12) — "Nomba × DevCareer Hackathon 2026"
- [CreateCollective.jsx:10-12](frontend/src/pages/CreateCollective.jsx#L10-L12) — step 2 of the wizard is what triggers VA provisioning
- [PayDues.jsx:23-26](frontend/src/pages/PayDues.jsx#L23-L26) — polls the member's contributions while waiting for the transfer to land

**Demo mode** ([demo/store.js](frontend/src/demo/store.js)) fakes the whole thing
in memory: `fakeNuban()` generates plausible 10-digit numbers, the bank is
`"Amucha MFB (Nomba)"`, and `simulateIncomingTransfer()`
([store.js:562-565](frontend/src/demo/store.js#L562-L565)) stands in for the
webhook so the ledger updates live with zero credentials.

---

## 9. Tooling

### `python find_transfer.py` — live diagnostics for money **in**

Reads the same `.env` as the app. Its purpose: prove whether money Nomba received
ever reached the app.

| Command | Does |
| --- | --- |
| *(no args)* | dumps collectives + their pay-in accounts, last 25 contributions, and the unmatched queue |
| `nomba <acct> [days]` | live per-VA transaction history (default 14 d), each row flagged **`>>> NOT in app`** if no contribution/unmatched row exists |
| `feed [days]` | wallet-wide feed (default 30 d), same flagging — use this one; the per-VA endpoint 404s on the shared wallet |
| `who <acct>` | which collective/member owns an account in the prod DB, then asks Nomba what it actually is (tries both `<acct>` and `mbr_<acct>` as refs) |

A row flagged `NOT in app` means the money is safe in the virtual account and only
the *recording* failed.

### `python test_webhook_flow.py` — offline pipeline test

Seeds a scratch SQLite DB and fires simulated `payment_success` events at the ASGI
app in-process. **No network, no credentials, no real money.** Covers: signature
round-trip (valid accepted, bogus rejected), exact payment, duplicate delivery
(idempotency), partial payment, and unknown sender → unmatched queue. Asserts a
final balance of ₦1,400. Note it reconfigures stdout to UTF-8 because the Windows
console can't print ₦.

---

## 10. Failure modes worth knowing

| Symptom | Cause | Where it lands |
| --- | --- | --- |
| Member VA creation 502s | special char in name that survived cleaning, or Nomba validation | member row rolls back; error surfaced to caller |
| Collective has no `bank_account_number` | create response omitted the NUBAN | auto-backfilled on next `GET /collectives/{id}` |
| Payment never appears | webhook not delivered (expected on the shared account) | healed by the 15 s sweep |
| Payment appears with no member | paid into the collective account, or sender phone unknown | `UnmatchedTransfer`, needs human resolution |
| Expense stuck `disbursing` forever | process restarted mid-poll | **no recovery path** — needs manual requery |
| Expense `manual_review` | 10 requeries, still non-terminal | ledger debit stands; unresolved |
| Payout 502 "Payout failed: …" | Nomba rejected (e.g. insufficient wallet funds) | debit already reversed, expense `failed` |
| Startup crash before any request | `NOMBA_SUB_ACCOUNT_ID` unset | required by schema despite being unused |

---

## 11. Known drift

[README.md](README.md) is out of date on two Nomba points — the code is right,
the prose isn't:

1. README:29 says processing errors "still return `200`". They return **500**, on
   purpose, so Nomba retries ([webhooks.py:32-41](backend/app/routers/webhooks.py#L32-L41)).
2. README:30 describes reconciliation as a 15-**minute** sweep "per collective"
   that merely *flags* missed payments. It is a 15-**second** shallow sweep plus a
   15-minute deep sweep, over the **wallet-wide** feed, and it **heals** payments
   by replaying them through the real handler.

Also open: `NOMBA_SUB_ACCOUNT_ID` is required but dead — either wire it up or drop
it from [config.py:24](backend/app/config.py#L24).
