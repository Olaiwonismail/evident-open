# Product

## Register

product

## Users

Nigerian collective treasurers and their members — estate/residents' associations, cooperatives, alumni groups, savings clubs (ajo/esusu), and church/community funds.

- **Organizers** set up the collective, invite members, assign committee power, and approve spending. Often on a laptop, but not always.
- **Committee members** approve or reject expenses — the check on spending.
- **Members** pay dues and watch the money. Mostly on phones, on variable networks.

The job to be done: **collect money and spend it transparently, without anyone having to "trust the treasurer."** The recurring real-world failure this replaces is a group treasurer holding funds in a personal account with no visibility.

## Product Purpose

Evident gives a collective a dedicated bank account with a **live public ledger**. Dues are paid by direct transfer and land on the ledger automatically; spending requires a public reason and committee approval before the payout goes to a verified recipient; money that can't be matched to a member is surfaced for review, never quietly absorbed.

Success looks like: **any member can answer "where is our money and where did it go?" at a glance, without asking anyone.** The ledger — not a person — is the source of trust.

## Brand Personality

Trustworthy, transparent, grounded. Three words: **honest, dependable, clear.**

- Voice: plain and reassuring — "trust the ledger, not the treasurer." Says what happened, including the bad news (rejections, failed payouts).
- Serious about money, but built for a community — credible without being a corporate bank, human without being gamified.
- Confidence through legibility, not decoration.

## Anti-references

*(Inferred from the current design critique; refine anytime.)*

- **Generic SaaS / crypto dashboard** — emerald-on-white rounded cards that could be any app. This is the current look and the thing to escape.
- **The navy-and-gold fintech cliché** — "serious about money" must NOT collapse into the saturated fintech default. Trustworthiness is carried by clarity and a distinctive-but-restrained identity, not by reflexive navy + gold.
- **Drab government portal** — grey, bureaucratic, the bad kind of "official."
- **Loud / gamified fintech** — confetti, badges, aggressive gradients, over-animation. Money is serious; celebration is quiet.

## Design Principles

- **The ledger is the product.** Transparency is the feature. Every screen should make "where did the money go" answerable at a glance; the ledger is the centerpiece, not a tab.
- **Honesty on the record.** Show rejected and failed items as prominently as successes. Nothing hides; the design earns trust by not flinching.
- **Confidence without coldness.** Precise and dependable like a bank, warm and legible like something a community actually owns.
- **Numbers must tie out.** Money is high-contrast, tabular, and reconciles visually (balance, flow, per-member) — a figure the user can't read or verify is a failure.
- **Respect the member's phone.** Fast, light, thumb-friendly on low-end Android; equally composed on desktop for organizers.

## Accessibility & Inclusion

- WCAG AA minimum. Financial figures and body text hit ≥4.5:1 — **never muted gray on tinted white** (the readability failure that undermines a trust product most).
- Mobile and desktop weighted equally: thumb-reachable primary actions, no hover-only affordances, layouts that hold from ~360px to desktop.
- `prefers-reduced-motion` honored on every animation.
- Tabular/lining figures for all money so columns align and scan.
- Performance is an accessibility feature here: minimize JS and payload for variable networks and low-end devices.
