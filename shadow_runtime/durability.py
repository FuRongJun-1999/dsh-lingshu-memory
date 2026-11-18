"""Cross-process locking, atomic temp->fsync->replace, and honest platform durability probes."""
from __future__ import annotations
import ctypes
import hashlib
import os
import pathlib
import platform
import tempfile
import threading
import time

if os.name == "nt":
    import ctypes.wintypes as wt
    import msvcrt
else:
    import fcntl

_PROCESS_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}


class LockBusyError(RuntimeError):
    """Raised when the cross-process write lock cannot be acquired within timeout."""


class DurabilityUnsupportedError(RuntimeError):
    """Raised when strict/power durability is requested without verified platform support."""


def _thread_lock_for(path_str: str) -> threading.RLock:
    with _PROCESS_LOCKS_GUARD:
        lk = _PROCESS_LOCKS.get(path_str)
        if lk is None:
            lk = threading.RLock()
            _PROCESS_LOCKS[path_str] = lk
        return lk


class ExclusiveFileLock:
    """Persistent non-deleted lock file guarded by both in-process RLock and OS file lock."""

    def __init__(self, lock_path: pathlib.Path, *, timeout_s: float = 5.0):
        self._path = pathlib.Path(lock_path).resolve()
        self._timeout_s = float(timeout_s)
        self._tlock = _thread_lock_for(str(self._path))
        self._fd: int | None = None
        self._depth = 0

    def __enter__(self):
        acquired = self._tlock.acquire(timeout=self._timeout_s)
        if not acquired:
            raise LockBusyError("LOCK_BUSY")
        if self._depth > 0:
            self._depth += 1
            return self
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Never delete, rename, or truncate the lock file; open O_CREAT|O_RDWR and lock byte 0.
        try:
            fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            self._tlock.release()
            raise LockBusyError("LOCK_UNAVAILABLE") from exc
        deadline = time.monotonic() + self._timeout_s
        while True:
            try:
                if os.name == "nt":
                    os.lseek(fd, 0, os.SEEK_SET)
                    # Ensure at least 1 byte exists for msvcrt.locking without truncating existing file
                    if os.fstat(fd).st_size == 0:
                        os.write(fd, b"0")
                        os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                self._depth = 1
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    self._tlock.release()
                    raise LockBusyError("LOCK_BUSY")
                time.sleep(0.01)

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._depth -= 1
            if self._depth == 0 and self._fd is not None:
                try:
                    if os.name == "nt":
                        os.lseek(self._fd, 0, os.SEEK_SET)
                        msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(self._fd, fcntl.LOCK_UN)
                finally:
                    os.close(self._fd)
                    self._fd = None
        finally:
            self._tlock.release()


def fsync_dir(dir_path: pathlib.Path) -> None:
    """Flush directory metadata to disk; raises OSError if unsupported or denied."""
    d = pathlib.Path(dir_path)
    if not d.is_dir():
        raise OSError("not a directory: " + str(d))
    if os.name == "nt":
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_ALL = 1 | 2 | 4
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p]
        k32.CreateFileW.restype = wt.HANDLE
        k32.FlushFileBuffers.argtypes = [wt.HANDLE]
        k32.FlushFileBuffers.restype = wt.BOOL
        k32.CloseHandle.argtypes = [wt.HANDLE]
        k32.CloseHandle.restype = wt.BOOL
        handle = k32.CreateFileW(
            str(d), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_ALL, None,
            OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None,
        )
        if handle == INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            raise OSError(err, f"CreateFileW directory failed: {err}")
        try:
            if not k32.FlushFileBuffers(handle):
                err = ctypes.get_last_error()
                raise OSError(err, f"FlushFileBuffers directory failed: {err}")
        finally:
            k32.CloseHandle(handle)
    else:
        fd = os.open(str(d), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _check_drive_fixed(dir_path: pathlib.Path) -> tuple[bool, str]:
    if os.name != "nt":
        return True, "posix"
    DRIVE_FIXED = 3
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetVolumePathNameW.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.DWORD]
    k32.GetVolumePathNameW.restype = wt.BOOL
    k32.GetDriveTypeW.argtypes = [wt.LPCWSTR]
    k32.GetDriveTypeW.restype = wt.UINT
    buf = ctypes.create_unicode_buffer(1024)
    if not k32.GetVolumePathNameW(str(dir_path.resolve()), buf, 1024):
        return False, "unknown_volume"
    dtype = k32.GetDriveTypeW(buf.value)
    if dtype != DRIVE_FIXED:
        return False, f"non_fixed_drive:{dtype}"
    return True, buf.value


def ensure_dir_durable(dir_path: pathlib.Path, *, durable: bool) -> None:
    d = pathlib.Path(dir_path)
    created = not d.exists()
    d.mkdir(parents=True, exist_ok=True)
    if durable:
        fsync_dir(d)
        if created and d.parent != d:
            fsync_dir(d.parent)


def atomic_write_text(path: pathlib.Path, content: str, *, durable: bool, fault_hook=None, stage_prefix: str = "write") -> None:
    """Write UTF-8 text via same-directory temp file -> flush/fsync -> os.replace -> fsync dir."""
    target = pathlib.Path(path)
    ensure_dir_durable(target.parent, durable=durable)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    tmp_path = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            if fault_hook is not None:
                fault_hook(f"{stage_prefix}:after_write_before_fsync", tmp_path)
            if durable:
                os.fsync(f.fileno())
        if fault_hook is not None:
            fault_hook(f"{stage_prefix}:before_replace", tmp_path)
        for attempt in range(30):
            try:
                os.replace(str(tmp_path), str(target))
                break
            except PermissionError:
                if attempt == 29:
                    raise
                time.sleep(0.01 * (attempt + 1))
        if durable:
            fsync_dir(target.parent)
        if fault_hook is not None:
            fault_hook(f"{stage_prefix}:after_replace", target)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def append_line_durable(path: pathlib.Path, line: str, *, durable: bool, fault_hook=None) -> None:
    target = pathlib.Path(path)
    ensure_dir_durable(target.parent, durable=durable)
    data = line.encode("utf-8")
    if fault_hook is not None:
        fault_hook("audit:before_append", target)
    fd = os.open(str(target), os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(fd, data)
        if durable:
            os.fsync(fd)
    finally:
        os.close(fd)
    if durable:
        fsync_dir(target.parent)


def probe_platform_durability(root_dir: pathlib.Path, *, dir_sync_fn=fsync_dir, drive_check_fn=_check_drive_fixed) -> dict:
    """Run an active durability sequence on the exact target root/volume; never cache across restarts."""
    try:
        root = pathlib.Path(root_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        fixed_ok, volume_id = drive_check_fn(root)
        if not fixed_ok:
            return {"supported": False, "reason": volume_id, "root": str(root), "os": platform.platform()}
        probe_dir = root / "_durability_probe"
        with ExclusiveFileLock(root / "locks/probe.lock", timeout_s=5.0):
            return _probe_durability_body(root, probe_dir, volume_id, dir_sync_fn)
    except Exception as exc:
        return {"supported": False, "reason": f"probe_error:{type(exc).__name__}", "root": str(root_dir), "os": platform.platform()}


def _probe_durability_body(root: pathlib.Path, probe_dir: pathlib.Path, volume_id: str, dir_sync_fn) -> dict:
    try:
        if probe_dir.exists():
            for child in probe_dir.iterdir():
                child.unlink()
            probe_dir.rmdir()
        probe_dir.mkdir()
        dir_sync_fn(root)
        dir_sync_fn(probe_dir)
        tmp = probe_dir / "probe.tmp"
        final = probe_dir / "probe.txt"
        payload = "probe-line-1\n"
        fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.write(fd, payload.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp), str(final))
        dir_sync_fn(probe_dir)
        fd2 = os.open(str(final), os.O_WRONLY | os.O_APPEND, 0o600)
        try:
            os.write(fd2, b"probe-line-2\n")
            os.fsync(fd2)
        finally:
            os.close(fd2)
        dir_sync_fn(probe_dir)
        readback = final.read_text(encoding="utf-8")
        if readback != "probe-line-1\nprobe-line-2\n":
            return {"supported": False, "reason": "readback_mismatch", "root": str(root), "os": platform.platform()}
        final.unlink()
        probe_dir.rmdir()
        dir_sync_fn(root)
        return {
            "supported": True,
            "volume_id": hashlib.sha256(volume_id.encode("utf-8")).hexdigest()[:16],
            "os": platform.system(),
            "probe_version": 1,
            "checked_at": int(time.time()),
        }
    except Exception as exc:
        return {"supported": False, "reason": f"probe_error:{type(exc).__name__}", "root": str(root), "os": platform.platform()}
