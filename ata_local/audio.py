"""Native WASAPI loopback + microphone. Callbacks only persist PCM, never run ML."""
import json
import threading
import time
from pathlib import Path


def devices():
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        host = audio.get_host_api_info_by_type(pa.paWASAPI)
        default_output = int(host["defaultOutputDevice"])
        default_input = int(host["defaultInputDevice"])
        output_name = audio.get_device_info_by_index(default_output)["name"] if default_output >= 0 else ""
        loops, microphones = [], []
        for index in range(audio.get_device_count()):
            dev = audio.get_device_info_by_index(index)
            if dev["hostApi"] != host["index"] or dev["maxInputChannels"] < 1:
                continue
            item = {"id": index, "name": dev["name"], "rate": int(dev["defaultSampleRate"]),
                    "channels": int(dev["maxInputChannels"])}
            if dev.get("isLoopbackDevice"):
                item["default"] = bool(output_name and output_name in dev["name"])
                loops.append(item)
            else:
                item["default"] = index == default_input
                microphones.append(item)
        return {"outputs": loops, "microphones": microphones}


class Recorder:
    def __init__(self):
        self.lock = threading.RLock()
        self.mid = None
        self.pa = None
        self.streams = []
        self.files = []
        self.paused = False
        self.error = ""
        self.levels = {}

    def start(self, mid, directory, output_id, microphone_id):
        import pyaudiowpatch as pa
        with self.lock:
            if self.mid:
                raise ValueError("Já existe uma gravação ativa")
            self.mid, self.error, self.levels = mid, "", {}
            self.paused = False
            self.elapsed = 0.0
            self.epoch = 0
            self.epoch_start = time.monotonic()
            self.pa = pa.PyAudio()
        try:
            sources = [("system", output_id)]
            if microphone_id is not None:
                sources.append(("microphone", microphone_id))
            manifest = {"sources": []}
            for name, index in sources:
                dev = self.pa.get_device_info_by_index(index)
                if bool(dev.get("isLoopbackDevice")) != (name == "system"):
                    raise ValueError("Dispositivo incompatível com a fonte selecionada")
                channels, rate = int(dev["maxInputChannels"]), int(dev["defaultSampleRate"])
                if channels < 1:
                    raise ValueError("Dispositivo sem canais de captura")
                raw = open(directory / f"{name}.pcm", "wb", buffering=0)
                idx = open(directory / f"{name}.jsonl", "w", encoding="utf-8", buffering=1)
                self.files.extend([raw, idx])
                manifest["sources"].append({"name": name, "rate": rate, "channels": channels,
                                            "device": dev["name"]})
                callback = self._callback(name, raw, idx, channels, rate, pa)
                stream = self.pa.open(format=pa.paInt16, channels=channels, rate=rate, input=True,
                                      input_device_index=index, frames_per_buffer=2048,
                                      stream_callback=callback, start=False)
                self.streams.append(stream)
            (directory / "capture.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            self.epoch_start = time.monotonic()
            for stream in self.streams:
                stream.start_stream()
        except BaseException:
            self._close()
            self.mid = None
            raise

    def _callback(self, name, raw, idx, channels, rate, pa):
        cursor, epoch = 0.0, -1

        def callback(data, frames, timing, flags):
            nonlocal cursor, epoch
            import numpy as np
            try:
                with self.lock:
                    if flags:
                        self.error = f"Falha/overflow na captura de {name} (código {flags}). Áudio parcial preservado."
                        return (None, pa.paAbort)
                    if self.paused:
                        self.levels[name] = 0
                        return (None, pa.paContinue)
                    if epoch != self.epoch:
                        epoch = self.epoch
                        cursor = self.elapsed + max(0, time.monotonic() - self.epoch_start - frames / rate)
                    offset = raw.tell()
                    raw.write(data)
                    idx.write(json.dumps([round(cursor, 6), offset, frames]) + "\n")
                    cursor += frames / rate
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768
                    self.levels[name] = float(min(1, np.sqrt(np.mean(samples * samples)) * 5))
                return (None, pa.paContinue)
            except BaseException as exc:
                self.error = f"Falha ao salvar áudio: {exc}"
                return (None, pa.paAbort)
        return callback

    def duration(self):
        if not self.mid:
            return 0
        return self.elapsed + (0 if self.paused else time.monotonic() - self.epoch_start)

    def pause(self):
        with self.lock:
            if not self.mid or self.paused:
                raise ValueError("Não há gravação em andamento")
            self.elapsed = self.duration()
            self.paused = True

    def resume(self):
        with self.lock:
            if not self.mid or not self.paused:
                raise ValueError("Não há gravação pausada")
            self.epoch += 1
            self.epoch_start = time.monotonic()
            self.paused = False

    def _close(self):
        # Never hold the callback lock while waiting for PortAudio callbacks to stop.
        for stream in self.streams:
            try:
                stream.stop_stream()
            finally:
                stream.close()
        self.streams.clear()
        for file in self.files:
            file.close()
        self.files.clear()
        if self.pa:
            self.pa.terminate()
        self.pa = None

    def stop(self):
        with self.lock:
            if not self.mid:
                raise ValueError("Não há gravação ativa")
            duration = self.duration()
            self.paused = True
        self._close()
        self.mid = None
        return duration

    def state(self):
        with self.lock:
            return {"id": self.mid, "paused": self.paused, "duration": self.duration(),
                    "levels": dict(self.levels), "error": self.error}


def prepare(directory, progress=lambda p, text: None):
    """Rebuild synchronized 16 kHz mono audio from durable PCM block indexes."""
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    from math import gcd
    manifest = json.loads((directory / "capture.json").read_text(encoding="utf-8"))
    indexed = []
    duration = 0
    for source in manifest["sources"]:
        blocks = []
        for line in (directory / f"{source['name']}.jsonl").read_text().splitlines():
            try:
                t, offset, frames = json.loads(line)
            except (ValueError, TypeError):
                continue  # A crash can leave only the final index line incomplete.
            blocks.append((t, offset, frames))
            duration = max(duration, t + frames / source["rate"])
        indexed.append((source, blocks))
    if duration < 0.25:
        raise ValueError("Gravação sem áudio suficiente")
    count = int(duration * 16000) + 16000
    mixpath = directory / "mix.f32"
    mixed = np.memmap(mixpath, mode="w+", dtype=np.float32, shape=(count,))
    mixed[:] = 0
    total = max(1, sum(len(blocks) for _, blocks in indexed))
    done = 0
    try:
        for source, blocks in indexed:
            rate, channels = source["rate"], source["channels"]
            divisor = gcd(rate, 16000)
            with open(directory / f"{source['name']}.pcm", "rb") as raw:
                for t, offset, frames in blocks:
                    raw.seek(offset)
                    payload = raw.read(frames * channels * 2)
                    if len(payload) != frames * channels * 2:
                        raise ValueError("Bloco PCM incompleto; mantenha o áudio original para recuperação")
                    samples = np.frombuffer(payload, dtype=np.int16).reshape(-1, channels).mean(axis=1).astype(np.float32) / 32768
                    samples = resample_poly(samples, 16000 // divisor, rate // divisor)
                    start = round(t * 16000)
                    mixed[start:start + len(samples)] += samples / len(indexed)
                    done += 1
                    if done % 100 == 0:
                        progress(done / total, "Sincronizando sistema e microfone")
        target = directory / "audio.tmp.wav"
        with sf.SoundFile(target, mode="w", samplerate=16000, channels=1, subtype="PCM_16") as output:
            for start in range(0, int(duration * 16000), 16000 * 30):
                end = min(start + 16000 * 30, int(duration * 16000))
                output.write(np.clip(mixed[start:end], -1, 1))
        target.replace(directory / "audio.wav")
    finally:
        mixed.flush()
        del mixed
        mixpath.unlink(missing_ok=True)
    return duration
