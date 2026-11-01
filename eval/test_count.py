"""Tests of the counting rule. Run: python3 -m unittest discover eval"""
import random
import tempfile
import unittest
from pathlib import Path

import count


def row(id_, pep, scan, decoy, score, ent=False, expmass=1000.0, ps=0.0):
    return {"id": id_, "peptide": pep, "scan": scan, "expmass": expmass, "decoy": decoy,
            "entrapment": ent, "primary_score": ps, "score": score}


class Normalize(unittest.TestCase):
    def test_sequences(self):
        self.assertEqual(count.sequence("K.n[42]PEPTIDE[16]c.R"), "PEPTLDE")
        self.assertEqual(count.sequence("-.MJK.-"), "MLK")
        self.assertEqual(count.entrap_sequence("PEPTIDE"), "PEPTLDE")
        self.assertEqual(count.normalize("A[unclosed"), "A[unclosed")
        self.assertEqual(count.normalize("A[x[y]B"), "AB")


class Acceptance(unittest.TestCase):
    def test_decoy_wins_an_exact_tie(self):
        rows = [row("a", "K.AAA.R", 1, False, 2.0), row("b", "K.CCC.R", 1, True, 2.0), row("c", "K.DDD.R", 2, False, 3.0)]
        ids = count.count_ids(rows)
        self.assertEqual(ids["competed_psms"], 2)
        # Winners b (decoy, 2.0) and c (3.0): FDR at c is (0 + 1) / 1, above 1%.
        self.assertEqual(ids["psms_q01"], 0)
        w = count.winners(rows, lambda r: (r["scan"], r["expmass"]))
        self.assertEqual([r["id"] for r in w], ["b", "c"])

    def test_one_sequence_alone_is_never_accepted(self):
        rows = [row("t", "K.AAA.R", i, False, 10.0 + i) for i in range(300)]
        ids = count.count_ids(rows)
        self.assertEqual(ids["psms_q01"], 300)
        self.assertEqual(ids["sequences_q01"], 0)  # one target, no decoys: (0 + 1) / 1

    def test_tie_groups_are_whole(self):
        # 100 targets then a group of 2 targets + 1 decoy at one score: (1 + 1) / 102 > 1%, so the group
        # is rejected and the q of the 100 above is (0 + 1) / 100 = 1%, accepted.
        rows = [row(f"t{i}", f"K.A{i}.R", i, False, 100.0 - i) for i in range(100)]
        rows += [row("u", "K.U.R", 200, False, 0.5), row("v", "K.V.R", 201, False, 0.5), row("d", "K.D.R", 202, True, 0.5)]
        self.assertEqual(len(count.accept(rows)), 100)

    def test_q_is_the_running_minimum_from_the_bottom(self):
        # A decoy early, then enough targets that the later FDR falls to 1%: the early targets inherit it.
        rows = [row("t0", "K.A.R", 0, False, 10.0), row("d0", "K.D.R", 1, True, 9.0)]
        rows += [row(f"t{i}", "K.A.R", i + 2, False, 8.0 - i * 0.01) for i in range(199)]
        self.assertEqual(len(count.accept(rows)), 200)  # (1 + 1) / 200 = 1%


class Entrapment(unittest.TestCase):
    def test_formula(self):
        f = count.fdp(31718, 204, 1.0606)
        self.assertEqual(f["fdp_combined"], 0.0124)

    def test_entrapment_targets_are_counted(self):
        rows = [row(f"t{i}", f"K.P{i}EP.R", i, False, 100.0 - i * 0.1, ent=(i % 50 == 0)) for i in range(400)]
        e = count.entrapment(rows, 1.0)["expmass"]
        self.assertEqual(e["psm"]["ne"], 8)
        self.assertEqual(e["psm"]["nt"], 392)


class AgainstDirectRules(unittest.TestCase):
    """The counter against a literal re-statement of the rule on random tables with
    repeated scans and masses, exact score ties, signed zeros, I/L/J variants and unflanked peptides."""

    def test_random_tables(self):
        peptides = ["K.PEPTIDE.R", "K.PEPTLDE.R", "-.PEPTJDE.-", "R.AAAK.R", "K.n[42]AAAK.-", "CCCK", "K.DDDM[16]R.K", "K.DDDMR.K"]
        rnd = random.Random(7)
        for _ in range(20):
            rows = []
            for i in range(400):
                scan = i // 2 if i < 200 else rnd.randrange(150)
                score = rnd.choice([0.0, -0.0, rnd.randrange(40) / 4 - 2])
                rows.append(row(f"id{i:03}", rnd.choice(peptides), scan, rnd.random() < 0.25, score,
                                expmass=1000.0 + rnd.randrange(3)))
            got = count.count_ids(rows)
            # Literal rule: winner per (scan, expmass) by (score, decoy, id), first appearance order.
            won = {}
            for r in rows:
                k = (r["scan"], r["expmass"])
                if k not in won or (r["score"], r["decoy"], r["id"]) > (won[k]["score"], won[k]["decoy"], won[k]["id"]):
                    won[k] = r
            w = list(won.values())
            self.assertEqual(got["competed_psms"], len(w))
            self.assertEqual(got["psms_q01"], len(count.accept(w)))


class ReadsLearnerDirectories(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "percolator").mkdir()
            pin = ["SpecId\tLabel\tScanNr\tExpMass\tprimary_score\tPeptide\tProteins"]
            psms, decoys = ["PSMId\tscore\tpeptide"], ["PSMId\tscore\tpeptide"]
            for i in range(300):
                decoy = i % 10 == 9
                prot = "rev_P1" if decoy else ("entrap_P2\tentrap_P3" if i % 37 == 0 else "P1\tentrap_P4")
                pin.append(f"s{i}\t{-1 if decoy else 1}\t{i}\t1000.0\t1.0\tK.PEP{i}K.R\t{prot}")
                (decoys if decoy else psms).append(f"s{i}\t{300 - i}\tK.PEP{i}K.R")
            (d / "evidence.pin").write_text("\n".join(pin) + "\n")
            (d / "percolator" / "percolator.psms.tsv").write_text("\n".join(psms) + "\n")
            (d / "percolator" / "percolator.decoys.tsv").write_text("\n".join(decoys) + "\n")
            rows = count.read_rows(d)
            self.assertEqual(len(rows), 300)
            # Entrapment needs every protein entrap_: "P1\tentrap_P4" is not.
            self.assertEqual(sum(r["entrapment"] for r in rows), sum(1 for i in range(300) if i % 37 == 0 and i % 10 != 9))


if __name__ == "__main__":
    unittest.main()
