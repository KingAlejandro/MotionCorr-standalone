#!/usr/bin/env python3
"""Original PID/birth identities and observed descendants for checked cleanup.

Linux uses /proc start ticks; macOS uses libproc birth seconds/microseconds.
Unavailable identity evidence is an error, never permission to signal by name
or historical PGID. Children born and exited between polls cannot be recovered.
"""
# SPDX-License-Identifier: GPL-2.0-or-later
# Validation-only observer derived from current main, with vanished-procfs ESRCH handling.
# Production source is unchanged by this external harness repair.
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
            # Linux procfs can return ESRCH when a process exits after open.
            # This means the process is gone; other read errors still refuse.
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
        return any(r['pgid'] == pgid and r['state'] not in ('Z', 'X')
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

    def watch(self, pid: int):
        record = self.table.read(pid)
        if record is None:
            raise RuntimeError(f'Original launched PID {pid} birth identity unavailable')
        with self._lock:
            self.identities[pid] = record['start']

    def refresh(self):
        with self._lock:
            known = dict(self.identities)
        records = self.table.records(known)
        owned = {pid for pid, r in records.items() if known.get(pid) == r['start']}
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
            if record and record['start'] == start and record['state'] not in ('Z', 'X'):
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
