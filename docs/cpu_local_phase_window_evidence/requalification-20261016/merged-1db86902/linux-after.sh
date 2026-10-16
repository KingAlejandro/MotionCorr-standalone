#!/bin/bash
set -eu
cd /home/ubuntu/fix183-20261016
export PATH="$HOME/.mc-venv/bin:$PATH" OMP_NUM_THREADS=6 OMP_THREAD_LIMIT=6
bash restore-metadata.sh > logs/metadata-pinned.log 2>&1
echo $? > logs/metadata-pinned.status
bash linux-builds.sh
~/.mc-venv/bin/python3 candidate/test-data/generate_synthetic_fixture.py --profile standard --outdir data > logs/synthetic-generate.log 2>&1
echo $? > logs/synthetic-generate.status
~/.mc-venv/bin/python3 exact.py > logs/exact-driver.log 2>&1
echo $? > logs/exact-driver.status
~/.mc-venv/bin/python3 linux-mutants.py > logs/mutants-driver.log 2>&1
echo $? > logs/mutants-driver.status
sha256sum candidate/build-release/{motioncorr,cpu_patch_phase_window} candidate/build-debug/{motioncorr,cpu_patch_phase_window} base-178/build/motioncorr > logs/restored-binary-sha256.txt
echo complete > logs/all.done
