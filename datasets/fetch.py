"""fetch.py OUTDIR [FILE ...]: download the benchmark inputs and verify each against datasets/manifest.tsv.

PRIDE files are located through the PRIDE Archive API; MassIVE files through the MassIVE FTP
server. A file is kept only if its size and SHA-256 equal the manifest's; otherwise it is
deleted and the script exits non-zero. Files already present and matching are skipped.
mzML rows are conversions, not deposits: run ThermoRawFileParser 2.0.0-dev on the RAW of the
same name and compare the hash. Standard library only.
"""
import csv
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

MANIFEST = Path(__file__).with_name("manifest.tsv")
PRIDE = "https://www.ebi.ac.uk/pride/ws/archive/v2/files/byProject?accession={}"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            h.update(block)
    return h.hexdigest()


def pride_urls(accession):
    with urllib.request.urlopen(PRIDE.format(accession)) as r:
        files = json.load(r)
    out = {}
    for f in files:
        for loc in f.get("publicFileLocations", []):
            if loc.get("name") == "FTP Protocol":
                out[f["fileName"]] = loc["value"].replace("ftp://", "https://", 1)
    return out


def massive_url(accession, name):
    return f"ftp://massive.ucsd.edu/v01/{accession}/raw/{name}"


def main(outdir, *only):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(MANIFEST), delimiter="\t"))
    urls, bad = {}, 0
    for r in rows:
        name = r["file"]
        if only and name not in only:
            continue
        if name.endswith(".mzML"):
            print(f"skip {name}: a ThermoRawFileParser conversion, not a deposit")
            continue
        dst = outdir / name
        if not (dst.exists() and str(dst.stat().st_size) == r["bytes"] and sha256(dst) == r["sha256"]):
            acc = r["accession"]
            if acc.startswith("PXD"):
                if acc not in urls:
                    urls[acc] = pride_urls(acc)
                url = urls[acc].get(name)
            else:
                url = massive_url(acc, name)
            if not url:
                print(f"FAIL {name}: not listed in {acc}"); bad += 1; continue
            print(f"get  {name} <- {url}")
            urllib.request.urlretrieve(url, dst)
        if r["bytes"] and str(dst.stat().st_size) != r["bytes"] or sha256(dst) != r["sha256"]:
            print(f"FAIL {name}: size or SHA-256 differs from the manifest; deleted"); dst.unlink(); bad += 1
        else:
            print(f"ok   {name}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(*sys.argv[1:])
