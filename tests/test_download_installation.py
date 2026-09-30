import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def downloader(tmp_path, monkeypatch):
    # Installation has its own online process; isolate its environment changes.
    for key in ("HF_HOME", "HF_HUB_DISABLE_TELEMETRY", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.setenv(key, "test")
    path = Path(__file__).resolve().parents[1] / "scripts" / "download_models.py"
    spec = importlib.util.spec_from_file_location("downloader", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    target = tmp_path / "runtime" / "llama"
    target.mkdir(parents=True)
    (target / "llama-server.exe").write_bytes(b"test")
    return module, target


@pytest.mark.parametrize("has_marker", [False, True])
def test_executable_without_complete_cuda_runtime_retries_download(downloader, monkeypatch, has_marker):
    module, target = downloader
    if has_marker:
        (target / "installation.json").write_text(json.dumps({"release": "b11160",
            "files": {"llama-server.exe": 4, "missing.dll": 10}}))
    client = Mock(side_effect=RuntimeError("download attempted"))
    monkeypatch.setattr("httpx.Client", client)
    with pytest.raises(RuntimeError, match="download attempted"):
        module.download_llama()
    client.assert_called_once()


def test_complete_installation_does_not_download_again(downloader, monkeypatch):
    module, target = downloader
    (target / "installation.json").write_text(json.dumps({"release": "b11160", "files": {"llama-server.exe": 4}}))
    client = Mock(side_effect=AssertionError("unexpected network"))
    monkeypatch.setattr("httpx.Client", client)
    module.download_llama()
    client.assert_not_called()
