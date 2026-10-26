#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Request handling for the native CCF DC conditioning hooks, end to end.

Runs in every build. A default build must refuse any request for the hooks
(MC_EXPERIMENT_CCF_DC_ARM other than none, MC_EXPERIMENT_CCF_DC_REPORT,
MC_DIAG_MODEL_OUT) instead of ignoring it, and arm=none must equal unset. An
experiment build (--experiment) must in addition refuse the --use_motioncor2
route, an existing report, and a multi-movie model tap, and must write a
witness whose counts select exactly the requested stage. Every refusal must
happen before any output is created. Device-free: no --gpu is passed, so the
refusals are shown to precede any device query only by the CPU-build route;
tests/experiment_ccf_dc_stage.cpp covers the CUDA call sites.
"""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from test_hotpixel_rng_determinism import read_mrc_pixels, write_movie, write_star


def invoke(binary, work, star, out, env_extra, extra=()):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('MC_EXPERIMENT', 'MC_DIAG'))}
    env.update(env_extra)
    args = [str(binary), '--i', str(star), '--o', str(out), '--use_own', '--j', '1',
            '--angpix', '1.0', '--patch_x', '1', '--patch_y', '1', '--seed', '1', '--skip_logfile', *extra]
    return subprocess.run(args, cwd=work, text=True, capture_output=True, timeout=300, env=env)


def refused(result, out, needle):
    assert result.returncode != 0, 'request was accepted: ' + result.stdout + result.stderr
    assert needle in result.stdout + result.stderr, (needle, result.stdout + result.stderr)
    assert not out.exists() or not any(out.rglob('*.mrc')), 'a refusal must precede every output'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', required=True)
    ap.add_argument('--experiment', action='store_true', help='binary built with -DMC_EXPERIMENT_CCF_DC=ON')
    ap.add_argument('--iso', action='store_true', help='test-only isotropic build; the witness must say so')
    opts = ap.parse_args()
    binary = Path(opts.binary).resolve()
    with tempfile.TemporaryDirectory() as t:
        work = Path(t)
        for name, seed in (('a', 11), ('b', 12)):
            write_movie(work / (name + '.mrc'), seed, None, [])
        write_star(work / 'one.star', ['a.mrc'])
        write_star(work / 'two.star', ['a.mrc', 'b.mrc'])
        one = work / 'one.star'

        base = invoke(binary, work, one, work / 'unset', {})
        assert base.returncode == 0, base.stdout + base.stderr
        none = invoke(binary, work, one, work / 'none', {'MC_EXPERIMENT_CCF_DC_ARM': 'none'})
        assert none.returncode == 0, none.stdout + none.stderr
        assert read_mrc_pixels(work / 'unset/a.mrc') == read_mrc_pixels(work / 'none/a.mrc'), 'none must equal unset'
        def console(r, out):  # the output directory is the only intended difference
            return (r.stdout + r.stderr).replace(str(out), 'OUT')
        assert console(base, work / 'unset') == console(none, work / 'none'), 'none must not change the console'

        refused(invoke(binary, work, one, work / 'bad', {'MC_EXPERIMENT_CCF_DC_ARM': 'bogus'}),
                work / 'bad', 'must be none|global|local|both')
        refused(invoke(binary, work, one, work / 'empty', {'MC_EXPERIMENT_CCF_DC_ARM': ''}),
                work / 'empty', 'must be none|global|local|both')
        if not opts.experiment:
            for label, env in (('arm', {'MC_EXPERIMENT_CCF_DC_ARM': 'both'}),
                               ('report', {'MC_EXPERIMENT_CCF_DC_REPORT': str(work / 'w.json')}),
                               ('tap', {'MC_DIAG_MODEL_OUT': str(work / 'tap.json')})):
                refused(invoke(binary, work, one, work / label, env), work / label, 'built without -DMC_EXPERIMENT_CCF_DC=ON')
            assert not (work / 'w.json').exists() and not (work / 'tap.json').exists()
            print('default build: PASS')
            return

        # --- experiment build ---
        env = {k: v for k, v in os.environ.items() if not k.startswith(('MC_EXPERIMENT', 'MC_DIAG'))}
        env['MC_EXPERIMENT_CCF_DC_ARM'] = 'global'
        r = subprocess.run([str(binary), '--i', str(one), '--o', str(work / 'm2'), '--use_motioncor2', '--angpix', '1.0',
                            '--skip_logfile'], cwd=work, text=True, capture_output=True, env=env)
        refused(r, work / 'm2', 'apply only to --use_own')

        # Witness: the arm selects exactly its stage; nothing reaches the console.
        counts = {}
        for arm in ('none', 'global', 'local', 'both'):
            rep = work / f'rep_{arm}.json'
            r = invoke(binary, work, one, work / f'arm_{arm}',
                       {'MC_EXPERIMENT_CCF_DC_ARM': arm, 'MC_EXPERIMENT_CCF_DC_REPORT': str(rep)},
                       ['--patch_x', '3', '--patch_y', '3'])
            assert r.returncode == 0, r.stdout + r.stderr
            assert 'MC_EXPERIMENT_CCF_DC' not in r.stdout + r.stderr, 'the witness must not touch the console'
            w = json.loads(rep.read_text())
            assert w['status'] == 'atexit' and w['arm'] == arm, w   # atexit != producer success: rc is checked above
            assert w['test_only_isotropic_global_weight'] is opts.iso, (w, 'binary identity differs from the build the test was told about')
            cpu = w['sites']['cpu']
            counts[arm] = cpu
            assert cpu['global']['frames_eligible'] > 0 and cpu['local']['frames_eligible'] > 0, cpu
            for stage in ('global', 'local'):
                sel = arm in ('both', stage)
                c = cpu[stage]
                assert c['frames_zeroed'] == (c['frames_eligible'] if sel else 0), (arm, stage, c)
                assert c['calls_zeroed'] == (c['calls_eligible'] if sel else 0), (arm, stage, c)
            for site in ('cuda_single', 'cuda_batched'):
                assert all(v == 0 for st in w['sites'][site].values() for v in st.values()), 'CPU run touched a CUDA site'
        base3 = invoke(binary, work, one, work / 'base3', {}, ['--patch_x', '3', '--patch_y', '3'])
        assert read_mrc_pixels(work / 'base3/a.mrc') == read_mrc_pixels(work / 'arm_none/a.mrc'), 'none must equal the unconditioned run'
        # An existing report is never overwritten.
        keep = work / 'keep.json'
        keep.write_text('retained\n')
        refused(invoke(binary, work, one, work / 'k', {'MC_EXPERIMENT_CCF_DC_ARM': 'both', 'MC_EXPERIMENT_CCF_DC_REPORT': str(keep)}),
                work / 'k', 'cannot be created exclusively')
        assert keep.read_text() == 'retained\n'

        # An unwritable or empty report/tap path is refused before any pixel.
        refused(invoke(binary, work, one, work / 'rm', {'MC_EXPERIMENT_CCF_DC_REPORT': str(work / 'nodir/w.json')}),
                work / 'rm', 'cannot be created exclusively')
        refused(invoke(binary, work, one, work / 'tm', {'MC_DIAG_MODEL_OUT': str(work / 'nodir/tap.json')}),
                work / 'tm', 'cannot be created exclusively')
        refused(invoke(binary, work, one, work / 'te', {'MC_DIAG_MODEL_OUT': ''}), work / 'te', 'is empty')

        # Runtime-model tap: one movie, created exclusively.
        refused(invoke(binary, work, work / 'two.star', work / 't2', {'MC_DIAG_MODEL_OUT': str(work / 'tap2.json')}),
                work / 't2', 'exactly one movie per process')
        assert not (work / 'tap2.json').exists(), 'the tap file must not be created for a multi-movie run'
        tap = work / 'tap.json'
        r = invoke(binary, work, one, work / 't1', {'MC_DIAG_MODEL_OUT': str(tap)}, ['--patch_x', '3', '--patch_y', '3'])
        assert r.returncode == 0, r.stdout + r.stderr
        m = json.loads(tap.read_text())
        assert len(m['global']) == 7 and len(m['coeff_x']) == 18 and len(m['coeff_y']) == 18 and 'local_enabled' in m, m.keys()
        before = tap.read_text()
        refused(invoke(binary, work, one, work / 't3', {'MC_DIAG_MODEL_OUT': str(tap)}), work / 't3', 'already exists')
        assert tap.read_text() == before
        print('experiment build: PASS')


if __name__ == '__main__':
    main()
