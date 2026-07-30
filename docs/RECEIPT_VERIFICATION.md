# Receipt verification

## The gap this closes

Evident verifies almost everything about an expense already:

| Field | Verified by |
| --- | --- |
| Recipient name | the bank — never user input |
| Money actually moved | the payment provider |
| Who approved it | role check + append-only ledger |
| **Amount** | **nobody** |
| **Reason** | **nobody** |

A treasurer could request ₦50,000 for "generator repair", attach a ₦5,000
invoice, and nothing in the system would notice. The receipt was uploaded and
never read. This is the last place Evident still said "trust me".

## Three checks, cheapest first

Deliberately ordered so the strongest signals don't depend on the model. With
no API key configured, checks 1 and 2 still run.

**1. Duplicate receipt** — no model needed for the exact case.
Two fingerprints: `sha256` over the file bytes catches a byte-identical
re-upload; a **content fingerprint** over `vendor + total + date` (as read off
the document) catches the same receipt re-photographed, cropped or
re-compressed. Scoped to one collective — a cross-collective match would be a
stronger signal but would leak one group's expenses to another.

**2. Unusual amount** — arithmetic, no model.
Fires only when the request is *both* more than 3σ above the collective's mean
*and* larger than anything it has ever paid. Needs 4+ prior expenses; below that
the mean is noise. Either condition alone fires constantly on a small, lumpy
expense history.

**3. Document reading** — Gemini vision (`gemini-3.6-flash`).
Extracts vendor, total, currency, date, line items and legibility under a strict
JSON schema, then compares the total against the requested amount (1% tolerance
for rounding and fees). Also flags a currency mismatch, an unreadable document,
and anything the model thinks a reviewer should know.

## Two rules the design is built on

**Flag, never block.** A false positive in a transparency product is expensive:
wrongly flagging a legitimate expense and getting it rejected damages the thing
the check exists to protect. Nothing here can stop a payout. Every failure path
— no API key, unreadable file, model error, refusal — degrades to *no opinion*,
never to *rejected*. The upload response carries an explicit `"blocking": false`.

Note the status vocabulary: a failed check returns `error`, not `clean`. Silence
must never be mistaken for a clean bill of health.

**The verdict is published.** Flags are stored on the expense and written into
the ledger entry's `actor_name` at approval, so the permanent public record
reads *"approved despite AI flag: requested ₦50,000 but the document totals
₦5,000 — Chinedu Balogun"*. The model is held to the same transparency rule as
the committee instead of being an invisible advisor.

## Perceptual image hashing was tried and removed

The conventional answer to "detect a re-photographed duplicate" is a perceptual
hash (dHash/aHash). It does not work on receipts, and this was measured rather
than assumed.

A receipt is ~95% white space. Downsampled to the hash grid it becomes a
near-uniform pale rectangle with the text gone, so every receipt hashes to
roughly the same value. On a 256-bit dHash with histogram equalisation:

| Pair | Hamming distance |
| --- | --- |
| Same receipt, re-photographed (the true duplicate) | 8 |
| Two genuinely different receipts | 5 |
| Two other genuinely different receipts | 7 |

Different documents scored **closer than the true duplicate**. No threshold
separates those populations, so it was removed rather than shipped with a
setting that cannot work. The content fingerprint replaces it, and is both more
robust (survives any amount of re-encoding) and more explainable — "same vendor,
same total, same date as expense X" is something an approver can act on, where a
Hamming distance is not.

## What this is not

It raises the bar; it does not close the door. A vision model reading a
convincingly forged receipt will report it as clean. This is receipt
*verification*, not fraud *prevention*, and should not be described as the
latter.

## Wiring

| Piece | File |
| --- | --- |
| Fingerprints, duplicates, amount baseline | `app/services/receipts.py` |
| Vision extraction + flag rules | `app/services/receipt_ai.py` |
| Upload + serve endpoints | `app/routers/receipts.py` |
| Verdict stored on the expense | `app/models/expense.py` |
| Verdict published to the ledger | `app/services/disbursement.py` |

`POST /collectives/{id}/receipts` (multipart: `file`, `amount`, `reason`) stores
the file, runs all three checks, and returns the verdict *before* the expense is
submitted — so the reviewer sees it while deciding. The result is then passed
through `POST /collectives/{id}/expenses` to be stored with the expense.

Config: `GEMINI_API_KEY` enables check 3; unset simply disables it.
`RECEIPT_STORAGE_DIR` defaults to `receipts/`.

## Verification status

| Verified | How |
| --- | --- |
| Duplicate detection — exact, re-photographed, no false positive | fingerprint tests |
| Flag rules and severities | synthetic mismatch/duplicate/anomaly cases |
| Degradation with no API key | upload route returns `error`, 0 flags, never raises |
| Duplicate flag fires with no model at all | upload route, key unset |
| Guards — empty file, unknown collective, path traversal | 400 / 404 / 404 |

**Not verified:** the live vision extraction. No Gemini credentials are
available on this machine, so `extract()` has never been run against the real
API — only its failure path has.

The request shape was taken from Google's live documentation rather than from
memory, which mattered: the current API is `client.interactions.create(...)`
with an `input=[...]` list and a `response_format` schema — **not** the
`generate_content` form most examples still show. Accepted upload types are
pinned to what the model can actually read (PNG, JPEG, WEBP, HEIC, HEIF, PDF —
HEIC included because that is the default iPhone camera format). Inline base64
caps the whole request at 20MB; the 10MB upload limit keeps receipts inside it.

Still, the first real call should be treated as unproven.
