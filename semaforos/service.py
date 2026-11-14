"""Arranque reproducible del núcleo en Docker/Easypanel."""
import os
import signal
import subprocess
import sys
import time

def commands(mode):
    api = [
        sys.executable, "-m", "uvicorn", "semaforos.api:create_app",
        "--factory", "--host", "0.0.0.0", "--port", "8000",
    ]
    worker = [sys.executable, "-m", "semaforos", "worker"]
    workers = [[sys.executable,'-m','semaforos.lanes',lane] for lane in ('text','media')] if os.getenv('SC_PARALLEL','0')=='1' else [worker]
    if mode == "api":
        return [api]
    if mode == "worker":
        return workers
    if mode == "all":
        return [api, *workers]
    raise ValueError("SC_PROCESS_must_be_api_worker_or_all")


def supervise(specs):
    children = [subprocess.Popen(spec) for spec in specs]
    stopping = False

    def stop(_signum=None, _frame=None):
        nonlocal stopping
        if stopping:
            return
        stopping = True
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while True:
            for child in children:
                code = child.poll()
                if code is not None:
                    was_stopping = stopping
                    stop()
                    for other in children:
                        if other.poll() is None:
                            try:
                                other.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                other.kill()
                    return code if code else (0 if was_stopping else 1)
            time.sleep(1)
    finally:
        stop()


def main():
    from .store import Store
    Store().migrate()
    mode = os.getenv("SC_PROCESS", "all").strip().lower()
    return supervise(commands(mode))


if __name__ == "__main__":
    raise SystemExit(main())
