"""Tiny synthetic products shared by the test baseline builder and the fake child (no MotionCorr, no real pixels)."""
import json
from pathlib import Path

WITNESS = ' EXPERIMENTAL local full-width weight: x_norm = 42, pnx = 42, nfx = 22'
LOCAL3 = ('noisy', 'affine', 'pedestal')


def local3(case):
    return case in LOCAL3


def star_text(case, arm):
    t = ('data_general\n\n_rlnMicrographMovieName  %s.mrcs\n\ndata_global_shift\n\nloop_\n_rlnMicrographFrameNumber\n_rlnMicrographShiftX\n_rlnMicrographShiftY\n'
         '1 0.0 0.0\n2 0.1 0.2\n3 0.2 0.3\n4 0.3 0.5\n5 0.4 0.6\n\ndata_local_shift\n\nloop_\n' % case)
    if arm == 'ON' and local3(case):
        t += '1 10 10 0.5 0.5\n'
    return t


def runtime_bytes(case, arm, ulp=False):
    g = [[0.0, 0.0], [0.1, 0.2], [0.2, 0.3], [0.3, 0.5], [0.4, 0.6]]
    if ulp:
        import math
        g[1][0] = math.nextafter(g[1][0], 1.0)
    cx = [0.0] * 18
    if arm == 'ON' and local3(case):
        cx[0] = 1e-3
    return json.dumps({'local_enabled': local3(case), 'global': g, 'coeff_x': cx, 'coeff_y': [0.0] * 18}).encode()


def log_text(case, arm, witness_delta=0):
    l3 = local3(case)
    t = 'Working on %s.mrcs with 2 thread(s).\n\nGlobal alignment:\n Iteration 1: RMSD = 0.31 px\n Iteration 2: RMSD = 0.12 px\n\nLocal alignments:\nPatches: X = %d Y = %d\n' % (case, 3 if l3 else 1, 3 if l3 else 1)
    if l3:
        n_wit = (9 if arm == 'ON' else 0) + witness_delta
        for i in range(9):
            t += 'Patch (%d, %d): %d / 9\n' % (i // 3 + 1, i % 3 + 1, i + 1)
            if i < n_wit:
                t += WITNESS + '\n'
            t += ' Iteration 1: RMSD = 0.40 px\n Iteration 2: RMSD = 0.20 px\n'
        for _ in range(max(0, n_wit - 9)):
            t += WITNESS + '\n'
    elif witness_delta > 0:
        t += WITNESS * 0 + (WITNESS + '\n') * witness_delta
    return t


def stdout_text(case, dc=True, g=(40, 40), l=None):
    l3 = local3(case)
    l = l if l is not None else ((360, 360) if l3 else (0, 0))
    out = []
    if dc:
        out.append('MC_EXPERIMENT_CCF_DC arm=both cpu.global=%d/%d cpu.local=%d/%d cuda_single.global=0/0 cuda_single.local=0/0 cuda_batched.global=0/0 cuda_batched.local=0/0' % (g + l))
    out.append('[coupled_peak] scope=global peaks=%d guard_fired=2 (not_negative_definite=1, offset_gt_1px=1)' % g[1])
    if l3:
        out += ['[coupled_peak] scope=patch peaks=%d guard_fired=0 (not_negative_definite=0, offset_gt_1px=0)' % (l[1] // 9)] * 9
    return '\n'.join(out) + '\n'


def write_output(out, case, arm, witness_delta=0, payload=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    R = str(out.resolve())
    mrc = bytes(range(256)) * 4 + (payload if payload is not None else (b'ON-PAYLOAD-LOCAL!' if (arm == 'ON' and local3(case)) else b'OFF-PAYLOAD-0000!'))[:16]
    files = {case + '.mrc': mrc, case + '.star': star_text(case, arm).encode(), case + '_shifts.eps': ('%%!PS root %s/%s_shifts.eps %s\n' % (R, case, case)).encode(),
             'corrected_micrographs.star': ('data_x\n_rlnMicrographName %s/%s.mrc\n' % (R, case)).encode(), 'logfile.pdf': b'%PDF-1.4 fake ' + case.encode(),
             'logfile.pdf.lst': ('lst ' + case + '\n').encode(), case + '.log': log_text(case, arm, witness_delta).encode()}
    for k in ('Early', 'Late', 'Total'):
        files['corrected_micrographs_all_rlnAccumMotion%s.eps' % k] = ('%%!PS %s/all%s.eps\n' % (R, k)).encode()
    for name, b in files.items():
        (out / name).write_bytes(b)
