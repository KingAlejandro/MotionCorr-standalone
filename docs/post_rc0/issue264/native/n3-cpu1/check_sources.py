# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the CPU-subset scratch to the frozen sources (FROZEN-CPU1.md) before any build. Exit 1 on any mismatch."""
import hashlib, os, re, subprocess, sys
from pathlib import Path

S = Path(os.environ['G_SCR']); SHA = os.environ['G_SHA']
BASE = '3691374061f782bc84531fd1c79d017ddcb5a7c2'
EXPECT = {  # tree: (HEAD, diff_sha256, runner sha256, helper sha256); identical to the iteration-1 SOURCES.txt
    'src-cand': (SHA, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
                 '439041e3ece1dadfb1af06f2b00f804fabe4b0f5ec564572113491b14aa1280b', '02d8f5c1c45d2f2e9637b44e6be67089e8abff0f863c761fc29294168f44c146'),
    'src-base': (BASE, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
                 '8a3a1ad80edebc6959abbb80d118a0a358f703ff5041a0ade4995cbc2307d903', 'absent'),
    'src-ov-base': (BASE, '4b01e2607e1ffc86a719ccbf68afbfe5789f2a5b026efe6921eeed62af7d8316',
                    '70fc2de003eac07b958e0a3acafe0d87674fd9139d69cb1c9bba17aa14dc2ef1', 'absent'),
    'src-ov-cand': (SHA, '26274cd38b2ab2026ad5fd3ebab8ecd5fce2a6210aa8fef035e78eb6f4aa2de0',
                    '554237935c6004876583817043e9cae104d1b8169a20ea00079c2c544bf6ed75', '02d8f5c1c45d2f2e9637b44e6be67089e8abff0f863c761fc29294168f44c146'),
    'src-ov-mut': (SHA, '74b983bccff71b062ca535e057bb1d3e3cad2e9dfb44bb503bfc902304c485b9',
                   '554237935c6004876583817043e9cae104d1b8169a20ea00079c2c544bf6ed75', 'd531871fa4a34986d375ac3f79053490cd8eb6eb512bb3d642d15955add1e347'),
}
FILES = {'docs/post_rc0/issue264/native/n3-iter2/predictions_iter2.json': '6ff11cb5145f3c9f3f0c6380de26b27913eb9da7ccb6652a783c777b205c859e',
         'docs/post_rc0/issue264/native/n3_observation_overlay.patch': 'f82196ac80349028d6921f53dc2d3a36de998d6c7e58c91deadb197a917e4249',
         'docs/post_rc0/issue264/native/tools/n3.py': '68dcf2927590ee25642f0211b4633f337cd802a44f5d0ba73e319be7a977ba3f',
         'docs/post_rc0/issue264/native/tools/runlib.py': 'faa27bfa1e1f463b154e414676ffd578d9348728531baab9883ca7dfaaae5454',
         'docs/post_rc0/issue264/native/tools/build.sh': 'e51a7cee05b8909aaf88808d3f38b2cad156bf7b04d180a2d5e390fcedb7b664'}
problems = []
got = {}
for line in (S / 'SOURCES.txt').read_text().splitlines():
    m = re.match(r'(\S+) HEAD=(\S+) diff_sha256=(\S+) status_lines=\S+ runner=(\S+) helper=(\S+)', line)
    if m: got[m.group(1)] = m.groups()[1:]
for tree, want in EXPECT.items():
    if got.get(tree) != want: problems.append(f'{tree}: {got.get(tree)} != {want}')
git = lambda *a: subprocess.run(['git', '-C', str(S / 'src-cand'), *a], capture_output=True, text=True)
for ref, paths in (('52affe31f0299723faf6966d14e7516ae8e5e9bc', ['src', 'tests', 'tools', 'CMakeLists.txt']),
                   ('4b0e4e736884777ca738c7865a37876a5e9b9e86', ['src'])):
    if git('diff', '--quiet', ref, 'HEAD', '--', *paths).returncode != 0: problems.append(f'src-cand differs from {ref[:8]} in {paths}')
for rel, want in FILES.items():
    h = hashlib.sha256((S / 'src-cand' / rel).read_bytes()).hexdigest()
    print(rel, h)
    if h != want: problems.append(f'{rel} {h} != {want}')
print('sources', 'PASS' if not problems else 'FAIL', problems)
sys.exit(0 if not problems else 1)
