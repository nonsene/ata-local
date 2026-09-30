import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("ATA_ROOT", Path(__file__).resolve().parents[1])).resolve()
DATA = Path(os.environ.get("ATA_DATA", ROOT / "data")).resolve()


def config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def model_path(key):
    path = Path(config()[key])
    return path if path.is_absolute() else ROOT / path


def offline():
    # Deliberately override inherited online settings in all inference processes.
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY",
                "PYANNOTE_METRICS_ENABLED", "DO_NOT_TRACK"):
        os.environ[key] = "0" if key == "PYANNOTE_METRICS_ENABLED" else "1"
    os.environ["HF_HOME"] = str(ROOT / "models" / ".cache")
    os.environ["MPLCONFIGDIR"] = str(DATA / "cache" / "matplotlib")
    os.environ["NUMBA_CACHE_DIR"] = str(DATA / "cache" / "numba")
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "false"
    from .privacy import restrict_network
    restrict_network()


def readiness():
    result = {}
    for key in ("asr_model", "aligner_model", "diarization_model", "summary_model", "llama_server"):
        path = model_path(key)
        if key in ("asr_model", "aligner_model"):
            ready = (path / "config.json").is_file() and any(path.glob("*.safetensors"))
        elif key == "diarization_model":
            ready = (path / "config.yaml").is_file() and any(path.rglob("*.bin"))
        else:
            ready = path.is_file() and path.stat().st_size > 1000
        result[key] = {"ready": ready, "path": str(path)}
    return result
