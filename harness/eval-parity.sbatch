#!/bin/bash
#SBATCH -J bench-eval-parity
#SBATCH -o $RUN_ROOT/logs/eval-parity-%j.log
#SBATCH -p reqp
#SBATCH -q requeue
#SBATCH -c 22
#SBATCH --mem=96G
#SBATCH -t 02:00:00
# Proves the open counter (eval/count.py, eval/sage_to_pin.py) gives the integers behind every
# identification count in the report. Reruns, once each on CPU, the LOGOS and Sage arms whose counts
# the report quotes, keeping their outputs on disk, and checks:
#   1. each LOGOS learner ids.json / entrap.json equals the recorded one (LOGOS is deterministic);
#   2. eval/count.py on the PIN + learner scores equals the engine's counts;
#   3. eval/sage_to_pin.py + eval/count.py on Sage's results equals the recorded Sage counts.
BENCH=eval-parity
source $RUN_ROOT/lib/common.sh
set +e
EV=$R/eval; RES=$R/results; KEEP=$SCRATCH/eval-parity-$SLURM_JOB_ID; mkdir -p $KEEP
SAGE=$HOME/Tools/sage/sage-v0.14.7-x86_64-unknown-linux-gnu/sage
need d3820543a31bfa2a556e04f91719204ce0ac6f34dcca6670314a13df87064625 $SAGE
sha256sum $SAGE $R/bin-79eeea50/logos $R/bin-a7418138/logos $EV/*.py >> $O/binaries.sha256

stage in $HOME/bench-picks/1-bakeoff/PXD028735/LFQ_Orbitrap_DDA_Human_01.raw $HOME/bench-picks/target_human_contam.fasta \
  $HOME/bench-picks/mzml/LFQ_Orbitrap_DDA_Human_01.mzML $SCRATCH/dda-pool-20261024/work/entrap_human.fasta \
  $HOME/bench-data/orbiter/5-astral-tmt/PXD058160/az01263_02152024.raw $R/mzml/az01263_02152024.mzML \
  $SCRATCH/orbiter-astral-20261021/databases/mouse-entrapment.fasta
awk '/^>/{e=($0 ~ /^>entrap_/)} { if (!e) print > "'$W'/in/target.fasta" }' $W/in/mouse-entrapment.fasta
awk '/^>/{e=($0 ~ /^>entrap_/)} { if (e) print > "'$W'/in/entrap.fasta" }' $W/in/mouse-entrapment.fasta
hash_inputs

# cfg SRC TAG [pin]: the recorded config with every staged path pointed at $W/in, written to $O/TAG/config.json.
cfg() { mkdir -p $O/$2; python3 -I - "$1" "$W" "$KEEP/$2/pin" "${3:-}" > $O/$2/config.json <<'PY'
import json, re, sys
src, w, pin, want = sys.argv[1:5]
text = re.sub(r"/dev/shm/showcase-user/[^/\"]+/(?:[^/\"]+/)*([^/\"]+)", lambda m: f"{w}/in/{m.group(1)}", open(src).read())
d = json.loads(text)
if want:
    d["pin"] = pin
print(json.dumps(d, indent=1))
PY
}
# arm TAG BIN SRC_CONFIG RECORDED_DIR [logos args...]
arm() { local tag=$1 bin=$2 src=$3 rec=$4; shift 4; local L=$O/$tag D=$KEEP/$tag; mkdir -p $D
  cfg $src $tag pin
  echo "$bin --config $L/config.json $*" > $L/command.txt
  /usr/bin/time -v -o $L/time.txt $AP exec --bind /wsu $SIF $bin --config $L/config.json --backend cpu --no-tsv --learn $D/learn "$@" > $L/stdout.txt 2> $L/logos.log; local rc=$?
  find $D -maxdepth 4 -type f | sed "s|$D/||" | sort > $L/files.txt
  (cd $D && find pin learn -type f \( -name '*.pin' -o -name '*.tsv' -o -name '*.json' \) -print0 | sort -z | xargs -0 -r sha256sum) > $L/outputs.sha256
  stamp "$tag rc=$rc $(wall $L/time.txt)"
  python3 -I $EV/check_logos.py $D $rec ${ENT:-} > $L/check.json 2> $L/check.err; stamp "$tag check: $(tail -1 $L/check.json)"; }
sagearm() { local tag=$1 src=$2 rec=$3; local L=$O/$tag D=$KEEP/$tag; mkdir -p $D
  cfg $src $tag
  /usr/bin/time -v -o $L/time.txt $AP exec --bind /wsu $SIF $SAGE $L/config.json -o $D/out --disable-telemetry-i-dont-want-to-improve-sage > $L/sage.log 2>&1; local rc=$?
  sha256sum $D/out/results.sage.tsv > $L/tsv.sha256
  python3 -I $EV/sage_to_pin.py $D/out/results.sage.tsv $D/cnt > $L/convert.log 2>&1
  $AP exec --bind /wsu $SIF $CI $D/cnt --out $L/count-ids.json --no-lists ${ENT:+--entrap $ENT --entrap-out $L/count-ids.entrap.json} > $L/count-ids.log 2>&1
  python3 -I $EV/count.py $D/cnt ${ENT:+--entrap $ENT} > $L/count.py.json 2> $L/count.py.err
  python3 -I $EV/check_sage.py $L $rec > $L/check.json 2> $L/check.err
  stamp "$tag rc=$rc $(wall $L/time.txt) check: $(tail -1 $L/check.json)"; }

C=$R/configs-c22; E=$RES/entrap-arms/40928398
arm lfq-open $R/bin-79eeea50/logos $C/lfq-open-fi.json $RES/lfq-c22/40928337/new-1 --entrapment-ratio 1
arm lfq-closed $R/bin/logos $C/lfq-plain-H.json $RES/lfq-c22/40901452/plain-H-1/learn/logos_0 --entrapment-ratio 1
arm astral-tmt $R/bin-a7418138/logos $C/astral-tmt-A1.json $RES/astral-tmt/40902791/logos-cpu-1 --entrapment-ratio 1
ENT=1.060595818801411 arm lfq-open-cal-lda-E $R/bin-79eeea50/logos $E/cfg/open-cal-lda.json $E/lfq-open-cal-lda-E \
  --entrapment $W/in/entrap_human.fasta --entrapment-ratio 1.060595818801411
R_AST=$(python3 -c "import json;print(json.loads(open('$E/r-astral.jsonl').read().splitlines()[0])['r'])")
ENT=$R_AST arm astral-logos-E $R/bin-79eeea50/logos $E/cfg/astral.json $E/astral-logos-E --entrapment $W/in/entrap.fasta --entrapment-ratio $R_AST
sagearm sage-open $C/sage-open.json $RES/lfq-c22/40928337/sage-1
sagearm sage-default $C/sage-default.json $RES/lfq-c22/40901452/sage-default-1
sagearm sage-astral $RES/astral-tmt/40902791/sage.json $RES/astral-tmt/40902791/sage-1
ENT=$R_AST sagearm sage-astral-E $E/cfg/sage-astral-E.json $E/astral-sage-E
stamp "EVAL-PARITY DONE; outputs kept in $KEEP"
