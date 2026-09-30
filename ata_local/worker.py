import os
import errno
import subprocess
import sys
import threading
import time
from . import store
from .config import ROOT, DATA, readiness


class InstanceBusy(RuntimeError):
    """Another process owns the queue; never read or remove its locked byte."""


class Supervisor:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.lockfile = None
        self.process_job = None

    def acquire_lock(self):
        if self.lockfile is not None:
            return
        DATA.mkdir(parents=True, exist_ok=True)
        handle = open(DATA / "worker.lock", "a+b", buffering=0)
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                # Windows permits locking beyond EOF. Never read another owner's byte.
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise InstanceBusy("Outra instância mantém a fila ocupada.") from None
            raise
        self.lockfile = handle

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return
        self.acquire_lock()
        self.stop_event.clear()
        try:
            store.recover()
            if os.name == "nt":
                from .windows_job import WindowsJob
                self.process_job = WindowsJob()
            self.thread = threading.Thread(target=self.run, name="gpu-queue", daemon=True)
            self.thread.start()
        except BaseException:
            self.close()
            raise

    def close(self):
        self.stop_event.set()
        if self.thread and self.thread.ident is not None:
            self.thread.join(timeout=20)
        if self.process_job:
            self.process_job.close()
            self.process_job = None
        if self.thread and self.thread.is_alive():
            raise RuntimeError("O processamento ainda está encerrando; a fila continua protegida.")
        self.thread = None
        if self.lockfile:
            self.lockfile.close()
            self.lockfile = None

    @staticmethod
    def terminate(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            import signal
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=15)

    def run(self):
        while not self.stop_event.wait(0.7):
            # Incomplete installation keeps jobs queued instead of repeatedly failing them.
            if not all(item["ready"] for item in readiness().values()):
                continue
            job = store.claim()
            if job:
                try:
                    self.process(job)
                except Exception as error:
                    store.update(job["id"], status="failed", stage="Falha", error=str(error))

    def process(self, job):
        mid = job["id"]
        directory = store.folder(mid)
        phases = [("prepare", "audio.wav"), ("diarize", "speakers.json"),
                  ("transcribe", "transcript.json"), ("summarize", "ata.md")]
        for phase, checkpoint in phases:
            if store.get(mid)["status"] == "cancelling":
                store.update(mid, status="cancelled", stage="Cancelado")
                return
            if (directory / checkpoint).exists():
                continue
            store.update(mid, progress=0, detail="Carregando etapa", stage=phase)
            with open(directory / f"{phase}.log", "a", encoding="utf-8") as log:
                process = subprocess.Popen([sys.executable, "-m", "ata_local.pipeline", phase, mid],
                    cwd=ROOT, stdout=log, stderr=log, env={**os.environ, "PYTHONUTF8": "1"},
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), start_new_session=os.name != "nt")
                if self.process_job:
                    self.process_job.add(process)
                while process.poll() is None:
                    if self.stop_event.wait(0.4):
                        self.terminate(process)
                        store.update(mid, status="queued", stage="Aguardando retomada")
                        return
                    if store.get(mid)["status"] == "cancelling":
                        self.terminate(process)
                        store.update(mid, status="cancelled", stage="Cancelado", detail="Áudio e etapas concluídas preservados")
                        return
                if process.returncode != 0:
                    tail = (directory / f"{phase}.log").read_text(encoding="utf-8", errors="replace")[-1800:]
                    raise RuntimeError(f"Falha na etapa {phase}. {tail}")
        store.update(mid, status="completed", stage="Concluído", progress=100, detail="Ata Markdown pronta", error="")
