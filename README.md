# LOGOS benchmarks

LOGOS is a peptide search engine for data-dependent acquisition (DDA) mass spectrometry. It is
written in Rust with a CUDA backend, reads Thermo RAW files directly, and runs on one CPU node
or one GPU. Filip Rumenovski develops it at Wayne State University.

**Report: [LOGOS-DDA-benchmarks.pdf](LOGOS-DDA-benchmarks.pdf)** (7 pages, A4): every benchmark
with figures, methods and limitations.

LOGOS has not been released, so this repository holds the evidence and not the code. Inputs are
pinned by SHA-256 to public deposits and benchmarked binaries by hash to their source commits.
Each Slurm job left a run record, and the counting rule is open Python that reproduces the
engine's own integers. [METHODOLOGY.md](METHODOLOGY.md) explains how each number was produced.

## Results

| Workload | Result | Hardware | Evidence |
|---|---|---|---|
| Open search, ±500 Da, of the HEK293 deposit PXD001468: 24 RAW files, 79.7 GB, 1,121,149 MS2 | **12.13 s**, 394 GB/min; 132,592 sequences at 1.03% entrapment FDP | 1× H200 NVL | Earlier build, 28 Sep 2026; notes |
| Closed search of the same 24 files | **7.89 s**, 606 GB/min | 1× H200 NVL | Earlier build, 28 Sep 2026; notes |
| Nine-layer cascade over the same files, each layer searching what the earlier ones left | **939,455 of 1,121,149 MS2 explained (83.8%)** at 0.87% entrapment FDP | 1× L40S | Earlier build; notes |
| ComPIL 2.0 metaproteome: one gut RAW against 111.5 million protein sequences | **178.9 billion candidates scored in 20.26 s** | 1× L40S | Earlier build, 18 Sep 2026; notes |
| The same ComPIL 2.0 search, current build | 65.05 s, identical identifications | 1× RTX PRO 4500 | [2026-10-30-compil2](runs/2026-10-30-compil2) |
| Against Sage 0.14.7 on the same node, interleaved | **12.2×** faster closed on CPU; open search **5.3 to 9.4×** on CPU across three nodes and **16.6×** on one GPU; **10.9× / 15.5×** (CPU / GPU) on an Astral TMTpro file; more sequences on all three | EPYC 9454 with RTX PRO 4500; EPYC 9374F; Xeon Gold 6326 | [Table below](#head-to-head-with-sage-0147) |
| Astral TMTpro study PXD058160, 48 files | **1,700,508 PSMs** at 0.997% entrapment FDP, against the authors' 1,333,804 from Comet with LDA; ahead in all 48 files | RTX PRO 4500 | Earlier build; notes |
| Real-time acquisition decision, one MS2 at a time, against Thermo's 80 ms budget | **0.884 ms** median, 1.205 ms at p99; all 27,674 decisions equal the offline reference | RTX PRO 4500 | [2026-10-22-rts-latency](runs/2026-10-22-rts-latency) |
| Replay of the 24 real-time-search acquisitions in PXD043660, on the authors' database | LOGOS triggers **fewer MS3 scans with lower error in all 24 files**: pooled entrapment FDP 0.56%, where the instrument's recorded triggers reach 2.95% | RTX PRO 4500 | [2026-10-21-rts-replay](runs/2026-10-21-rts-replay) |

FDP is the false-discovery proportion measured by entrapment (see [Error control](#error-control)).

A row whose evidence is a run record can be checked all the way down: binary hash, input
hashes, configuration, each repeat's wall time, and the hash of the counted output. A row marked
"notes" was recorded with an earlier build. Its date, hardware and settings are in the report,
but the run log behind it is private, so it carries no hashes here.

On ComPIL 2.0 the current build is 3.2× slower than the recorded one, on different hardware, and
the cause is open. The RTX PRO 4500 has 82 streaming multiprocessors to the L40S's 142, which
accounts for about 1.7×. Whether the remaining 1.9× is the
hardware generation or a regression is not yet known, because the current build has not been run
on an L40S.

## Head to head with Sage 0.14.7

Both engines ran in the same Slurm job on the same node with 22 cores. Runs were interleaved,
and the order rotated between three repeats. Each time is the median wall time of the whole
process, container start included. Sage reads the mzML that ThermoRawFileParser writes, and its
conversion time is not counted. Every count comes from the same open counting rule,
[`eval/count.py`](eval/count.py).

<!-- claims:begin -->
| Benchmark | CPU / GPU | LOGOS CPU | LOGOS GPU | Sage | Speed-up CPU / GPU | Run |
|---|---|---|---|---|---|---|
| Closed DDA, LFQ human | EPYC 9454 / RTX PRO 4500 | 1.41 s | 1.53 s | 17.25 s | 12.2× / 11.3× | [2026-11-01-h2h-current](runs/2026-11-01-h2h-current) |
| Open −100 to +500 Da, LFQ human | EPYC 9454 / RTX PRO 4500 | 6.96 s | 2.79 s | 46.23 s | 6.6× / 16.6× | [2026-10-31-lfq-open-ymh4](runs/2026-10-31-lfq-open-ymh4) |
| Open −100 to +500 Da, LFQ human | EPYC 9374F / none | 7.08 s | n/a | 37.79 s | 5.3× / n/a | [2026-10-31-lfq-open-bbc1](runs/2026-10-31-lfq-open-bbc1) |
| Open −100 to +500 Da, LFQ human | Xeon Gold 6326 / none | 11.36 s | n/a | 106.37 s | 9.4× / n/a | [2026-10-31-lfq-open-arw3](runs/2026-10-31-lfq-open-arw3) |
| Astral TMTpro, one file | EPYC 9454 / RTX PRO 4500 | 3.68 s | 2.58 s | 40.06 s | 10.9× / 15.5× | [2026-11-01-h2h-current](runs/2026-11-01-h2h-current) |

| Benchmark | Engine | Sequences at 1% FDR | Entrapment arm: sequences, FDP | Source |
|---|---|---|---|---|
| Closed DDA, LFQ human | LOGOS | 33,102 | 31,718, 1.24% | [2026-10-30-lfq-counts](runs/2026-10-30-lfq-counts) |
| Closed DDA, LFQ human | Sage 0.14.7 | 32,453 | 31,489, 1.24% | [2026-10-30-lfq-sage-entrapment](runs/2026-10-30-lfq-sage-entrapment) |
| Open −100 to +500 Da, LFQ human | LOGOS | 34,130 | 32,086, 1.00% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
| Open −100 to +500 Da, LFQ human | LOGOS + LDA rescoring | n/a | 35,650, 1.10% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
| Open −100 to +500 Da, LFQ human | LOGOS + calibration + LDA | 37,178 | 35,595, 1.04% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
| Open −100 to +500 Da, LFQ human | Sage 0.14.7 | 31,744 | 30,343, 0.90% | [2026-11-01-fill-gaps](runs/2026-11-01-fill-gaps) |
| Astral TMTpro, one file | LOGOS | 7,769 | 7,568, 0.76% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
| Astral TMTpro, one file | Sage 0.14.7 | 7,470 | 7,212, 1.02% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
<!-- claims:end -->

`reports/from_runs.py` generates both tables from the run records, and `--check` fails in CI if
the tables or the report data drift from them.

Without rescoring, LOGOS's open search reports 32,086 entrapment-arm sequences at 1.00% FDP,
against Sage's 30,343 at 0.90%. The calibrated and rescored arm reports more sequences but at a
higher error, 1.04%. In closed search both engines measure 1.24%.

## Where LOGOS loses

- **Ion-trap spectra and modifications.** On ion-trap HCD spectra LOGOS identifies 8.5% fewer
  sequences than CHIMERYS, a chimeric-spectrum engine. CHIMERYS also leads on three PTM sets
  combined, by 5.8%, and narrowly on chimeric LFQ data.
- **Quantification.** On the LFQbench mixtures LOGOS quantifies 17,762 precursors to CHIMERYS's
  35,053 at equal accuracy.
- **DDA+ on low-resolution data.** DDA+ is twelve times slower than the plain search on the LFQ
  file. I expected it to help on low-resolution ion-trap spectra as it does on the Astral, and
  it does the opposite: on twelve Orbitrap Ascend ion-trap files it keeps only 18 to 37% of the
  plain search's PSMs. A likely cause, not yet tested, is that the 0.3 Da fragment window admits
  too many competing candidates into each spectrum.
- **Proteins in the real-time replay.** The replay's lower error does not buy more proteins.
  Pooled over the 24 files, LOGOS and the recorded triggers both reach 5,442 proteins. LOGOS
  trails by up to 10 proteins on the HYpro files and leads in only 6 of the 24 files. Under this
  repository's rule that a win must be strictly higher, the tie counts as a loss.
- **Short searches on a GPU.** On a search as short as the closed LFQ one, the GPU build (1.53 s)
  is slower than the CPU build (1.41 s), because starting the device costs more than the work it
  saves.

## How LOGOS works

**Reading.** LOGOS decodes Thermo RAW files itself. ThermoRawFileParser takes 341 s to convert
one 2.6 GB Astral file to mzML. LOGOS reads and searches the same RAW file in 3.61 s on a CPU
node.

**Residency.** Spectra and the peptide index are built once and stay in memory, on the GPU when
there is one, for every file and every layer of a search. Several files share one process, and
each file's identifications are byte-identical to searching it alone. Eight Astral files take
8.68 s together on one GPU, 1.09 s each, where one file alone takes 2.48 s.

**Preselection.** The strongest fragment peaks of each spectrum vote for candidate peptides
through a fragment index. The vote does not use the precursor mass, so widening the precursor
window to ±500 Da adds little cost: 12.13 s against 7.89 s on the HEK293 files. The CPU index
uses the layout Sage introduced, which is mass-sorted buckets of 8,192 peptides with the
fragments sorted within each bucket.

**Scoring and localization.** Every preselected candidate is scored exactly against its
spectrum. In open search, LOGOS places the mass shift on the residue that explains the spectrum
best.

**Chimeric spectra (DDA+).** A wide isolation window often holds several precursors. DDA+
keeps each co-isolated precursor as a separate hypothesis and can accept more than one peptide
per spectrum. On the LFQ human file it reports 40,453 sequences at 0.98% entrapment FDP, against
33,102 for the plain search, and takes 17.00 s against 1.41 s.

**Rescoring.** A Rust implementation of Percolator runs inside the search process. On one
1.87-million-row input it takes 18.88 s and reports 59,330 sequences, where C++ Percolator 3.09
takes 636.90 s and reports 59,451. An optional stage adds predicted fragment intensities and
retention times from AlphaPeptDeep models, run natively, and rescores with a small neural
network.

**Real-time decisions.** The same engine can run on one MS2 at a time, as each spectrum arrives
from the instrument. A candidate search, XCorr, a predicted-spectrum lookup and a retention-time
check that uses only earlier spectra feed a frozen score model. The trigger policy turns that
score into a decision to fire or skip the MS3. Candidate search takes 0.69 ms of the 0.88 ms
median decision.

### Error control

Every count is at 1% FDR by target-decoy competition. Where a result says "entrapment", the
search also ran against a second database of shuffled proteins that cannot be in the sample.
Every accepted hit to that database is a known false discovery, so the error is measured rather
than estimated. The FDP formula and the counting rule are in [METHODOLOGY.md](METHODOLOGY.md).

## How the numbers are kept honest

- **The CPU build is the reference.** Every GPU kernel is tested against it. The open search's
  identifications hash to `583ae51be609…` from either build.
- **Results are deterministic.** Reductions do not depend on thread order, so the same binary,
  input and settings give the same output on every run. An A/B comparison checks outputs by hash,
  and only the timings vary, which is why each speed is a median of interleaved repeats.
- **Changes are kept only on a measured win.** Performance work starts from an `nsys` or `ncu`
  profile. A change stays only if it wins an interleaved A/B with identical output. Changes that
  lost were reverted, and they are recorded as carefully as the wins.
- **Counts come from an open counter.** [`eval/count.py`](eval/count.py) reproduces the
  engine's own integers on five LOGOS arms and four Sage arms. Its tests are in
  [`eval/test_count.py`](eval/test_count.py).
- **Latency is recomputed from raw samples.** [`eval/latency.py`](eval/latency.py) recomputes
  every real-time percentile from the replay's per-MS2 samples. It matches the replay's own log
  to four decimals and records the hash of the samples it read. One of 83,022 timed decisions
  missed the 80 ms budget, because of a single 11.3 s host stall.

## Checking a claim

1. Find the claim's run in `runs/`. `run.json` names the node, CPU and GPU, and hashes the
   LOGOS binary and every input. For every arm it gives the configuration hash,
   each repeat's wall time and peak memory, and the counts with the hash of the file they came
   from.
2. Fetch the inputs with `python3 datasets/fetch.py DIR`. It keeps a file only if its size and
   hash match the manifest.
3. Run Sage 0.14.7 with the stored configuration (`configs/<hash>.json`; paths are file names).
   Convert its output with `python3 eval/sage_to_pin.py results.sage.tsv OUT`, then count with
   `python3 eval/count.py OUT`. The counts should equal the run record's.
4. For LOGOS, the run record's `ids_json_sha256` is the hash of the identification counts. A
   released build of the commit in `binaries/BINARIES.tsv` should reproduce it.

`python3 -m unittest discover eval` runs the counting and latency tests.

## Layout

```
README.md, METHODOLOGY.md, LOGOS-DDA-benchmarks.pdf
datasets/   manifest.tsv (accession, file, bytes, SHA-256), fetch.py
databases/  manifest.tsv, build_entrap.py (generates the entrapment database)
binaries/   BINARIES.tsv (every benchmarked LOGOS binary: SHA-256, source commit, runs)
configs/    every configuration, named by hash
runs/       one directory per Slurm job: run.json, stages.txt, summary.txt
eval/       count.py, sage_to_pin.py, entrapment_ratio.py, latency.py, checks and tests
harness/    the Slurm drivers behind the newest runs, and collect.py and collect_rt.py,
            which write run.json (cluster paths appear as $RUN_ROOT and $SCRATCH)
reports/    the script, LaTeX source and data that build the PDF report
```

No search outputs are stored here, only their hashes; see [METHODOLOGY.md](METHODOLOGY.md).
