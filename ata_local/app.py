import secrets
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal
from . import store
from .audio import Recorder, devices
from .config import offline, readiness
from .worker import Supervisor

offline()
recorder = Recorder()
supervisor = Supervisor()
control = threading.Lock()
session_token = secrets.token_urlsafe(32)
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app):
    store.init()
    try:
        supervisor.start()
        yield
    finally:
        try:
            if recorder.mid:
                mid = recorder.mid
                duration = recorder.stop()
                store.update(mid, status="interrupted", stage="Gravação interrompida", duration=duration,
                             error="Aplicativo encerrado durante a captura. Recupere o áudio parcial.")
        finally:
            supervisor.close()


app = FastAPI(title="Ata Local", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def local_only(request: Request, call_next):
    # Host check prevents DNS rebinding. Token + exact origin prevents drive-by capture.
    host = request.headers.get("host", "")
    if host not in {"127.0.0.1:8765", "localhost:8765", "testserver"}:
        return JSONResponse({"detail": "Acesso restrito ao computador local"}, status_code=403)
    if request.method not in {"GET", "HEAD"}:
        origin = request.headers.get("origin")
        if origin and origin not in {"http://127.0.0.1:8765", "http://localhost:8765", "http://testserver"}:
            return JSONResponse({"detail": "Origem não autorizada"}, status_code=403)
        if not secrets.compare_digest(request.headers.get("x-ata-token", ""), session_token):
            return JSONResponse({"detail": "Sessão inválida; atualize a página"}, status_code=403)
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ValueError)
async def value_error(request, error):
    return JSONResponse({"detail": str(error)}, status_code=400)


class NewMeeting(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    output_id: int = Field(ge=0)
    microphone_id: int | None = Field(default=None, ge=0)
    client: str = Field(default="", max_length=200)
    supplier: str = Field(default="", max_length=200)
    my_side: Literal["cliente", "fornecedor", "indeterminado"] = "indeterminado"
    speakers: int | None = Field(default=None, ge=1, le=30)
    context: str = Field(default="", max_length=2000)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    return {"token": session_token, "recorder": recorder.state(), "meetings": store.all_meetings(), "models": readiness()}


@app.get("/api/health")
def health():
    # Liveness does not wait for SQLite, model files or the recorder callback lock.
    return {"app": "ata-local", "pid": os.getpid(), "status": "ready"}


@app.get("/api/devices")
def audio_devices():
    try:
        return devices()
    except Exception as error:
        raise HTTPException(503, f"Não foi possível consultar WASAPI: {error}") from error


@app.post("/api/shutdown")
def shutdown():
    with control:
        if recorder.mid:
            raise HTTPException(409, "Encerre a gravação antes de fechar o aplicativo")
        callback = getattr(app.state, "shutdown", None)
        if not callback:
            raise HTTPException(409, "Encerre pelo terminal que iniciou o servidor")
        callback()
        return {"stopping": True}


@app.post("/api/record/start")
def start(payload: NewMeeting):
    with control:
        if recorder.mid:
            raise HTTPException(409, "Já existe uma gravação ativa")
        job = store.create(payload.title, payload.model_dump(exclude={"title", "output_id", "microphone_id"}))
        try:
            recorder.start(job["id"], store.folder(job["id"]), payload.output_id, payload.microphone_id)
        except Exception as error:
            store.update(job["id"], status="failed", stage="Falha na captura", error=str(error))
            raise HTTPException(400, f"Não foi possível iniciar a captura: {error}") from error
        return job


@app.post("/api/record/{action}")
def recording_action(action: Literal["pause", "resume", "stop"]):
    with control:
        mid = recorder.mid
        if not mid:
            raise HTTPException(409, "Não há gravação ativa")
        if action == "pause":
            recorder.pause()
            store.update(mid, status="paused", stage="Pausado")
        elif action == "resume":
            recorder.resume()
            store.update(mid, status="recording", stage="Gravando")
        else:
            duration = recorder.stop()
            error = recorder.error
            store.update(mid, status="interrupted" if error else "queued", stage="Captura com falha" if error else "Na fila",
                         duration=duration, error=error, detail="Áudio parcial preservado" if error else "Aguardando processamento local")
        return store.get(mid)


@app.post("/api/meetings/{mid}/{action}")
def meeting_action(mid: str, action: Literal["retry", "cancel", "recover"]):
    with control:
        job = store.get(mid)
        if not job:
            raise HTTPException(404, "Reunião não encontrada")
        if action == "cancel" and job["status"] in {"queued", "processing"}:
            running = job["status"] == "processing"
            store.update(mid, status="cancelling" if running else "cancelled", stage="Cancelando" if running else "Cancelado")
        elif action in {"retry", "recover"} and job["status"] in {"failed", "cancelled", "interrupted"}:
            if not (store.folder(mid) / "capture.json").exists():
                raise HTTPException(409, "Não há áudio para recuperar; inicie outra gravação")
            store.update(mid, status="queued", stage="Na fila", progress=0, error="", detail="Retomando etapas pendentes")
        else:
            raise HTTPException(409, "Ação incompatível com o estado atual")
        return store.get(mid)


ARTIFACTS = {"ata.md", "transcricao.md", "transcript.json", "summary.json", "audio.wav"}


@app.get("/api/meetings/{mid}/files/{name}")
def artifact(mid: str, name: str, download: bool = True):
    if name not in ARTIFACTS:
        raise HTTPException(404)
    path = store.folder(mid) / name
    if not path.is_file():
        raise HTTPException(404, "Arquivo ainda não disponível")
    return FileResponse(path, filename=name if download else None,
                        media_type="audio/wav" if name == "audio.wav" else "text/plain; charset=utf-8")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
