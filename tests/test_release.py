import importlib.util
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_release", ROOT / "scripts" / "build_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_distribution_excludes_private_data_and_includes_installation(tmp_path):
    archive = release.build(ROOT, tmp_path)
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert "ata-local/Instalar.ps1" in names
        assert "ata-local/ata_local/static/app.js" in names
        assert "ata-local/config.json" in names
        for name in names:
            assert not {"data", "models", "runtime", "exemplos", ".git", ".venv"}.intersection(Path(name).parts)
        assert package.testzip() is None
    # Identical inputs produce an identical archive and checksum.
    original = archive.read_bytes()
    release.build(ROOT, tmp_path)
    assert archive.read_bytes() == original


def test_release_rejects_token_without_printing_it(tmp_path):
    token = "hf_" + "x" * 30
    path = tmp_path / "config.json"
    path.write_text(token)
    with pytest.raises(ValueError) as error:
        release.audit(tmp_path, [path])
    assert token not in str(error.value)
    assert "config.json" in str(error.value)
