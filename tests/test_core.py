import json
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pytest
from ata_local import store
from ata_local.audio import prepare, Recorder
from ata_local.pipeline import assign_speaker, windows, restore_punctuation
from ata_local.summarize import Notes, validate_notes, render


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    store.init()
    return tmp_path


def test_atomic_queue_claim_prevents_duplicate_gpu_work(database):
    job = store.create("Reunião", {})
    store.update(job["id"], status="queued")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.claim(), range(8)))
    assert sum(result is not None for result in results) == 1
    assert store.get(job["id"])["status"] == "processing"


def test_crash_recovery_preserves_recording_and_requeues_work(database):
    capturing = store.create("Em captura", {})
    processing = store.create("Em processamento", {})
    store.update(processing["id"], status="processing")
    store.recover()
    assert store.get(capturing["id"])["status"] == "interrupted"
    assert store.get(processing["id"])["status"] == "queued"
    assert store.folder(capturing["id"]).exists()


def test_reconstruct_two_audio_sources_and_partial_index(tmp_path):
    import soundfile as sf
    manifest = {"sources": [{"name": name, "channels": 1, "rate": rate}
                            for name, rate in [("system", 48000), ("microphone", 16000)]]}
    (tmp_path / "capture.json").write_text(json.dumps(manifest))
    for name, rate, t in [("system", 48000, 0), ("microphone", 16000, 0.5)]:
        samples = np.full(rate, 10000, dtype=np.int16)
        (tmp_path / f"{name}.pcm").write_bytes(samples.tobytes())
        (tmp_path / f"{name}.jsonl").write_text(json.dumps([t, 0, rate]) + '\n[1.5,')
    duration = prepare(tmp_path)
    audio, rate = sf.read(tmp_path / "audio.wav")
    assert duration == 1.5 and rate == 16000
    assert abs(float(audio[12000]) - 10000 / 32768) < 0.01
    assert abs(float(audio[4000]) - 5000 / 32768) < 0.01


def test_pause_does_not_write_and_resume_does_not_include_gap(tmp_path):
    import time
    from types import SimpleNamespace
    recorder = Recorder()
    recorder.mid = "a" * 32
    recorder.elapsed = 0
    recorder.epoch = 0
    recorder.epoch_start = time.monotonic()
    fake_pa = SimpleNamespace(paContinue=0, paAbort=1)
    with open(tmp_path / "raw", "wb") as raw, open(tmp_path / "index", "w") as index:
        callback = recorder._callback("system", raw, index, 1, 16000, fake_pa)
        payload = np.zeros(1600, dtype=np.int16).tobytes()
        assert callback(payload, 1600, {}, 0)[1] == 0
        recorder.pause()
        offset = raw.tell()
        callback(payload, 1600, {}, 0)
        assert raw.tell() == offset
        recorder.resume()
        callback(payload, 1600, {}, 0)
        assert raw.tell() == offset * 2
        assert callback(payload, 1600, {}, 2)[1] == 1
        assert "overflow" in recorder.error


def test_speaker_assignment_is_overlap_based_not_nearest_guess():
    turns = [{"start": 1, "end": 3, "speaker": "Pessoa 1"}, {"start": 3, "end": 5, "speaker": "Pessoa 2"}]
    assert assign_speaker(2.9, 3.6, turns) == "Pessoa 2"
    assert assign_speaker(8, 9, turns) == "Pessoa não determinada"


def test_windows_cover_long_speech_without_duplicated_audio():
    turns = [{"start": 0, "end": 100}, {"start": 103, "end": 107}]
    chunks = windows(turns)
    assert all(0 < end - start <= 40.001 for start, end in chunks)
    assert all(chunks[i][1] <= chunks[i + 1][0] for i in range(len(chunks) - 1))
    assert chunks[0][0] == 0 and chunks[-1][1] >= 107


def sample_notes():
    return Notes.model_validate({"overview": [{"text": "Escopo discutido", "refs": ["U00001"]}],
      "affiliations": [{"speaker": "Pessoa 1", "side": "cliente", "company": "Acme", "confidence": "baixa",
                        "evidence": "Ambíguo", "refs": ["U00001"]}],
      "decisions": [], "actions": [], "questions": [], "risks": []})


def test_low_confidence_role_is_not_presented_as_fact():
    result = validate_notes(sample_notes(), {"U00001"}, {"Pessoa 1"})
    assert result.affiliations[0].side == "indeterminado"


def test_invented_evidence_is_rejected():
    with pytest.raises(ValueError, match="inexistente"):
        validate_notes(sample_notes(), {"U00002"}, {"Pessoa 1"})


def test_markdown_keeps_unassigned_speakers_and_evidence():
    transcript = [{"id": "U00001", "speaker": "Pessoa 1", "start": 12},
                  {"id": "U00002", "speaker": "Pessoa 2", "start": 20}]
    text = render(sample_notes(), {"title": "Escopo", "duration": 100, "meta": {}}, transcript)
    assert "Pessoa 2 | indeterminado" in text
    assert "U00001 · 00:00:12" in text


def test_folder_traversal_is_rejected():
    with pytest.raises(ValueError):
        store.folder("../config.json")


def test_aligner_does_not_remove_asr_punctuation():
    words = [{"text": x, "start": i, "end": i + 1} for i, x in enumerate(["Bom", "dia", "sexta", "feira"])]
    restored = restore_punctuation("Bom dia. Sexta-feira!", words)
    assert [w["text"] for w in restored] == ["Bom", "dia.", "Sexta-", "feira!"]


def test_invalid_alignment_is_not_silently_accepted():
    with pytest.raises(ValueError, match="divergiram"):
        restore_punctuation("Bom dia.", [{"text": "inexistente"}])


def test_tiny_vad_gap_between_same_speaker_is_bridged():
    turns = [{"start": 0, "end": 1, "speaker": "Pessoa 1"},
             {"start": 1.2, "end": 2, "speaker": "Pessoa 1"}]
    assert assign_speaker(1.04, 1.1, turns) == "Pessoa 1"
    turns[1]["speaker"] = "Pessoa 2"
    assert assign_speaker(1.04, 1.1, turns) == "Pessoa não determinada"
