"""Build an audited source distribution without models, recordings or credentials."""
import argparse
import hashlib
from pathlib import Path
import re
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    ".gitignore", "Autorizar-Community.ps1", "Iniciar.ps1", "Instalar.ps1",
    "LICENSE", "README.md", "THIRD_PARTY.md", "VALIDACAO.md", "CHANGELOG.md",
    "CONTRIBUTING.md", "config.json", "models-lock.json", "pyproject.toml",
    "requirements-lock.txt",
)
SECRET_PATTERNS = (
    re.compile(rb"hf_[a-zA-Z0-9]{20,}"),
    re.compile(rb"gh[pousr]_[a-zA-Z0-9]{20,}"),
    re.compile(rb"github_pat_[a-zA-Z0-9_]{20,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?i)[a-z]:[\\/]Users[\\/](?!PUBLIC[\\/])[^\s\"']+"),
)


def release_files(root):
    files = [root / name for name in ROOT_FILES]
    for folder in ("ata_local", "scripts", "tests"):
        files.extend(p for p in (root / folder).rglob("*.py") if "__pycache__" not in p.parts)
    files.extend(p for p in (root / "ata_local" / "static").rglob("*")
                 if p.is_file() and p.suffix in {".html", ".js", ".css", ".svg", ".png", ".ico"})
    return sorted(set(files))


def audit(root, files):
    for path in files:
        relative = path.relative_to(root)
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"External or symbolic path refused: {relative}")
        data = path.read_bytes()
        if path.suffix not in {".png", ".ico"}:
            for pattern in SECRET_PATTERNS:
                if pattern.search(data):
                    # Never print the matched value.
                    raise ValueError(f"Possible credential or personal path in {relative}")


def build(root=ROOT, destination=None):
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Expected a numeric release version")
    files = release_files(root)
    audit(root, files)
    destination = destination or root / "dist"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"ata-local-{version}-windows.zip"
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in files:
            info = zipfile.ZipInfo(f"ata-local/{path.relative_to(root).as_posix()}", (2026, 9, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, path.read_bytes())
    with zipfile.ZipFile(temporary) as output:
        if output.testzip():
            raise ValueError("ZIP integrity check failed")
    temporary.replace(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(".zip.sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"{archive.name}: {len(files)} audited files; SHA-256 {digest}")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    build(destination=args.output)
