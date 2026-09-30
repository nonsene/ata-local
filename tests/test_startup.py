import errno
import os
import subprocess
import sys
import asyncio
import pytest
from ata_local import worker
from ata_local.__main__ import server_config


def test_selector_loop_and_bounded_shutdown():
    config = server_config(lambda: None)
    loop = config.get_loop_factory()()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
        assert config.timeout_graceful_shutdown == 5
        assert config.use_colors is False
    finally:
        loop.close()


def test_existing_lock_is_reported_without_reading_its_byte(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'DATA', tmp_path)
    # Use a different process so the OS enforces its actual byte-range lock.
    code = "from ata_local.worker import Supervisor; s=Supervisor(); s.acquire_lock(); print('ready',flush=True); input(); s.close()"
    child = subprocess.Popen([sys.executable, '-c', code], env={**os.environ, 'ATA_DATA': str(tmp_path)},
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    candidate = worker.Supervisor()
    try:
        assert child.stdout.readline().strip() == 'ready'
        with pytest.raises(worker.InstanceBusy, match='Outra instância'):
            candidate.acquire_lock()
        assert candidate.lockfile is None
        child.communicate('\n', timeout=5)
        candidate.acquire_lock()
        candidate.close()
        candidate.close()  # Cleanup is idempotent.
        candidate.acquire_lock()
        candidate.close()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        candidate.close()


def test_failed_startup_releases_queue_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'DATA', tmp_path)
    def fail():
        raise OSError('database unavailable')
    monkeypatch.setattr(worker.store, 'recover', fail)
    supervisor = worker.Supervisor()
    with pytest.raises(OSError, match='database unavailable'):
        supervisor.start()
    assert supervisor.lockfile is None
    other = worker.Supervisor()
    other.acquire_lock()
    other.close()
