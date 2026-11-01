"""Identification counts and entrapment FDP of one scored PSM table.

This is the counting rule behind every identification number in this
repository, applied the same way to LOGOS and to Sage. It reads a PIN file
(one row per candidate PSM) and the scores a learner assigned to its rows,
and reports PSMs, distinct sequences and peptidoforms accepted at 1% FDR by
target-decoy competition; with an entrapment ratio it also reports the
entrapment-measured false discovery proportion.

The rules:

- Competition: one winner per (ScanNr, ExpMass). A row beats another on
  (score, decoy, SpecId): higher score wins, a decoy wins an exact score
  tie, then the larger SpecId.
- Acceptance: sort by score, descending, in whole groups of equal score.
  At the end of each group FDR = (D + 1) / max(1, T) over everything so
  far; q is the running minimum of FDR from the bottom; the targets of
  every group with q <= 0.01 are accepted. Ties are never split.
- Sequences: among the winners, the best row per sequence (I and J read
  as L, modifications and terminal markers removed) on (score, decoy),
  the first row keeping an exact tie; then acceptance as above.
  Peptidoforms: the same per modified peptide.
- Entrapment: a target row is an entrapment hit when every protein it maps
  to carries the prefix entrap_. With N_t accepted targets from the real
  database and N_e from the entrapment database, and r the ratio of
  entrapment to target sequence space,
  FDP = N_e (1 + 1/r) / (N_t + N_e).

Usage:
  count.py DIR                 # DIR/evidence.pin + DIR/percolator/percolator.{psms,decoys}.tsv
  count.py DIR --entrap R      # also the entrapment FDP at ratio R
Prints one JSON object. Standard library only.
"""
import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)
_MOD = re.compile(r"\[[^]]*\]")


def normalize(s):
    """Bare sequence: bracketed modifications and n/c terminal markers removed, I and J read as L."""
    return _MOD.sub("", s).strip("nc").replace("I", "L").replace("J", "L")


def sequence(peptide):
    """Sequence of a flanked PIN peptide (K.PEPTIDE.R): two characters stripped per side."""
    return normalize(peptide[2:-2])


def entrap_sequence(peptide):
    """Sequence of a peptide whose flanks may be absent."""
    if len(peptide) > 4 and peptide[1] == "." and peptide[-2] == ".":
        return normalize(peptide[2:-2])
    return normalize(peptide)


def beats(a, b):
    """Competition order: (score, decoy, SpecId), strictly greater."""
    return (a["score"], a["decoy"], a["id"]) > (b["score"], b["decoy"], b["id"])


def winners(rows, key, better=beats):
    """One winner per key, in order of each key's first appearance; an exact tie keeps the earlier row."""
    won = {}
    for r in rows:
        k = key(r)
        w = won.get(k)
        if w is None or better(r, w):
            won[k] = r
    return list(won.values())


def best_per(rows, key):
    """Best row per key on (score, decoy); the first row keeps an exact tie."""
    return winners(rows, key, lambda a, b: (a["score"], a["decoy"]) > (b["score"], b["decoy"]))


def accept(rows):
    """Targets accepted at q <= 0.01 by whole-tie-group (D + 1) / T acceptance."""
    order = sorted(rows, key=lambda r: r["score"], reverse=True)
    groups, t, d = [], 0, 0
    for i, r in enumerate(order):
        if r["decoy"]:
            d += 1
        else:
            t += 1
        if i + 1 == len(order) or order[i + 1]["score"] != r["score"]:
            groups.append((i, (d + 1) / max(1, t)))
    ok, q = [False] * len(groups), 1.0
    for g in range(len(groups) - 1, -1, -1):
        q = min(q, groups[g][1])
        ok[g] = q <= 0.01
    out, start = [], 0
    for g, (end, _) in enumerate(groups):
        if ok[g]:
            out.extend(r for r in order[start:end + 1] if not r["decoy"])
        start = end + 1
    return out


def count_ids(rows):
    w = winners(rows, lambda r: (r["scan"], r["expmass"]))
    seqs = accept(best_per(w, lambda r: sequence(r["peptide"])))
    return {
        "candidate_rows": len(rows),
        "competed_psms": len(w),
        "psms_q01": len(accept(w)),
        "sequences_q01": len(seqs),
        "peptidoforms_q01": len(accept(best_per(w, lambda r: r["peptide"][2:-2]))),
    }


def fdp(nt, ne, r, n=None):
    n = max(1, nt + ne if n is None else n)
    return {"nt": nt, "ne": ne, "fdp_combined": round(ne * (1 + 1 / r) / n, 4), "fdp_lower": round(ne / n, 4)}


def entrapment(rows, r):
    """Entrapment FDP at PSM and sequence level under four competition rules."""
    rules = {
        "expmass": winners(rows, lambda x: (x["scan"], x["expmass"])),
        "top1": winners(rows, lambda x: x["scan"]),
        "native1": winners(rows, lambda x: x["scan"],
                           lambda a, b: (a["primary_score"], a["decoy"], a["id"]) > (b["primary_score"], b["decoy"], b["id"])),
        "none": list(rows),
    }
    out = {}
    for name, comp in rules.items():
        acc = accept(comp)
        ne = sum(x["entrapment"] for x in acc)
        sacc = accept(best_per(comp, lambda x: entrap_sequence(x["peptide"])))
        sne = sum(x["entrapment"] for x in sacc)
        state = {}
        for x in acc:
            k = entrap_sequence(x["peptide"])
            state[k] = state.get(k, True) and x["entrapment"]
        m, me = len(state), sum(state.values())
        out[name] = {
            "competed": len(comp),
            "competed_decoys": sum(x["decoy"] for x in comp),
            "psm": fdp(len(acc) - ne, ne, r),
            "seqlvl": fdp(len(sacc) - sne, sne, r),
            "seqs": fdp(m - me, me, r, m),
        }
    return out


def read_rows(directory, pins=None):
    """PIN rows joined to their learner scores (SpecId -> score); every row must be scored.
    pins: PIN files, each with its own header (default DIR/evidence.pin)."""
    d = Path(directory)
    scores = {}
    for name, decoy in (("psms", False), ("decoys", True)):
        with open(d / "percolator" / f"percolator.{name}.tsv", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                s = float(row["score"])
                if not math.isfinite(s):
                    raise ValueError(f"non-finite score for {row['PSMId']}")
                if row["PSMId"] in scores:
                    raise ValueError(f"duplicate PSMId {row['PSMId']}")
                scores[row["PSMId"]] = (s, decoy)
    rows = []
    for pin in pins or [d / "evidence.pin"]:
        rows.extend(_pin_rows(pin, scores))
    if len(rows) != len(scores):
        raise ValueError(f"{len(rows)} PIN rows but {len(scores)} scores")
    return rows


def _pin_rows(pin, scores):
    rows = []
    with open(pin, newline="") as f:
        lines = iter(f)
        head = next(lines).rstrip("\r\n").split("\t")
        ix = {h: i for i, h in enumerate(head)}
        np_ = ix["Proteins"]
        for line in lines:
            line = line.rstrip("\r\n")
            if not line:
                continue
            fields = line.split("\t", np_)
            decoy = fields[ix["Label"]] == "-1"
            proteins = fields[np_].split("\t") if len(fields) > np_ else []
            score, sdecoy = scores[fields[ix["SpecId"]]]
            if sdecoy != decoy:
                raise ValueError(f"label mismatch for {fields[ix['SpecId']]}")
            rows.append({
                "id": fields[ix["SpecId"]],
                "peptide": fields[ix["Peptide"]],
                "scan": int(fields[ix["ScanNr"]]),
                "expmass": float(fields[ix["ExpMass"]]),
                "decoy": decoy,
                "entrapment": (not decoy) and all(p.startswith("entrap_") or p == "ENTRAPMENT" for p in proteins),
                "primary_score": float(fields[ix["primary_score"]]) if "primary_score" in ix else 0.0,
                "score": score,
            })
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("dir", help="learner directory: evidence.pin and percolator/percolator.{psms,decoys}.tsv")
    p.add_argument("--pin", nargs="+", help="PIN files, each with its own header (default DIR/evidence.pin)")
    p.add_argument("--entrap", type=float, metavar="R", help="entrapment ratio r: also report entrapment FDP")
    a = p.parse_args(argv)
    rows = read_rows(a.dir, a.pin)
    out = count_ids(rows)
    if a.entrap is not None:
        out["entrapment"] = entrapment(rows, a.entrap)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
