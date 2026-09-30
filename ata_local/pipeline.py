"""One GPU phase per subprocess, with disk checkpoints and measured progress."""
import json
import sys
import unicodedata
from . import store
from .config import config, model_path, offline


def report(mid, stage, fraction, detail=""):
    store.update(mid, stage=stage, progress=max(0, min(100, fraction * 100)), detail=detail)


def assign_speaker(start, end, turns):
    if end <= start:
        end = start + 0.01
    scores = {}
    for turn in turns:
        overlap = max(0, min(end, turn["end"]) - max(start, turn["start"]))
        if overlap:
            speaker = turn["speaker"]
            scores[speaker] = scores.get(speaker, 0) + overlap
    if not scores:
        previous = [turn for turn in turns if turn["end"] <= start]
        following = [turn for turn in turns if turn["start"] >= end]
        if previous and following:
            left = max(previous, key=lambda turn: turn["end"])
            right = min(following, key=lambda turn: turn["start"])
            if left["speaker"] == right["speaker"] and right["start"] - left["end"] <= 0.35:
                return left["speaker"]
        return "Pessoa não determinada"
    return max(scores, key=scores.get)


def windows(turns, limit=40):
    """Keep pauses as boundaries where possible, and cover every detected speech span."""
    result = []
    for turn in turns:
        start, end = max(0, turn["start"] - 0.15), turn["end"] + 0.15
        if result and start <= result[-1][1] + 1 and end - result[-1][0] <= limit:
            result[-1][1] = max(result[-1][1], end)
            continue
        if result:
            start = max(start, result[-1][1])
        while end > start:
            stop = min(end, start + limit)
            result.append([start, stop])
            start = stop
    return result


def restore_punctuation(text, words):
    """Map normalized aligner words back to the recognizer's original punctuation."""
    def normalized(value):
        return "".join(c for c in unicodedata.normalize("NFKD", value.lower()) if c.isalnum())
    letters, offsets = [], []
    for index, char in enumerate(text):
        for letter in normalized(char):
            letters.append(letter)
            offsets.append(index)
    plain = "".join(letters)
    cursor, starts = 0, []
    for word in words:
        key = normalized(word["text"])
        found = plain.find(key, cursor) if key else -1
        if found < 0:
            # Never silently pretend an uncertain alignment is precise.
            raise ValueError("Texto e alinhamento divergiram; o trecho precisa ser reprocessado")
        starts.append(offsets[found])
        cursor = found + len(key)
    for index, word in enumerate(words):
        start = starts[index] if index else 0
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        word["text"] = text[start:end].strip()
    return words


def diarize(mid, directory):
    import torch
    import soundfile as sf
    from pyannote.audio import Pipeline
    report(mid, "Separando falantes", 0, "Carregando Community-1")
    pipeline = Pipeline.from_pretrained(str(model_path("diarization_model")))
    pipeline.to(torch.device("cuda"))
    wave, rate = sf.read(directory / "audio.wav", dtype="float32", always_2d=True)
    last = [0.0]

    def hook(step, artifact, file=None, total=None, completed=None):
        import time
        if time.monotonic() - last[0] < 0.4:
            return
        last[0] = time.monotonic()
        fraction = completed / total if total and completed is not None else 0
        report(mid, "Separando falantes", fraction, f"{step}: {completed or 0}/{total or '?'}")

    meta = store.get(mid)["meta"]
    kwargs = {"num_speakers": meta["speakers"]} if meta.get("speakers") else {}
    result = pipeline({"waveform": torch.from_numpy(wave.T.copy()), "sample_rate": rate}, hook=hook, **kwargs)
    names = {}
    exclusive = []
    for segment, label in result.exclusive_speaker_diarization:
        if label not in names:
            names[label] = f"Pessoa {len(names) + 1}"
        exclusive.append({"start": segment.start, "end": segment.end, "speaker": names[label]})
    regular = []
    for segment, label in result.speaker_diarization:
        if label not in names:
            names[label] = f"Pessoa {len(names) + 1}"
        regular.append({"start": segment.start, "end": segment.end, "speaker": names[label]})
    store.atomic_json(directory / "speakers.json", {"exclusive": exclusive, "regular": regular})
    report(mid, "Separando falantes", 1, f"{len(names)} falantes detectados")


def transcribe(mid, directory):
    import torch
    import soundfile as sf
    from qwen_asr import Qwen3ASRModel
    report(mid, "Transcrevendo", 0, "Carregando Qwen3-ASR e alinhador")
    model = Qwen3ASRModel.from_pretrained(
        str(model_path("asr_model")), dtype=torch.bfloat16, device_map="cuda:0",
        local_files_only=True, max_inference_batch_size=1, max_new_tokens=2048,
        forced_aligner=str(model_path("aligner_model")),
        forced_aligner_kwargs={"dtype": torch.bfloat16, "device_map": "cuda:0", "local_files_only": True})
    turns = json.loads((directory / "speakers.json").read_text(encoding="utf-8"))
    chunks = windows(turns["exclusive"], config()["asr_window_seconds"])
    if not chunks:
        raise ValueError("Nenhuma fala detectada. Confira os dispositivos e o áudio gravado.")
    cache = directory / "asr-chunks"
    cache.mkdir(exist_ok=True)
    utterances = []
    metadata = store.get(mid)["meta"]
    vocabulary = "Termos de referência para esta reunião: " + "; ".join(
        str(metadata.get(key, "")) for key in ("client", "supplier") if metadata.get(key))
    for index, (start, end) in enumerate(chunks):
        checkpoint = cache / f"{index:05d}.json"
        if checkpoint.exists():
            words = json.loads(checkpoint.read_text(encoding="utf-8"))
        else:
            # Context on both sides avoids cutting phonemes at the 40-second boundary.
            read_start = max(0, start - 0.75)
            read_end = end + 0.75
            with sf.SoundFile(directory / "audio.wav") as audio:
                audio.seek(min(len(audio), int(read_start * 16000)))
                sample = audio.read(int((read_end - read_start) * 16000), dtype="float32")
            output = model.transcribe(audio=(sample, 16000), language="Portuguese", context=vocabulary,
                                      return_time_stamps=True)[0]
            words = [{"start": float(w.start_time) + read_start, "end": float(w.end_time) + read_start, "text": w.text}
                     for w in (output.time_stamps or [])]
            if output.text.strip() and not words:
                raise ValueError("O alinhador não retornou tempos para o trecho; reprocessamento necessário")
            words = restore_punctuation(output.text, words)
            words = [word for word in words if start <= (word["start"] + word["end"]) / 2 < end]
            (cache / f"{index:05d}.txt").write_text(output.text, encoding="utf-8")
            store.atomic_json(checkpoint, words)
        for word in words:
            speaker = assign_speaker(word["start"], word["end"], turns["exclusive"])
            overlapping = {t["speaker"] for t in turns["regular"]
                           if min(t["end"], word["end"]) > max(t["start"], word["start"])}
            uncertain = len(overlapping) > 1
            if (utterances and utterances[-1]["speaker"] == speaker and
                    word["start"] - utterances[-1]["end"] < 1.5 and
                    word["end"] - utterances[-1]["start"] < 25 and
                    utterances[-1]["overlap"] == uncertain):
                utterances[-1]["text"] += " " + word["text"]
                utterances[-1]["end"] = word["end"]
            else:
                utterances.append({"id": f"U{len(utterances) + 1:05d}", "start": word["start"],
                                   "end": word["end"], "speaker": speaker, "text": word["text"],
                                   "overlap": uncertain})
        report(mid, "Transcrevendo", (index + 1) / len(chunks), f"Trecho {index + 1}/{len(chunks)} · {end:.0f}s de áudio")
    if not utterances:
        raise ValueError("A transcrição ficou vazia; confira o áudio")
    store.atomic_json(directory / "transcript.json", utterances)
    lines = ["# Transcrição", "", "Tempos relativos ao áudio, descontando pausas de gravação.", ""]
    for item in utterances:
        flag = " · sobreposição: atribuição incerta" if item["overlap"] else ""
        lines.append(f"**[{stamp(item['start'])}] {item['speaker']} ({item['id']}){flag}**\n\n{item['text']}\n")
    (directory / "transcricao.md").write_text("\n".join(lines), encoding="utf-8")


def stamp(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def main():
    offline()
    phase, mid = sys.argv[1:3]
    directory = store.folder(mid)
    if phase == "prepare":
        from .audio import prepare
        duration = prepare(directory, lambda p, d: report(mid, "Preparando áudio", p, d))
        store.update(mid, duration=duration)
    elif phase == "diarize":
        diarize(mid, directory)
    elif phase == "transcribe":
        transcribe(mid, directory)
    elif phase == "summarize":
        from .summarize import summarize
        summarize(mid, directory)
    else:
        raise ValueError("Etapa desconhecida")


if __name__ == "__main__":
    main()
