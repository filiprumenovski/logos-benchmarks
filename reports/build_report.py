"""LOGOS DDA benchmark report, typeset: data/*.json -> figures (matplotlib, PDF) + LaTeX -> PDF (XeLaTeX).

Usage: python3 build_report.py            (writes LOGOS-DDA-benchmarks.pdf beside this script)
Needs matplotlib and a TeX Live with pdflatex, lmodern, booktabs, tabularx, caption, microtype, enumitem.
"""
import json, pathlib, re, shutil, subprocess, tempfile

import matplotlib
matplotlib.use("pdf")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).parent
DATA = HERE / "data"
load = lambda n: json.load(open(DATA / n))["rows"]
speed, ids, multi, conv = load("speed.json"), load("ids.json"), load("multifile.json"), load("conversion.json")
cover, scale, losses, catalog = load("coverage.json"), load("scale.json"), load("losses.json"), load("catalog.json")
board, speedup = load("scoreboard.json"), load("speedup.json")
power = json.load(open(DATA / "power.json"))

INK, MUTED, GRID = "#000000", "#333333", "#d9d9d9"
C_CPU, C_GPU, C_SAGE = "#3a3a3a", "#9a9a9a", "#ffffff"
plt.rcParams.update({"font.family": "serif", "font.serif": ["cmr10"], "mathtext.fontset": "cm", "axes.unicode_minus": False,
                     "axes.formatter.use_mathtext": True, "font.size": 8, "pdf.fonttype": 42, "axes.edgecolor": INK,
                     "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.color": INK,
                     "ytick.color": INK, "axes.labelcolor": INK, "patch.edgecolor": INK, "patch.linewidth": 0.5,
                     "hatch.linewidth": 0.4})


def mt(text):
    """Figure text in Computer Modern: symbols cmr10 lacks go through mathtext."""
    return str(text).replace("\u00b1", r"$\pm$").replace("\u00d7", r"$\times$").replace("\u2212", r"$-$")

SPECIAL = {"±": r"\ensuremath{\pm}", "−": r"\ensuremath{-}", "✓": r"\ensuremath{\checkmark}", "·": r"\textperiodcentered{}",
           "→": r"\ensuremath{\rightarrow}", "…": r"\dots{}", "Δ": r"\ensuremath{\Delta}", "≥": r"\ensuremath{\geq}",
           "≤": r"\ensuremath{\leq}", "µ": r"\ensuremath{\mu}", "×": r"\ensuremath{\times}"}


def tex(s):
    s = "" if s is None else str(s)
    s = s.replace("**", "").replace("`", "").replace("__", "")
    out = []
    for ch in s:
        if ch in "\\":
            out.append(r"\textbackslash{}")
        elif ch in "&%$#_{}":
            out.append("\\" + ch)
        elif ch == "~":
            out.append(r"\textasciitilde{}")
        elif ch == "^":
            out.append(r"\textasciicircum{}")
        elif ch in SPECIAL:
            out.append(SPECIAL[ch])
        else:
            out.append(ch)
    # Let long tokens (paths, hashes) break.
    s = re.sub(r"([/:,=])(?=[^\s\d])", r"\1\\allowbreak{}", "".join(out))
    return s.replace(r"\_", r"\_\allowbreak{}")


num = lambda v: "--" if v is None else f"{v:,}"
sec = lambda v: "--" if v is None else (f"{v:.2f}" if v < 100 else f"{v:.1f}")
ratio = lambda a, b: f"{a / b:.1f}" if a and b else "--"
by = {r["key"]: r for r in speed}


def fig_speed(path):
    rows = speed
    fig, ax = plt.subplots(figsize=(7.2, 2.2))
    h = 0.26
    names = [("logos_cpu_s", C_CPU, "LOGOS, CPU"), ("logos_gpu_s", C_GPU, "LOGOS, one GPU"), ("sage_s", C_SAGE, "Sage 0.14.7, CPU")]
    for k, (col, color, name) in enumerate(names):
        first = True
        for i, r in enumerate(rows):
            v = r[col]
            if v is None:
                continue
            y = i + (k - 1) * h
            ax.barh(y, v, height=h * 0.9, color=color, label=name if first else None, edgecolor=INK, linewidth=0.5)
            ax.text(v * 1.06, y, f"{v:.2f} s" if v < 100 else f"{v:.0f} s", va="center", fontsize=6.3, color=MUTED)
            first = False
    ax.set_xscale("log")
    ax.set_xlim(1, 450)
    ticks = [1, 3, 10, 30, 100, 300]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t}" for t in ticks])
    ax.minorticks_off()
    ax.set_xlabel("Wall time to identifications at 1% FDR (s, log scale)")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{r['benchmark']} ({r['node'].split(' · ')[0]})" for r in rows], fontsize=7)
    ax.invert_yaxis()
    ax.grid(axis="x", color=GRID, linewidth=0.4)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="lower right", fontsize=6.8, frameon=False)
    fig.tight_layout(pad=0.2)
    fig.savefig(path)
    plt.close(fig)


def fig_throughput(path):
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 1.55), gridspec_kw={"wspace": 0.62})
    def panel(ax, rows, label, value, color, log, xlab, tag):
        vals = [value(r) for r in rows]
        ys = list(range(len(rows)))
        ax.barh(ys, vals, height=0.6, color=[color(r) for r in rows], edgecolor=INK, linewidth=0.5)
        for y, v in zip(ys, vals):
            ax.text(v * 1.08 if log else v + max(vals) * 0.02, y, f"{v:.2f}" if v < 100 else f"{v:.0f}", va="center", fontsize=6.6, color=INK)
        if log:
            ax.set_xscale("log")
            ax.set_xlim(1, max(vals) * 4)
            ticks = [t for t in (1, 3, 10, 30, 100, 300, 1000) if t <= max(vals) * 4]
            ax.set_xticks(ticks)
            ax.set_xticklabels([str(t) for t in ticks])
            ax.minorticks_off()
        else:
            ax.set_xlim(0, max(vals) * 1.25)
        ax.set_yticks(ys)
        ax.set_yticklabels([label(r) for r in rows], fontsize=6.8)
        ax.invert_yaxis()
        ax.set_xlabel(xlab, fontsize=7)
        ax.grid(axis="x", color=GRID, linewidth=0.4)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_title(tag, loc="left", fontsize=8)
    panel(a, multi, lambda r: f"{r['backend']}, {r['files']} file{'s' if r['files'] > 1 else ''}", lambda r: r["wall_s"] / r["files"],
          lambda r: C_CPU if r["backend"] == "CPU" else C_GPU, False, "Wall time per file (s)", "(a) Files searched in one run")
    panel(b, conv, lambda r: r["case"].replace(" (no conversion)", "").replace("LOGOS whole search", "LOGOS search"), lambda r: r["seconds_per_file"],
          lambda r: C_CPU if r["key"] == "logos-cpu" else (C_GPU if r["key"] == "logos-gpu" else C_SAGE), True, "Seconds per Astral file (log scale)",
          "(b) RAW to mzML conversion vs LOGOS search")
    fig.savefig(path, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def fig_power(path):
    """Every like-for-like speed-up on one log axis, grouped by what is being compared."""
    groups = [("Search, against Sage 0.14.7 on the same node", [
                  (f"{r['benchmark']}, {r['backend']}", r["x"], C_GPU if r["backend"] == "GPU" else C_CPU) for r in speedup])]
    for g in dict.fromkeys(r["group"] for r in power["speedups"]):
        groups.append((g, [(r["label"], r["comp_s"] / r["logos_s"], C_CPU)
                           for r in power["speedups"] if r["group"] == g]))
    n = sum(len(rows) for _, rows in groups)
    fig, ax = plt.subplots(figsize=(7.3, 0.2 * n + 0.75))
    import matplotlib.transforms as mtrans
    tr = mtrans.blended_transform_factory(ax.transAxes, ax.transData)
    y, ys, labels = 0.0, [], []
    for title, rows in groups:
        ax.text(-0.012, y - 0.95, title, fontsize=7, fontstyle="italic", ha="right", va="center", transform=tr)
        for label, x, color in rows:
            ax.barh(y, x, height=0.66, color=color, edgecolor=INK, linewidth=0.5)
            ax.text(x * 1.07, y, f"{x:.1f}" + r"$\times$", va="center", fontsize=6.6)
            ys.append(y); labels.append(mt(label)); y += 1
        y += 1.4
    ax.set_xscale("log")
    ax.set_xlim(1, 260)
    ax.set_xticks([1, 2, 5, 10, 20, 50, 100])
    ax.set_xticklabels([f"{t}" + r"$\times$" for t in (1, 2, 5, 10, 20, 50, 100)])
    ax.minorticks_off()
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=6.6)
    ax.set_ylim(y - 1.2, -1.6)
    ax.set_xlabel("Speed-up of LOGOS over the comparator (comparator time / LOGOS time, log scale)", fontsize=7)
    ax.grid(axis="x", color=GRID, linewidth=0.4)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def fig_cascade(path):
    """Waterfall: each layer searches only what every earlier layer left unexplained."""
    c = power["cascade"]
    total, layers = c["total_ms2"], c["layers"]
    fig, ax = plt.subplots(figsize=(7.3, 0.2 * len(layers) + 0.85))
    left = 0.0
    for i, l in enumerate(layers):
        w = 100 * l["n"] / total
        hot = l["fdp"] > 1.0
        ax.barh(i, w, left=left, height=0.66, color=C_PAR if hot else C_WIN, edgecolor=INK, linewidth=0.5, hatch="//////" if hot else None)
        ax.text(left + w + 1.6, i, f"{l['n']:,}   FDP {l['fdp']:.2f}%", va="center", fontsize=6.6)
        left += w
    ax.axvline(100 * c["explained"] / total, color=INK, linewidth=0.6, linestyle=(0, (3, 2)))
    ax.text(100 * c["explained"] / total - 0.8, -0.95, f"{100 * c['explained'] / total:.1f}% of all MS2 explained, entrapment FDP {c['fdp']:.2f}%",
            ha="right", va="center", fontsize=6.8)
    ax.set_xlim(0, 112)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xticklabels([f"{t}%" for t in (0, 20, 40, 60, 80, 100)])
    ax.set_yticks(range(len(layers)))
    ax.set_yticklabels([mt(l["name"]) for l in layers], fontsize=6.6)
    ax.set_ylim(len(layers) - 0.5, -1.45)
    ax.set_xlabel(f"Share of all {total:,} MS2 spectra in PXD001468 (cumulative)", fontsize=7)
    ax.grid(axis="x", color=GRID, linewidth=0.4)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


C_WIN, C_PAR, C_LOSS = "#3a3a3a", "#b5b5b5", "#ffffff"


def fig_force(path):
    fig = plt.figure(figsize=(7.3, 3.55))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.32, 1], wspace=0.95)
    a, b = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    groups = [("Sage", "vs Sage"), ("Published", "vs published results"), ("CHIMERYS", "vs CHIMERYS")]
    ys, labels, y = [], [], 0
    heads = []
    for g, title in groups:
        rows = [r for r in board if r["group"] == g]
        heads.append((y - 1.05, title))
        for r in rows:
            d = r["delta_pct"]
            color = C_WIN if d > 1 else (C_LOSS if d < -1 else C_PAR)
            a.barh(y, d, height=0.62, color=color, edgecolor=INK, linewidth=0.5, hatch="//////" if d < -1 else None)
            filled = "entrapment" in r["error"]
            a.plot([d], [y], marker="o", ms=3.0, mfc=INK if filled else "white", mec=INK, mew=0.7, zorder=3)
            a.text(max(d, 0) + 0.9, y, (f"+{d:.1f}" if d >= 0 else f"$-${-d:.1f}") + "%", va="center", ha="left", fontsize=6.6, color=INK)
            ys.append(y); labels.append(mt(r["dataset"])); y += 1
        y += 1.55
    import matplotlib.transforms as mtrans
    tr = mtrans.blended_transform_factory(a.transAxes, a.transData)
    for yy, t in heads:
        a.text(-0.035, yy + 0.15, t, fontsize=7, fontstyle="italic", va="center", ha="right", color=INK, clip_on=False, transform=tr)
    a.axvline(0, color="#444444", linewidth=0.6)
    a.set_xlim(-10.5, 33)
    a.set_ylim(y - 1.0, -1.7)
    a.set_yticks(ys)
    a.set_yticklabels(labels, fontsize=6.4)
    a.set_xticks([-10, 0, 10, 20, 30])
    a.set_xticklabels(["$-$10%", "0", "+10%", "+20%", "+30%"])
    a.set_xlabel("Identifications relative to the strongest comparator", fontsize=6.8)
    a.grid(axis="x", color=GRID, linewidth=0.4)
    a.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        a.spines[sp].set_visible(False)
    a.tick_params(axis="y", length=0)
    a.set_title(f"(a) Identifications on {len(board)} benchmarks", loc="left", fontsize=8, x=-0.62)
    rows = sorted(speedup, key=lambda r: -r["x"])
    for i, r in enumerate(rows):
        c = C_CPU if r["backend"] == "CPU" else C_GPU
        b.barh(i, r["x"], height=0.62, color=c, edgecolor=INK, linewidth=0.5)
        if r["node_range"]:
            lo, hi = r["node_range"]
            b.plot([lo, hi], [i, i], color=INK, linewidth=0.7)
            b.plot([lo, lo], [i - 0.18, i + 0.18], color=INK, linewidth=0.7)
            b.plot([hi, hi], [i - 0.18, i + 0.18], color=INK, linewidth=0.7)
        b.text(max(r["x"], (r["node_range"] or [0, 0])[1]) * 1.07, i, f"{r['x']:.1f}" + r"$\times$", va="center", fontsize=6.6, color=INK)
    b.set_xscale("log")
    b.set_xlim(1, 40)
    b.set_xticks([1, 2, 5, 10, 20])
    b.set_xticklabels([f"{t}" + r"$\times$" for t in (1, 2, 5, 10, 20)])
    b.minorticks_off()
    b.set_yticks(range(len(rows)))
    b.set_yticklabels([mt(f"{r['benchmark']}, {r['backend']}") for r in rows], fontsize=6.6)
    b.invert_yaxis()
    b.set_xlabel("Speed-up over Sage (wall time, log scale)", fontsize=6.8)
    b.grid(axis="x", color=GRID, linewidth=0.4)
    b.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        b.spines[sp].set_visible(False)
    b.tick_params(axis="y", length=0)
    b.set_title("(b) Speed against Sage", loc="left", fontsize=8, x=-0.75)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


# Identifications with entrapment arms (target-only counts from ids.json; arms recorded per job).
def id_table():
    """Table rows from data/ids.json, grouped by benchmark in file order."""
    num = lambda v: "--" if v is None else f"{v:,}"
    pct = lambda e: f"{100 * e['fdp']:.2f}"
    lines, seen = [], []
    for r in ids:
        if r["benchmark"] not in seen:
            if seen:
                lines.append(r"\addlinespace[2pt]")
            seen.append(r["benchmark"])
            lines.append(rf"\multicolumn{{10}}{{@{{}}l}}{{\textit{{{tex(r['benchmark'])}}}}}\\")
        s_, p_ = r["entrapment"]["sequences"], r["entrapment"]["psms"]
        lines.append(rf"\quad {tex(r['engine'])} & {num(r['sequences'])} & {num(r['psms'])} && {num(s_['nt'])} & {s_['ne']} & {pct(s_)} "
                     rf"&& {num(p_['nt'])} & {p_['ne']} & {pct(p_)}\\")
    return "\n".join(lines)


def floats(body):
    """Each centred minipage becomes a figure or table float LaTeX may place."""
    def one(m):
        inner = m.group(1)
        kind = "figure" if r"\captionof{figure}" in inner else "table"
        inner = inner.replace(r"\captionof{" + kind + "}", r"\caption").replace(r"\centering", "")
        spot = "H"
        return rf"\begin{{{kind}}}[{spot}]\centering{inner}\end{{{kind}}}"
    return re.sub(r"\\begin\{center\}\\begin\{minipage\}\{\\linewidth\}(.*?)\\end\{minipage\}\\end\{center\}", one, body, flags=re.S)


def zebra(doc):
    """Shade alternate body rows; a group heading or rule restarts the alternation."""
    def one(m):
        out, k = [], 0
        for line in m.group(1).split("\n"):
            if line.startswith((r"\midrule", r"\addlinespace", r"\multicolumn")) or not line.endswith("\\\\"):
                k = 0
            else:
                line = (r"\rowcolor{zebra}" if k % 2 == 0 else "") + line
                k += 1
            out.append(line)
        return r"\midrule" + "\n".join(out) + r"\bottomrule"
    return re.sub(r"\\midrule(.*?)\\bottomrule", one, doc, flags=re.S)


def rows_tex(rows, ncols):
    return "\n".join(" & ".join(tex(c) for c in r) + r"\\" for r in rows)


total_files = sum(r["files"] for r in cover)
open_cpu = ratio(by["lfq-open-ymh4"]["sage_s"], by["lfq-open-ymh4"]["logos_cpu_s"])
open_gpu = ratio(by["lfq-open-ymh4"]["sage_s"], by["lfq-open-ymh4"]["logos_gpu_s"])
closed = ratio(by["lfq-closed"]["sage_s"], by["lfq-closed"]["logos_cpu_s"])
astral = ratio(by["astral-tmt"]["sage_s"], by["astral-tmt"]["logos_cpu_s"])

speed_body = "\n".join(
    rf"{tex(r['benchmark'])} & {tex(r['node'] + ' · ' + re.sub(r'^(AMD|Intel\(R\) Xeon\(R\)) |\s*\d+-Core Processor|\s*CPU @.*', '', r['cpu']))} & {sec(r['logos_cpu_s'])} & {sec(r['logos_gpu_s'])} & {sec(r['sage_s'])} & "
    rf"{ratio(r['sage_s'], r['logos_cpu_s'])} & {ratio(r['sage_s'], r['logos_gpu_s'])} & {r['logos_binary_sha256'][:8]} & {r['slurm_job']}\\"
    for r in speed)
cover_body = "\n".join(rf"{tex(r['accession'])} & {tex(r['dataset'])} & {tex(r['instrument'])} & {r['files']} & {tex(r['benchmarked'])} & {tex(r['comparators'])} & {r['ledger_rows']}\\" for r in cover)
scale_body = "\n".join(rf"{tex(r['workload'])} & {tex(r['result'])} & {tex(r['ids'])} & {tex(r['hardware'])} & {tex(r['note'])}\\" for r in power["scale"])
loss_body = "\n".join(rf"{tex(r['benchmark'])} & {tex(r['logos'])} & {tex(r['comparator'])} & {tex(r['note'])}\\" for r in losses)
H = r"\hspace{0pt}"
def cite(src):
    first = re.split(r"[;]| // ", src)[0]
    first = re.sub(r"\s*\(.*$", "", first).replace("archive/inventory/", "").replace("archive/", "")
    return first.strip()
cat_body = "\n".join(rf"{tex(r['date'])} & {H}{tex(r['area'])} & {H}{tex(r['dataset'])} & {H}{tex(r['logos'])} & {H}{tex(r['comparator'])} & {tex(r['status'])} & {H}{tex(r['caveat'])} & {H}{tex(cite(r['source']))}\\" for r in catalog)

BODY = (HERE / "body.tex").read_text()

DOC = r"""\documentclass[10pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern,textcomp}
\usepackage[a4paper,hmargin=2.1cm,vmargin=2cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{microtype}
\usepackage[table]{xcolor}
\usepackage{booktabs,tabularx,array}
\usepackage{graphicx}
\usepackage{float}
\usepackage[font=small,labelfont=bf]{caption}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\setlist{itemsep=1pt,topsep=3pt}
\renewcommand{\topfraction}{0.9}
\renewcommand{\bottomfraction}{0.8}
\renewcommand{\textfraction}{0.07}
\renewcommand{\floatpagefraction}{0.85}
\setcounter{totalnumber}{4}
\renewcommand{\arraystretch}{1.3}
\renewcommand{\tabularxcolumn}[1]{m{#1}}
\setlength{\aboverulesep}{0pt}
\setlength{\belowrulesep}{0pt}
\definecolor{zebra}{gray}{0.93}
\newcolumntype{L}{>{\raggedright\arraybackslash}X}
\title{LOGOS: Benchmarks for DDA Peptide Search}
\author{Filip Rumenovski}
\date{1 November 2026}
\begin{document}
\maketitle
\begin{abstract}
LOGOS is a proteomics search engine written in Rust with a CUDA backend. It reads Thermo RAW files directly and searches on one CPU node or one GPU. Against Sage 0.14.7 on the same node, chemistry and 22 cores, it runs closed DDA """ + closed + r"""$\times$ and open search """ + open_cpu + r"""$\times$ faster on the CPU, and open search """ + open_gpu + r"""$\times$ faster on one GPU, while reporting more peptide sequences at an entrapment-measured error. At scale it searches the 79.7 GB HEK293 deposit PXD001468 in an open search in 12.13 s on one GPU, and one gut metaproteome against 111.5 million sequences in 20.3 s on an L40S (recorded on an earlier build). CPU and GPU builds produce byte-identical identifications. The record behind this report covers """ + str(total_files) + r""" RAW files from """ + str(len(cover)) + r""" public datasets and """ + str(len(catalog)) + r""" recorded comparisons against external tools, released with it as data.
Measurements were taken through 31 October 2026 on the Warrior cluster at Wayne State University; this report covers data-dependent acquisition only.
\end{abstract}

NEW_BODY_TOKEN
\end{document}
"""

fmt_n = lambda v: f"{v:,}"
bd = {r['key']: r for r in board}
board_body = "\n".join(
    rf"{tex(r['dataset'])} & {tex(r['accession'])}\newline {tex(r['instrument'])} & {tex(r['comparator'])} & {fmt_n(r['logos'])} & {fmt_n(r['comp'])} & "
    + (r"\textbf{" if r['delta_pct'] > 1 else "{") + f"{r['delta_pct']:+.1f}" + r"\%} & " + rf"{tex(r['error'])} & {tex(r['basis'])}\\"
    for r in board)
DOC = DOC.replace("NEW_BODY_TOKEN", floats(BODY).replace("@@CLOSED@@", closed).replace("@@OPENGPU@@", open_gpu).replace("@@TOTAL@@", str(total_files)).replace("@@NCAT@@", str(len(catalog)))
     .replace("@@NBOARD@@", str(len(board))).replace("@@NDATA@@", str(len({x.strip() for r in board for x in r["accession"].split(",")})))
     .replace("@@NINST@@", str(len({r["instrument"] for r in board}))).replace("@@NTASK@@", str(len({r["task"] for r in board})))
     .replace("@@D_CLOSED@@", f'{bd["lfq-closed"]["delta_pct"]:.1f}').replace("@@D_ASTRAL@@", f'{bd["astral-tmt"]["delta_pct"]:.1f}')
     .replace("@@D_OPEN@@", f'{bd["lfq-open"]["delta_pct"]:.1f}'))
DOC = (DOC.replace("BOARD_BODY", board_body).replace("SPEED_BODY", speed_body).replace("ID_BODY", id_table())
       .replace("COVER_BODY", cover_body).replace("SCALE_BODY", scale_body))
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    fig_force(tmp / "fig-force.pdf")
    fig_throughput(tmp / "fig-throughput.pdf")
    fig_power(tmp / "fig-power.pdf")
    fig_cascade(tmp / "fig-cascade.pdf")
    (tmp / "report.tex").write_text(zebra(DOC))
    for _ in range(2):
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "report.tex"], cwd=tmp, capture_output=True, text=True)
        if r.returncode:
            print(r.stdout[-3000:])
            raise SystemExit("pdflatex failed")
    out = HERE / "LOGOS-DDA-benchmarks.pdf"
    shutil.copy(tmp / "report.pdf", out)
    shutil.copy(tmp / "report.tex", HERE / "LOGOS-DDA-benchmarks.tex")
    warn = [l for l in (tmp / "report.log").read_text(errors="ignore").splitlines() if "Overfull" in l or "Missing character" in l]
    print(out, out.stat().st_size, "warnings:", len(warn))
    for l in warn[:12]:
        print(" ", l)
