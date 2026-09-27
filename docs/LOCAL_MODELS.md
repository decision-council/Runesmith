# Running Runesmith on a small local model

Runesmith is built for people who cannot rent frontier models. This page shows how to run it on your own machine with a small open model, and what to expect.

## 1. Serve a model locally

Any server that speaks the OpenAI chat API works. With [Ollama](https://ollama.com):

```bash
ollama pull qwen2.5-coder:7b
```

```bash
ollama serve
```

LM Studio, llama.cpp's `llama-server` and vLLM expose the same `/v1/chat/completions` endpoint.

## 2. Point Runesmith at it

```bash
python -m runesmith --home .runesmith init
```

Then edit `.runesmith/runesmith.json`:

```json
{"instruments": {"local": {"kind": "openai", "base_url": "http://127.0.0.1:11434/v1",
                           "model": "qwen2.5-coder:7b", "json_mode": "json_object"}},
 "roles": {"repair": ["local"], "kaizen": ["local"]}}
```

- `json_mode` asks the server for a JSON object; if your server does not support it, set it to `"none"`.
- `tolerant_json` (default `true`) lets Runesmith pull the JSON object out of an answer that wraps it in prose, which small models often do. The organ still validates every field, so a bad answer costs one call and nothing else.
- Keys are never stored in the config. For hosted free tiers, name an environment variable with `api_key_env`.

Check that Runesmith can reach the model (it contacts `/models` only):

```bash
python -m runesmith --home .runesmith doctor
```

## 3. Use it

```bash
python -m runesmith --home .runesmith discover path/to/your/repo
```

```bash
python -m runesmith --home .runesmith repair --opportunity 0
```

```bash
python -m runesmith --home .runesmith run
```

## What to expect (measured, not promised)

- On 2026-09-24, a **2.6B-parameter** free model (`liquid/lfm-2.5-2.6b`) strictly repaired **6 of 16** real single-line regressions in HatOS repositories:
  - 4 of 8 through the shipped repair organ g0;
  - 2 of 8 through a Kaizen-authored candidate.
  This was an exploratory probe on opened development tasks, not a preregistered result.
- Whether the suit helps, compared with the same model's best plain scaffold at equal budget, was tested in a preregistered study (SR6-W, sealed 2026-09-25): **not shown**. A 2.6B free model repaired 5 of 68 fresh tasks in the suit and 12 of 68 in the scaffold, so the direction favoured the scaffold. C7 was not tested with a small model.
- Small models fail more often on large repositories. Runesmith's Kaizen loop is designed to find where your model struggles and improve the organs around it. It never raises the envelope: the gains must come from better use of the same calls.

## The envelope

Every opportunity has kernel-enforced ceilings: calls, tokens per call, test runs, request size and wall-clock time. You can lower them in `"envelope"` in the config to fit a slow machine. Runesmith will then do less per opportunity, but it never exceeds them.
