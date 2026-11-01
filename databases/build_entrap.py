#!/usr/bin/env python3
"""Build a mimic-style entrapment FASTA: every target protein shuffled between tryptic cleavage
sites (C-terminal K/R of each segment and a protein N-terminal M held fixed), one copy (r~1).
Segments whose shuffle equals the original (I/L-normalized) are reshuffled up to 50 times.
Reports target/entrapment distinct-peptide counts (KR, no P rule, <=2 missed cleavages, N-term Met clip)
and the entrapment ratio r = |E \\ T| / |T| for the given length ranges."""
import json, random, sys, hashlib
src, out, seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
rng = random.Random(seed)
def fasta(p):
    h = None; s = []
    for l in open(p):
        l = l.rstrip('\n')
        if l.startswith('>'):
            if h is not None: yield h, ''.join(s)
            h = l[1:]; s = []
        else: s.append(l.strip())
    if h is not None: yield h, ''.join(s)
def segments(s):
    seg = []; cur = []
    for c in s:
        cur.append(c)
        if c in 'KR': seg.append(''.join(cur)); cur = []
    if cur: seg.append(''.join(cur))
    return seg
N = lambda x: x.replace('I', 'L')
def shuffle_seg(seg, first):
    lo = 1 if (first and seg.startswith('M')) else 0
    hi = len(seg) - 1 if seg[-1] in 'KR' else len(seg)
    mid = list(seg[lo:hi])
    if len(set(N(''.join(mid)))) < 2: return seg
    for _ in range(50):
        rng.shuffle(mid); t = seg[:lo] + ''.join(mid) + seg[hi:]
        if N(t) != N(seg): return t
    return t
targets = list(fasta(src)); ent = []; unchanged = 0
for h, s in targets:
    segs = segments(s); new = ''.join(shuffle_seg(g, i == 0) for i, g in enumerate(segs))
    assert len(new) == len(s) and sorted(new) == sorted(s)
    unchanged += new == s
    ent.append(('entrap_' + h.split()[0] + ' ENTRAPMENT=1 shuffle=between_cleavage seed=%d' % seed, new))
with open(out, 'w') as f:
    for h, s in ent:
        f.write('>' + h + '\n')
        for i in range(0, len(s), 60): f.write(s[i:i+60] + '\n')
def digest(prots, lo, hi, mc=2):
    S = set()
    for s in prots:
        segs = segments(s)
        starts = [0]
        for g in segs: starts.append(starts[-1] + len(g))
        for i in range(len(segs)):
            for j in range(i, min(i + mc + 1, len(segs))):
                p = s[starts[i]:starts[j+1]]
                if lo <= len(p) <= hi: S.add(N(p))
                if i == 0 and s.startswith('M') and lo <= len(p) - 1 <= hi: S.add(N(p[1:]))
    return S
rep = dict(source=src, output=out, seed=seed, proteins=len(ent), proteins_unchanged=unchanged,
           sha256=hashlib.sha256(open(out, 'rb').read()).hexdigest())
for lo, hi in [(7, 30), (7, 50)]:
    T = digest([s for _, s in targets], lo, hi); E = digest([s for _, s in ent], lo, hi)
    rep[f'len{lo}_{hi}'] = dict(target_peptides=len(T), entrap_peptides=len(E), shared=len(E & T),
                                entrap_only=len(E - T), r=len(E - T) / len(T))
json.dump(rep, open(out + '.json', 'w'), indent=1); print(json.dumps(rep, indent=1))
