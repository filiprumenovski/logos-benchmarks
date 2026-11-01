# Methodology

How every number in this repository was produced, and how to check it without the
LOGOS binary.

## Inputs

Every input file is listed in [`datasets/manifest.tsv`](datasets/manifest.tsv) (instrument
files and the mzML conversions Sage reads) and [`databases/manifest.tsv`](databases/manifest.tsv)
(search databases), each with its public accession, size and SHA-256.
[`datasets/fetch.py`](datasets/fetch.py) downloads the deposits and keeps a file only if
its size and hash match. Every Slurm job hashed its inputs before running and refused
to start on a file whose hash differed from the recorded one; those hashes are in each
`runs/*/run.json` under `inputs`. Across all runs each file name has exactly one hash.

The entrapment database for the LFQ human search is generated, not downloaded:
[`databases/build_entrap.py`](databases/build_entrap.py) shuffles every target protein
between its tryptic cleavage sites (the C-terminal K/R and a leading M stay in place)
with seed 20260922, and the result's SHA-256 is in the database manifest.

## Binaries

LOGOS is not released. [`binaries/BINARIES.tsv`](binaries/BINARIES.tsv) lists the SHA-256
of every LOGOS binary that produced a number here, with the source commit it was built
from and the runs that used it. When LOGOS is released, a build of the same commit can
be compared against these hashes. Each run record names, for every timed arm, the
binary it executed and that binary's hash.

All LOGOS binaries were built in the same container (CUDA 12.9), with
`RUSTFLAGS="-C target-cpu=x86-64-v3"`, CUDA architecture sm_120 and the features
`rawr,cuda,mimalloc`. Builds from commit 3c2454d3 onward have link-time optimisation off;
earlier builds have it on.

Sage is the 0.14.7 release binary for x86-64 Linux
(SHA-256 `d3820543…`), run with `--disable-telemetry-i-dont-want-to-improve-sage`.

## Configurations

Every configuration a timed or counted arm ran is in [`configs/`](configs/), named by
the first 16 hex digits of its SHA-256 and referenced from the run record. Paths are
reduced to file names, which are the names in the manifests.

Sage runs its release defaults, including its LDA rescoring and retention-time model,
with the chemistry set to match LOGOS's: enzyme, missed cleavages, peptide length,
fixed and variable modifications, precursor and fragment tolerances, charge range and
isotope errors. The exact Sage files are the `sage*` configs referenced from the run
records. LOGOS reads Thermo RAW files directly; Sage reads the mzML that
ThermoRawFileParser 2.0.0-dev writes from the same RAW. Conversion time is not
included in Sage's wall time.

## Timing

- Wall time is GNU `time -v` around the whole process, container start included, from
  input files to identifications at 1% FDR. Inputs are staged in RAM (`/dev/shm`)
  first, so disk speed is not measured.
- Engines are timed in the same Slurm job on the same node, interleaved, with the
  order rotated between repeats, after one untimed warm-up run of each.
- The reported time is the median of three or more repeats; the run records hold
  every repeat. Ratios are taken within one node, because Sage's speed varies by a
  factor of 2.8 across the nodes used.
- Warrior nodes are shared with other tenants. The load average before and after
  every run is in each run's `stages.txt`.

## Counting

[`eval/count.py`](eval/count.py) states and implements the counting rule; its docstring
is the specification. In short: one winner per (scan, precursor mass), a decoy winning
an exact score tie; acceptance in whole groups of equal score at
q = running minimum of (D + 1)/T ≤ 1%; sequences counted as the best PSM per
I/L-normalised bare sequence, then accepted by the same rule. The same program
counts LOGOS and Sage: [`eval/sage_to_pin.py`](eval/sage_to_pin.py) writes Sage's
`results.sage.tsv` as the PIN and score tables the counter reads, ranked by
`sage_discriminant_score`.

`python3 -m unittest discover eval` runs the tests; each planted error in the rule
(strict instead of non-strict 1%, target winning a tie, split tie groups, no I/L merge,
the wrong FDP denominator) fails at least one test.

LOGOS's engine counts with a Rust implementation of the same rule. The run
[`runs/2026-11-01-eval-parity`](runs/2026-11-01-eval-parity) reran every counted arm
on CPU, kept the outputs, and checked that the open counter, the engine's counter and
the recorded counts agree on every integer.

## Error control

Every identification count is at 1% FDR by target-decoy competition. Where a result
says "entrapment", its error was also measured: the search ran against the target
database plus an entrapment database of equal size whose sequences cannot be in the
sample, so every accepted entrapment hit is a known false discovery. With N_t accepted
targets from the real database, N_e from the entrapment database and r the ratio of
entrapment to target sequence space,

    FDP = N_e (1 + 1/r) / (N_t + N_e)

r is computed from each search's own digestion by
[`eval/entrapment_ratio.py`](eval/entrapment_ratio.py): 1.0606 for the LFQ human
database, 0.9998 for the Astral mouse database.

## Determinism and parity

The same binary, input and settings give byte-identical identifications on every run;
the CPU and GPU builds give byte-identical identifications to each other. Run records
carry the SHA-256 of every `ids.json`, so a repeat that differs is visible.

## What is not here

Search outputs (PIN files, score tables, Sage's `results.sage.tsv`) are not in the
repository: they are hundreds of megabytes per run. Their SHA-256 values are in the
run records, LOGOS is deterministic, and the outputs of the parity run are kept on the
cluster and available on request.
