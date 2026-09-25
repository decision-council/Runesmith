"""The manual instrument: a person relays requests to a chat model and hands the reply back."""

from __future__ import annotations

import codecs
import json
import threading
import time
from pathlib import Path

import pytest

from runesmith import cli, manual
from runesmith.config import build_router
from runesmith.instruments import Router, TransportCensored
from runesmith.kaizen.improve import AUTHOR_SCHEMA
from runesmith.ledger import Ledger
from runesmith.manual import ManualInstrument

SCHEMA = {"type": "object", "properties": {"mechanism": {"type": "string"}, "module_source": {"type": "string"}},
          "required": ["mechanism", "module_source"], "additionalProperties": False}


def fake_time():
    now = [0.0]
    return (lambda: now[0]), (lambda seconds: now.__setitem__(0, now[0] + seconds))


def chat_reply(data: dict, blocks: dict[str, str]) -> str:
    """What a chat model's copy button gives: prose, a json block, named blocks, CRLF line endings."""
    text = "Here is my answer.\n\n```json\n" + json.dumps(data, indent=2) + "\n```\n"
    for name, body in blocks.items():
        text += f"\n````python @block:{name}\n{body}````\n"
    return text.replace("\n", "\r\n")


def test_a_relayed_chat_reply_becomes_the_answer(tmp_path):
    directory = tmp_path / "manual"
    told = []
    instrument = ManualInstrument("chat", "a chat model", directory=directory, poll_s=0.01,
                                  notify=lambda rid, path: told.append(rid))
    result = {}
    worker = threading.Thread(target=lambda: result.update(outcome=instrument.complete(
        prompt="Improve the organ.", system="You improve code.", schema=SCHEMA, max_tokens=100, key="kaizen-x-1-a0")))
    worker.start()
    deadline = time.time() + 20
    while not manual.pending_requests(directory) and time.time() < deadline:
        time.sleep(0.01)
    [row] = manual.pending_requests(directory)
    pasted = Path(row["prompt"]).read_text(encoding="utf-8")
    assert pasted.startswith("You improve code.") and "Improve the organ." in pasted
    assert '"module_source"' in pasted and "@block:NAME" in pasted
    source = 'def run(view, cockpit):\n    return {"fence": "```"}\n'
    saved = manual.submit_answer(directory, row["id"],
                                 chat_reply({"mechanism": "read more", "module_source": "@block:organ"},
                                            {"organ": source}), model="some-chat-model")
    assert saved["problems"] == [] and saved["written"]
    worker.join(20)
    outcome = result["outcome"]
    assert outcome.ok and outcome.data == {"mechanism": "read more", "module_source": source}   # exact, LF
    assert outcome.receipt["answered_by"] == "some-chat-model" and outcome.receipt["provider"] == "manual"
    assert told == [row["id"]]
    assert manual.pending_requests(directory) == []
    done = json.loads((directory / "done" / row["id"] / "outcome.json").read_text(encoding="utf-8"))
    assert done["ok"] and done["answered_by"] == "some-chat-model"


def test_no_answer_is_transport_and_retries_wait_on_the_same_request(tmp_path):
    clock, sleep = fake_time()
    told = []
    instrument = ManualInstrument("chat", directory=tmp_path, timeout_s=5, poll_s=1, clock=clock, sleep=sleep,
                                  notify=lambda rid, path: told.append(rid))
    router = Router({"chat": instrument}, {"kaizen": "chat"}, backoff_s=(0, 0), sleep=lambda s: None)
    with pytest.raises(TransportCensored):
        router.call("kaizen", prompt="p", system="s", schema=SCHEMA, max_tokens=10, key="k")
    assert len(manual.pending_requests(tmp_path)) == 1                 # three attempts, one request
    assert len(told) == 3 and len(set(told)) == 1                      # a reminder per attempt
    rid = told[0]
    manual.submit_answer(tmp_path, rid, '{"mechanism": "m", "module_source": "x = 1\\n"}')
    outcome = router.call("kaizen", prompt="p", system="s", schema=SCHEMA, max_tokens=10, key="k")
    assert outcome.ok and outcome.data["module_source"] == "x = 1\n"   # answered ahead: read at once
    other = manual.request_id("another-call", "s", "p", SCHEMA)
    assert other != rid                                                # distinct calls never share a request


def test_the_parser_accepts_how_chat_models_write_and_refuses_what_is_broken():
    parse = manual.parse_chat_answer
    assert parse('{"a": "line one\nline two"}') == {"a": "line one\nline two"}   # raw newline inside a string
    assert parse('I think {this} is fine.\n```json\n{"a": 1}\n```\nHope it helps!') == {"a": 1}
    assert parse('{"edits": [{"new_text": "@block:e1"}]}\n````text @block:e1\nabc\n````') == \
        {"edits": [{"new_text": "abc\n"}]}
    with pytest.raises(ValueError, match="does not contain it"):
        parse('{"a": "@block:missing"}')
    with pytest.raises(ValueError, match="never closed"):
        parse('{"a": "@block:b"}\n````python @block:b\nprint(1)\n')
    with pytest.raises(ValueError, match="no JSON object"):
        parse("Sorry, I cannot help with that.")
    assert manual.decode_reply(codecs.BOM_UTF8 + b'{"a": "x"}\r\n') == '{"a": "x"}\n'
    assert manual.decode_reply('{"a": "é"}\r\n'.encode("utf-16")) == '{"a": "é"}\n'


def test_submitting_checks_the_reply_and_says_what_to_fix(tmp_path):
    problems = manual.schema_problems({"a": 1, "z": 2}, {"type": "object", "properties": {"a": {"type": "string"}},
                                                         "required": ["a", "b"], "additionalProperties": False})
    assert problems == ["answer: missing required field 'b'", "answer: unexpected field 'z'",
                        "answer.a: expected string, got int"]
    clock, sleep = fake_time()
    ManualInstrument("chat", directory=tmp_path, timeout_s=1, poll_s=1, clock=clock, sleep=sleep,
                     notify=lambda rid, path: None).complete(prompt="p", system="s", schema=AUTHOR_SCHEMA,
                                                             max_tokens=10, key="author-1")
    rid = manual.resolve_request(tmp_path, "author")                   # a unique prefix is enough
    incomplete = '```json\n{"hypotheses": ["h"], "mechanism": "m", "prediction": "p", "falsifier": "f"}\n```'
    refused = manual.submit_answer(tmp_path, rid, incomplete)
    assert refused["written"] is None
    assert refused["problems"] == ["answer: missing required field 'edits'",
                                   "answer: missing required field 'module_source'"]
    assert manual.submit_answer(tmp_path, rid, incomplete, force=True)["written"]


def test_the_cli_lists_shows_and_takes_answers(tmp_path, capsys, monkeypatch):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    clock, sleep = fake_time()
    ManualInstrument("chat", directory=home / "manual", timeout_s=1, poll_s=1, clock=clock, sleep=sleep,
                     notify=lambda rid, path: None).complete(prompt="Fix the organ, please.", system="s",
                                                             schema=SCHEMA, max_tokens=10, key="kaizen-9")
    capsys.readouterr()
    cli.main(["--home", str(home), "manual", "list"])
    listed = capsys.readouterr().out
    assert "kaizen-9-" in listed and "waiting for an answer" in listed
    cli.main(["--home", str(home), "manual", "show"])                  # the only waiting request
    assert "Fix the organ, please." in capsys.readouterr().out
    bad = tmp_path / "reply.txt"
    bad.write_bytes(b"I would rather not.")
    with pytest.raises(SystemExit, match="not saved"):
        cli.main(["--home", str(home), "manual", "answer", "--file", str(bad)])
    monkeypatch.setattr(manual, "read_clipboard", lambda: '{"mechanism": "m", "module_source": "x = 2\\n"}')
    cli.main(["--home", str(home), "manual", "answer", "kaizen-9", "--clipboard", "--model", "free-chat"])
    assert "answer saved" in capsys.readouterr().out
    [row] = manual.pending_requests(home / "manual")
    assert row["answered"]


def test_config_and_doctor_know_the_manual_kind(tmp_path):
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    config = json.loads((home / "runesmith.json").read_text(encoding="utf-8"))
    config["instruments"]["chat"] = {"kind": "manual", "model": "a chat model"}
    config["roles"]["kaizen"] = ["chat"]
    (home / "runesmith.json").write_text(json.dumps(config), encoding="utf-8")
    router = build_router(config, home=home)
    assert router.instruments["chat"].directory == home.resolve() / "manual"
    from runesmith.doctor import diagnose_home
    rows = {row["check"]: row for row in diagnose_home(home, network=False)}
    assert rows["instrument chat (kaizen)"]["ok"] is True
    assert "a person relays requests" in rows["instrument chat (kaizen)"]["detail"]


def test_a_chat_author_relayed_by_hand_improves_runesmith_end_to_end(tmp_path):
    """The Kaizen demo with the author replaced by a person relaying to a chat model (here: SR5's answer)."""
    from runesmith import generations
    from runesmith.demo_kaizen import load_b_answer, run_kaizen_demo
    home = tmp_path / "home"
    cli.main(["--home", str(home), "init"])
    g0 = generations.active(home)
    b = load_b_answer()
    data = {k: b[k] for k in ("hypotheses", "mechanism", "prediction", "falsifier")}
    data.update(edits=[], module_source="@block:organ")
    relayed = []

    def person(rid: str, prompt_path: Path) -> None:                    # paste, wait for the chat, copy back
        relayed.append(prompt_path.read_text(encoding="utf-8"))
        manual.submit_answer(home / "manual", rid, chat_reply(data, {"organ": b["module_source"]}),
                             model="chat-model-x")

    author = ManualInstrument("chat", "a chat model", directory=home / "manual", poll_s=0.01, notify=person)
    lines: list[str] = []
    result = run_kaizen_demo(home, out=lines.append, author=author)
    assert len(relayed) == 1 and "ORGAN CONTRACT" in relayed[0]
    assert result["kaizen"]["decision"] == "frozen_candidate"
    assert result["trial"]["decision"] == "activate" and result["active"] == result["candidate"] != g0
    organ = (home / "generations" / result["candidate"] / "organs" / "repair.py").read_bytes()
    assert organ == b["module_source"].encode("utf-8")                  # byte-exact through CRLF and blocks
    assert any("answered by chat-model-x" in line for line in lines)
    assert Ledger(home / "ledger.jsonl").verify()["ok"]
