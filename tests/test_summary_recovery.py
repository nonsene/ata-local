import json
from unittest.mock import Mock

import pytest
from ata_local import summarize as summary


def notes(ref="U00001"):
    return summary.Notes(overview=[summary.Fact(text="Escopo discutido", refs=[ref])],
                         affiliations=[], decisions=[], actions=[], questions=[], risks=[])


class Client:
    def __init__(self, reasons):
        self.reasons = iter(reasons)
        self.budgets = []

    def post(self, path, json):
        if path == "/apply-template":
            payload = {"prompt": "rendered template"}
        elif path == "/tokenize":
            payload = {"tokens": [1] * 1000}
        else:
            self.budgets.append(json["max_tokens"])
            reason = next(self.reasons)
            payload = {"choices": [{"finish_reason": reason, "message": {
                "content": notes().model_dump_json() if reason == "stop" else '{"overview":['}}]}
        response = Mock()
        response.json.return_value = payload
        return response


def test_truncation_retries_with_larger_context_safe_budget(monkeypatch):
    monkeypatch.setattr(summary, "config", lambda: {"context_size": 9000})
    client = Client(["length", "stop"])
    result = summary.generate(client, "input", {}, {"U00001"}, set(), "extract")
    assert result == notes()
    assert client.budgets == [6000, 7744]


def test_persistent_truncation_is_never_accepted():
    with pytest.raises(summary.SummaryCapacityError):
        summary.generate(Client(["length", "length"]), "input", {}, {"U00001"}, set(), "extract")


def test_no_generation_when_context_is_full(monkeypatch):
    monkeypatch.setattr(summary, "config", lambda: {"context_size": 2000})
    client = Client([])
    with pytest.raises(summary.SummaryCapacityError):
        summary.generate(client, "input", {}, set(), set(), "extract")
    assert client.budgets == []


def test_split_preserves_every_entry_and_can_resume(tmp_path, monkeypatch):
    calls = []
    def generate(client, data, meta, refs, speakers, task):
        items = [json.loads(line) for line in data.splitlines()]
        calls.append(items)
        if len(items) > 1:
            raise summary.SummaryCapacityError()
        assert refs == {items[0]["id"]}
        return notes(items[0]["id"])
    monkeypatch.setattr(summary, "generate", generate)
    entries = [json.dumps({"id": ref}) for ref in ["U00001", "U00002"]]
    args = (None, entries, {}, {"U00001", "U00002"}, set(), "extract", tmp_path, lambda: None)
    result = summary.cached_generate(*args)
    assert {item.refs[0] for item in result.overview} == {"U00001", "U00002"}
    assert len(calls) == 3
    assert summary.cached_generate(*args) == result
    assert len(calls) == 3
    summary.cached_generate(None, entries[:1], {"client": "changed"}, {"U00001"}, set(),
                            "extract", tmp_path, lambda: None)
    assert len(calls) == 4


def test_failed_single_entry_does_not_save_invalid_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, "generate", Mock(side_effect=summary.SummaryCapacityError()))
    with pytest.raises(summary.SummaryCapacityError):
        summary.cached_generate(None, ['{"id":"U00001"}'], {}, {"U00001"}, set(), "extract",
                                tmp_path, lambda: None)
    assert list(tmp_path.iterdir()) == []


def test_merge_preserves_actions_deadlines_and_divergences():
    a, b = notes(), notes("U00002")
    a.actions = [summary.Action(text="Enviar proposta", owner="Pessoa 1", deadline="sexta-feira", refs=["U00001"])]
    b.risks = [summary.Fact(text="Prazo contestado", refs=["U00002"])]
    merged = summary.merge_notes([a, b, a], {"U00001", "U00002"}, set())
    assert merged.actions == a.actions
    assert merged.risks == b.risks
    assert len(merged.overview) == 2


def test_cache_cannot_reference_an_unprovided_utterance(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, "generate", lambda *args: notes("U00002"))
    with pytest.raises(ValueError):
        summary.cached_generate(None, ['{"id":"U00001"}'], {}, {"U00001", "U00002"}, set(),
                                "extract", tmp_path, lambda: None)
    assert list(tmp_path.iterdir()) == []


def test_resume_after_second_child_fails_keeps_first_child(tmp_path, monkeypatch):
    fail = True
    counts = {"U00001": 0, "U00002": 0}
    def generate(client, data, *args):
        items = [json.loads(line) for line in data.splitlines()]
        if len(items) > 1:
            raise summary.SummaryCapacityError()
        ref = items[0]["id"]
        counts[ref] += 1
        if ref == "U00002" and fail:
            raise RuntimeError("interruption")
        return notes(ref)
    monkeypatch.setattr(summary, "generate", generate)
    entries = [json.dumps({"id": ref}) for ref in counts]
    args = (None, entries, {}, set(counts), set(), "extract", tmp_path, lambda: None)
    with pytest.raises(RuntimeError, match="interruption"):
        summary.cached_generate(*args)
    fail = False
    assert len(summary.cached_generate(*args).overview) == 2
    assert counts == {"U00001": 1, "U00002": 2}


def test_nonshrinking_consolidation_finishes_with_all_extracted_records(tmp_path, monkeypatch):
    from contextlib import nullcontext
    transcript = [{"id": "U00001", "speaker": "Pessoa 1", "start": 0},
                  {"id": "U00002", "speaker": "Pessoa 2", "start": 10}]
    source = json.dumps(transcript).encode()
    (tmp_path / "transcript.json").write_bytes(source)
    monkeypatch.setattr(summary.store, "get", lambda _: {"title": "Test", "meta": {}, "duration": 20})
    monkeypatch.setattr(summary, "report", Mock())
    monkeypatch.setattr(summary, "local_model", lambda _: nullcontext(None))
    monkeypatch.setattr(summary, "pack", lambda client, entries, **kw: entries)
    monkeypatch.setattr(summary, "generate", lambda client, data, *args: notes(json.loads(data)["id"]))
    summary.summarize("test", tmp_path)
    final = summary.Notes.model_validate_json((tmp_path / "summary.json").read_text())
    assert len(final.overview) == 2
    assert (tmp_path / "transcript.json").read_bytes() == source
    assert "podem existir repetições" in (tmp_path / "ata.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "summary-recovery.json").read_text())["retained_parts_without_further_reduction"]
