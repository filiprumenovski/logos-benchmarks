#!/bin/bash
#SBATCH -J bench-eval-checks
#SBATCH -o $RUN_ROOT/logs/eval-checks-%j.log
#SBATCH -p reqp
#SBATCH -q requeue
#SBATCH -c 4
#SBATCH --mem=48G
#SBATCH -t 00:45:00
# The LOGOS half of eval-parity on its kept outputs: eval/count.py against the recorded and rerun counts.
set -uo pipefail
module load python/3.11 >/dev/null 2>&1 || true
R=$RUN_ROOT; EV=$R/eval; RES=$R/results; K=$SCRATCH/eval-parity-${PARITY:?}; O=$RES/eval-parity/$PARITY
E=$RES/entrap-arms/40928398
R_AST=$(python3 -c "import json;print(json.loads(open('$E/r-astral.jsonl').read().splitlines()[0])['r'])")
chk() { python3 -I $EV/check_logos.py $K/$1 $2 ${3:-} > $O/$1/check.json 2> $O/$1/check.err; echo "$(date -Is) $1 check: $(tail -1 $O/$1/check.json) $(tail -1 $O/$1/check.err)" | tee -a $O/stages.txt; }
chk lfq-open $RES/lfq-c22/40928337/new-1
chk lfq-closed $RES/lfq-c22/40901452/plain-H-1/learn/logos_0
chk astral-tmt $RES/astral-tmt/40902791/logos-cpu-1
chk lfq-open-cal-lda-E $E/lfq-open-cal-lda-E 1.060595818801411
chk astral-logos-E $E/astral-logos-E $R_AST
