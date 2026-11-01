# LOGOS

LOGOS is a peptide search engine for data-dependent acquisition (DDA) mass spectrometry,
written in Rust with a CUDA backend by Filip Rumenovski at Wayne State University. It reads
Thermo RAW files directly and runs on one CPU node or one GPU. It has not been released, so
this repository carries the evidence instead of the code: every input pinned to a public
deposit by SHA-256, every benchmarked binary pinned by hash to its source commit, a record of
every run, and the counting rule as open Python that gives the engine's own integers.
[METHODOLOGY.md](METHODOLOGY.md) explains how each number was produced, and the typeset report is
[`reports/LOGOS-DDA-benchmarks.pdf`](reports/LOGOS-DDA-benchmarks.pdf).

## Results

- **Repository scale.** An open search (±500 Da, localized) of the Gygi lab's HEK293 deposit
  PXD001468, 24 RAW files and 79.7 GB holding 1,121,149 MS2 spectra, finishes in 12.13 s on one
  NVIDIA H200 (394 GB/min) and reports 132,592 peptide sequences at an entrapment-measured FDR
  of 1.03%. The closed search of the same files takes 7.89 s. Both were recorded on
  28 September 2026 with an earlier build; a rerun on the current build is queued.
- **Against Sage 0.14.7**, same node, same Slurm job, interleaved repeats: closed search is
  12.2× faster on CPU, open search 6.6× faster on CPU and 16.6× on one GPU, and one Astral TMTpro
  file 10.9× and 15.5×. LOGOS reports more sequences than Sage on all three. Its measured error
  is equal to Sage's in closed search, lower on the Astral file and higher in open search, 1.04%
  against 0.90% (table below).
- **Metaproteomics.** One gut-microbiome run against the 111.5 million protein sequences of
  ComPIL 2.0 scores 178.9 billion candidates in 20.26 s on an NVIDIA L40S (recorded
  18 September). The current build takes 65.05 s for identical identifications on an RTX PRO
  4500. I expected the smaller card to account for all of that: it has 82 streaming
  multiprocessors to the L40S's 142, which explains about 1.7×. The remaining factor of 1.9 is
  unexplained until an L40S rerun of the current build, now queued, says whether it is the
  hardware generation or a regression.
- **Every spectrum.** A nine-layer search cascade over the same HEK293 files assigns
  939,455 of the 1,121,149 MS2 spectra (83.8%) at an overall entrapment FDP of 0.87%.
- **Against published searches.** On a 48-file Astral TMTpro study (PXD058160) LOGOS reports
  1,700,508 PSMs at 0.997% entrapment FDP against the authors' 1,333,804 from Comet with LDA,
  ahead in all 48 files.
- **Real time.** Replaying a recorded Thermo real-time-search acquisition one MS2 at a time,
  LOGOS decides whether to trigger an MS3 in a median 0.884 ms (1.205 ms at the 99th percentile)
  on one RTX PRO 4500, and all 27,674 decisions equal the offline reference. Thermo's budget is
  80 ms. A separate replay of all 24 acquisitions in PXD043660, on the authors' own database,
  triggers scans whose identifications carry an entrapment FDP of 0.56% against 2.95% for the
  instrument's recorded triggers, lower in every file.

## How LOGOS works

**Reading.** LOGOS decodes Thermo RAW files itself. Converting one 2.6 GB Astral file to the mzML
that other engines read takes ThermoRawFileParser 341 s, while LOGOS searches that file from
RAW in 3.61 s on a CPU node.

**Residency.** Spectra and the peptide index are built once and stay in memory, on the GPU
when there is one, for every file and every layer of a search. Several files run in one process,
and each file's identifications are byte-identical to searching it alone; eight Astral files take
8.68 s on one GPU, 1.09 s each, where one file alone takes 2.48 s.

**Preselection.** The strongest fragment peaks of each spectrum vote for candidate peptides
through a fragment index. The vote ignores the precursor mass, which is why a ±500 Da open search
of the HEK293 files (12.13 s) costs little more than the closed one (7.89 s). The CPU
preselection uses the fragment-index layout Sage introduced: mass-sorted buckets of 8,192
peptides with their fragments sorted within each bucket.

**Scoring and localization.** Every preselected candidate is scored exactly against its
spectrum, and in open search the mass shift is placed on the residue that explains it best.

**Chimeric spectra (DDA+).** A wide isolation window often holds several precursors. DDA+ keeps
the co-isolated precursors as separate hypotheses and can accept more than one peptide per
spectrum. On the LFQ human file it reports 40,453 sequences against 33,102 for the plain search,
at 0.98% entrapment FDP, and costs 17.00 s against 1.41 s.

**Rescoring.** A Rust implementation of Percolator runs inside the search process; on one
1.87-million-row input it takes 18.88 s where C++ Percolator 3.09 takes 636.90 s, for 59,330
against 59,451 sequences. An optional stage adds predicted fragment intensities and retention
times from AlphaPeptDeep models, run natively, and rescores with a small neural network.

**Real-time decisions.** The same engine also runs one MS2 at a time as it arrives. Candidate
search, XCorr, a predicted-spectrum lookup and a causal retention-time check feed a frozen score
model, whose output the trigger policy turns into fire or skip. Candidate search takes 0.69 ms of the 0.88 ms median decision.
Every percentile in [`runs/2026-10-22-rts-latency`](runs/2026-10-22-rts-latency) is recomputed from
the replay's raw per-MS2 samples by [`eval/latency.py`](eval/latency.py), which reproduces the
replay's own log to four decimals. One of 83,022 timed decisions missed the 80 ms budget, a single
11.3 s host stall.

**Error control.** Every count is at 1% FDR by target-decoy competition. Where a result says
"entrapment", the search also ran against a second database of shuffled proteins that cannot be in
the sample, so every accepted hit to it is a known false discovery and the error is measured
rather than estimated.

## Engineering rules

Every GPU kernel is tested against the CPU implementation, which is the reference. The open
search's identifications hash to `583ae51be609…` from either build.
Results are deterministic, because reductions are order-independent, so the same binary, input and
settings give the same output on every run, and an A/B comparison checks its outputs by hash; only
the timings carry noise, which is why every speed number is a median of interleaved repeats.
Performance work starts from an `nsys` or `ncu` profile, and a change is kept only if it wins an
interleaved A/B with identical output; changes that lost were reverted and are recorded with the
same care as the wins.

## Where LOGOS loses

- CHIMERYS, a chimeric-spectrum engine, beats LOGOS on ion-trap HCD spectra, where LOGOS
  identifies 8.5% fewer sequences. It also leads on three PTM sets combined (5.8%) and, narrowly,
  on chimeric LFQ data.
- On the LFQbench mixtures LOGOS quantifies 17,762 precursors to CHIMERYS's 35,053 at equal
  accuracy.
- DDA+ is twelve times slower than the plain search on the LFQ file. I expected it to help on
  low-resolution ion-trap spectra as it does on the Astral. It does the opposite: on twelve
  Orbitrap Ascend ion-trap files it keeps only 18 to 37% of the plain search's PSMs, most likely
  because a 0.3 Da fragment window lets too many competing candidates into each spectrum.
- In the 24-file real-time replay LOGOS ties Thermo's recorded triggers on raw protein count
  (5,442 each), which our own rule counts as a loss, trails on both HYpro regimes by up to 10
  proteins, and has more proteins in only 6 of the 24 files.
- On a search as short as the closed LFQ one, the GPU build (1.53 s) is slower than the CPU build
  (1.41 s): starting the device costs more than the work it saves.

## Head to head with Sage 0.14.7

Both engines ran in the same Slurm job on the same node, interleaved, with the order rotated
between three repeats. Each time is the median wall time of the whole process, container start
included. Sage reads the mzML that ThermoRawFileParser writes; its conversion is not counted.

<!-- claims:begin -->
| Benchmark | Node | LOGOS CPU | LOGOS GPU | Sage | Speed-up CPU / GPU | Run |
|---|---|---|---|---|---|---|
| Closed DDA, LFQ human | ymh4 | 1.41 s | 1.53 s | 17.25 s | 12.2x / 11.3x | [2026-11-01-h2h-current](runs/2026-11-01-h2h-current) |
| Open −100 to +500 Da, LFQ human | ymh4 | 6.96 s | 2.79 s | 46.23 s | 6.6x / 16.6x | [2026-10-31-lfq-open-ymh4](runs/2026-10-31-lfq-open-ymh4) |
| Open −100 to +500 Da, LFQ human | bbc1 | 7.08 s | -- | 37.79 s | 5.3x / -- | [2026-10-31-lfq-open-bbc1](runs/2026-10-31-lfq-open-bbc1) |
| Open −100 to +500 Da, LFQ human | arw3 | 11.36 s | -- | 106.37 s | 9.4x / -- | [2026-10-31-lfq-open-arw3](runs/2026-10-31-lfq-open-arw3) |
| Astral TMTpro, one file | ymh4 | 3.68 s | 2.58 s | 40.06 s | 10.9x / 15.5x | [2026-11-01-h2h-current](runs/2026-11-01-h2h-current) |

| Benchmark | Engine | Sequences at 1% FDR | Entrapment arm: sequences, FDP | Source |
|---|---|---|---|---|
| Closed DDA, LFQ human | LOGOS | 33,102 | 31,718, 1.24% | [2026-10-30-lfq-counts](runs/2026-10-30-lfq-counts) |
| Closed DDA, LFQ human | Sage 0.14.7 | 32,453 | 31,489, 1.24% | [2026-10-30-lfq-sage-entrapment](runs/2026-10-30-lfq-sage-entrapment) |
| Open −100 to +500 Da, LFQ human | LOGOS | 34,130 | 32,086, 1.00% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
| Open −100 to +500 Da, LFQ human | LOGOS + LDA rescoring | -- | 35,650, 1.10% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
| Open −100 to +500 Da, LFQ human | LOGOS + calibration + LDA | 37,178 | 35,595, 1.04% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
| Open −100 to +500 Da, LFQ human | Sage 0.14.7 | 31,744 | 30,343, 0.90% | [2026-11-01-fill-gaps](runs/2026-11-01-fill-gaps) |
| Astral TMTpro, one file | LOGOS | 7,769 | 7,568, 0.76% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
| Astral TMTpro, one file | Sage 0.14.7 | 7,470 | 7,212, 1.02% | [2026-10-31-entrapment-arms](runs/2026-10-31-entrapment-arms) |
<!-- claims:end -->

Each row is generated from its run records by `reports/from_runs.py`; `--check` fails if this table or the report data drift from them.

## Checking a claim

1. Find the claim's run in `runs/`. `run.json` names the node, CPU and GPU, the LOGOS
   binary and its hash, the hash of every input, and for every arm the configuration hash,
   each repeat's wall time and peak memory, and the counts with the hash of the file they
   came from.
2. Fetch the inputs with `python3 datasets/fetch.py DIR`; it keeps a file only if its size
   and hash match the manifest.
3. Run Sage 0.14.7 with the stored configuration (`configs/<hash>.json`, paths are file names),
   convert with `python3 eval/sage_to_pin.py results.sage.tsv OUT`, and count with
   `python3 eval/count.py OUT`. The counts should equal the run record's.
4. For LOGOS, the run record's `ids_json_sha256` is the hash of the identification counts;
   a released build of the commit in `binaries/BINARIES.tsv` should reproduce it.

`python3 -m unittest discover eval` runs the counting tests.

## Layout

```
README.md, METHODOLOGY.md
datasets/   manifest.tsv (accession, file, bytes, SHA-256), fetch.py
databases/  manifest.tsv, build_entrap.py (the entrapment database generator)
binaries/   BINARIES.tsv (every benchmarked LOGOS binary: SHA-256, source commit, runs)
configs/    every configuration, named by hash
runs/       one directory per Slurm job: run.json, stages.txt, summary.txt
eval/       count.py, sage_to_pin.py, entrapment_ratio.py, latency.py, checks and tests
harness/    the Slurm drivers that produced the newest runs (cluster paths written as $RUN_ROOT, $SCRATCH), and collect.py and collect_rt.py, which write run.json
reports/    the PDF report and the script and data that build it
```

No search outputs are stored here, only their hashes; see METHODOLOGY.md.
