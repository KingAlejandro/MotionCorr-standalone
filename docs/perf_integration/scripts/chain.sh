#!/bin/bash
R=/home/alex/mc-rc; cd $R
until grep -q "rc_vs_dfca087 rc=" camp/status.txt; do sleep 20; done
./prune.sh rc_vs_dfca087
for v in noA noB noC; do
  ./campaign.sh loo_$v $v $R/build-$v/motioncorr $R/src-$v rc $R/build-rc/motioncorr $R/src-rc
  ./prune.sh loo_$v
done
echo CHAIN_DONE >> camp/status.txt
