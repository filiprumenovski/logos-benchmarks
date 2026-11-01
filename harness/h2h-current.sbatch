#!/bin/bash
#SBATCH -J bench-h2h-current
#SBATCH -o $RUN_ROOT/logs/h2h-current-%j.log
#SBATCH -p reqp
#SBATCH -q requeue
#SBATCH --gres=gpu:nvidia_rtx_pro_4500_blackwell:1
#SBATCH -c 22
#SBATCH --mem=96G
#SBATCH -t 01:30:00
# Head to head on one binary (79eeea50, which contains every earlier change), one job, one node:
# LFQ human-01 closed and DDA+, Astral TMTpro az01263. Per benchmark LOGOS CPU, LOGOS GPU and Sage 0.14.7
# run interleaved, order rotated, 3 repeats after one warm-up each; load average logged around every run.
# LOGOS CPU ids.json must equal GPU ids.json; Sage is counted by count-ids and by eval/count.py.
BENCH=h2h-current
source $RUN_ROOT/lib/common.sh
set +e
EV=$R/eval; RES=$R/results; C=$R/configs-c22
SAGE=$HOME/Tools/sage/sage-v0.14.7-x86_64-unknown-linux-gnu/sage
need d3820543a31bfa2a556e04f91719204ce0ac6f34dcca6670314a13df87064625 $SAGE
BIN=$R/bin-79eeea50/logos
need 47068225e4a0d61e4f52c93e980581a5d91ede7e32c437b6bee75fd60155d89e $BIN
sha256sum $SAGE $BIN $EV/*.py >> $O/binaries.sha256
stage in $HOME/bench-picks/1-bakeoff/PXD028735/LFQ_Orbitrap_DDA_Human_01.raw $HOME/bench-picks/target_human_contam.fasta \
  $HOME/bench-picks/mzml/LFQ_Orbitrap_DDA_Human_01.mzML \
  $HOME/bench-data/orbiter/5-astral-tmt/PXD058160/az01263_02152024.raw $R/mzml/az01263_02152024.mzML
awk '/^>/{e=($0 ~ /^>entrap_/)} { if (!e) print > "'$W'/in/target.fasta" }' $SCRATCH/orbiter-astral-20261021/databases/mouse-entrapment.fasta
hash_inputs
ld() { cut -d' ' -f1-3 /proc/loadavg; }
cfg() { mkdir -p $O/cfg; python3 -I - "$1" "$W" > $O/cfg/$2.json <<'PY'
import json, re, sys
src, w = sys.argv[1:3]
print(json.dumps(json.loads(re.sub(r"/dev/shm/showcase-user/[^/\"]+/(?:[^/\"]+/)*([^/\"]+)", lambda m: f"{w}/in/{m.group(1)}", open(src).read())), indent=1))
PY
}
cfg $C/lfq-plain-H.json lfq-closed; cfg $C/lfq-ddaplus-H.json lfq-ddaplus; cfg $C/astral-tmt-A1.json astral
cfg $C/sage-default.json sage-lfq; cfg $RES/astral-tmt/40902791/sage.json sage-astral

lg() { local tag=$1 c=$2 be=$3; local L=$O/$tag D=$W/out/$tag; rm -rf $D; mkdir -p $D $L; local nv=""; [ $be = cuda ] && nv=$NV; local l0=$(ld)
  echo "$BIN --config $O/cfg/$c.json --backend $be --no-tsv --learn @learn --entrapment-ratio 1 --timing" > $L/command.txt
  /usr/bin/time -v -o $L/time.txt $AP exec $nv --bind /wsu $SIF $BIN --config $O/cfg/$c.json --backend $be --no-tsv --learn $D/learn --entrapment-ratio 1 --timing > $L/stdout.txt 2> $L/logos.log; local rc=$?
  cp $D/learn/logos_0/ids.json $L/ 2>/dev/null; sha256sum $L/ids.json 2>/dev/null | cut -c1-64 > $L/ids.sha
  stamp "$tag rc=$rc $(wall $L/time.txt) load=[$l0 -> $(ld)] | $(grep -E '^learn: ' $L/logos.log | tail -1 | grep -oE '[0-9]+ PSMs, [0-9]+ sequences') ids=$(cut -c1-12 $L/ids.sha)"
  [ $rc = 0 ] || echo $tag >> $O/FAILED; rm -rf $D; }
sg() { local tag=$1 c=$2 count=${3:-}; local L=$O/$tag D=$W/out/$tag; rm -rf $D; mkdir -p $D $L; local l0=$(ld)
  /usr/bin/time -v -o $L/time.txt $AP exec --bind /wsu $SIF $SAGE $O/cfg/$c.json -o $D --disable-telemetry-i-dont-want-to-improve-sage > $L/sage.log 2>&1; local rc=$?
  sha256sum $D/results.sage.tsv | cut -c1-64 > $L/tsv.sha256
  if [ -n "$count" ]; then python3 -I $EV/sage_to_pin.py $D/results.sage.tsv $D/cnt > $L/convert.log 2>&1
    $AP exec --bind /wsu $SIF $CI $D/cnt --out $L/sage.ids.json --no-lists > $L/count-ids.log 2>&1
    python3 -I $EV/count.py $D/cnt > $L/count.py.json 2> $L/count.py.err; fi
  stamp "$tag rc=$rc $(wall $L/time.txt) load=[$l0 -> $(ld)] tsv=$(cut -c1-12 $L/tsv.sha256)"
  [ $rc = 0 ] || echo $tag >> $O/FAILED; rm -rf $D; }

lg warm-lfq-cpu lfq-closed cpu; lg warm-lfq-gpu lfq-closed cuda; sg warm-sage-lfq sage-lfq
for rep in 1 2 3; do
  case $rep in 1) o="cpu gpu sage plus";; 2) o="sage plus gpu cpu";; 3) o="gpu cpu plus sage";; esac
  for a in $o; do case $a in
    cpu) lg lfq-cpu-$rep lfq-closed cpu;; gpu) lg lfq-gpu-$rep lfq-closed cuda;; plus) lg lfq-ddaplus-cpu-$rep lfq-ddaplus cpu;;
    sage) sg lfq-sage-$rep sage-lfq $([ $rep = 1 ] && echo count);; esac; done
done
lg warm-astral-cpu astral cpu; lg warm-astral-gpu astral cuda; sg warm-sage-astral sage-astral
for rep in 1 2 3; do
  case $rep in 1) o="cpu gpu sage";; 2) o="sage gpu cpu";; 3) o="gpu sage cpu";; esac
  for a in $o; do case $a in
    cpu) lg astral-cpu-$rep astral cpu;; gpu) lg astral-gpu-$rep astral cuda;;
    sage) sg astral-sage-$rep sage-astral $([ $rep = 1 ] && echo count);; esac; done
done
python3 -I - $O <<'PY' 2>&1 | tee $O/summary.txt
import json, pathlib, re, statistics as st, sys
O = pathlib.Path(sys.argv[1])
def wall(t):
    m = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", (O / t / "time.txt").read_text()).group(1).split(":")
    return sum(float(x) * 60**i for i, x in enumerate(reversed(m)))
def sha(t):
    p = O / t / "ids.sha"; return p.read_text().strip() if p.exists() else "missing"
for b, arms in (("lfq", ("cpu", "gpu", "sage", "ddaplus-cpu")), ("astral", ("cpu", "gpu", "sage"))):
    w = {a: [wall(f"{b}-{a}-{r}") for r in (1, 2, 3)] for a in arms}
    for a, v in w.items():
        print(f"SUMMARY {b} {a:11s} wall {st.median(v):.2f} [{min(v):.2f}..{max(v):.2f}]")
    s = {sha(f"{b}-{a}-{r}") for a in ("cpu", "gpu") for r in (1, 2, 3)}
    print(f"PARITY {b} CPU==GPU " + ("byte-identical " + s.pop()[:12] if len(s) == 1 and "missing" not in s else f"DIFFERS {sorted(s)}"))
    l = json.load(open(O / f"{b}-cpu-1" / "ids.json")); g = json.load(open(O / f"{b}-sage-1" / "sage.ids.json")); p = json.load(open(O / f"{b}-sage-1" / "count.py.json"))
    print(f"IDS {b} logos seq {l['sequences_q01']} psm {l['psms_q01']} | sage count-ids seq {g['sequences_q01']} psm {g['psms_q01']} | sage count.py seq {p['sequences_q01']} psm {p['psms_q01']}")
PY
stamp "H2H-CURRENT DONE"
