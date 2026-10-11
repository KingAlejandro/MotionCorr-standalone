#!/bin/bash
# keep report.md compare.json provenance.json identity.json and trace timelines; delete the rest
set -u
name=$1; R=/home/alex/mc-rc; W=$R/camp/$name; E=$R/evidence/$name
mkdir -p $E
cp $W/report.md $W/compare.json $W/provenance.json $W/identity.json $E/
for t in $W/trace/*/p0*/timeline.json; do a=$(basename $(dirname $(dirname $t))); p=$(basename $(dirname $t)); cp $t $E/timeline_${a}_${p}.json; done
gzip -9 -f $E/timeline_*.json
rm -rf $W
echo "pruned $name: $(du -sh $E | cut -f1)" >> $R/camp/status.txt
