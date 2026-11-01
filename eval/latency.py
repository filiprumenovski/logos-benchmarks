"""Per-decision latency of a real-time replay, recomputed from its raw samples.

  latency.py SAMPLES.jsonl [...]      one JSON object per run on stdout

Each SAMPLES line is one MS2: the replay times every decision end to end (`e2e_us`) and
per stage, and records whether the decision and its scored rows equal the offline
reference (`decision_match`, `exact`). Reported per run: the number of decisions,
end-to-end p50 / p95 / p99 / max in ms, how many decisions took longer than 5 ms and
than 80 ms (the Thermo real-time-search budget), the median of each stage, how many decisions
matched the reference, and the SHA-256 of the samples file so the record names exactly
the data it summarises. Percentiles are linear interpolation between order statistics,
the convention of the replay's own log.

Fields are read when present: TKO and HYpro replays carry xcorr_us, rt_us and ms1_us;
the Astral replay does not. Standard library only.
"""
import hashlib
import json
import sys

STAGES = ("search_us", "xcorr_us", "prosit_us", "rt_us", "gbdt_us", "policy_us", "ms1_us", "queue_us")


def percentile(sorted_values, q):
    """Linear interpolation between order statistics (numpy's default)."""
    if not sorted_values:
        return None
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def summarize(path):
    h = hashlib.sha256()
    e2e, stages, n, exact, match, fire, before_next = [], {s: [] for s in STAGES}, 0, 0, None, 0, 0
    with open(path, "rb") as f:
        for raw in f:
            h.update(raw)
            line = raw.strip()
            if not line:
                continue
            r = json.loads(line)
            n += 1
            e2e.append(r["e2e_us"] / 1000.0)
            for s in STAGES:
                if s in r:
                    stages[s].append(r[s] / 1000.0)
            exact += bool(r.get("exact", False))
            if "decision_match" in r:
                match = (match or 0) + bool(r["decision_match"])
            fire += bool(r.get("fire", False))
            before_next += bool(r.get("before_next", False))
    e2e.sort()
    out = {
        "samples_sha256": h.hexdigest(),
        "decisions": n,
        "e2e_ms": {"p50": round(percentile(e2e, 0.50), 4), "p95": round(percentile(e2e, 0.95), 4),
                   "p99": round(percentile(e2e, 0.99), 4), "max": round(e2e[-1], 3)},
        "stage_median_ms": {s[:-3]: round(percentile(sorted(v), 0.5), 4) for s, v in stages.items() if v},
        "over_5_ms": sum(x > 5.0 for x in e2e),
        "over_80_ms": sum(x > 80.0 for x in e2e),
        "exact_rows": exact,
        "decisions_matching_reference": match,  # None when the replay did not record it per decision
        "triggers": fire,
    }
    if before_next:
        out["finished_before_next_ms2"] = before_next
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps({"file": p.rsplit("/", 1)[-1], **summarize(p)}))
