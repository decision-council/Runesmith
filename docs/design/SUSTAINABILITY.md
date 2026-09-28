# Sustainability: earning on inference without bending the evidence

Status: **idea and design direction, not built.** Proposed by Lars on 2026-09-28. The research (web, sourced and dated, with the unconfirmed claims marked) is in [research/inference_monetization_2026-09-28.md](research/inference_monetization_2026-09-28.md).

## The idea (Lars, 2026-09-28)

People choose and connect models inside the Studio, so Runesmith could earn on inference to sustain the open-source project. There are two routes:
- an affiliate or referral program with inference providers;
- becoming our own inference provider, with an especially easy "click and add" setup and recommendations inside the program.

## The rule

**Runesmith recommends models by measured results, never by what pays.** It exists to tell people honestly which model works, weak and free ones included. A recommendation shaped by a commission would destroy the scientific credibility the paper and the community rest on. So, whatever we build:
1. Rankings come from measurements: success per call, per euro, per unit of free quota, and on the owner's own kind of project. The measurement catalogue (`SELF_IMPROVEMENT_MEASUREMENTS.md`, in progress) supplies them, and the ranking method is published.
2. Any paid relationship is disclosed **right next to the recommendation it touches**, not in a footer. This is also the legal minimum: the US FTC and the UK ASA/CMA both require clear disclosure at the point of recommendation.
3. Free and local options stay first-class and are always shown.
4. Free tiers are never pooled, shared or resold. Every provider checked ties free quota to the account, and several forbid multiple accounts.

## What the research found

- **Real affiliate programs for inference are rare.** Confirmed on the providers' own pages:
  - Novita AI: 10% of referred spend for 180 days.
  - Cerebras: token-bonus referrals, US only, plus a partner program.
  - Replicate: an affiliate program; the rate is not disclosed.
  - Anthropic: an enterprise referral program; credits for paying subscribers.

  OpenAI, the Gemini API, Mistral, DeepInfra, Cloudflare and Vercel have none. Groq and Together programs appear only on third-party trackers (unconfirmed). OpenRouter's app attribution only puts an app in its public rankings; it pays nothing.
- **Reselling needs real agreements.** Every major provider's terms forbid reselling raw API access by default. Lawful routes are a formal partner or reseller agreement (for example Groq's "Resold Customers", Mistral's authorised partners), or hosting open-weight models ourselves.
- **What comparable open-source tools do.** The common pattern is free bring-your-own-key at cost, plus an optional hosted-credits product:
  - Zed: its hosted models at list price + 10%;
  - Kilo Code: subscription credits, and its own affiliate program;
  - OpenHands and Cline: hosted models at cost, plus team plans;
  - OpenCode: curated models by subscription, and a pay-as-you-go gateway for models it has benchmarked. That gateway is close to our evidence-first idea.
- **Charging people.** A merchant of record (Paddle or Lemon Squeezy, about 5% + $0.50, often 7-8% all-in) takes over VAT, tax and chargebacks. That matters for a small open-source team.

## Options, in order

1. **Disclosed "get a key" links, only where a real program exists and only for paid tiers.** They sit next to measured recommendations and carry an inline note such as "Runesmith earns a commission if you sign up here". Low effort, low risk, low to medium revenue. Each program's terms must be re-checked on the provider's own site before shipping.
2. **Runesmith credits through Milliner, at cost or with a small published markup** (the Zed and Kilo pattern). This is the most revenue potential and the easiest setup: one account, every model, no keys. It needs:
   - genuine reseller or partner agreements upstream, or self-hosted open-weight models;
   - a merchant of record;
   - a credits ledger.

   Bring-your-own-key always stays at zero markup, and rankings stay independent of what Milliner hosts cheaply.
3. **Open-source and startup credit programs** (Fireworks for Startups, maintainer grants, the Goose grant program). They fund our own test and benchmark inference, earn nothing, carry no risk, and take only applications.
4. **A self-hosted "Runesmith Cloud" for open-weight models.** It has the highest ceiling, but pays off only with steady use (on-demand H100s run about $3-8 an hour) and needs real operations work. It comes later, if at all.
5. **OpenRouter attribution headers.** Free visibility in OpenRouter's app rankings, and worth doing, but not income.

## How it would look in the Studio (first version)

- Thinking power shows the recommended models for this project with their measured numbers.
- Where a disclosed program exists, a "Get a key" link sits beside the numbers, with its disclosure.
- If Runesmith credits (option 2) exist, "One account for every model" is offered next to bring-your-own-key and local, with its markup shown.
- Nothing about the ranking changes when a link pays.

## Decisions only Lars can make

- Whether to run option 2, which needs a legal entity to sign reseller agreements and to receive payments.
- Which merchant of record to use.
- Whether affiliate income goes to the project's maintainers or a community fund. Showing it publicly would match the evidence-first stance.

## Order of work

1. **Now:** nothing in the release. The release ships with no commercial links, so the first impression is untouched.
2. **Right after release:** options 3 and 5, then option 1 once each program is verified directly.
3. **When there are users:** option 2 on Milliner, with the rankings driven by the community's aggregate evidence (`COMMUNITY_EVOLUTION.md`).
