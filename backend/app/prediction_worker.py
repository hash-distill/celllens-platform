"""Isolated prediction attempt; owned by the persistent GPU worker."""

import argparse
import os
import signal
import subprocess
import threading
import time

from backend.app.config import get_settings
from backend.app.container import build_container


def watch_owner(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if handle:
            kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
            kernel.CloseHandle(handle)
        subprocess.run(
            ["taskkill", "/PID", str(os.getpid()), "/T", "/F"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        os._exit(1)
    while os.getppid() == pid:
        time.sleep(1)
    # Parent launches this subprocess in its own session; kill its STATE descendants too.
    os.killpg(os.getpgrp(), signal.SIGKILL)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--parent-pid", required=True, type=int)
    args = parser.parse_args()
    threading.Thread(target=watch_owner, args=(args.parent_pid,), daemon=True).start()
    settings = get_settings()
    build_container(settings).pipeline._run_sync(args.run_id)


if __name__ == "__main__":
    main()
