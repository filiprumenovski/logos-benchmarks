"""from_runs.py: the report's speed and identification tables, computed from runs/*/run.json.

Every row names the run and arms it comes from; build_report.py reads the JSON this writes.
`python3 reports/from_runs.py --check` recomputes and fails if reports/data differs, so a
hand edit to a number cannot survive a build.
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "reports" / "data"
RUNS = {p.parent.name: json.loads(p.read_text()) for p in ROOT.glob("runs/*/run.json")}

# (key, benchmark, run, CPU arm prefix, GPU arm prefix, Sage arm prefix)
SPEED = [
    ("lfq-closed", "Closed DDA, LFQ human", "2026-11-01-h2h-current", "lfq-cpu", "lfq-gpu", "lfq-sage"),
    ("lfq-open-ymh4", "Open −100 to +500 Da, LFQ human", "2026-10-31-lfq-open-ymh4", "cpu", "cuda", "sage"),
    ("lfq-open-bbc1", "Open −100 to +500 Da, LFQ human", "2026-10-31-lfq-open-bbc1", "new", None, "sage"),
    ("lfq-open-arw3", "Open −100 to +500 Da, LFQ human", "2026-10-31-lfq-open-arw3", "new", None, "sage"),
    ("astral-tmt", "Astral TMTpro, one file", "2026-11-01-h2h-current", "astral-cpu", "astral-gpu", "astral-sage"),
]

# (key, benchmark, engine, (run, arm) for target-only counts, (run, arm) for the entrapment arm)
IDS = [
    ("c-logos", "Closed DDA, LFQ human", "LOGOS", ("2026-11-01-h2h-current", "lfq-cpu-1"), ("2026-10-30-lfq-counts", "plain-H-E")),
    ("c-sage", "Closed DDA, LFQ human", "Sage 0.14.7", ("2026-10-30-lfq-counts", "sage-default-1"), ("2026-10-30-lfq-sage-entrapment", "sage-default-E")),
    ("o-logos", "Open −100 to +500 Da, LFQ human", "LOGOS", ("2026-10-31-lfq-open-ymh4", "cpu-1"), ("2026-10-31-entrapment-arms", "lfq-open-lean-E")),
    ("o-logos-lda", "Open −100 to +500 Da, LFQ human", "LOGOS + LDA rescoring", None, ("2026-10-31-entrapment-arms", "lfq-open-lda-E")),
    ("o-logos-cal", "Open −100 to +500 Da, LFQ human", "LOGOS + calibration + LDA", ("2026-11-01-fill-gaps", "open-cal-lda-1"), ("2026-10-31-entrapment-arms", "lfq-open-cal-lda-E")),
    ("o-sage", "Open −100 to +500 Da, LFQ human", "Sage 0.14.7", ("2026-10-31-lfq-open-ymh4", "sage-1"), ("2026-11-01-fill-gaps", "sage-open-E")),
    ("a-logos", "Astral TMTpro, one file", "LOGOS", ("2026-11-01-h2h-current", "astral-cpu-1"), ("2026-10-31-entrapment-arms", "astral-logos-E")),
    ("a-sage", "Astral TMTpro, one file", "Sage 0.14.7", ("2026-11-01-h2h-current", "astral-sage-1"), ("2026-10-31-entrapment-arms", "astral-sage-E")),
]


def walls(run, prefix):
    arms = RUNS[run]["arms"]
    v = [a["wall_s"] for k, a in sorted(arms.items()) if k.rsplit("-", 1)[0] == prefix and k.rsplit("-", 1)[1].isdigit()]
    if len(v) < 3:
        raise SystemExit(f"{run}/{prefix}: {len(v)} repeats, need at least 3")
    return v


def binary(run, prefix):
    arms = RUNS[run]["arms"]
    b = {a.get("binary_sha256") for k, a in arms.items() if k.rsplit("-", 1)[0] == prefix}
    if len(b) != 1 or None in b:
        raise SystemExit(f"{run}/{prefix}: binaries {b}")
    return b.pop()


def speed():
    rows = []
    for key, bench, run, cpu, gpu, sage in SPEED:
        r = RUNS[run]
        row = {"key": key, "benchmark": bench, "run": run, "slurm_job": r["slurm_job"], "node": r["node"], "cpu": r.get("cpu"),
               "gpu": r.get("gpu") if gpu else None}
        for name, prefix in (("logos_cpu", cpu), ("logos_gpu", gpu), ("sage", sage)):
            if prefix is None:
                row[f"{name}_s"] = None
                continue
            v = walls(run, prefix)
            row[f"{name}_s"] = round(statistics.median(v), 2)
            row[f"{name}_repeats_s"] = v
        row["logos_binary_sha256"] = binary(run, cpu)
        rows.append(row)
    return rows


def ids():
    rows = []
    for key, bench, engine, target, entrap in IDS:
        row = {"key": key, "benchmark": bench, "engine": engine, "sequences": None, "psms": None}
        if target:
            run, arm = target
            c = RUNS[run]["arms"][arm]["counts"]
            row.update(sequences=c["sequences_q01"], psms=c["psms_q01"], target_source=f"{run}/{arm}")
        run, arm = entrap
        e = RUNS[run]["arms"][arm]["entrapment"]["expmass"]
        row["entrapment"] = {"sequences": e["seqlvl"], "psms": e["psm"]}
        row["entrapment_source"] = f"{run}/{arm}"
        rows.append(row)
    return rows


def speedups(sp):
    """speedup.json: rows measured in the runs are recomputed; rows recorded earlier are kept, labelled."""
    by = {r["key"]: r for r in sp}
    x = lambda a, b: round(a / b, 1)
    run_date = lambda k: "measured " + by[k]["run"][:10]
    open_ratios = [x(by[k]["sage_s"], by[k]["logos_cpu_s"]) for k in ("lfq-open-ymh4", "lfq-open-bbc1", "lfq-open-arw3")]
    measured = [
        ("lfq-closed", "LFQ human, closed", "CPU", "lfq-closed", "logos_cpu_s", None),
        ("lfq-open-cpu", "LFQ human, open", "CPU", "lfq-open-ymh4", "logos_cpu_s", [min(open_ratios), max(open_ratios)]),
        ("lfq-open-gpu", "LFQ human, open", "GPU", "lfq-open-ymh4", "logos_gpu_s", None),
        ("astral-cpu", "Astral TMTpro, one file", "CPU", "astral-tmt", "logos_cpu_s", None),
        ("astral-gpu", "Astral TMTpro, one file", "GPU", "astral-tmt", "logos_gpu_s", None),
    ]
    rows = [{"key": k, "benchmark": b, "backend": be, "logos_s": by[src][col], "sage_s": by[src]["sage_s"], "node": by[src]["node"],
             "basis": run_date(src), "node_range": rng, "x": x(by[src]["sage_s"], by[src][col]), "run": by[src]["run"]}
            for k, b, be, src, col, rng in measured]
    keep = [r for r in json.loads((DATA / "speedup.json").read_text())["rows"] if r["basis"].startswith("recorded")]
    return rows + keep


# Scoreboard rows against Sage that the runs measure: (key, dataset label, LOGOS ids row, Sage ids row).
BOARD = [
    ("lfq-open", "LFQ human, open \u2212100 to +500 Da", "o-logos-cal", "o-sage"),
    ("lfq-closed", "LFQ human, closed", "c-logos", "c-sage"),
    ("astral-tmt", "Astral TMTpro, one file", "a-logos", "a-sage"),
]


def board(id_rows):
    """scoreboard.json: the Sage rows the runs measure use the entrapment-arm sequence counts; other rows are kept."""
    by = {r["key"]: r for r in id_rows}
    rows = json.loads((DATA / "scoreboard.json").read_text())["rows"]
    for key, label, lk, sk in BOARD:
        r = next(x for x in rows if x["key"] == key)
        lo, sa = by[lk]["entrapment"]["sequences"], by[sk]["entrapment"]["sequences"]
        fl, fs = f"{100 * lo['fdp']:.2f}%", f"{100 * sa['fdp']:.2f}%"
        r.update(dataset=label, logos=lo["nt"], comp=sa["nt"], delta_pct=round(100 * (lo["nt"] / sa["nt"] - 1), 1),
                 error=f"entrapment {fl} each" if fl == fs else f"entrapment {fl} vs {fs}",
                 basis="measured " + min(by[lk]["entrapment_source"][:10], by[sk]["entrapment_source"][:10]),
                 source=f"runs {by[lk]['entrapment_source'].split('/')[0]}, {by[sk]['entrapment_source'].split('/')[0]}")
    return rows


def claims(sp, id_rows):
    """The README's head-to-head table, in markdown, from the same rows as the report."""
    ib = {r["key"]: r for r in id_rows}
    x = lambda a, b: "--" if not (a and b) else f"{a / b:.1f}x"
    s = lambda v: "--" if v is None else f"{v:.2f} s"
    out = ["| Benchmark | Node | LOGOS CPU | LOGOS GPU | Sage | Speed-up CPU / GPU | Run |", "|---|---|---|---|---|---|---|"]
    for r in sp:
        out.append(f"| {r['benchmark']} | {r['node']} | {s(r['logos_cpu_s'])} | {s(r['logos_gpu_s'])} | {s(r['sage_s'])} | "
                   f"{x(r['sage_s'], r['logos_cpu_s'])} / {x(r['sage_s'], r['logos_gpu_s'])} | [{r['run']}](runs/{r['run']}) |")
    out += ["", "| Benchmark | Engine | Sequences at 1% FDR | Entrapment arm: sequences, FDP | Source |", "|---|---|---|---|---|"]
    for r in id_rows:
        e = r["entrapment"]["sequences"]
        out.append(f"| {r['benchmark']} | {r['engine']} | {'--' if r['sequences'] is None else f'{r[chr(115)+chr(101)+chr(113)+chr(117)+chr(101)+chr(110)+chr(99)+chr(101)+chr(115)]:,}'} | "
                   f"{e['nt']:,}, {100 * e['fdp']:.2f}% | [{r['entrapment_source'].split('/')[0]}](runs/{r['entrapment_source'].split('/')[0]}) |")
    return "\n".join(out)


def main(check=False):
    sp = speed()
    id_rows = ids()
    out = {"speed.json": {"rows": sp}, "ids.json": {"rows": id_rows}, "speedup.json": {"rows": speedups(sp)},
           "scoreboard.json": {"rows": board(id_rows)}}
    bad = 0
    readme = ROOT / "README.md"
    text = readme.read_text()
    a, b = text.index("<!-- claims:begin -->") + len("<!-- claims:begin -->"), text.index("<!-- claims:end -->")
    new = text[:a] + "\n" + claims(sp, id_rows) + "\n" + text[b:]
    if check and new != text:
        print("README.md claims table differs from the run records"); bad += 1
    elif not check:
        readme.write_text(new)
    for name, data in out.items():
        text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
        path = DATA / name
        if check:
            if not path.exists() or path.read_text() != text:
                print(f"{name}: differs from the run records"); bad += 1
        else:
            path.write_text(text)
            print(f"wrote {path.relative_to(ROOT)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main("--check" in sys.argv)
