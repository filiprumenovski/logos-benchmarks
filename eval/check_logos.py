"""check_logos.py RUN RECORDED [R]: one rerun LOGOS arm against its record.

RUN holds the rerun's PIN files (RUN/pin/*.pin) and learner directory (RUN/learn);
RECORDED holds the recorded ids.json (and entrap.json when R is given). Prints one
JSON object whose last line is a verdict: PASS only if the rerun's counts equal the
record and eval/count.py, run on the rerun's PIN and scores, equals both.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I does not add the script's folder
import count  # noqa: E402

FIELDS = ("candidate_rows", "competed_psms", "psms_q01", "sequences_q01", "peptidoforms_q01")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(run, recorded, r=None):
    run, recorded = Path(run), Path(recorded)
    [learner] = {p.parent.parent for p in run.glob("learn/**/percolator/percolator.psms.tsv")}
    pins = sorted(p for p in run.glob("pin/**/*.pin"))
    rerun_ids = json.loads((learner / "ids.json").read_text())
    rec_ids = json.loads((recorded / "ids.json").read_text())
    rows = count.read_rows(learner, pins)
    ours = count.count_ids(rows)
    out = {
        "pins": [p.name for p in pins],
        "ids_json_sha256": {"rerun": sha(learner / "ids.json"), "recorded": sha(recorded / "ids.json")},
        "fields": {f: {"recorded": rec_ids.get(f), "rerun": rerun_ids.get(f), "count.py": ours[f]} for f in FIELDS},
    }
    ok = all(v["recorded"] == v["rerun"] == v["count.py"] for v in out["fields"].values())
    if r is not None:
        rec_e = json.loads((recorded / "entrap.json").read_text())["rules"]
        ours_e = count.entrapment(rows, float(r))
        cmp = {}
        for rule, levels in ours_e.items():
            for level in ("psm", "seqlvl", "seqs"):
                a = rec_e[rule][level]
                b = ours_e[rule][level]
                cmp[f"{rule}.{level}"] = {"recorded": [a["Nt"], a["Ne"], a["fdp_combined"]],
                                          "count.py": [b["nt"], b["ne"], b["fdp_combined"]]}
        out["entrapment"] = cmp
        ok = ok and all(v["recorded"] == v["count.py"] for v in cmp.values())
    print(json.dumps(out, indent=1))
    print(json.dumps({"verdict": "PASS" if ok else "FAIL"}))


if __name__ == "__main__":
    main(*sys.argv[1:])
