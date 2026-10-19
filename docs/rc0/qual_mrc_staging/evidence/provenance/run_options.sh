#!/bin/bash
export MC_BIN=/mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/build/cuda-nvcomp-1db86902/motioncorr TMPDIR=/mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/synth
PY=/home/alex/mc-env/bin/python3
S=/mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/src/docs/rc0/qual_mrc_staging
$PY -I $S/synth_mrc_matrix.py --binary /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/gpu3run.sh --gpu 0 --work /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/synth/full --out /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/synth/cuda-options.json --section options > /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/logs/cuda-options.log 2>&1
run() { tag=$1; shift; $PY -I $S/real_data_identity.py --binary /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/gpu3run.sh --gpu 0 --inputs /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/inputs --work /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/runs/opts --out /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/runs/opts_$tag.json --families e10216 --tag $tag --rss "$@" >> /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/logs/opts.log 2>&1; }
run baseline_rss --configs G
run late_bin2 --configs G,L --extra '--no_early_binning --bin_factor 2'
run early_bin2 --configs G,L --extra '--bin_factor 2' --expect-route float --pinned-compact
run early_bin2_explicit --configs G --extra '--early_binning --bin_factor 2' --expect-route float --pinned-compact
run noDW_evenodd --configs G,L --extra '--save_noDW --even_odd_split'
run ps_group4 --configs G,L --extra '--grouping_for_ps 4'
echo ALLDONE >> /mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/logs/opts.log
