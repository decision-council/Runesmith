# U1-UPLIFT Amendment 2 (before any model session)

Designer: Claude Opus 5.5 (integration operator). Written before any U1 evaluation session; no outcome of U1 exists.

**Route.** The protocol's paid fallback (OpenRouter) holds about US$0.11 and cannot be topped up before the release. The run
uses **Vercel's hosted `gpt-oss-20b`** (the same open-weights model) for every call of every arm; OpenRouter's `gpt-oss-20b`
remains the fallback only if Vercel refuses a call, and the route of every call is recorded. The spend cap stays US$2 (the
Vercel balance is about US$0.39). If the balance runs out, the protocol's censoring rule applies: censored sessions are
re-queued once at the end and otherwise reported as censored, never scored; no session is started that the balance cannot cover.
Reported as a deviation, with this amendment's digest, wherever U1 is reported.
