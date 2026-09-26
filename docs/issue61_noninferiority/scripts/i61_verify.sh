#!/bin/bash
R=/home/alex/mc-issue61
echo "--- extracted particle stack digests (movie 00022); must all differ"
for a in cpu default allfftw ctrl_noise_f005 ctrl_envelope_b20; do
  f=$R/proj/$a/Extract61/Movies/20170629_00022_frameImage.mrcs
  printf "%-18s %s bytes=%s\n" "$a" "$(sha256sum $f | cut -c1-16)" "$(stat -c%s $f)"
done
echo "--- held22 metadata columns (coords, orientations, subset); must all be IDENTICAL"
for a in cpu default allfftw ctrl_noise_f005 ctrl_envelope_b20 ctrl_noise_f020; do
  printf "%-18s %s\n" "$a" "$(awk '{print $1,$2,$18,$19,$20,$21,$26}' $R/stars/$a/held22.star | sha256sum | cut -c1-16)"
done
echo "--- held22 particle counts"
for a in cpu default allfftw ctrl_noise_f005 ctrl_envelope_b20 ctrl_noise_f020; do
  printf "%-18s %s\n" "$a" "$(grep -c mrcs $R/stars/$a/held22.star)"
done
