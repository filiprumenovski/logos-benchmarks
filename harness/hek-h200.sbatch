#!/bin/bash
#SBATCH -J showcase-hek-h200
#SBATCH -o $RUN_ROOT/logs/b2-hek-%j.log
#SBATCH -p reqp
#SBATCH -q requeue
#SBATCH --gres=gpu:nvidia_h200:1
#SBATCH -c 32
#SBATCH --mem=160G
#SBATCH -t 01:30:00
# Bench 2: PXD001468 (Chick 2015 HEK293), all 24 RAWs (79,698,414,833 bytes) in /dev/shm, one process, open
# search [-500,500] Da localized cascade, pooled in-process learner (hek293-rerun HA-C, db473f8):
#   recorded 12.13 s median of 3 on one H200 NVL (msa2) / 20.30 s on RTX PRO 4000 (ymh3, 1d6af8f);
#   132,592 sequences / 688,428 PSMs pooled 1%; entrapment arm 128,061 Nt / 664 Ne, FDP 1.03% (17.40 s H200).
# Needs prep-db.sbatch first ($R/db/hek). /dev/shm holds ~80 GB here: --mem 128G covers it plus ~6 GB RSS.
BENCH=hek
source $RUN_ROOT/lib/common.sh
BIN=$R/bin-79eeea50/logos; need 47068225e4a0d61e4f52c93e980581a5d91ede7e32c437b6bee75fd60155d89e $BIN; sha256sum $BIN >> $O/binaries.sha256
C=$R/configs; SRC=$HOME/bench-picks/case07/PXD001468
[ -f $R/db/hek/entrap_ensembl78.fasta ] || { echo "run prep-db.sbatch first"; exit 1; }
stage db $R/db/hek/ensembl78_crap_maxquant.fasta $R/db/hek/entrap_ensembl78.fasta
need a3306c817c823f33e81680a3e6279e2d6173d54990e52795e42093e3857d64e8 $W/db/ensembl78_crap_maxquant.fasta
need 7ea97dd22556d47fc6618765197976cf6cf9de42a548e7da52d7bbd7174b19e4 $W/db/entrap_ensembl78.fasta
stage raw $(ls $SRC/*.raw)
[ "$(stat -c %s $W/raw/*.raw | awk '{s+=$1} END{print s}')" = 79698414833 ] || { stamp "RAW byte total != 79,698,414,833"; exit 3; }
hash_inputs
E=$W/db/entrap_ensembl78.fasta; RE=1.0024981818613863
# Warm-up (untimed): device context, census of the RAM FASTA, page cache.
logos warm $C/hek-open.json --no-tsv --learn @O/learn --learn-pooled
# Target arm x3 and entrapment arm x3, interleaved (T E / E T / T E). Commands are the recorded ones.
for rep in 1 2 3; do
  t() { logos T-$rep $C/hek-open.json --out @O/out.tsv --learn @O/learn --learn-pooled; }
  e() { logos E-$rep $C/hek-open.json --no-tsv --entrapment $E --learn @O/learn --learn-pooled --entrapment-ratio $RE; }
  if [ $rep = 2 ]; then e; t; else t; e; fi
  if [ $rep -gt 1 ]; then rm -rf $W/out/T-$rep $W/out/E-$rep; fi
done
(cd $O && cat T-*/tsv.sha256 | awk '{print $1}' | sort | uniq -c) > $O/tsv-identity.txt
stamp "B2 DONE $(cat $O/tsv-identity.txt | tr '\n' ' ')"
