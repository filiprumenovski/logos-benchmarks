"""check_sage.py RUN RECORDED: one rerun Sage arm against its record.

RUN holds count-ids.json (the engine's counter) and count.py.json (eval/count.py), both
on the PIN that eval/sage_to_pin.py wrote; RECORDED holds the recorded sage.ids.json
(and entrap.json for an entrapment arm). PASS only if all three agree on every count,
and the converted PIN is byte-identical to the one the recorded count read.
"""
import json
import sys
from pathlib import Path

FIELDS = ("candidate_rows", "competed_psms", "psms_q01", "sequences_q01", "peptidoforms_q01")


def main(run, recorded):
    run, recorded = Path(run), Path(recorded)
    rec = json.loads((recorded / "sage.ids.json").read_text())
    ci = json.loads((run / "count-ids.json").read_text())
    ours = json.loads((run / "count.py.json").read_text())
    out = {
        "evidence_sha256": {"recorded": rec.get("evidence_sha256"), "rerun": ci.get("evidence_sha256")},
        "fields": {f: {"recorded": rec.get(f), "count-ids": ci.get(f), "count.py": ours[f]} for f in FIELDS},
    }
    ok = out["evidence_sha256"]["recorded"] == out["evidence_sha256"]["rerun"]
    ok = ok and all(len({v["recorded"], v["count-ids"], v["count.py"]}) == 1 for v in out["fields"].values())
    if (recorded / "entrap.json").exists():
        rec_e = json.loads((recorded / "entrap.json").read_text())["rules"]
        cmp = {}
        for rule, levels in ours["entrapment"].items():
            for level in ("psm", "seqlvl", "seqs"):
                a, b = rec_e[rule][level], levels[level]
                cmp[f"{rule}.{level}"] = {"recorded": [a["Nt"], a["Ne"], a["fdp_combined"]],
                                          "count.py": [b["nt"], b["ne"], b["fdp_combined"]]}
        out["entrapment"] = cmp
        ok = ok and all(v["recorded"] == v["count.py"] for v in cmp.values())
    print(json.dumps(out, indent=1))
    print(json.dumps({"verdict": "PASS" if ok else "FAIL"}))


if __name__ == "__main__":
    main(*sys.argv[1:])
