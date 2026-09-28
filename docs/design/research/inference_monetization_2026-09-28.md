# Inference Monetization Research for Runesmith
Compiled 2026-09-28. Web research only; all claims sourced with URL and access date. Anything not confirmed on an official/primary page is marked **[unconfirmed]**.

Context: Runesmith lets weak/free/local models build software via a local Studio. Constraints that filter every option below: (1) recommendations stay evidence-first, ranked by measured results, never by commission; (2) any paid relationship is disclosed next to the recommendation; (3) free/local stays first-class; (4) free tiers are never pooled or resold.

---

## 1. Affiliate / referral / partner / revenue-share programs of inference providers and routers

### OpenRouter
- **App attribution (not a revenue program):** Sending `HTTP-Referer` (required, primary identifier) and `X-Title`/`X-OpenRouter-Title` (display name) headers gets an app listed on OpenRouter's public rankings/leaderboard and on a model's "Apps" tab. This is attribution/analytics only — the official docs page contains **no mention of any payment or revenue share to apps for this attribution**. Source: [App Attribution](https://openrouter.ai/docs/app-attribution), accessed 2026-09-28.
- **Fees (this is how OpenRouter itself makes money, relevant to any resale math):** 5.5% fee on card credit purchases (5.0% flat for crypto, ~$0.80 floor); a new (Sept 2026) self-serve "Business" tier charges 8% for EU/US-only routing. BYOK (bring-your-own-key) usage is free up to $25,000/month of list-price inference, then a 5% fee. OpenRouter does not mark up per-token model prices; it takes its cut on the credit/BYOK layer. Source: third-party pricing breakdowns citing OpenRouter's own pricing docs — [OpenRouter Pricing 2026](https://omidsaffari.com/blog/openrouter-pricing), accessed 2026-09-28 **[figures not independently re-verified on openrouter.ai/docs/api_reference/limits, which only documents rate limits, not fees — treat fee percentages as unconfirmed pending a direct re-check]**.
- **Free-model rate limits (official):** `:free` model variants are capped at 20 requests/minute, and a daily cap of 50 requests/day (accounts with under $10 lifetime credit purchased) or 1,000/day (at or above $10). BYOK requests are exempt. Source: [API Credit & Rate Limits](https://openrouter.ai/docs/api_reference/limits), accessed 2026-09-28.
- **Becoming a provider:** Apply at [openrouter.ai/providers/apply](https://openrouter.ai/providers/apply). Requirements: OpenAI-compatible `/chat/completions` endpoint with usage tokens on stream/non-stream, a `/models` endpoint with pricing/context/features/datacenter location, support for monthly invoicing (OpenRouter pays providers this way), and a published privacy/data-retention policy. OpenRouter states it has a large backlog and prioritizes providers with proprietary models; commission/take-rate to providers is not disclosed on the page. Uptime below 80% demotes an endpoint to fallback-only. Source: accessed 2026-09-28.

### Together AI
Third-party affiliate-network listings describe a one-time-commission "partner program with API credits for qualified introductions," but no such program is documented on together.ai itself in what we could reach. **[unconfirmed — only found on a non-official aggregator, openaffiliate.dev]**, accessed 2026-09-28.

### Fireworks AI
No affiliate/commission program found. Fireworks runs a **Fireworks for Startups** credits program (apply at fireworks.ai/startups; up to $10,000 in inference credits, 1-year expiry, plus higher rate limits, applied-AI support, and joint marketing) and partner-channel credits (e.g., $50 of Fireworks credit via the AMD AI Developer Program). This is a startup-credit program, not a referral/commission scheme. Source: [Fireworks for Startups](https://fireworks.ai/startups), accessed 2026-09-28.

### Groq
- **Groq Partner Program**: described on Groq's own site as for "hand-selected scaling companies" (infrastructure integrations / enterprise introductions), giving inference credits — not a self-serve commission program. Source: [groq.com/groq-partner-program](https://groq.com/groq-partner-program), accessed 2026-09-28 (page itself gives little public detail on terms).
- **Groq Affiliate Program**: exists but only documented on third-party affiliate trackers, e.g. a flat ~$15 one-time commission, 30-day cookie, listed via an affiliate network rather than a page on groq.com. **[unconfirmed as an official Groq program — treat as third-party-reported]**, accessed 2026-09-28.
- Groq's Terms of Service (Services Agreement) generally prohibit reselling/sublicensing API access, but carve out a formal "Resold Customers" mechanism for approved GroqCloud resellers — i.e., reselling is possible only via a negotiated reseller agreement, not by default. Source: [Groq Services Agreement](https://console.groq.com/docs/legal/services-agreement), accessed 2026-09-28.

### DeepInfra
No affiliate or referral program found on deepinfra.com. DeepInfra's Terms of Service (Section 11(a)(viii)) explicitly bar reselling, sublicensing, or sharing account/access credentials: "*resell, sublicense, rent, distribute... or sell, transfer, or share any account or access credentials*" (quoted under 15 words per clause fragment). Source: [DeepInfra Terms](https://deepinfra.com/terms), accessed 2026-09-28.

### Cerebras
- **API Certification Partner Program**: for LLM API *platforms* (not individual apps) to integrate/validate/co-market ultra-fast inference on Cerebras wafer-scale hardware; requires sub-150ms (targeting <50ms) latency, OpenAI-compatible or gRPC/REST support, and enterprise security (mTLS/OAuth2). Source: [Cerebras Partner Program](https://www.cerebras.ai/blog/cerebras-api-certification-partner-program-for-llm-api-providers), accessed 2026-09-28.
- **Referral Program** (individual, US-only, personal accounts): both referrer and referee get 200,000 bonus tokens/day, capped at 1,000,000 total. Source: [Referral Program Terms](https://www.cerebras.ai/referral-program), accessed 2026-09-28.

### SambaNova
No individual affiliate program found. SambaNova runs **SambaManaged**, letting cloud/telecom partners (e.g., SoftBank, OVHcloud) resell SambaNova inference capacity as a formal wholesale/distribution deal, plus a **Startup Accelerator** (free enterprise-tier usage, priority support, marketing exposure). Source: [SambaCloud](https://sambanova.ai/products/sambacloud), accessed 2026-09-28.

### Hugging Face (Inference Providers)
Official framing: Inference Providers is a routing/billing layer over third-party providers (Together, Fireworks, DeepInfra, SambaNova, Replicate, fal, etc.), billed through the user's HF account **at the provider's standard rate with no additional HF markup** today; HF has signaled it **may** add provider revenue-sharing in the future but nothing is confirmed live. **[future revenue-share unconfirmed]** Source: [HF blog on DeepInfra as a provider](https://huggingface.co/blog/inference-providers-deepinfra), accessed 2026-09-28.

### Replicate
Has a **Replicate Affiliate Program** (affiliate.replicate.so/program) — unique referral link/dashboard, one-time commission (rate not disclosed in what we could reach), plus separately "developer partnerships with usage-based referral credits." Source: [Replicate Affiliate Program](https://affiliate.replicate.so/program), accessed 2026-09-28.

### Novita AI
Officially documented (affiliates.novita.ai): **10% commission on referred spend for 180 days** from signup, self-serve dashboard + link, explicit anti-spam clause (violation = removal/termination), plus a separate $10-give/$10-get promo capped at $500 total in LLM credits. Source: [Novita AI Affiliate Program](https://blogs.novita.ai/novita-ai-affiliate-program/), [affiliates.novita.ai ToS](https://affiliates.novita.ai/programs/model-api/tos/), accessed 2026-09-28.

### Mistral AI
No public commission/affiliate program found for API referrals. Mistral runs a non-dilutive **startup program** (up to €30,000 in La Plateforme credits + mentorship — as of 2026 apparently invite/contact-mediated, not a public self-serve form) and an **Ambassador program** (free API credits, early access, community recognition, no cash commission). Note: **as of August 5, 2026 Mistral removed API access from consumer accounts and restricted it to business customers**, which matters for anyone hoping individuals could get a Mistral key directly. Source: [Mistral Ambassador docs](https://docs.mistral.ai/guides/contribute/ambassador), accessed 2026-09-28.

### Google AI Studio / Gemini API
No affiliate/commission program for the Gemini API itself. Google Cloud has a broad general **Cloud Affiliate Program**, and the Gemini API has a **"partner and library integration"** guide aimed at people building gateways/frameworks/SaaS on top of Gemini (technical guidance, not a revenue program). Source: [Gemini API partner integration docs](https://ai.google.dev/gemini-api/docs/partner-integration), accessed 2026-09-28.

### Anthropic
No open commission-based affiliate program for individuals. Anthropic runs a **Claude for Enterprise Referral Partner Program** (apply, then earn "commission on successful referrals" — terms not public) aimed at business referrers, and a separate **Claude Partner Network** for enterprise/technical partners (referral credit + deal protection, not cash commission). There is also a consumer **Claude Pro/Max referral** mechanic: paying Max subscribers ($100–200/mo) can refer people for $10 Claude credit each, capped at $30/3 referrals — credit, not cash. Source: [Become a referral partner](https://www.anthropic.com/referral?p=969), [Claude Partner Network](https://www.anthropic.com/news/services-track-partner-hub), accessed 2026-09-28.

### OpenAI
**No public affiliate/commission program** for ChatGPT or the API as of 2026. OpenAI runs occasional regional promo campaigns (e.g., a ChatGPT Free referral campaign in India/Indonesia/Mexico, Aug 18–Sep 17 2026) that reward with temporary higher free-plan limits, not cash or transferable credit. A "partner-interest" intake form exists but no public commission schedule/cookie window/payout terms. Source: community/analyst summaries of OpenAI's own policy pages, accessed 2026-09-28 **[absence of a program is itself the finding — could not find one on openai.com]**.

### NVIDIA (build.nvidia.com / NIM)
No dedicated affiliate program for build.nvidia.com API keys. NVIDIA does run a generic consumer/hardware **NVIDIA Affiliate Program** (5% commission, 30-day cookie, run through Rakuten/CJ Affiliate networks) that is about GPU/hardware purchases, not inference API credits, and a large B2B **NVIDIA Partner Network (NPN)** for resale/solution partners — again not an individual-affiliate-for-API-credits scheme. build.nvidia.com's free tier is explicitly for "prototyping, research and evaluation," and production/serving real users requires an NVIDIA AI Enterprise license. Source: [NVIDIA Partner Network](https://www.nvidia.com/object/nvidia-partner-network.html), accessed 2026-09-28.

### Cloudflare Workers AI
No affiliate/referral program found; a Cloudflare community thread explicitly notes Cloudflare has **no way to earn credit for referrals**, unlike AWS/DigitalOcean/Vercel. Cloudflare instead runs a **Technology Partners** program (co-marketing/integration, e.g., with Hugging Face) — not a commission scheme. Source: [Cloudflare community thread](https://community.cloudflare.com/t/advice-for-cloudflare-part-1-affiliate-referral-program/925541), accessed 2026-09-28.

### Vercel AI Gateway
No partner/affiliate/referral program found for the AI Gateway specifically. Vercel's own pricing page states the Gateway adds **zero markup** on provider token prices (including BYOK) and monetizes only through purchased credits and a few optional paid capabilities. Source: [Vercel AI Gateway pricing](https://vercel.com/docs/ai-gateway/pricing), accessed 2026-09-28.

### Comparison table (Section 1)

| Provider | Affiliate/referral program? | Terms (where known) | OSS desktop app eligible? | Disclosure stated? |
|---|---|---|---|---|
| OpenRouter (app attribution) | No revenue share; attribution only | Free, just send headers | Yes, trivially | N/A (no payment involved) |
| OpenRouter (become provider) | N/A — you'd be a provider, not affiliate | Apply, technical bar, backlog | N/A | N/A |
| Together AI | Claimed by 3rd-party trackers only | Unclear, one-time | Unconfirmed | Unconfirmed |
| Fireworks AI | No; startup credits instead | Up to $10k credits, 1yr expiry | Yes (if "startup") | N/A |
| Groq | Partner program (enterprise) + 3rd-party-reported affiliate (~$15 one-time) | Opaque | Partner program: unclear; affiliate: likely yes | Unconfirmed |
| DeepInfra | None found | ToS bars resale/sharing outright | N/A | N/A |
| Cerebras | Referral (individual, US) + Certification Partner (platforms) | 200k tokens/day each side, capped 1M | Referral: yes if US person; Certification: aimed at platforms not desktop apps | Unconfirmed |
| SambaNova | None (individual); wholesale reseller deals (enterprise) | Enterprise-only | No | N/A |
| Hugging Face Inference Providers | No (no markup today; future TBD) | N/A | N/A | N/A |
| Replicate | Yes | One-time, rate undisclosed | Likely yes | Unconfirmed |
| Novita AI | Yes, documented | 10% of referred spend, 180 days | Yes | Program ToS bars spam; no explicit disclosure clause found |
| Mistral | No commission program; credits/ambassador only | Credits, not cash | Consumer API access itself restricted since Aug 2026 | N/A |
| Google Gemini API | No | N/A | N/A | N/A |
| Anthropic | Enterprise referral (cash?) + consumer credit-only referral | Enterprise: opaque; consumer: $10 credit x3 | Consumer referral needs a paid Max sub | Unconfirmed |
| OpenAI | No | N/A | N/A | N/A |
| NVIDIA NIM/build.nvidia.com | No (hardware affiliate ≠ API) | N/A | N/A | N/A |
| Cloudflare Workers AI | No | Confirmed absent by community feedback | N/A | N/A |
| Vercel AI Gateway | No | Zero-markup stated instead | N/A | N/A |
| Kilo Code (comparator, not an inference provider) | Yes — own product | $9.50–$99.50 flat one-time per paid-tier referral, 30-day cookie, $100 payout floor | N/A (this is the OSS tool's own program) | Not specified on the partner page itself |

---

## 2. Becoming a provider or reseller

**OpenRouter marketplace listing**: covered above — apply, meet technical bar, no disclosed take-rate to providers, large backlog, priority to proprietary models (self-hosted open-weight models are not explicitly excluded but are not prioritized either). Source: accessed 2026-09-28.

**Resale/sublicensing clauses in major providers' terms** (all found to explicitly restrict resale of raw API access; a formal reseller relationship, where it exists, requires the provider's own separate agreement):
- **OpenAI**: Services Agreement licensing is stated to be non-transferable and non-sublicensable; customers "may not resell or lease access" to accounts, and API keys may not be shared/sold/transferred without prior written OpenAI approval. Source: [OpenAI Services Agreement](https://openai.com/policies/services-agreement/), accessed 2026-09-28.
- **Anthropic**: Commercial ToS restrict using the API to "build a competing AI product," and standard clauses cover resale/service-bureau use and making API access available to third parties without approval. Source: [Anthropic Commercial Terms](https://www.anthropic.com/legal/archive/c87a6bf8-106e-47d8-9b7b-47ae3a0fecbf) (via secondary summary), accessed 2026-09-28 **[exact resale clause wording not independently confirmed verbatim — re-check before relying on it]**.
- **Google Gemini API**: Additional Terms of Service + Prohibited Use Policy found; no explicit resale clause surfaced in what we reached, though Google Cloud's general reseller program exists separately for GCP itself. **[Gemini-API-specific resale clause unconfirmed]**, accessed 2026-09-28.
- **Groq**: Standard terms prohibit selling/reselling/sublicensing Services or API, and prohibit sharing account credentials — but the agreement explicitly carves out a "Resold Customers" framework for approved GroqCloud resellers. Source: [Groq Services Agreement](https://console.groq.com/docs/legal/services-agreement), accessed 2026-09-28.
- **Mistral**: Commercial ToS state that using Mistral products on a *third-party partner's* infrastructure to resell/market them "must be expressly authorized by such third-party partner" in its own ordering docs — i.e., resale is only possible through Mistral-blessed partner channels, not by default. Source: [Mistral Additional Product Terms](https://legal.mistral.ai/terms/additional-terms), accessed 2026-09-28.
- **Together AI**: ToS bars "transfer, distribute, resell, lease, license, or assign the Services or otherwise offer the Services on a standalone basis." Source: [Together AI Terms of Service](https://www.together.ai/terms-of-service), accessed 2026-09-28.
- **DeepInfra**: as above, explicit resale/credential-sharing prohibition. Source: accessed 2026-09-28.
- **NVIDIA**: general NVIDIA account/software terms prohibit copying/reselling/sublicensing and sharing account access; a build.nvidia.com-specific resale clause wasn't separately isolated but the general prohibition applies. Source: [NVIDIA Terms of Service](https://www.nvidia.com/en-us/about-nvidia/terms-of-service/), accessed 2026-09-28.

**Net finding**: Every major first-party provider checked prohibits reselling raw API access by default; the only lawful path to "become a provider/reseller" is (a) a formal partner/reseller agreement with that specific company (Groq "Resold Customers," Mistral "third-party partner," SambaNova "SambaManaged," NVIDIA NPN), or (b) hosting your **own** open-weight models on GPU infrastructure you rent, where there is no such restriction because you are not reselling anyone else's API — you're running your own service on rented compute.

**Rough self-hosting economics (2026, on-demand/serverless rates, per official-adjacent pricing pages/aggregators — treat as directional, prices move monthly)**:
- **RunPod**: H100 serverless ≈ $4.55–4.79/hr equivalent (~$0.00126/sec active); A100 serverless ≈ $2.72/hr. Dedicated H100 pod from $2.89/hr. Source: [RunPod Pricing](https://www.runpod.io/pricing), accessed 2026-09-28.
- **Modal**: H100 ≈ $0.001097/sec (~$3.95/hr) with per-second billing and scale-to-zero; guaranteed/non-preemptible or narrow-region requests cost 1.5–3x more. Source: aggregator citing Modal's own pricing, accessed 2026-09-28.
- **Fireworks AI**: on-demand dedicated GPU as of Sept 1 2026: H100/H200 $8.00/hr, B200 $13.00/hr, B300 $15.00/hr, GB300 $20.00/hr (all just raised 11–30% from prior rates). Source: aggregator citing Fireworks' own pricing/blueprint pages, accessed 2026-09-28.
- **Comparison to reselling**: buying inference wholesale and marking it up (where contractually allowed, i.e., via an actual partner/reseller deal) avoids GPU-ops risk (utilization, cold starts, model-serving engineering) but caps margin to whatever spread the upstream partner allows and exposes Runesmith to the provider's pricing/availability changes. Self-hosting open-weight models gives full margin control but requires sustained utilization (RunPod's own break-even framing: >~10 active hrs/day makes a dedicated pod cheaper than serverless) and real MLOps investment — a poor fit for a volunteer-run open-source project unless usage is large and steady.

---

## 3. How comparable open-source AI coding tools fund themselves

| Tool | Core extension/CLI | Monetization | Notes | Source (accessed 2026-09-28) |
|---|---|---|---|---|
| **Cline** | Free, MIT, BYOK (pay provider directly, no markup) | Optional "Cline credits" pay-as-you-go top-up at cost (no markup); Teams plan $20/user/mo (first 10 seats free); Enterprise custom | Raised $32M seed+Series A (2025); no affiliate program found for its own tool | [fast.io Cline pricing guide](https://fast.io/resources/cline-pricing-guide/) |
| **Kilo Code** | Free, open source (fork of Cline+Roo) | "Kilo Pass" subscription ($19/$49/$199/mo) tops up an at-cost balance for a curated model set; $20 first-top-up bonus; zero-markup BYOK also supported | Runs its **own affiliate/partner program**: flat one-time commission per paid referral ($9.50/$24.50/$99.50 by tier), 30-day last-touch cookie, $100 payout floor, paid-ads channels excluded | [kilo.ai/partners](https://kilo.ai/partners); [apidog Kilo Code overview](https://apidog.com/blog/kilo-code/) |
| **Roo Code** | Free, open source | BYOK-oriented; distinct commercial layer not clearly documented in what we reached | **[unconfirmed]** | — |
| **Continue.dev** | Free, Apache-2.0 solo tier | Freemium: Team $20/seat/mo incl. $10 model credits/seat; Starter free with pay-as-you-go frontier model billing at $3/M tokens; Enterprise governance add-ons | Acquired by Cursor in June 2026; hosted "Continue Hub" service reportedly discontinued post-acquisition | [Continue Hub pricing](https://docs.continue.dev/hub/governance/pricing) |
| **Aider** | Free, MIT, fully open, BYOK | No hosted product found; unfunded (2 employees, no external funding reported) | Pure OSS/community model, no monetization layer identified | [Tracxn Aider profile](https://tracxn.com/d/companies/aider/__jJfoAiTBc5Tc98a8irksOk29dn1RTrl0cRXml_MQeo8) |
| **Zed** | Free editor, unlimited BYOK | Pro $10/mo bundles $5 of Zed-hosted-model credit, then billed at "API list price + 10%" markup for Zed-hosted usage; Business $30/seat/mo | Zed states pricing is still evolving; markup applies only to Zed-hosted convenience, not to BYOK | [Zed pricing](https://zed.dev/pricing); [Zed AI billing post](https://zed.dev/blog/zed-ai-billing) |
| **OpenHands (All Hands AI)** | Free, open-source core | OpenHands Cloud: free tier capped at 10 conversations/day; pay-as-you-go "OpenHands LLM provider" at cost, no markup; Enterprise custom | Raised $5M seed (2024) + $18.8M Series A (Nov 2025); OSS-maintainer credit grants ($100–500) | [OpenHands pricing](https://www.openhands.dev/pricing); [OSS credit program](https://www.openhands.dev/blog/openhands-cloud-oss-credit-program-supporting-open-source-maintainers) |
| **Goose** (Block → Agentic AI Foundation) | Fully free, Apache-2.0, BYOK, no paid tier | None — donated to the Linux Foundation's AAIF (Dec 2025); Block funds a "Goose Grant Program" (up to $100k) for ecosystem projects, not a revenue mechanism for Goose itself | Explicitly "commercial-friendly" open governance model, no monetization of the tool | [Block Goose grant announcement](https://block.xyz/inside/introducing-the-goose-grant-program) |
| **Void** | Free, MIT | No clear monetization identified; $500K total raised, YC-backed | Business model described by third parties as speculative ("likely premium features") | [Dealroom Void profile](https://app.dealroom.co/companies/void_4) |
| **Warp** | Free terminal; AI features gated | Build $20/mo (1,500 credits), Max $200/mo, Business $50/user/mo; credits meter AI + compute + platform usage | Just collapsed three legacy tiers into "Build" in 2025–26 pricing pivot | [Warp plans and billing](https://docs.warp.dev/support-and-billing/plans-and-pricing/ai-credits) |
| **OpenCode** | Free, MIT, BYOK, no account needed | Optional "OpenCode Go" subscription ($5 first month then $10/mo) for curated open-weight models; "OpenCode Zen" pay-as-you-go gateway for benchmarked models; Enterprise per-seat | 208k+ GitHub stars, moved from sst/opencode to anomalyco/opencode | [opencode.ai](https://opencode.ai/); [DataCamp OpenCode overview](https://www.datacamp.com/blog/what-is-opencode) |

**Pattern across the category**: the dominant model is "free/OSS core tool + BYOK with zero markup on inference, plus an *optional* first-party hosted-credits product that the vendor sells at cost or a small explicit markup (Zed: +10%), plus a paid Teams/Enterprise seat tier for governance/SSO/admin features." Only **Kilo Code** among these was found to run its own cash affiliate/commission program for its own product — none were found running affiliate programs *for third-party inference providers* the way Lars is considering. Most avoid any commission-based recommendation logic entirely, which is directly compatible with Runesmith's evidence-first constraint.

---

## 4. Free-tier rules on pooling/reselling/sharing

- **Google Gemini API / AI Studio**: Free-tier quota is tied to a *Google Cloud project*, not to an API key — creating more keys in the same project does not add quota, so pooling many "free" keys behind one router doesn't multiply capacity the way it might look. Buying/sharing a ready-made key is explicitly discouraged because the seller "can revoke it, inspect usage, [or] share its quota with other buyers." Separately, Gemini CLI's OAuth login is barred from third-party proxies (violation ⇒ ban). Source: aggregator citing Google's own docs/behavior, accessed 2026-09-28 **[exact ToS clause text not independently pulled from ai.google.dev; behavior described is consistent with Google's usage-policies page]**.
- **Groq**: rate limits (free tier: 30 req/min, 6,000 tokens/min, 14,400 req/day) apply **at the organization level** — "multiple API keys don't help," and ToS prohibits creating multiple accounts to bypass limits (risk: suspension). Source: [Groq rate limits docs](https://console.groq.com/docs/rate-limits), accessed 2026-09-28.
- **OpenRouter**: free (`:free`-suffixed) models are capped 20 req/min and 50–1,000 req/day depending on lifetime credit purchased; the daily allowance is **shared across all free models on the account**, and "extra keys or accounts do not raise the platform limit." Free capacity is explicitly a shared subsidized pool that can 429 even for light users when a popular free model saturates. Source: [OpenRouter rate limits](https://openrouter.ai/docs/api_reference/limits), accessed 2026-09-28.
- **NVIDIA build.nvidia.com**: free-tier keys are for "prototyping, research and evaluation" only; serving real end users/production requires an NVIDIA AI Enterprise license, and general NVIDIA account terms bar sharing account access with third parties. Source: aggregator + [NVIDIA ToS](https://www.nvidia.com/en-us/about-nvidia/terms-of-service/), accessed 2026-09-28.
- **Mistral La Plateforme**: the free "Experiment" tier (~1B tokens/month cap) is explicitly "for evaluation, not production" and requires opting into data being used for model training; exact rate limits are account-specific and shown only in-console, not published. Source: aggregator summary, accessed 2026-09-28.

**Bottom line for Runesmith**: every free tier checked ties its quota to an individual account/project and is explicitly framed as a personal, non-production allowance; none permit pooling multiple users' free quota behind a shared router, and several (Groq, Google) have anti-multi-account language. This directly confirms and supports Lars's existing constraint that free tiers can never be pooled or resold — it is not just an ethical stance, it would risk mass account bans for users who opted into any pooled-free-tier feature.

---

## 5. Practicalities of charging users

**Merchant-of-record (MoR) options for usage-based billing/credits:**
- **Stripe**: not itself an MoR in the traditional sense for this use case, but has purpose-built usage-based billing: as of the 2025-03-31 API version, metered pricing requires a "Meter" object, and Stripe added a first-class **Credits** feature for prepaid-credit / burn-down billing (common pattern for AI apps). Stripe's own Metronome product targets sophisticated usage-based billing. Stripe does **not** act as merchant of record by default — you remain the seller of record and are responsible for your own tax compliance unless using Stripe Tax/Connect in specific configurations. Source: [Stripe: Introducing credits for usage-based billing](https://stripe.com/blog/introducing-credits-for-usage-based-billing), accessed 2026-09-28.
- **Paddle**: acts as **merchant of record** — handles global tax/VAT, compliance, fraud, chargebacks — for a flat **5% + $0.50/transaction**, no monthly fee on the standard plan; ships usage-based metering under "Paddle Billing." Effective global cost often nearer 7% once FX/complexity is included. Source: [Paddle 101](https://www.paddle.com/paddle-101), accessed 2026-09-28.
- **Lemon Squeezy**: also merchant of record, same headline **5% + $0.50/transaction**, no monthly fee; add-ons stack (international +1.5%, PayPal +1.5%, subscriptions +0.5%, affiliate referrals +3%), so a real blended rate can run 5.5–11%. Source: [Lemon Squeezy fees docs](https://docs.lemonsqueezy.com/help/getting-started/fees), accessed 2026-09-28.
- **Takeaway**: if Runesmith ever sells its own metered credits (option (b) in the brief), Paddle/Lemon Squeezy remove the sales-tax/VAT/compliance burden from a small open-source team at a ~5–8% all-in cost; Stripe is cheaper on raw processing but pushes tax/compliance liability back onto Runesmith unless paired with Stripe Tax.

**Disclosure law for affiliate links:**
- **US (FTC Endorsement Guides)**: any "material connection" (commission, credit, free product) between recommender and provider must be disclosed **clearly and conspicuously, at the point of recommendation, before the link** — a footer/sidebar/separate disclosure page is explicitly called insufficient. The FTC's 2023 update also puts compliance responsibility partly on the advertiser/operator, not just the individual affiliate. Penalties can run **up to ~$51,744 per violation**. Source: [FTC Endorsement Guides FAQ](https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking), accessed 2026-09-28.
- **UK**: ASA (Advertising Standards Authority) and CMA (Competition and Markets Authority) require commercial relationships — including affiliate/commission arrangements — to be made "upfront, prominent, and unambiguous" before the consumer engages; a bare link or discount code alone does not count as disclosure. Since the Digital Markets, Competition and Consumers Act 2024 (in force April 2025), the CMA can fine up to **10% of global annual turnover** directly, without going to court first. Source: [Pinsent Masons: ASA and CMA guidance](https://www.pinsentmasons.com/out-law/analysis/asa-and-cma-guidance-influencers-ads), accessed 2026-09-28.
- **EU**: baseline consumer protection comes from the Unfair Commercial Practices Directive, implemented differently per member state, with the Digital Services Act adding platform-level transparency obligations; there is no single EU-wide "FTC equivalent," enforcement is more fragmented than the UK's ASA/CMA model. Source: [Flinque: influencer marketing regulations in Europe](https://www.flinque.com/blog/influencer-marketing-regulations-in-europe-uk-eu-updates/), accessed 2026-09-28.
- **Practical implication for Runesmith**: any "get a key" link inside Studio that carries a commission needs an inline, unmissable disclosure right next to that specific recommendation (not just in a README or settings page) to satisfy both FTC and UK ASA/CMA standards — this maps directly onto Lars's existing "disclosed next to the recommendation" constraint, and confirms it's not just good ethics but the legal minimum in both major markets.

---

## Options for Runesmith

Ranked by (expected revenue, effort, trust risk, legal/terms risk) — all options are filtered to respect: evidence-first ranking, disclosure, free/local first-class, no pooling/reselling of free tiers.

### 1. Novita-style disclosed affiliate links for paid tiers only (highest ranked)
- **What**: Add "get a key" links for providers with real, confirmed commission programs (confirmed: Novita 10%/180 days, Cerebras individual referral bonus, Replicate affiliate, and possibly Groq's third-party-reported affiliate) — shown only next to paid-tier recommendations, never next to free/local options, with an inline disclosure tag ("Runesmith earns a commission if you sign up here") and the underlying ranking still driven by Runesmith's own benchmark results, not by which provider pays.
- **Revenue**: Low-medium initially (affiliate commissions are typically one-time or capped-duration; e.g. Novita's 10% only lasts 180 days per user) — scales only with actual paid conversions, which will be a minority of an open-source, free-first user base.
- **Effort**: Low — mostly UI copy + links + a disclosure component; no billing infrastructure, no ToS risk since these are official programs designed for exactly this kind of recommendation.
- **Trust risk**: Low, provided disclosure is inline and rankings are visibly commission-blind (e.g., publish the benchmark methodology).
- **Legal/terms risk**: Low — using official affiliate programs as intended; must re-verify each program's terms before shipping since several were only found via third-party aggregators (Groq, Together AI) and should be confirmed directly before relying on payout terms.

### 2. Zed/Kilo-style "at-cost or small fixed-markup" Runesmith-hosted credits, built on Milliner
- **What**: Let users optionally buy inference credits from Milliner (Lars's existing multi-provider gateway) inside Studio, priced at provider cost + a small transparent markup (Zed uses +10% precedent) or flat subscription tiers (Kilo Pass precedent: $19/$49/$199). Requires Milliner to hold its own commercial agreements with upstream providers (this is legally distinct from "reselling a consumer API key" — Milliner would need genuine partner/reseller terms with each upstream provider, per Section 2's finding that default ToS bar resale).
- **Revenue**: Medium-high and recurring — this is the model most comparable OSS coding tools that *do* monetize inference have converged on (Cline, Kilo, Zed, OpenCode, Warp).
- **Effort**: Medium-high — needs Stripe/Paddle/Lemon-Squeezy billing integration, a wallet/credits ledger, and (importantly) real reseller-tier agreements with at least the open-weight-model providers, since none of the majors' standard consumer ToS permit resale by default.
- **Trust risk**: Medium — must keep model rankings independent of which models Milliner happens to host cheaply; the Zed precedent (rankings unaffected, markup only on convenience-hosted path, BYOK always available at zero markup) is the safe pattern to copy.
- **Legal/terms risk**: Medium — must secure actual partner/reseller status (e.g., a Groq "Resold Customer" arrangement, or self-hosting only open-weight models where no upstream ToS applies) rather than reselling a personal API key, which every provider's ToS we found prohibits.

### 3. Startup/OSS-maintainer credit programs (non-monetizing, but funds development)
- **What**: Apply to existing programs meant for exactly this (Fireworks for Startups: up to $10k credits; OpenHands' OSS-maintainer credit grants ($100–500); Block's Goose Grant Program up to $100k; Mistral's startup credits) to fund Runesmith's own testing/CI/demo inference, not to resell to users.
- **Revenue**: None directly (saves cost rather than making money) but frees budget elsewhere.
- **Effort**: Low — just applications.
- **Trust risk**: None — invisible to users.
- **Legal/terms risk**: Low — these programs are designed for OSS projects.

### 4. Self-hosting open-weight models as a paid "Runesmith Cloud" tier
- **What**: Rent GPUs (RunPod/Modal/Fireworks on-demand) to serve open-weight models directly, sold at a markup, with no upstream-provider ToS conflict since Runesmith would be the model host, not a reseller of someone else's API.
- **Revenue**: Potentially the highest ceiling, but only past a break-even utilization threshold (RunPod's own guidance: ~10 active hours/day before dedicated beats serverless) — risky without proven steady demand.
- **Effort**: High — real MLOps burden (model serving, scaling, safety, uptime) that is a mismatch for a small open-source team, and directly competes with the "no manual keys/servers from Lars" simplicity goal.
- **Trust risk**: Medium — once Runesmith becomes a model host, results and hosting-provider recommendations sit under the same roof, so the evidence-first firewall must be enforced procedurally (e.g., published, reproducible benchmark suite) to avoid the appearance of self-dealing.
- **Legal/terms risk**: Low on the ToS-resale front (own hosting, not resale) but adds new obligations (data handling, uptime SLAs, possibly payment-processor/MoR compliance at higher volume).

### 5. OpenRouter app-attribution-only (lowest ranked, essentially free but no revenue)
- **What**: Send `HTTP-Referer`/`X-Title` headers so Runesmith appears in OpenRouter's public app rankings — pure visibility/marketing, not monetization, since OpenRouter's own docs show no revenue share for this.
- **Revenue**: None found.
- **Effort**: Trivial.
- **Trust/legal risk**: None.
- **Verdict**: Worth doing regardless (free marketing), but does not answer the "earn money" goal and shouldn't be counted as a monetization option.

---

## Notably unconfirmed items (flagged for follow-up before acting on them)
- OpenRouter's exact fee percentages (5.5%/5%/8%) were found only on third-party pricing-aggregator pages, not re-verified verbatim on an official openrouter.ai pricing page in this pass.
- Together AI's and Groq's "affiliate program" commission terms were found only on third-party affiliate-directory sites (openaffiliate.dev, devpicks.dev), not on together.ai or groq.com directly — confirm directly before relying on payout figures.
- Anthropic's exact commercial-ToS resale clause wording was read via a secondary summary, not the primary legal document text.
- Google Gemini API's own terms were not found to contain an explicit resale/sublicense clause in this pass (Google Cloud's general reseller program is separate); needs a direct read of ai.google.dev's Additional Terms of Service if this matters for a decision.
- Hugging Face's "may add revenue-sharing in future" is explicitly speculative, not a live program.
