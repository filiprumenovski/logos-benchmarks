"""Entrapment ratio r: distinct digested sequences in the entrapment set over the target set,
under one search's digestion (trypsin KR, optional not-before-P, missed cleavages, length and
monoisotopic mass window with static mods). Prints r with and without I/L merged."""
import sys, json
mono = {'G':57.02146,'A':71.03711,'S':87.03203,'P':97.05276,'V':99.06841,'T':101.04768,'C':103.00919,'L':113.08406,'I':113.08406,
        'N':114.04293,'D':115.02694,'Q':128.05858,'K':128.09496,'E':129.04259,'M':131.04049,'H':137.05891,'F':147.06841,'R':156.10111,
        'Y':163.06333,'W':186.07931,'U':150.95364,'O':237.14773}
def read(path, keep):
    name, seq = None, []
    for line in open(path):
        line = line.strip()
        if line.startswith('>'):
            if name is not None and keep(name): yield ''.join(seq)
            name, seq = line[1:], []
        elif line: seq.append(line)
    if name is not None and keep(name): yield ''.join(seq)
def peptides(prot, cfg):
    sites = [i + 1 for i, a in enumerate(prot[:-1]) if a in 'KR' and not (cfg['restrict_p'] and prot[i + 1] == 'P')]
    cuts = [0] + sites + [len(prot)]
    for i in range(len(cuts) - 1):
        for j in range(i + 1, min(i + 2 + cfg['missed'], len(cuts))):
            p = prot[cuts[i]:cuts[j]]
            if not (cfg['min_len'] <= len(p) <= cfg['max_len']) or any(a not in mono for a in p): continue
            m = 18.010565 + sum(mono[a] for a in p) + sum(cfg['static'].get(a, 0) * p.count(a) for a in cfg['static'] if a != '^') + cfg['static'].get('^', 0)
            if cfg['min_mass'] <= m <= cfg['max_mass']: yield p
def count(path, keep, cfg, merge):
    s = set()
    for prot in read(path, keep):
        for p in peptides(prot, cfg): s.add(p.replace('I', 'L') if merge else p)
    return len(s)
cfg = json.loads(sys.argv[3]); is_e = lambda n: n.startswith('entrap_')
for merge in (False, True):
    t = count(sys.argv[1], lambda n: not is_e(n), cfg, merge); e = count(sys.argv[2], is_e if sys.argv[1] == sys.argv[2] else (lambda n: True), cfg, merge)
    print(json.dumps({"il_merged": merge, "targets": t, "entrapment": e, "r": e / t}))
