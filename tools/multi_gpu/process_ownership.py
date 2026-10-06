#!/usr/bin/env python3
"""Original PID/birth identities and observed descendants for checked cleanup.

Linux uses /proc start ticks; macOS uses libproc birth seconds/microseconds.
Unavailable identity evidence is an error, never permission to signal by name
or historical PGID. Linux launchers enable child-subreaper adoption before
starting workers, recovering surviving fast-reparented children for checked
cleanup. This is a process lifecycle contract, not a security containment boundary.
"""
from __future__ import annotations
import ctypes
import errno
import os
import sys
import threading
from pathlib import Path


class ProcessTable:
    def __init__(self, proc: Path = Path('/proc')):
        self.proc = proc
        self.darwin = sys.platform == 'darwin' and proc == Path('/proc')
        if self.darwin:
            # Layout/selector from the macOS SDK sys/proc_info.h proc_bsdinfo.
            class BsdInfo(ctypes.Structure):
                _fields_ = [(name, ctypes.c_uint32) for name in (
                    'flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid',
                    'ruid', 'rgid', 'svuid', 'svgid', 'reserved')]
                _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
                _fields_ += [(name, ctypes.c_uint32) for name in (
                    'nfiles', 'pgid', 'pjobc', 'tdev', 'tpgid')]
                _fields_ += [('nice', ctypes.c_int32), ('start_sec', ctypes.c_uint64),
                            ('start_usec', ctypes.c_uint64)]
            self.info_type = BsdInfo
            self.lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
            self.lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                             ctypes.c_void_p, ctypes.c_int]
            self.lib.proc_pidinfo.restype = ctypes.c_int
            self.lib.proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self.lib.proc_listallpids.restype = ctypes.c_int
        elif not proc.is_dir():
            raise RuntimeError('PID/birth identity unavailable: no /proc or libproc')

    def pids(self):
        if not self.darwin:
            return [int(p.name) for p in self.proc.iterdir() if p.name.isdigit()]
        count = self.lib.proc_listallpids(None, 0)
        if count <= 0:
            raise RuntimeError('libproc could not enumerate process identities')
        array = (ctypes.c_int * (count + 64))()
        actual = self.lib.proc_listallpids(array, ctypes.sizeof(array))
        if actual <= 0 or actual > len(array):
            raise RuntimeError('libproc process identity enumeration was incomplete')
        return [int(pid) for pid in array[:actual] if pid > 0]

    def read(self, pid: int):
        if self.darwin:
            info = self.info_type()
            ctypes.set_errno(0)
            size = self.lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
            if size != ctypes.sizeof(info):
                error = ctypes.get_errno()
                if error in (errno.ESRCH, errno.ENOENT):
                    return None
                raise OSError(error, f'Cannot read PID/birth identity for {pid}')
            if info.pid != pid or info.start_sec <= 0:
                raise RuntimeError(f'Invalid libproc identity for {pid}')
            return {'pid': pid, 'ppid': info.ppid, 'pgid': info.pgid,
                    'start': (info.start_sec, info.start_usec),
                    'state': 'Z' if info.status == 5 else 'R'}
        try:
            raw = (self.proc / str(pid) / 'stat').read_text()
        except (FileNotFoundError, ProcessLookupError):
            # Linux may report ESRCH after opening stat if the process exits
            # before its contents are read. This is disappearance, not an
            # unreadable live identity; permission/other errors still refuse.
            return None
        fields = raw.rsplit(')', 1)[1].split()
        if int(raw.split(' ', 1)[0]) != pid or int(fields[19]) <= 0:
            raise RuntimeError(f'Invalid /proc PID/birth identity for {pid}')
        return {'pid': pid, 'ppid': int(fields[1]), 'pgid': int(fields[2]),
                'start': int(fields[19]), 'state': fields[0]}

    def records(self, known=()):
        records = {}
        for pid in self.pids():
            try:
                record = self.read(pid)
            except (OSError, ValueError, IndexError):
                if pid in known:
                    raise RuntimeError(f'Cannot verify owned PID/birth identity {pid}')
                continue  # unrelated processes need not be readable
            if record is not None:
                records[pid] = record
        return records

    def group_live(self, pgid: int):
        return any(r['pgid'] == pgid and r['state'] != 'Z'
                   for r in self.records().values())


class ProcessOwnership(threading.Thread):
    def __init__(self, interval: float = 0.05, table=None):
        super().__init__(daemon=True)
        self.table = table if table is not None else ProcessTable()
        self.interval = interval
        self.identities = {}
        self.errors = []
        self._lock = threading.Lock()
        self._finish = threading.Event()
        self.adoption = False
        self.previous_subreaper = None
        self.preexisting_children = {}
        self.parent_pid = os.getpid()
        self.parent_group = os.getpgrp()
        self.parent_birth = None
        self.roots = {}
        self.mode = 'observed-descendants-only'

    @staticmethod
    def native_supported():
        return sys.platform == 'linux'

    def _child_pids(self):
        """Read our actual thread child lists; only proven exited threads vanish."""
        parent = self.table.read(self.parent_pid)
        if parent is None or (self.parent_birth is not None and parent['start'] != self.parent_birth):
            raise RuntimeError('Launcher PID/birth identity unavailable')
        tasks = list((Path('/proc') / str(self.parent_pid) / 'task').iterdir())
        if not tasks:
            raise RuntimeError('Launcher thread child inventory unavailable')
        children = set()
        for task in tasks:
            try:
                children.update(map(int, (task / 'children').read_text().split()))
            except (FileNotFoundError, ProcessLookupError):
                if self.table.read(int(task.name)) is not None:
                    raise RuntimeError('Live launcher thread child inventory unavailable')
        return children

    def activate(self, native_required=False):
        """Enable Linux orphan adoption before any worker or helper starts.

        Non-Linux polling remains available for portable simulated CPU controls,
        but cannot certify arbitrary native-worker descendant containment.
        """
        if sys.platform != 'linux':
            if native_required:
                raise RuntimeError('Native multi-GPU worker cleanup requires Linux child-subreaper support')
            return
        if self.table.proc != Path('/proc'):
            raise RuntimeError('Child-subreaper ownership requires the actual process table')
        # Refuse pre-existing live children: their later orphaned descendants
        # cannot be distinguished from worker descendants. Preserve them untouched.
        # Failure to read our own child inventory refuses before any worker starts.
        parent = self.table.read(self.parent_pid)
        if parent is None:
            raise RuntimeError('Launcher PID/birth identity unavailable')
        self.parent_birth = parent['start']
        children = self._child_pids()
        for pid in children:
            record = self.table.read(pid)
            if record:
                self.preexisting_children[pid] = record['start']
                if record['state'] != 'Z':
                    raise RuntimeError('Cannot isolate worker adoption with pre-existing live launcher children')
        lib = ctypes.CDLL(None, use_errno=True)
        lib.prctl.restype = ctypes.c_int
        old = ctypes.c_int()
        if lib.prctl(37, ctypes.byref(old), 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'Cannot read child-subreaper state')
        self.previous_subreaper = old.value
        if lib.prctl(36, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'Cannot establish child-subreaper ownership')
        self.adoption = True  # restoration is required even if readback fails
        current = ctypes.c_int()
        if lib.prctl(37, ctypes.byref(current), 0, 0, 0) != 0 or current.value != 1:
            raise RuntimeError('Child-subreaper readback failed; refusing worker launch')
        self.mode = 'linux-child-subreaper'

    def restore(self):
        """Restore process state only after checked owned cleanup and reaping."""
        if not self.adoption:
            return
        # Callers stop worker/helper creation and join their observer first.
        # Original roots must have exited; two immediate empty observations of
        # adopted/recorded descendants then support this quiescent cleanup scope.
        # They are not a security guarantee against arbitrary concurrent forks.
        for pid, birth in self.roots.items():
            record = self.table.read(pid)
            if record and record['start'] == birth and record['state'] != 'Z':
                raise RuntimeError('Cannot restore subreaper while an original worker remains live')
        for _ in range(2):
            self.refresh()
            if self.errors or self.known_live():
                raise RuntimeError('Cannot restore subreaper while owned children or errors remain')
        for pid, birth in list(self.identities.items()):
            record = self.table.read(pid)
            if record and record['start'] == birth and record['ppid'] == self.parent_pid:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass  # Popen already reaped an original worker
        lib = ctypes.CDLL(None, use_errno=True)
        if lib.prctl(36, self.previous_subreaper, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'Cannot restore child-subreaper state')
        current = ctypes.c_int()
        if lib.prctl(37, ctypes.byref(current), 0, 0, 0) != 0 or current.value != self.previous_subreaper:
            raise RuntimeError('Restored child-subreaper readback failed')
        self.adoption = False

    def watch(self, pid: int):
        record = self.table.read(pid)
        if record is None:
            raise RuntimeError(f'Original launched PID {pid} birth identity unavailable')
        with self._lock:
            self.identities[pid] = record['start']
            self.roots[pid] = record['start']

    def refresh(self):
        with self._lock:
            known = dict(self.identities)
        if self.adoption:
            # These are OUR direct children, including unsampled orphans. A
            # missing/invalid live birth cannot be silently dropped as unrelated.
            for pid in self._child_pids():
                record = self.table.read(pid)
                if record:
                    known.setdefault(pid, None)
        records = self.table.records(known)
        owned = {pid for pid, r in records.items() if known.get(pid) == r['start']}
        if self.adoption:
            for pid, record in records.items():
                # Orphans are now direct launcher children. Ordinary launcher
                # helpers retain our own group; pre-existing children are never
                # adopted as owned. A worker may setsid before orphaning, so its
                # original group cannot be used as the adoption criterion.
                if (record['ppid'] != self.parent_pid or
                    record['pgid'] == self.parent_group or
                    self.preexisting_children.get(pid) == record['start']):
                    continue
                child = self.table.read(pid)
                if (child and child['start'] == record['start'] and
                    child['ppid'] == self.parent_pid and
                    child['pgid'] != self.parent_group):
                    owned.add(pid)
        while True:
            added = set()
            for pid, record in records.items():
                parent = record['ppid']
                if pid in owned or parent not in owned:
                    continue
                # Bind both ends of the parent-child observation, excluding a
                # recycled parent or child during process-table collection.
                before = self.table.read(parent)
                child = self.table.read(pid)
                after = self.table.read(parent)
                if (before and child and after and
                    before['start'] == after['start'] == records[parent]['start'] and
                    child['start'] == record['start'] and child['ppid'] == parent):
                    added.add(pid)
            if not added:
                break
            owned |= added
        with self._lock:
            for pid in owned:
                self.identities[pid] = records[pid]['start']

    def known_live(self):
        with self._lock:
            known = dict(self.identities)
        live = []
        for pid, start in known.items():
            record = self.table.read(pid)
            if record and record['start'] == start and record['state'] != 'Z':
                live.append(record)
        return live

    def verified_group(self, pgid):
        # Called immediately before every TERM/KILL, even after an earlier check.
        self.refresh()
        return any(record['pgid'] == pgid for record in self.known_live())

    def run(self):
        while not self._finish.is_set():
            try:
                self.refresh()
            except Exception as exc:
                self.errors.append(f'Process ownership observer failed: {exc}')
                return
            self._finish.wait(self.interval)

    def stop(self):
        self._finish.set()
