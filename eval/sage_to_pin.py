"""Sage's PSM table as a directory count.py reads.

  sage_to_pin.py results.sage.tsv DIR [SCORE]

Writes DIR/evidence.pin and DIR/percolator/percolator.{psms,decoys}.tsv, every
row ranked by SCORE (default sage_discriminant_score, Sage's own final score
after its LDA rescoring). Peptides get '-.' / '.-' flanks because count.py strips
two characters per side; Sage's bracketed modifications are removed by the
counter. Sage's results are counted by exactly the rule applied to LOGOS.
"""
import csv
import os
import sys

csv.field_size_limit(sys.maxsize)


def convert(src, d, key="sage_discriminant_score"):
    os.makedirs(f"{d}/percolator", exist_ok=True)
    n = 0
    with open(src, newline="") as f, open(f"{d}/evidence.pin", "w") as pin, \
            open(f"{d}/percolator/percolator.psms.tsv", "w") as psms, \
            open(f"{d}/percolator/percolator.decoys.tsv", "w") as decoys:
        pin.write("SpecId\tLabel\tScanNr\tExpMass\tCalcMass\tprimary_score\tPeptide\tProteins\n")
        tabs = {1: psms, -1: decoys}
        for t in tabs.values():
            t.write("PSMId\tscore\tpeptide\n")
        for r in csv.DictReader(f, delimiter="\t"):
            label = int(r["label"])
            scan = r["scannr"].rsplit("scan=", 1)[-1]
            sid = f"{r['filename']}_{scan}_{r['charge']}_{r['rank']}"
            pep = f"-.{r['peptide']}.-"
            pin.write(f"{sid}\t{label}\t{scan}\t{r['expmass']}\t{r['calcmass']}\t{r['hyperscore']}\t{pep}\t"
                      + "\t".join(r["proteins"].split(";")) + "\n")
            tabs[label].write(f"{sid}\t{r[key]}\t{pep}\n")
            n += 1
    return n


if __name__ == "__main__":
    src, d = sys.argv[1:3]
    key = sys.argv[3] if len(sys.argv) > 3 else "sage_discriminant_score"
    print(f"{convert(src, d, key)} rows from {src} scored by {key}")
