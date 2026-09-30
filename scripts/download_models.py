"""Explicit online installation only. Never imported by the offline application."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(ROOT / "models" / ".cache")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ.pop("HF_HUB_OFFLINE", None)
os.environ.pop("TRANSFORMERS_OFFLINE", None)


def download_llama():
    import httpx
    target = ROOT / "runtime" / "llama"
    target.mkdir(parents=True, exist_ok=True)
    release = "b11160"
    marker = target / "installation.json"
    if marker.exists():
        installed = json.loads(marker.read_text(encoding="utf-8"))
        if (installed.get("release") == release and installed.get("files")
                and (target / "llama-server.exe").exists()
                and all((target / name).is_file() and (target / name).stat().st_size == size
                        for name, size in installed["files"].items())):
            return
    # An executable alone does not prove the CUDA DLL archive finished downloading.
    installed_files = {}
    names = [f"llama-{release}-bin-win-cuda-13.4-x64.zip", "cudart-llama-bin-win-cuda-13.4-x64.zip"]
    hashes = ["966b2b052a820d71ba1c2040a73c46afc772659a75395260a583746effb72cff",
              "738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668"]
    with httpx.Client(follow_redirects=True, timeout=600) as client:
        for name, expected in zip(names, hashes):
            print(f"Baixando {name}", flush=True)
            archive = target / name
            sha = hashlib.sha256()
            with client.stream("GET", f"https://github.com/ggml-org/llama.cpp/releases/download/{release}/{name}") as response:
                response.raise_for_status()
                with archive.open("wb") as output:
                    for chunk in response.iter_bytes(1024 * 1024):
                        output.write(chunk)
                        sha.update(chunk)
            if sha.hexdigest() != expected:
                raise ValueError(f"Hash inválido: {name}")
            with zipfile.ZipFile(archive) as package:
                for item in package.infolist():
                    if item.is_dir():
                        continue
                    # Only native runtime files; flatten the official release layout.
                    leaf = Path(item.filename).name
                    if Path(leaf).suffix.lower() in {".exe", ".dll", ".txt", ".md", ".json"}:
                        with package.open(item) as source, (target / leaf).open("wb") as output:
                            shutil.copyfileobj(source, output)
                        installed_files[leaf] = (target / leaf).stat().st_size
            archive.unlink()
    if not (target / "llama-server.exe").is_file():
        raise ValueError("llama-server.exe não encontrado no pacote oficial")
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps({"release": release, "files": installed_files}, indent=2), encoding="utf-8")
    temporary.replace(marker)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--community", action="store_true")
    args = parser.parse_args()
    from huggingface_hub import HfApi, snapshot_download, hf_hub_download
    api = HfApi()
    models = ROOT / "models"
    models.mkdir(exist_ok=True)
    manifest_path = models / "downloads.json"
    lock = manifest_path if manifest_path.exists() else ROOT / "models-lock.json"
    manifest = json.loads(lock.read_text(encoding="utf-8-sig")) if lock.exists() else {}

    def snapshot(repo, destination, token=None):
        revision = manifest.get(repo, {}).get("revision") or api.model_info(repo, token=token).sha
        print(f"Baixando {repo} ({revision[:12]})", flush=True)
        snapshot_download(repo, revision=revision, local_dir=models / destination, token=token,
                          ignore_patterns=["*.msgpack", "*.h5", "*.onnx"])
        manifest[repo] = {"revision": revision, "directory": destination}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.community:
        print("Aceite primeiro os termos em https://huggingface.co/pyannote/speaker-diarization-community-1")
        print("Crie um token de leitura em https://huggingface.co/settings/tokens")
        print("O token será usado apenas para baixar os arquivos; não será salvo pelo aplicativo.")
        token = getpass.getpass("Token Hugging Face (entrada oculta): ").strip()
        if not token:
            raise ValueError("Token não informado")
        snapshot("pyannote/speaker-diarization-community-1", "speaker-diarization-community-1", token)
    else:
        snapshot("Qwen/Qwen3-ASR-1.7B", "Qwen3-ASR-1.7B")
        snapshot("Qwen/Qwen3-ForcedAligner-0.6B", "Qwen3-ForcedAligner-0.6B")
        repo = "unsloth/Qwen3.5-9B-GGUF"
        revision = manifest.get(repo, {}).get("revision") or api.model_info(repo).sha
        filename = "Qwen3.5-9B-Q8_0.gguf"
        print(f"Baixando {filename}", flush=True)
        hf_hub_download(repo, filename, revision=revision, local_dir=models)
        manifest[repo] = {"revision": revision, "filename": filename}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        download_llama()
    print("Download concluído. A execução do aplicativo é offline.", flush=True)


if __name__ == "__main__":
    main()
