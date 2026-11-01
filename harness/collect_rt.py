"""collect_rt.py LATENCY_SUMMARY.jsonl OUT: run records for the real-time replays.

LATENCY_SUMMARY is eval/latency.py's output over the replays' raw per-MS2 samples
(job 40703237 on ymh4). Writes OUT/runs/2026-10-22-rts-latency/run.json and
OUT/runs/2026-10-22-astral-latency/run.json with every run's recomputed percentiles,
and the records of the decision-quality replays, which were policy replays over frozen
search scores and carry no timing; those outcomes are copied from the cited result
files, labelled recorded.
"""
import json
import re
import statistics
import sys
from pathlib import Path

GPU, CPU, NODE, JOB = "NVIDIA RTX PRO 4500 Blackwell", "AMD EPYC 9454 48-Core Processor", "ymh4", 40703237
BIN = {
    "s3": "d9653c18ef7b963b40ad824f27981ee62e0dfbcdbf5063ccf9dce09d14c8b2ca",
    "s4": "ec18187d58faf7f634a4a4523e71660c51062e62866788638feb6e681e1182d3",
    "s7": "d19178db72b135ec1ba029d9275f50740923a90c468da528e8b88b8043ce66bf",
    "astral-opt": "00ba14c959fa8b48242f9dd0504bdcca643ec916c8234c6806c6bea33245729b",
    "astral-opt3": "199727df3795715bcce465373035f7fe3cb79de1385243e0ebecef6a5e95120d",
}
BASE_FLAGS = ["LAT_FI_FUSED=1", "LAT_INPUT_FUSED=1"]
# A/B set: (file key, binary, flags of arm A, flags arm B adds)
SETS = {
    "fullab3": ("tko", "s3", BASE_FLAGS, ["LAT_MS1_PREFIX=1"]),
    "fullsel1": ("tko", "s7", BASE_FLAGS + ["LAT_MS1_PREFIX=1"], ["LAT_FI_SELBLK=1"]),
    "hyab1": ("hypro", "s4", BASE_FLAGS, ["LAT_MS1_PREFIX=1"]),
    "hysel1": ("hypro", "s7", BASE_FLAGS + ["LAT_MS1_PREFIX=1"], ["LAT_FI_SELBLK=1"]),
}
FILES = {
    "tko": {"raw": "20221127_Ascend_Neo_uPAC_125ng-TKO_TKO_RTSMS3_005.raw", "accession": "PXD043660",
            "raw_sha256": "5b92fcce23cefde11bd6457d1ebf7c52451909eb62c5edc74e590565be6ad123", "raw_bytes": 373088942,
            "fasta_sha256": "57386a0e32d3f9a8be1bc78312050438b0070e7e03f79148f6a183caec6add3c",
            "time_to_next_ms2_p50_ms": 81.0},
    "hypro": {"raw": "20220726_Ascend_2ProteomeMix_Keese_qysrsColumn_HYpro_TMT16_G65min_RTSMS3_CID34IT23MS2_HCD55MS3IT105ms_029.raw",
              "accession": "PXD043660", "raw_sha256": "f65198d427618426dae2fc08129230b0e8710ab44443c8e89fd5af5a99d25844",
              "raw_bytes": 492522338, "fasta_sha256": "18f8477f12b11c83ca08f26d39aee5ab72340f880941c0ac8c921dfbf8dc9401",
              "time_to_next_ms2_p50_ms": 73.8},
}
SETTINGS = ("batch 1, one host thread, CUDA, mimalloc, in-process predicted-spectrum lookup and policy, flat (back-to-back) "
            "replay, RAW decode excluded; precursor 50 ppm, fragments 0.3 Da; interleaved A/B, arms alternating, 3 runs each")


def main(summary, out):
    out = Path(out)
    rows = [json.loads(l) for l in open(summary)]
    arms, sets = {}, {}
    for r in rows:
        m = re.match(r"samples-\d-flat-(\w+)-([AB])-r(\d)-", r["file"])
        if not m:
            continue
        name, arm, rep = m.groups()
        key, b, flags, extra = SETS[name]
        arms[f"{name}-{arm}-r{rep}"] = {"file": key, "binary": b, "binary_sha256": BIN[b],
                                        "flags": flags + (extra if arm == "B" else []), **{k: v for k, v in r.items() if k != "file"}}
        sets.setdefault((name, arm), []).append(r)
    summary_rows = []
    for (name, arm), runs in sorted(sets.items()):
        key, b, flags, extra = SETS[name]
        summary_rows.append({"set": f"{name}-{arm}", "file": key, "binary": b, "flags": flags + (extra if arm == "B" else []),
                             "runs": len(runs), "p50_ms_median": round(statistics.median(x["e2e_ms"]["p50"] for x in runs), 4),
                             "p99_ms_median": round(statistics.median(x["e2e_ms"]["p99"] for x in runs), 4),
                             "max_ms_worst": max(x["e2e_ms"]["max"] for x in runs),
                             "over_80_ms_total": sum(x["over_80_ms"] for x in runs),
                             "decisions": runs[0]["decisions"],
                             "decisions_matching_reference_min": min(x["decisions_matching_reference"] for x in runs),
                             "exact_rows_min": min(x["exact_rows"] for x in runs)})
    rec = {"name": "2026-10-22-rts-latency", "measured": "Real-time MS3 decision latency, replay of recorded Thermo RTS acquisitions (PXD043660), TKO and HYpro files",
           "slurm_job": JOB, "node": NODE, "cpu": CPU, "gpu": GPU, "settings": SETTINGS, "inputs": FILES,
           "source": "binaries assembled from branch claude/orbiter-rts-engine (commits 23aa9ace, 9b4a060d) with patches P1 to P12; no single commit",
           "budgets": {"thermo_rts_cap_ms": 80, "thermo_rts_cap_source": "Shuken et al. 2023, not measured",
                       "time_to_next_ms2_p50_ms": {k: v["time_to_next_ms2_p50_ms"] for k, v in FILES.items()}},
           "summary": summary_rows, "arms": arms,
           "computed_by": "eval/latency.py over the raw per-MS2 samples; samples_sha256 names each file"}
    (out / "runs" / rec["name"]).mkdir(parents=True, exist_ok=True)
    (out / "runs" / rec["name"] / "run.json").write_text(json.dumps(rec, indent=1) + "\n")

    ast = {r["file"]: r for r in rows if not r["file"].startswith("samples-")}
    rec = {"name": "2026-10-22-astral-latency", "measured": "Real-time decision latency on Orbitrap Astral, replay of PXD058160 az01263 (135,711 MS2)",
           "slurm_job": JOB, "node": NODE, "cpu": CPU, "gpu": GPU,
           "inputs": {"raw": "az01263_02152024.raw", "accession": "PXD058160",
                      "raw_sha256": "4d4e3f73b99ca25c76989f396390e483684068d199f2a03ab53242bd71b5b66e",
                      "fasta": "mouse-entrapment.fasta", "fasta_sha256": "525a47b084e499142a1b7a6fb389c2acf053080d7719a016628280d30b9c8074"},
           "budgets": {"recorded_ms2_gap_median_ms": 24.848, "recorded_ms2_gap_min_ms": 2.848},
           "arms": {
               "full-file-flat": {"binary": "astral-opt", "binary_sha256": BIN["astral-opt"], "repeats": 1,
                                  "note": "one run; per-decision match not recorded, row exactness is; triggers equal the offline reference's (30,539)",
                                  **{k: v for k, v in ast["replay-full-opt-flat.jsonl"].items() if k != "file"}},
               "slice-at-recorded-pace": {"binary": "astral-opt3", "binary_sha256": BIN["astral-opt3"], "repeats": 1,
                                          "note": "scans 60,000 to 65,999 replayed at the recorded acquisition pace, one lane",
                                          **{k: v for k, v in ast["lanes-m2-recorded-l1.jsonl"].items() if k != "file"}},
           },
           "computed_by": "eval/latency.py over the raw per-MS2 samples"}
    (out / "runs" / rec["name"]).mkdir(parents=True, exist_ok=True)
    (out / "runs" / rec["name"] / "run.json").write_text(json.dumps(rec, indent=1) + "\n")

    regimes = [  # LOGOS / Thermo recorded: author-pass, modified peptides, raw proteins, MS3, entrapment FDP %
        ("HYpro, Ascend (2 files)", (15954, 15950), (9542, 9390), (2322, 2332), (20036, 20041), (1.793, 6.966)),
        ("HYpro, Eclipse (2 files)", (17408, 17194), (10581, 10473), (2673, 2675), (20333, 20564), (1.479, 6.202)),
        ("TKO11, Ascend (10 files)", (67328, 67176), (16259, 15973), (2528, 2518), (73561, 73645), (0.271, 1.750)),
        ("TKO11, Eclipse (10 files)", (67024, 66693), (16545, 16229), (2665, 2655), (72999, 73202), (0.245, 2.206)),
        ("Pooled, 24 files", (167714, 167013), (30766, 30182), (5442, 5442), (186929, 187452), (0.556, 2.947)),
    ]
    rec = {"name": "2026-10-21-rts-replay", "recorded": True,
           "measured": "Causal replay of 24 Thermo RTS acquisitions (PXD043660): LOGOS trigger decisions against the recorded triggers, authors' exact database",
           "method": "policy replay over frozen offline search scores; rules (v11) chosen on other files; no timing",
           "search": {"slurm_job": 40697435, "binary_sha256": "472ad7d7ab90150240c609e944fd81fd7cbb6bfb34e82b1d122c5daa5f687d1c",
                      "database_sha256": {"authors_exact_human_yeast": "5b36945e269029a54b2369df2c4c69d0c382b7271dc748420e00f14c82399af8",
                                          "tko": "c0de8e71f630296b8f97a7ee1ab024c06cb9ff0fdaf8e9cf37dd1428940389fd"}},
           "fdp_note": "entrapment FDP of the triggered scans' winning identifications; the recorded triggers are classified by the same LOGOS scorer",
           "regimes": [{"regime": g, "author_pass": a, "modified_peptides": p, "raw_proteins": pr, "ms3": m, "entrapment_fdp_pct": f}
                       for g, a, p, pr, m, f in regimes],
           "per_file": {"lower_fdp": "24 of 24 (sign test p = 1.2e-7)", "fewer_ms3": "24 of 24 (p = 1.2e-7)",
                        "more_author_pass": "18 of 24", "more_raw_proteins": "6 of 24"},
           "verdict_strict_rule": "loss: pooled raw proteins tie at 5,442, and a tie fails the rule that every count must be strictly higher",
           "sources": ["orbiter-fasta RESULT-FASTA-pre-addendum6.md:92-96", "sign tests: two-sided binomial over the 24 per-file rows of the same replay"]}
    (out / "runs" / rec["name"]).mkdir(parents=True, exist_ok=True)
    (out / "runs" / rec["name"] / "run.json").write_text(json.dumps(rec, indent=1) + "\n")

    rec = {"name": "2026-10-20-orbiter-replay", "recorded": True,
           "measured": "Replay of 12 Orbiter RTS acquisitions (PXD017823, Schweppe et al. 2020): LOGOS triggers against Orbiter's recorded triggers",
           "method": "policy replay over frozen offline search scores; policies chosen retrospectively, not by the strict causal rule; different database from the authors'",
           "policies": [
               {"policy": "c-open-k1-run-b100", "author_pass": [38169, 30815], "ms3": [40340, 41647], "raw_accessions": [8857, 9245],
                "estimated_false_trigger_pct": [2.713, 16.354]},
               {"policy": "global-q05-k2-b100", "ms3": [39536, 41647], "proteins_at_1pct_picked_protein_fdr": [8710, 8315],
                "proteins_with_2plus_peptides": [6563, 5821], "proteins_with_3plus_peptides": [4316, 3617], "raw_accessions": [8870, 9245]},
           ],
           "pairs": "each pair is LOGOS, Orbiter recorded",
           "sources": ["orbiter-headroom RESULT-Q2.md:225-226", "orbiter-protfdr RESULT-P.md:9-11"]}
    (out / "runs" / rec["name"]).mkdir(parents=True, exist_ok=True)
    (out / "runs" / rec["name"] / "run.json").write_text(json.dumps(rec, indent=1) + "\n")

    rec = {"name": "2026-10-20-broad-window-search", "recorded": True,
           "measured": "Per-MS2 search call at batch 1 with a broad closed precursor window, 4,096 MS2 of PXD017823 c06306",
           "note": "search call only: no scoring model, policy or queueing; a symmetric closed window, not open search, which the live interface does not support",
           "binary_sha256": "48e36dfec841dfe103b41ca5684a6eb572986f112496ca386dcf8fe9b4670514",
           "source_commit": "45c200a3a38148b127f528b407c08fe8d4e01dd4 (branch claude/orbiter-rts-engine)",
           "inputs": {"raw": "c06306_qy_RTS_3cell_2_A1.raw", "raw_sha256": "5b93136f3752a8784aae5c0b576b5e89c7134c6de2e61ff8d52d11e08deeb863",
                      "fasta": "human.fasta", "fasta_sha256": "205f1626241074c9a3d1561f80990c008161190ecebfcd98269e7e2eff390609"},
           "arms": {"pm500da-gpu": {"slurm_job": 40651342, "gpu": "NVIDIA A30", "cpu": "AMD EPYC 9124", "p50_ms": 32.734, "p99_ms": 44.216},
                    "pm500da-cpu": {"slurm_job": "40651642_0..7", "cpu": "AMD EPYC 7313, 8 shards", "p50_ms": 2743.264, "p99_ms": 3871.597},
                    "pm50ppm-cpu": {"slurm_job": "40651642_0..7", "cpu": "AMD EPYC 7313, 8 shards", "p50_ms": 2.014, "p99_ms": 3.966},
                    "pm50ppm-gpu": {"slurm_job": 40651342, "gpu": "NVIDIA A30", "p50_ms": 3.792, "p99_ms": 5.882}},
           "comparator": "Orbiter's published median search time, 17 ms (Schweppe et al. 2020); different hardware",
           "sources": ["orbiter-openlive RESULT-Z.md:17-38"]}
    (out / "runs" / rec["name"]).mkdir(parents=True, exist_ok=True)
    (out / "runs" / rec["name"] / "run.json").write_text(json.dumps(rec, indent=1) + "\n")
    print("wrote 5 real-time records")


if __name__ == "__main__":
    main(*sys.argv[1:])
