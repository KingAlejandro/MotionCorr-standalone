#!/bin/bash
# Runs under: flock /tmp/motioncorr-bench.lock taskset -c 96-103
# Replays the worker header logfile.pdf build (CPlot2D.cpp command, base run w0 inputs).
cd /home/alex/mc-wpdf-20261013; mkdir -p gs-replay
date -Is; gs --version
for i in 1 2 3 4 5 6; do
  /usr/bin/time -f "gs_wall_s=%e" sh -c "gs -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -dSAFER -dDEVICEWIDTHPOINTS=800 -dDEVICEHEIGHTPOINTS=800 -sOutputFile=gs-replay/logfile.pdf @runs/base/workers/w0/logfile.pdf.lst > /dev/null"
done
