#!/bin/bash
#SBATCH -J bench-fullstack
#SBATCH -o $RUN_ROOT/logs/fullstack-%j.log
#SBATCH -p reqp
#SBATCH -q requeue
#SBATCH --gres=gpu:nvidia_rtx_pro_4500_blackwell:1
#SBATCH -c 22
#SBATCH --mem=160G
#SBATCH -t 04:00:00
# LOGOS full stack, LOGOS only, on binary 79eeea50: the search writes its PIN, then logos-boost adds
# predicted-spectrum, retention-time and mixture features and rescores with the MLP (the recorded gboost
# recipe; it scores the closed stratum). Every dataset: one target arm and one entrapment arm.
#   LFQ human-01 (PXD028735): DDA+ pool, instrument QE, entrap_human (r 1.0606).
#   Astral TMTpro az01263 (PXD058160): the A1 search, instrument ThermoTOF, mouse entrapment (r from its digestion).
#   Wide-window DDA, PXD053241 mouse, isolation 1-20 Th: the recorded DDA+ configs (wwdda-charter-20260918),
#     instrument QE, entrapment database generated here by build_entrap.py, r from the search's digestion.
BENCH=fullstack
source $RUN_ROOT/lib/common.sh
set +e
EV=$R/eval; RES=$R/results; C=$R/configs-c22; E=$RES/entrap-arms/40928398
BIN=$R/bin-79eeea50/logos
need 47068225e4a0d61e4f52c93e980581a5d91ede7e32c437b6bee75fd60155d89e $BIN
sha256sum $BIN $EV/*.py >> $O/binaries.sha256
WW=$HOME/bench-picks/2-wwDDA/PXD053241; WC=$HOME/logos-runs/wwdda-charter-20260918/configs
stage in $HOME/bench-picks/1-bakeoff/PXD028735/LFQ_Orbitrap_DDA_Human_01.raw $HOME/bench-picks/target_human_contam.fasta \
  $SCRATCH/dda-pool-20261024/work/entrap_human.fasta \
  $HOME/bench-data/orbiter/5-astral-tmt/PXD058160/az01263_02152024.raw \
  $SCRATCH/orbiter-astral-20261021/databases/mouse-entrapment.fasta $(ls $WW/*.raw)
awk '/^>/{e=($0 ~ /^>entrap_/)} { if (!e) print > "'$W'/in/target.fasta" }' $W/in/mouse-entrapment.fasta
awk '/^>/{e=($0 ~ /^>entrap_/)} { if (e) print > "'$W'/in/entrap.fasta" }' $W/in/mouse-entrapment.fasta
# Mouse wide-window database: the deposit's own two FASTA members, as recorded (sha256 85c6d807...).
(cd $W/in && unzip -p $HOME/bench-picks/1-bakeoff/PXD053241/FASTA.zip FASTA/JoT_uniprot-proteome_musmusculus_review_canonical_20220623.fasta FASTA/jpr_2022_contaminants.fasta > target_mouse_contam.fasta)
need 85c6d8070f3210a8af69db741c30def22639b87e0ba9e698b24e9805d5f72f27 $W/in/target_mouse_contam.fasta
python3 -I $EV/build_entrap.py $W/in/target_mouse_contam.fasta $W/in/entrap_mouse.fasta 20260922 > $O/build_entrap_mouse.json 2>&1
hash_inputs
R_LFQ=1.060595818801411
R_AST=$(python3 -c "import json;print(json.loads(open('$E/r-astral.jsonl').read().splitlines()[0])['r'])")
python3 -I $EV/entrapment_ratio.py $W/in/target_mouse_contam.fasta $W/in/entrap_mouse.fasta \
  '{"restrict_p": false, "missed": 2, "min_len": 7, "max_len": 50, "min_mass": 500, "max_mass": 5000, "static": {"C": 57.02146}}' | tee $O/r-mouse.jsonl
R_WW=$(python3 -c "import json;print(json.loads(open('$O/r-mouse.jsonl').read().splitlines()[0])['r'])")
stamp "entrapment ratios: lfq $R_LFQ astral $R_AST wide-window $R_WW"

# cfg SRC NAME [RAW]: the config with paths on $W/in, run-local output keys dropped, engine block as the
# showcase configs (mkconfigs.py): backend cuda, DDA+ arena 4096 MB. Prints the --explain verdict.
cfg() { mkdir -p $O/cfg; python3 -I - "$1" "$W" "${3:-}" > $O/cfg/$2.json <<'PY'
import json, re, sys
src, w, raw = sys.argv[1:4]
d = json.loads(re.sub(r"/dev/shm/[^\"]*/([^/\"]+)", lambda m: f"{w}/in/{m.group(1)}", open(src).read()))
for k in ("pin", "output"):
    d.pop(k, None)
d.setdefault("engine", {"backend": "cuda"})
if d.get("dda_plus"):
    d["engine"].setdefault("resources", {}).setdefault("dda_plus_arena_mb", 4096)
if raw:
    d["inputs"] = [f"{w}/in/{raw}"]
print(json.dumps(d, indent=1))
PY
  $AP exec --bind /wsu $SIF $BIN --config $O/cfg/$2.json --explain > $O/cfg/$2.explain 2>&1 && echo ok || echo REJECTED; }
full() { local tag=$1 c=$2 inst=$3; shift 3
  logos $tag $O/cfg/$c.json --no-tsv --pin @O/pin --learn @O/learn "$@"
  boost $tag $tag $inst 30
  rm -rf $W/out/$tag $W/boost/$tag; }

stamp "cfg lfq: $(cfg $C/lfq-ddaplus-H.json lfq)  astral: $(cfg $C/astral-tmt-A1.json astral)  astral-E: $(cfg $E/cfg/astral.json astral-E)"
export ENTRAP_R=$R_LFQ
full lfq-full lfq QE --entrapment-ratio 1
full lfq-full-E lfq QE --entrapment $W/in/entrap_human.fasta --entrapment-ratio $R_LFQ
export ENTRAP_R=$R_AST
full astral-full astral ThermoTOF --entrapment-ratio 1
full astral-full-E astral-E ThermoTOF --entrapment $W/in/entrap.fasta --entrapment-ratio $R_AST
export ENTRAP_R=$R_WW
for iw in 1 3 6 8 10 12 15 20; do
  v=$(cfg $WC/plus-iw$iw.json ww$iw 210129_wwDDA_10ug_60min_IW$iw.raw); stamp "cfg ww$iw: $v"
  [ "$v" = ok ] || { tail -3 $O/cfg/ww$iw.explain | tee -a $O/stages.txt; continue; }
  full ww$iw-full ww$iw QE --entrapment-ratio 1
  full ww$iw-full-E ww$iw QE --entrapment $W/in/entrap_mouse.fasta --entrapment-ratio $R_WW
done
stamp "FULLSTACK DONE"
