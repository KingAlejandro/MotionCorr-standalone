#!/usr/bin/env python3
"""Sample simultaneous current RSS of explicitly owned roots and descendants.

RSS sums count shared mappings more than once, so the sampled maximum is an
upper bound on unique resident pages, and a lower bound on this summed metric's
true time peak. Children born and exited between polls cannot be recovered.
No process is signalled or admitted by executable name alone.
"""
from __future__ import annotations
import os
import threading
import time
from pathlib import Path


class OwnedTreeSampler(threading.Thread):
    def __init__(self, interval: float = 0.1, proc: Path = Path('/proc')):
        if interval <= 0:
            raise ValueError('RSS sampling interval must be positive')
        super().__init__(daemon=True)
        self.interval, self.proc = interval, proc
        self.roots: dict[int, int] = {}
        self.identities: dict[int, int] = {}
        self.samples: list[dict] = []
        self.errors: list[str] = []
        self.unavailable = None if proc.is_dir() else 'No /proc: owned tree RSS unavailable'
        self._finish = threading.Event()
        self._lock = threading.Lock()

    def stat(self, pid: int):
        raw = (self.proc / str(pid) / 'stat').read_text()
        f = raw.rsplit(')', 1)[1].split()
        return {'pid':pid, 'ppid':int(f[1]), 'pgid':int(f[2]),
                'start_ticks':int(f[19]), 'state':f[0]}

    def watch(self, pid: int) -> None:
        if self.unavailable:
            return
        try:
            start = self.stat(pid)['start_ticks']
        except (OSError, ValueError, IndexError) as exc:
            self.errors.append(f'Owned root {pid} identity unavailable: {exc}')
            return
        with self._lock:
            self.roots[pid] = start
            self.identities[pid] = start

    def snapshot(self) -> dict:
        records = {}
        with self._lock:
            known = dict(self.identities)
        unreadable = []
        for entry in self.proc.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                records[pid] = self.stat(pid)
            except (OSError, ValueError, IndexError) as exc:
                if pid in known and entry.exists():
                    unreadable.append(f"Owned PID {pid} identity unreadable: {exc}")
                # Process directories race with exit; ownership is never inferred
                # from an unreadable record. Root failures remain explicit above.
                continue
        with self._lock:
            known = dict(self.identities)
        owned = {pid for pid, rec in records.items()
                 if known.get(pid) == rec['start_ticks']}
        while True:
            children = {pid for pid, rec in records.items() if rec['ppid'] in owned}
            new = children - owned
            if not new:
                break
            owned |= new
        readings, problems = [], unreadable
        for pid in sorted(owned):
            rec = records[pid]
            try:
                exe = os.readlink(self.proc / str(pid) / 'exe')
                status = (self.proc / str(pid) / 'status').read_text()
                rss = next(int(line.split()[1]) for line in status.splitlines()
                           if line.startswith('VmRSS:'))
                if self.stat(pid)['start_ticks'] != rec['start_ticks']:
                    raise ValueError('PID identity changed during sampling')
                rec = dict(rec, executable=exe, rss_kib=rss)
                try:
                    rollup = (self.proc / str(pid) / 'smaps_rollup').read_text()
                    rec['pss_kib'] = next(int(line.split()[1]) for line in rollup.splitlines()
                                          if line.startswith('Pss:'))
                except (OSError, StopIteration, ValueError):
                    rec['pss_kib'] = None
                readings.append(rec)
            except (OSError, StopIteration, ValueError, IndexError) as exc:
                # A vanished/zombie member has no live resident allocation. If it
                # is still live and readable identity matches, retain an error;
                # missing readings cannot become a fabricated zero measurement.
                try:
                    live = self.stat(pid)
                    if live['start_ticks'] == rec['start_ticks'] and live['state'] != 'Z':
                        problems.append(f'Owned PID {pid} RSS unavailable: {exc}')
                except (OSError, ValueError, IndexError):
                    pass
        with self._lock:
            for pid in owned:
                self.identities[pid] = records[pid]['start_ticks']
        return {'monotonic_s':time.monotonic(), 'processes':readings,
                'rss_sum_kib':sum(r['rss_kib'] for r in readings) if not problems else None,
                'pss_sum_kib':sum(r['pss_kib'] for r in readings)
                              if readings and all(r['pss_kib'] is not None for r in readings) else None,
                'errors':problems}

    def run(self) -> None:
        if self.unavailable:
            return
        while not self._finish.is_set():
            try:
                sample = self.snapshot()
                self.samples.append(sample)
                self.errors.extend(sample['errors'])
            except Exception as exc:
                self.errors.append(f'RSS sampler failed: {type(exc).__name__}: {exc}')
                return
            self._finish.wait(self.interval)

    def known_live(self) -> list[dict]:
        """Identity-verified survivors for cleanup, including reparented children."""
        if self.unavailable:
            return []
        with self._lock:
            known=dict(self.identities)
        live=[]
        for pid,start in known.items():
            try:
                record=self.stat(pid)
            except FileNotFoundError:
                continue
            except (OSError,ValueError,IndexError) as exc:
                raise RuntimeError(f'Cannot verify owned PID {pid} cleanup: {exc}') from exc
            if record['start_ticks']==start and record['state']!='Z':live.append(record)
        return live

    def stop(self) -> None:
        self._finish.set()

    def report(self) -> dict:
        valid = [s['rss_sum_kib'] for s in self.samples
                 if s['rss_sum_kib'] is not None and s['processes']]
        return {'status':'UNAVAILABLE' if self.unavailable else 'INCOMPLETE' if self.errors else 'SAMPLED' if valid else 'NO_SAMPLES',
                'unavailable':self.unavailable, 'errors':self.errors,
                'interval_s':self.interval, 'units':'KiB',
                'peak_simultaneous_sum_rss_kib':max(valid) if valid else None,
                'note':'Current RSS summed at each observation, not summed VmHWM. '
                       'Shared pages are counted more than once. Sampled peak may miss '
                       'brief peaks/children born and exited between polls; PSS is optional. '
                       'Only exact PID/start roots and their observed descendants are owned.',
                'samples':self.samples}
