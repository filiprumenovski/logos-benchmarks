"""collect.py JOBS_ROOT OUT: compact run records from the Warrior job directories.

For each job directory listed in JOBS (below) writes OUT/runs/<name>/run.json and copies
its stages.txt / summary.txt; every config a LOGOS or Sage arm ran is stored once as
OUT/configs/<sha256[:16]>.json and referenced by hash. Paths inside configs are rewritten
to the input file names, so a config names its inputs exactly as datasets/manifest.tsv does.
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

JOBS = {
    # name: (job directory relative to JOBS_ROOT, what it measured)
    "2026-10-30-lfq-counts": ("lfq-c22/40901452", "LFQ human-01: LOGOS plain, DDA+ and open; Sage default and open; entrapment arms"),
    "2026-10-30-lfq-closed-speed": ("lfq-c22/40903172", "LFQ human-01 closed search: LOGOS CPU and GPU wall time, 5 interleaved repeats"),
    "2026-10-31-lfq-open-ymh4": ("lfq-c22/40928343", "LFQ human-01 open search on ymh4: LOGOS CPU, LOGOS GPU and Sage, 3 interleaved repeats"),
    "2026-10-31-lfq-open-bbc1": ("lfq-c22/40928337", "LFQ human-01 open search on bbc1: LOGOS CPU and Sage, 3 interleaved repeats"),
    "2026-10-31-lfq-open-arw3": ("lfq-c22/40928265", "LFQ human-01 open search on arw3: LOGOS CPU and Sage, 3 interleaved repeats"),
    "2026-10-30-lfq-sage-entrapment": ("lfq-sageE/40901959", "LFQ human-01: Sage default with the entrapment database"),
    "2026-10-31-entrapment-arms": ("entrap-arms/40928398", "Entrapment arms: LFQ open (three rescoring settings), Astral TMTpro LOGOS and Sage"),
    "2026-10-30-astral-tmt-counts": ("astral-tmt/40902791", "Astral TMTpro az01263: LOGOS CPU/GPU and Sage, counts and wall time"),
    "2026-10-30-astral-tmt-speed": ("astral-tmt/40903171", "Astral TMTpro az01263: LOGOS CPU and GPU wall time, 5 interleaved repeats"),
    "2026-10-31-astral-multifile-1": ("astral-multi/40912674", "Astral TMTpro: 1 and 8 files in one process, GPU"),
    "2026-10-31-astral-multifile-2": ("astral-multi/40912675", "Astral TMTpro: files in one process"),
    "2026-10-31-astral-multifile-3": ("astral-multi/40911945", "Astral TMTpro: files in one process"),
    "2026-10-31-raw-to-mzml": ("trfp-multi/40913997", "ThermoRawFileParser 2.0.0-dev converting Astral RAW files to mzML, one and six at once"),
    "2026-10-30-astral-cycle": ("astral/40895348", "Astral DDA cycle replicates (PXD046453), DDA+ with boost, target and entrapment"),
    "2026-10-30-iontrap": ("iontrap/40895345", "Ion-trap CID and HCD iw04 (PXD053241)"),
    "2026-10-30-compil2": ("compil2/40895349", "ComPIL 2.0: one gut RAW against 111.5 M sequences, 3 repeats"),
    "2026-11-01-h2h-current": ("h2h-current/40931267", "Head to head on one binary (79eeea50): LFQ closed and DDA+, Astral TMTpro; LOGOS CPU, LOGOS GPU and Sage interleaved, 3 repeats"),
    "2026-11-01-eval-parity": ("eval-parity/40930749", "Counting parity: every counted arm rerun on CPU; eval/count.py against the engine's counter and the record"),
    "2026-11-01-fill-gaps": ("fill-gaps/40931332", "LOGOS open + calibration + LDA on the target database alone (3 repeats); Sage open with the entrapment database; entrapment database rebuilt from its generator"),
    "2026-10-30-hek293-failed": ("hek/40895347", "HEK293 PXD001468 24-file open search: FAILED during staging (exit 123)"),
}

# Which binary each A/B arm ran, by dash-separated token in the arm name. From each driver's
# declaration (e.g. ab-matrix4.sbatch: declare -A B=([ROOT]=bin-$OLD [NEW]=bin-$NEW)) and the
# submission's OLD/NEW values, which the driver writes to binaries.sha256 in declaration order.
# Arms not listed name their binary in command.txt.
ARM_BINARY = {
    "lfq-c22/40928343": {"*": "bin-79eeea50"},
    "lfq-c22/40928337": {"old": "bin-6f323a4b", "new": "bin-79eeea50"},
    "lfq-c22/40928265": {"old": "bin-98bea377", "mid": "bin-3c2454d3", "new": "bin-59d5908a"},
    "lfq-c22/40903172": {"ROOT": "bin-b3d5a5f3", "NEW": "bin-870fc8ad"},
    "astral-tmt/40903171": {"ROOT": "bin-b3d5a5f3", "NEW": "bin-870fc8ad"},
    "astral-tmt/40902791": {"logos": "bin-a7418138", "base": "bin"},
    "astral-multi/40912674": {"OLD": "bin-b0d3637b", "NEW": "bin-57e480f0"},
    "astral-multi/40912675": {"OLD": "bin-b0d3637b", "NEW": "bin-57e480f0"},
    "entrap-arms/40928398": {"lfq": "bin-79eeea50", "logos": "bin-79eeea50"},
    "h2h-current/40931267": {"*": "bin-79eeea50"},
    "fill-gaps/40931332": {"*": "bin-79eeea50"},
    "astral-multi/40911945": {"*": "bin-870fc8ad"},
}


def binary_of(rel, arm_name, a):
    if "binary" in a:
        return a["binary"]
    for token, b in ARM_BINARY.get(rel, {}).items():
        if token == "*" or token in arm_name.split("-"):
            return b
    return None


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gnu_time(path):
    t = path.read_text()
    w = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", t)
    if not w:
        return None
    wall = sum(float(x) * 60 ** i for i, x in enumerate(reversed(w.group(1).split(":"))))
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", t)
    cpu = re.search(r"Percent of CPU this job got: (\d+)%", t)
    return {"wall_s": round(wall, 3), "peak_rss_gb": round(int(rss.group(1)) / 1048576, 2) if rss else None,
            "cpu_percent": int(cpu.group(1)) if cpu else None}


def strip_paths(text):
    """Every staged path reduced to its file name: configs then name inputs as the manifest does."""
    return re.sub(r"(/dev/shm|/wsu|/tmp)/[^\"\s]*/([^/\"\s]+)", r"\2", text)


def store_config(src, out):
    text = strip_paths(src.read_text())
    data = json.loads(text)
    canon = json.dumps(data, indent=1, sort_keys=True) + "\n"
    key = hashlib.sha256(canon.encode()).hexdigest()[:16]
    (out / "configs").mkdir(parents=True, exist_ok=True)
    (out / "configs" / f"{key}.json").write_text(canon)
    return key


COUNT_FIELDS = ("candidate_rows", "competed_psms", "psms_q01", "sequences_q01", "peptidoforms_q01")


def counts(path):
    d = json.loads(path.read_text())
    return {k: d[k] for k in COUNT_FIELDS if k in d}


def entrap(path):
    rules = json.loads(path.read_text())["rules"]
    return {rule: {lvl: {"nt": v[lvl]["Nt"], "ne": v[lvl]["Ne"], "fdp": v[lvl]["fdp_combined"]} for lvl in ("psm", "seqlvl", "seqs")}
            for rule, v in rules.items() if rule == "expmass"}


def arm(d, out):
    a = {}
    for name in ("command.txt",):
        if (d / name).exists():
            raw = (d / name).read_text().strip()
            m = re.search(r"/(bin(?:-[0-9a-f]{8})?)/logos\b", raw)
            if m:
                a["binary"] = m.group(1)
            a["command"] = strip_paths(raw)
    if (d / "config.json").exists():
        a["config"] = store_config(d / "config.json", out)
    for t in ("time.txt",):
        if (d / t).exists():
            a.update(gnu_time(d / t) or {})
    found = list(d.glob("**/ids.json"))
    if found:
        a["counts"] = counts(found[0])
        a["ids_json_sha256"] = sha256(found[0])
    found = list(d.glob("**/entrap.json")) or list(d.glob("sage.entrap.json"))
    if found:
        a["entrapment"] = entrap(found[0])
    if (d / "sage.ids.json").exists():
        a["counts"] = counts(d / "sage.ids.json")
        a["counted_pin_sha256"] = json.loads((d / "sage.ids.json").read_text()).get("evidence_sha256")
    if (d / "check.json").exists():
        body, _, verdict = (d / "check.json").read_text().strip().rpartition("\n")
        a["parity"] = {"verdict": json.loads(verdict)["verdict"], **{k: v for k, v in json.loads(body).items() if k != "pins"}}
    for name, key in (("tsv.sha256", "sage_results_sha256"), ("pin.sha256", "pin_sha256")):
        if (d / name).exists():
            a[key] = (d / name).read_text().split()[0]
    return a


def host(d):
    t = (d / "host.txt").read_text().splitlines() if (d / "host.txt").exists() else []
    out = {"node": t[0] if t else None, "started": t[1] if len(t) > 1 else None}
    for line in t:
        if line.startswith("job="):
            out.update(dict(kv.split("=") for kv in line.split()))
        if "Model name" in line:
            out["cpu"] = line.split(":", 1)[1].strip()
    gpu = [l for l in t if "," in l and ("NVIDIA" in l or "RTX" in l)]
    if gpu:
        out["gpu"] = gpu[0].split(",")[0].strip()
    return out


def main(root, out):
    root, out = Path(root), Path(out)
    for name, (rel, what) in JOBS.items():
        d = root / rel
        rec = {"name": name, "measured": what, "slurm_job": int(rel.split("/")[1]), **host(d)}
        if (d / "BUILD.json").exists():
            b = json.loads((d / "BUILD.json").read_text())
            rec["build"] = {k: b[k] for k in ("commit", "features", "RUSTFLAGS", "container", "toolchain") if k in b}
        if (d / "binaries.sha256").exists():
            rec["binaries"] = {Path(p).parent.name + "/" + Path(p).name: h for h, p in
                               (l.split() for l in (d / "binaries.sha256").read_text().splitlines() if re.match(r"[0-9a-f]{64}  \S", l))
                               if not p.endswith((".json", ".txt", ".sha256"))}
        if (d / "inputs.sha256").exists():
            rec["inputs"] = {Path(p).name: h for h, p in (l.split() for l in (d / "inputs.sha256").read_text().splitlines() if re.match(r"[0-9a-f]{64}  \S", l))}
        rec["arms"] = {s.name: arm(s, out) for s in sorted(d.iterdir()) if s.is_dir() and s.name not in ("cfg", "learn")}
        rec["arms"] = {k: v for k, v in rec["arms"].items() if v}
        for k, v in rec["arms"].items():
            if "sage" not in k:
                b = binary_of(rel, k, v)
                if b:
                    v["binary"] = b + "/logos"
                    v["binary_sha256"] = rec.get("binaries", {}).get(b + "/logos")
        r = out / "runs" / name
        r.mkdir(parents=True, exist_ok=True)
        (r / "run.json").write_text(json.dumps(rec, indent=1) + "\n")
        for f in ("stages.txt", "summary.txt"):
            if (d / f).exists():
                (r / f).write_text(strip_paths((d / f).read_text()))
        print(f"{name}: {len(rec['arms'])} arms")


if __name__ == "__main__":
    main(*sys.argv[1:])
