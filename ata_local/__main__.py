import argparse
import asyncio
import sys
import threading
import time
import webbrowser
import httpx
import uvicorn

ADDRESS = "http://127.0.0.1:8765"


def is_running():
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            health = client.get(ADDRESS + "/api/health")
            if health.status_code == 200 and health.json().get("app") == "ata-local":
                return True
            if health.status_code == 404:
                state = client.get(ADDRESS + "/api/state")
                data = state.json()
                return state.status_code == 200 and "models" in data and "recorder" in data
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return False


def loop_factory():
    # Proactor may leave wait_closed stuck after a connection reset on Windows.
    # GPU subprocesses use synchronous Popen on the worker thread, not asyncio.
    return asyncio.SelectorEventLoop()


def server_config(app):
    return uvicorn.Config(app, host="127.0.0.1", port=8765, workers=1,
                          loop="ata_local.__main__:loop_factory", use_colors=False,
                          timeout_graceful_shutdown=5)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    def reuse():
        if not args.no_browser:
            webbrowser.open(ADDRESS)
        print("Ata Local já está em execução: " + ADDRESS)
        return 0

    if is_running():
        return reuse()

    from .app import app, supervisor
    from .worker import InstanceBusy
    from .config import DATA
    try:
        supervisor.acquire_lock()
    except InstanceBusy:
        for _ in range(12):
            if is_running():
                return reuse()
            time.sleep(0.25)
            try:
                supervisor.acquire_lock()
                break
            except InstanceBusy:
                continue
        else:
            print("Ata Local: outra instância ainda mantém a fila ocupada, mas a interface não responde. "
                  "Ela pode estar encerrando ou travada. Não apague worker.lock. "
                  "Feche a instância anterior e tente novamente.", file=sys.stderr)
            return 2
    except OSError as error:
        print(f"Ata Local: não foi possível acessar a pasta {DATA}: {error}", file=sys.stderr)
        return 1

    done = threading.Event()
    try:
        if not args.no_browser:
            def open_when_ready():
                for _ in range(40):
                    if done.is_set():
                        return
                    if is_running():
                        webbrowser.open(ADDRESS)
                        return
                    if done.wait(0.25):
                        return
            threading.Thread(target=open_when_ready, daemon=True).start()
        server = uvicorn.Server(server_config(app))
        app.state.shutdown = lambda: setattr(server, "should_exit", True)
        server.run()
        return 0 if server.started else 1
    finally:
        done.set()
        supervisor.close()


if __name__ == "__main__":
    sys.exit(main())
