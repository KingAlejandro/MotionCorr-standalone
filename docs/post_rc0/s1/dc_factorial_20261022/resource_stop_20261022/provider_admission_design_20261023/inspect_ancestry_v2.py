#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only, bounded own-ancestry inspection for an ownership DESIGN, not an admission runner.

No child process, jobs, signals, controller or test-suite launch. Read argv only for own-UID ancestors
and emit recognized mode words/public-ID comparisons; never retain argv or environment blocks.
All files/lease are confined to this new design directory; cap 16 MiB.
"""
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import time

D = Path(__file__).resolve().parent
ROOT = next(p for p in D.parents if (p / 'tools/multi_gpu/process_ownership.py').is_file())
CAP = 16 * 1024**2
MAX_ANCESTORS = 12
N = time.time_ns()
lease = open(D / '.inspection.lease', 'a')
fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
assert sum(p.stat().st_size for p in D.rglob('*') if p.is_file()) < CAP
space = shutil.disk_usage(D)
if space.free < CAP: raise SystemExit('insufficient free space for bounded design inspection')

spec = importlib.util.spec_from_file_location('frozen_process_table', ROOT / 'tools/multi_gpu/process_ownership.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
table = m.ProcessTable()
if not table.darwin: raise SystemExit('this inspection is specified for the current macOS host only')
lib = table.lib
lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
lib.proc_pidpath.restype = ctypes.c_int

# Layouts read from the installed SDK sys/proc_info.h; no experiment/test is compiled or run.
class Stat(ctypes.Structure):
    _fields_ = [('dev', ctypes.c_uint32), ('mode', ctypes.c_uint16), ('nlink', ctypes.c_uint16),
                ('ino', ctypes.c_uint64), ('uid', ctypes.c_uint32), ('gid', ctypes.c_uint32)]
    _fields_ += [(name, ctypes.c_int64) for name in ['atime','atimensec','mtime','mtimensec','ctime','ctimensec','birthtime','birthtimensec','size','blocks']]
    _fields_ += [('blksize', ctypes.c_int32), ('flags', ctypes.c_uint32), ('gen', ctypes.c_uint32), ('rdev', ctypes.c_uint32), ('qspare', ctypes.c_int64 * 2)]
class Vnode(ctypes.Structure):
    _fields_ = [('stat', Stat), ('type', ctypes.c_int), ('pad', ctypes.c_int), ('fsid', ctypes.c_int32 * 2)]
class VnodePath(ctypes.Structure):
    _fields_ = [('vi', Vnode), ('path', ctypes.c_char * 1024)]
class VnodePaths(ctypes.Structure):
    _fields_ = [('cwd', VnodePath), ('root', VnodePath)]

libc = ctypes.CDLL(None, use_errno=True)
libc.sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
libc.sysctl.restype = ctypes.c_int

def public_env():
    out = {}
    for key in ['CODEX_SESSION_ID','CODEX_THREAD_ID','CODEX_TOOL_CALL_ID']:
        v = os.environ.get(key)
        out[key] = v if v and re.fullmatch(r'[A-Za-z0-9:_-]{1,200}', v) else None
    return out

public = public_env()

def modes_and_id_matches(pid):
    # KERN_PROCARGS2 returns argv followed by environment. Parse exactly argc arguments, and never
    # parse, decode, retain or emit the trailing environment. Unknown arguments are discarded.
    mib = (ctypes.c_int * 3)(1, 49, pid)
    buf = ctypes.create_string_buffer(65536); size = ctypes.c_size_t(len(buf))
    if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
        return dict(available=False, errno=ctypes.get_errno())
    raw = buf.raw[:size.value]
    argc = int.from_bytes(raw[:4], sys.byteorder, signed=True)
    if not 0 <= argc <= 256: return dict(available=False, reason='argc outside bound')
    start = raw.find(b'\0', 4)
    if start < 0: return dict(available=False, reason='missing executable terminator')
    start += 1
    while start < len(raw) and raw[start] == 0: start += 1
    modes, matches = [], set()
    for _ in range(argc):
        end = raw.find(b'\0', start)
        if end < 0: return dict(available=False, reason='truncated argv')
        arg = raw[start:end]
        if arg in (b'app-server', b'exec', b'exec-server'): modes.append(arg.decode('ascii'))
        for key, val in public.items():
            if val and arg in [val.encode(), *[(flag + val).encode() for flag in ['--thread-id=','--session-id=','--resume=']]]:
                matches.add(key)
        start = end + 1
    return dict(available=True, recognized_modes=modes, exact_public_id_matches=sorted(matches), raw_argv_retained=False, environment_parsed=False)

rows = []
pid = os.getpid()
seen = set()
(D / f'preflight-{N}.json').write_text(json.dumps(dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),load=os.getloadavg(),free_bytes=space.free,cap_bytes=CAP,lease='private nonblocking inspection flock',command=[sys.executable,'-B',str(Path(__file__).resolve())]),indent=1)+'\n')
for _ in range(MAX_ANCESTORS):
    if pid <= 1 or pid in seen: break
    seen.add(pid)
    try: before = table.read(pid)
    except OSError as e:
        rows.append(dict(pid=pid, identity_unreadable=True, errno=e.errno)); break
    if not before: break
    info = table.info_type()
    n = lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    if n != ctypes.sizeof(info):
        rows.append(dict(pid=pid, identity_unreadable=True, errno=ctypes.get_errno())); break
    path = ctypes.create_string_buffer(4096)
    count = lib.proc_pidpath(pid, path, len(path))
    vnode = VnodePaths()
    cwd_n = lib.proc_pidinfo(pid, 9, 0, ctypes.byref(vnode), ctypes.sizeof(vnode))
    row = dict(pid=pid, ppid=before['ppid'], uid=info.uid, birth=before['start'], pgid=before['pgid'],
               executable=os.fsdecode(path.value) if count > 0 else None,
               cwd=os.fsdecode(vnode.cwd.path) if cwd_n == ctypes.sizeof(vnode) else None)
    if info.uid == os.getuid(): row['argv_public_projection'] = modes_and_id_matches(pid)
    else: row['argv_public_projection'] = dict(skipped='ancestor has another UID; argv not read')
    try: after = table.read(pid)
    except OSError: after = None
    row['birth_and_parent_stable'] = bool(after and after['start'] == before['start'] and after['ppid'] == before['ppid'])
    rows.append(row)
    if not row['birth_and_parent_stable']: break
    pid = before['ppid']

out = dict(schema='dc262-provider-design-observation/1', utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
    observation_id=N, host=socket.gethostname(), pid=os.getpid(), uid=os.getuid(),
    occupancy_scope='aggregate load and bounded own ancestry only; no unrelated process inventory/arguments',
    load=os.getloadavg(), logical_cpus=os.cpu_count(), free_bytes=space.free, cap_bytes=CAP,
    private_inspection_lease='nonblocking flock held through observation write; not a proposed controller lease',
    cwd=os.getcwd(), public_environment=public,
    relevant_environment_key_names=sorted(k for k in os.environ if k.startswith(('T3_','CODEX_','CHATGPT_','ACP_')) or k == 'PWD'),
    ancestry_bound=MAX_ANCESTORS, ancestry=rows,
    sdk_struct_sizes=dict(stat=ctypes.sizeof(Stat),vnode=ctypes.sizeof(Vnode),paths=ctypes.sizeof(VnodePaths)),
    sdk_header='/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/sys/proc_info.h',
    sdk_header_sha256=hashlib.sha256(Path('/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/sys/proc_info.h').read_bytes()).hexdigest(),
    inspector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    limits='observation only; env markers are inherited/self-assertable, no unique per-thread OS owner or cross-thread host exclusivity follows')
f = D / f'observation-{N}.json'
f.write_text(json.dumps(out,indent=1)+'\n')
assert sum(p.stat().st_size for p in D.rglob('*') if p.is_file()) < CAP
print(json.dumps(out,indent=1))
