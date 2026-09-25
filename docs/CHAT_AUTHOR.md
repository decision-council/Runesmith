# A chat model as Runesmith's author (no API key needed)

Runesmith improves itself by asking an **author** model to rewrite the organ behind its weakest capability (see [How it improves itself](../README.md#how-it-improves-itself)). A campaign needs only a few author calls, at most 8 by default. The generation it produces then runs on whatever model does the everyday work, including small free ones.

So the author is where a strong model matters most, and it is also where one is easiest to borrow. If you can reach a strong model only through a chat window, such as a free tier of ChatGPT, Claude or Gemini, you can relay the author's requests by hand. Runesmith calls this the **manual instrument**.

## Set it up

Add a `manual` instrument to `runesmith.json` and give it the `kaizen` role. Keep your everyday model on `repair`:

```json
{"instruments": {"local": {"kind": "openai", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5-coder:7b"},
                 "chat":  {"kind": "manual", "model": "the chat model you relay to"}},
 "roles": {"repair": ["local"], "kaizen": ["chat"]}}
```

Options:
- `timeout_s`: how long each attempt waits for your answer. The default is 3600. The router retries, so a request can wait several hours in all.
- `poll_s`: how often it checks for your answer. The default is 2.
- `dir`: where requests are written. The default is `<home>/manual`.

## Relay a request

When Runesmith needs the author, it writes the request to `<home>/manual/<id>.prompt.md` and prints what to do. It then waits.

1. **Give the request to a chat model.** Open the `.prompt.md` file, copy all of it and paste it into the chat. A Kaizen author request is about 60 KB, roughly 15,000 tokens. If the chat window refuses a paste that long, attach the file instead.
2. **Copy the model's whole reply.** The chat's own copy button works best, because it keeps code blocks intact.
3. **Hand it back:**

   ```bash
   python -m runesmith --home .runesmith manual answer --clipboard --model "the model's name"
   ```

   Use `--file reply.txt` instead of `--clipboard` if you saved the reply to a file. Runesmith first checks the reply against the requested format. If something is missing, it says what, and nothing is saved, so you can ask the model to fix its answer and try again. `--force` hands the reply over as it is, and it then counts as the model's answer.
4. **The run continues.** It picks up the answer within seconds.

`manual list` shows the requests that are waiting, and `manual show [ID]` prints one. An ID can be shortened to any unique prefix. When only one request is waiting, the ID can be left out.

## How the model may reply

The request ends with a short **HOW TO REPLY** section for the model:
- The answer is one JSON object in a ```` ```json ```` block, and prose around it is fine.
- Whole source files do not have to be escaped inside JSON. The model can write a value as `"@block:NAME"` and put the text in a separate fenced block that opens with four backticks followed by `@block:NAME`. Runesmith puts it back byte for byte, with LF line endings.
- Raw line breaks inside JSON strings are accepted.
- Windows line endings and files saved as UTF-16 are handled.

## What is recorded

Everything is recorded, the same as for any other instrument:
- The request, the reply and an `outcome.json` are archived under `<home>/manual/done/<id>/`.
- The call's receipt names the instrument and `answered_by`, the model you named with `--model`.
- The Kaizen attempt record and the generation's provenance name the author.

A request you never answer is a *transport* failure. The work is censored and never counted against the model.

The model's identity rests on your word. Runesmith's preregistered studies used API instruments, so that the router logged every call. A relayed author is for using Runesmith, and its lineage says so.

## Try it on the demo

```bash
python -m runesmith --home .demo-kaizen demo --kaizen --manual-author
```

The Kaizen demo normally replays the change that gpt-oss-120b wrote in the SR5 study. With `--manual-author`, it writes the author request for you to relay instead. Your chat model's change then goes through the same qualification, freeze and online trial. The demo's repair model is a scripted stand-in, so this exercises the machinery on eight small slips. Whether a change helps on real work is what a trial on your own work decides.
