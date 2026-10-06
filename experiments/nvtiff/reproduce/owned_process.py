#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Acceptance-only checked PID/birth cleanup, including observed reparenting."""
import os
from pathlib import Path
import signal
import subprocess
import time
from process_ownership import ProcessOwnership


def signal_owned(ownership, group, signum, send=os.killpg):
    if group == os.getpgrp():
        raise RuntimeError('Refusing acceptance controller own group')
    # Immediately re-read original/observed PID births before EVERY signal.
    # No cached numeric PGID or old Popen object authorizes this operation.
    if ownership.errors or not ownership.verified_group(group):
        raise RuntimeError('Refusing signal: PID/birth group ownership unverifiable')
    current = ownership.table.records(ownership.identities)
    live = [r for r in current.values() if r['pgid'] == group and r['state'] not in ('Z', 'X')]
    verified = {r['pid']: r['start'] for r in ownership.known_live()}
    if not live or any(verified.get(r['pid']) != r['start'] for r in live):
        raise RuntimeError('Refusing signal: group contains unverified/recycled identities')
    try:
        send(group, signum)
    except ProcessLookupError:
        pass


def cleanup(proc, ownership, grace=3.0):
    ownership.refresh()
    live = ownership.known_live()
    for group in sorted({r['pgid'] for r in live}):
        signal_owned(ownership, group, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while ownership.known_live() and time.monotonic() < deadline:
        proc.poll()
        time.sleep(.025)
    ownership.refresh()
    for group in sorted({r['pgid'] for r in ownership.known_live()}):
        signal_owned(ownership, group, signal.SIGKILL)
    if proc.poll() is None:
        proc.wait(timeout=10)
    deadline = time.monotonic() + 5
    while ownership.known_live() and time.monotonic() < deadline:
        time.sleep(.025)
    if ownership.errors or ownership.known_live():
        raise RuntimeError('Owned PID/birth cleanup incomplete or observation failed')


def run(command, log, cwd=None, timeout=300):
    ownership = ProcessOwnership(interval=.01)
    record = {'command': list(map(str, command)), 'cwd': str(cwd) if cwd else None}
    with Path(log).open('w') as output:
        proc = subprocess.Popen(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        record.update(pid=proc.pid, pgid=proc.pid)
        ownership.watch(proc.pid)
        record['original_start'] = ownership.identities[proc.pid]
        try:
            record.update(proc_stat=(Path('/proc') / str(proc.pid) / 'stat').read_text(), status=(Path('/proc') / str(proc.pid) / 'status').read_text(), executable=os.readlink('/proc/%d/exe' % proc.pid))
        except OSError:
            record['proc_snapshot'] = 'unavailable; PID birth remains recorded'
        ownership.start()
        try:
            timedout = False
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timedout = True; code = None
            ownership.refresh()
            survivors = ownership.known_live()
            group_members = [r for r in ownership.table.records(ownership.identities).values()
                             if r['pgid'] == proc.pid and r['state'] not in ('Z', 'X')]
            known = {r['pid']: r['start'] for r in survivors}
            unverified = [r for r in group_members if known.get(r['pid']) != r['start']]
            record.update(returncode=code, timeout=timedout, unexpected_live_descendants=survivors,
                          unverified_original_group_members=unverified)
            if unverified:
                # A live numeric group with no identity proof is a failed row,
                # never permission to signal a possibly recycled group.
                raise RuntimeError('Original group has unverified/recycled members: ' + str(record))
            if timedout or survivors:
                cleanup(proc, ownership)
            record['final_live_owned'] = ownership.known_live()
            record['ownership_errors'] = list(ownership.errors)
            record['observed_pid_births'] = dict(ownership.identities)
            if timedout or survivors or record['final_live_owned'] or ownership.errors:
                raise RuntimeError('Acceptance child timeout/unexpected owned descendants: ' + str(record))
            return code, Path(log).read_text(), record
        finally:
            ownership.stop(); ownership.join(timeout=10)
