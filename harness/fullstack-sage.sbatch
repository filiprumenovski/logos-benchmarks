#!/bin/bash
#SBATCH -J bench-fullstack-sage
#SBATCH -o $RUN_ROOT/logs/fullstack-sage-%j.log
#SBATCH -p reqp
#SBATCH -q requeue
#SBATCH --gres=gpu:nvidia_rtx_pro_4500_blackwell:1
#SBATCH -c 22
#SBATCH --mem=128G
#SBATCH -t 02:30:00
# LOGOS full stack against Sage 0.14.7 in one job on one node. Full stack: the search writes its PIN
# (LFQ: DDA+ co-isolation pool; Astral TMTpro: the A1 search), then logos-boost adds predicted-spectrum,
# retention-time and mixture features and rescores with the MLP (the recorded gboost recipe). Per
# dataset: 3 interleaved repeats of (LOGOS search + boost) and Sage default, one warm-up each, then one
# entrapment arm of each engine. Search and boost wall times are recorded separately.
BENCH=fullstack-sage
source $RUN_ROOT/lib/common.sh
set +e
EV=$R/eval; RES=$R/results; C=$R/configs-c22; E=$RES/entrap-arms/40928398
BIN=$R/bin-79eeea50/logos
need 47068225e4a0d61e4f52c93e980581a5d91ede7e32c437b6bee75fd60155d89e $BIN
SAGE=$HOME/Tools/sage/sage-v0.14.7-x86_64-unknown-linux-gnu/sage
need d3820543a31bfa2a556e04f91719204ce0ac6f34dcca6670314a13df87064625 $SAGE
sha256sum $SAGE $BIN $EV/*.py >> $O/binaries.sha256
stage in $HOME/bench-picks/1-bakeoff/PXD028735/LFQ_Orbitrap_DDA_Human_01.raw $HOME/bench-picks/target_human_contam.fasta \
  $HOME/bench-picks/mzml/LFQ_Orbitrap_DDA_Human_01.mzML $SCRATCH/dda-pool-20261024/work/entrap_human.fasta \
  $HOME/bench-data/orbiter/5-astral-tmt/PXD058160/az01263_02152024.raw $R/mzml/az01263_02152024.mzML \
  $SCRATCH/orbiter-astral-20261021/databases/mouse-entrapment.fasta
awk '/^>/{e=($0 ~ /^>entrap_/)} { if (!e) print > "'$W'/in/target.fasta" }' $W/in/mouse-entrapment.fasta
awk '/^>/{e=($0 ~ /^>entrap_/)} { if (e) print > "'$W'/in/entrap.fasta" }' $W/in/mouse-entrapment.fasta
hash_inputs
R_LFQ=1.060595818801411
R_AST=$(python3 -c "import json;print(json.loads(open('$E/r-astral.jsonl').read().splitlines()[0])['r'])")
cfg() { mkdir -p $O/cfg; python3 -I - "$1" "$W" > $O/cfg/$2.json <<'PY'
import json, re, sys
src, w = sys.argv[1:3]
print(json.dumps(json.loads(re.sub(r"/dev/shm/showcase-user/[^/\"]+/(?:[^/\"]+/)*([^/\"]+)", lambda m: f"{w}/in/{m.group(1)}", open(src).read())), indent=1))
PY
}
cfg $C/lfq-ddaplus-H.json lfq; cfg $C/astral-tmt-A1.json astral; cfg $E/cfg/astral.json astral-E
cfg $C/sage-default.json sage-lfq; cfg $C/sage-default-E.json sage-lfq-E
cfg $RES/astral-tmt/40902791/sage.json sage-astral; cfg $E/cfg/sage-astral-E.json sage-astral-E
ld() { cut -d' ' -f1-3 /proc/loadavg; }
# full TAG CONFIG INSTRUMENT [search args]: search (PIN kept), then boost; ENTRAP_R in the environment.
full() { local tag=$1 c=$2 inst=$3; shift 3; local l0=$(ld)
  logos $tag $O/cfg/$c.json --no-tsv --pin @O/pin --learn @O/learn "$@"
  boost $tag $tag $inst 30
  stamp "$tag load=[$l0 -> $(ld)]"; rm -rf $W/out/$tag $W/boost/$tag; }
sg() { local tag=$1 c=$2 r=${3:-}; local L=$O/$tag D=$W/out/$tag; rm -rf $D; mkdir -p $D $L; local l0=$(ld)
  /usr/bin/time -v -o $L/time.txt $AP exec --bind /wsu $SIF $SAGE $O/cfg/$c.json -o $D --disable-telemetry-i-dont-want-to-improve-sage > $L/sage.log 2>&1; local rc=$?
  sha256sum $D/results.sage.tsv | cut -c1-64 > $L/tsv.sha256
  python3 -I $EV/sage_to_pin.py $D/results.sage.tsv $D/cnt > $L/convert.log 2>&1
  $AP exec --bind /wsu $SIF $CI $D/cnt --out $L/sage.ids.json --no-lists ${r:+--entrap $r --entrap-out $L/entrap.json} > $L/count-ids.log 2>&1
  python3 -I $EV/count.py $D/cnt ${r:+--entrap $r} > $L/count.py.json 2> $L/count.py.err
  stamp "$tag rc=$rc $(wall $L/time.txt) load=[$l0 -> $(ld)] | $(python3 -c "import json;d=json.load(open('$L/count.py.json'));print('seq',d['sequences_q01'],'psm',d['psms_q01'])" 2>&1 | tail -1)"
  [ $rc = 0 ] || echo $tag >> $O/FAILED; rm -rf $D; }

export ENTRAP_R=$R_LFQ
full warm-lfq lfq QE --entrapment-ratio 1; sg warm-sage-lfq sage-lfq
for rep in 1 2 3; do
  if [ $rep = 2 ]; then full lfq-full-$rep lfq QE --entrapment-ratio 1; sg lfq-sage-$rep sage-lfq
  else sg lfq-sage-$rep sage-lfq; full lfq-full-$rep lfq QE --entrapment-ratio 1; fi
done
full lfq-full-E lfq QE --entrapment $W/in/entrap_human.fasta --entrapment-ratio $R_LFQ
sg lfq-sage-E sage-lfq-E $R_LFQ

export ENTRAP_R=$R_AST
full warm-astral astral ThermoTOF --entrapment-ratio 1; sg warm-sage-astral sage-astral
for rep in 1 2 3; do
  if [ $rep = 2 ]; then full astral-full-$rep astral ThermoTOF --entrapment-ratio 1; sg astral-sage-$rep sage-astral
  else sg astral-sage-$rep sage-astral; full astral-full-$rep astral ThermoTOF --entrapment-ratio 1; fi
done
full astral-full-E astral-E ThermoTOF --entrapment $W/in/entrap.fasta --entrapment-ratio $R_AST
sg astral-sage-E sage-astral-E $R_AST
stamp "FULLSTACK-SAGE DONE"
