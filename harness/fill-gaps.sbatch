#!/bin/bash
#SBATCH -J bench-fill-gaps
#SBATCH -o $RUN_ROOT/logs/fill-gaps-%j.log
#SBATCH -p reqp
#SBATCH -q requeue
#SBATCH -c 22
#SBATCH --mem=64G
#SBATCH -t 01:00:00
# Counts the report quotes that no current-build run held: LOGOS open + calibration + LDA on the target
# database alone, and Sage open search with the entrapment database. Also regenerates entrap_human.fasta
# with databases/build_entrap.py and checks its SHA-256 against the database manifest.
BENCH=fill-gaps
source $RUN_ROOT/lib/common.sh
set +e
EV=$R/eval; RES=$R/results; C=$R/configs-c22; E=$RES/entrap-arms/40928398
BIN=$R/bin-79eeea50/logos
need 47068225e4a0d61e4f52c93e980581a5d91ede7e32c437b6bee75fd60155d89e $BIN
SAGE=$HOME/Tools/sage/sage-v0.14.7-x86_64-unknown-linux-gnu/sage
need d3820543a31bfa2a556e04f91719204ce0ac6f34dcca6670314a13df87064625 $SAGE
sha256sum $SAGE $BIN $EV/*.py >> $O/binaries.sha256
stage in $HOME/bench-picks/1-bakeoff/PXD028735/LFQ_Orbitrap_DDA_Human_01.raw $HOME/bench-picks/target_human_contam.fasta \
  $HOME/bench-picks/mzml/LFQ_Orbitrap_DDA_Human_01.mzML $SCRATCH/dda-pool-20261024/work/entrap_human.fasta
cat $W/in/target_human_contam.fasta $W/in/entrap_human.fasta > $W/in/target_entrap_human.fasta
hash_inputs
R_LFQ=1.060595818801411
python3 -I $EV/build_entrap.py $W/in/target_human_contam.fasta $T/entrap_rebuilt.fasta 20260922 > $O/build_entrap.json 2>&1
stamp "entrap_human rebuilt: $(sha256sum $T/entrap_rebuilt.fasta | cut -c1-64) (manifest 932aba3a84e0954919b5a0a48430434deab3c78c09dfdbaa52be927f9a2cd6d3)"
cfg() { mkdir -p $O/cfg; python3 -I - "$1" "$W" "${3:-}" > $O/cfg/$2.json <<'PY'
import json, re, sys
src, w, fasta = sys.argv[1:4]
d = json.loads(re.sub(r"/dev/shm/showcase-user/[^/\"]+/(?:[^/\"]+/)*([^/\"]+)", lambda m: f"{w}/in/{m.group(1)}", open(src).read()))
if fasta:
    d["database"]["fasta"] = f"{w}/in/{fasta}"
print(json.dumps(d, indent=1))
PY
}
cfg $E/cfg/open-cal-lda.json open-cal-lda; cfg $C/sage-open.json sage-open-E target_entrap_human.fasta
for rep in 1 2 3; do logos open-cal-lda-$rep $O/cfg/open-cal-lda.json --backend cpu --no-tsv --learn @O/learn --entrapment-ratio 1; done
L=$O/sage-open-E D=$W/out/sage-open-E; mkdir -p $L $D
/usr/bin/time -v -o $L/time.txt $AP exec --bind /wsu $SIF $SAGE $O/cfg/sage-open-E.json -o $D --disable-telemetry-i-dont-want-to-improve-sage > $L/sage.log 2>&1
sha256sum $D/results.sage.tsv | cut -c1-64 > $L/tsv.sha256
python3 -I $EV/sage_to_pin.py $D/results.sage.tsv $D/cnt > $L/convert.log 2>&1
$AP exec --bind /wsu $SIF $CI $D/cnt --out $L/sage.ids.json --no-lists --entrap $R_LFQ --entrap-out $L/sage.entrap.json > $L/count-ids.log 2>&1
python3 -I $EV/count.py $D/cnt --entrap $R_LFQ > $L/count.py.json 2> $L/count.py.err
stamp "sage-open-E $(wall $L/time.txt) | $(python3 -c "import json;e=json.load(open('$L/count.py.json'))['entrapment']['expmass']['seqlvl'];print('seqlvl',e)")"
stamp "FILL-GAPS DONE"
