import unittest

import analisi_grafi as G


class TestStats(unittest.TestCase):
    def test_mcnemar(self):
        self.assertAlmostEqual(G.mcnemar_exact(10, 3), 0.0923, places=4)
        self.assertEqual(G.mcnemar_exact(0, 0), 1.0)
        self.assertEqual(G.mcnemar_exact(4, 4), 1.0)

    def test_holm(self):
        self.assertEqual(G.holm({"a": 0.01, "b": 0.04, "c": 0.03}), {"a": 0.03, "c": 0.06, "b": 0.06})
        self.assertEqual(G.holm({"a": 0.5}), {"a": 0.5})

    def test_paired(self):
        out = G.paired({"t1": 1, "t2": 1, "t3": 0, "t4": 0}, {"t1": 1, "t2": 0, "t3": 0, "t5": 1})
        self.assertEqual((out["n"], out["first_only"], out["second_only"]), (3, 1, 0))


if __name__ == "__main__":
    unittest.main()
