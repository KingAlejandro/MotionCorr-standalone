"""Content digests of worker outputs, bound to the file state they describe.

A digest is recorded together with the file's stat key (device, inode, size,
mtime, ctime). Any later write to the file changes its mtime and ctime, and a
replacement changes the inode, so a later reader whose stat key matches the
recorded one can reuse the digest instead of reading the bytes again. ctime
cannot be set from userspace, so restoring mtime with utimensat after a
rewrite does not restore the key.

Two details keep that inference sound:

* The file must not change while it is read. Every digest is taken between an
  fstat before and after the read, and both must equal the key recorded when
  the file was first listed.
* Timestamps are taken from a coarse clock. A write in the same clock tick as
  the file's last recorded change would leave ctime unchanged, so before any
  file is read, `ctime_barrier` waits until a probe on the same filesystem gets
  a ctime later than every listed file's. From then on, any write to a listed
  file produces a ctime later than the one recorded for it.

hashlib releases the GIL for large updates, so a thread pool hashes in
parallel. Pool threads inherit the creating thread's CPU affinity on Linux.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CHUNK = 1 << 20
# Written into each worker directory by run_multi_gpu.py, not by the worker.
LAUNCHER_FILES = frozenset({"launcher.console.log", "command.json"})
BARRIER_TIMEOUT_S = 5.0


class FileChanged(Exception):
    """The file's stat key moved while, or since, it was listed."""


def stat_key(st: os.stat_result) -> list[int]:
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def hash_file(path: Path, key: list[int]) -> str:
    """sha256 of `path`, which must still have stat key `key` before and after."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        if stat_key(os.fstat(fh.fileno())) != key:
            raise FileChanged(f"{path} changed after it was listed")
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
        if stat_key(os.fstat(fh.fileno())) != key:
            raise FileChanged(f"{path} changed while it was read")
    return digest.hexdigest()


def copy_with_digest(src: Path, dst: Path, key: list[int]) -> str:
    """Copy src to a new dst, hashing the bytes copied; then copy metadata.

    The source must keep stat key `key` for the whole copy, so the digest
    describes both the source state and the bytes written.
    """
    digest = hashlib.sha256()
    with open(src, "rb") as fin:
        if stat_key(os.fstat(fin.fileno())) != key:
            raise FileChanged(f"{src} changed after it was listed")
        with open(dst, "xb") as fout:
            for chunk in iter(lambda: fin.read(CHUNK), b""):
                digest.update(chunk)
                fout.write(chunk)
        if stat_key(os.fstat(fin.fileno())) != key:
            raise FileChanged(f"{src} changed while it was copied")
    shutil.copystat(src, dst)
    return digest.hexdigest()


def ctime_barrier(probe_dir: Path, after_ns: int, devices: set[int],
                  timeout: float = BARRIER_TIMEOUT_S) -> float:
    """Wait until a new write on probe_dir's filesystem gets ctime > after_ns.

    Returns the seconds waited. Raises RuntimeError if the files span another
    filesystem, whose clock this probe cannot order, or if the timestamp does
    not advance within `timeout` (for example a file dated in the future).
    """
    t0 = time.monotonic()
    fd, name = tempfile.mkstemp(prefix=".ctime-probe-", dir=probe_dir)
    try:
        dev = os.fstat(fd).st_dev
        if devices - {dev}:
            raise RuntimeError(f"files span filesystems {sorted(devices)}; the probe in "
                               f"{probe_dir} can only order timestamps on {dev}")
        while True:
            os.write(fd, b"x")
            if os.fstat(fd).st_ctime_ns > after_ns:
                return time.monotonic() - t0
            if time.monotonic() - t0 > timeout:
                raise RuntimeError(f"file timestamps in {probe_dir} did not advance past "
                                   f"{after_ns} within {timeout} s")
            time.sleep(0.001)
    finally:
        os.close(fd)
        os.unlink(name)


def pool_size(cpus: set[int] | None = None) -> int:
    if cpus:
        return max(1, min(32, len(cpus)))
    try:
        n = len(os.sched_getaffinity(0))
    except AttributeError:
        n = os.cpu_count() or 1
    return max(1, min(32, n))


def pin_current_thread(cpus: set[int] | None) -> None:
    if cpus and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, cpus)


def digest_tree(root: Path, probe_dir: Path, *, skip: frozenset[str] = frozenset(),
                cpus: set[int] | None = None,
                stop: threading.Event | None = None) -> dict[str, dict]:
    """{relative path: {"sha256", "key"} or {"error"}} for every file under root.

    Pins the calling thread to `cpus` first, so the hashing pool runs there.
    Raises RuntimeError if the barrier fails or `stop` is set, because a
    partial record would read as "file appeared after exit" downstream.
    """
    pin_current_thread(cpus)
    keys: dict[str, list[int]] = {}
    records: dict[str, dict] = {}
    for f in sorted(root.rglob("*")):
        rel = str(f.relative_to(root))
        if rel in skip or not f.is_file():
            continue
        try:
            keys[rel] = stat_key(f.stat())
        except OSError as exc:
            records[rel] = {"error": f"{type(exc).__name__}: {exc}"}
    if keys:
        ctime_barrier(probe_dir, max(k[4] for k in keys.values()),
                      {k[0] for k in keys.values()})

    def one(rel: str) -> tuple[str, dict]:
        if stop is not None and stop.is_set():
            return rel, {"error": "stopped"}
        try:
            return rel, {"sha256": hash_file(root / rel, keys[rel]), "key": keys[rel]}
        except (OSError, FileChanged) as exc:
            return rel, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=pool_size(cpus)) as pool:
        records.update(pool.map(one, sorted(keys)))
    if stop is not None and stop.is_set():
        raise RuntimeError("stopped before every output was digested")
    return records
