import unittest

import numpy as np
import pandas as pd

from modele_d import suivi_regle


class TestSuiviRegle(unittest.TestCase):
    def setUp(self):
        self.params = suivi_regle.charger_regle()  # verifie aussi l'empreinte du fichier fige

    def _matchs(self):
        cotes = pd.DataFrame({"p_avgc_h": [0.5, 0.1], "p_avgc_d": [0.3, 0.2], "p_avgc_a": [0.2, 0.7]})
        return cotes

    def test_probas_somment_a_un(self):
        p = suivi_regle.probas_recalibrees(self._matchs(), self.params)
        np.testing.assert_allclose(p.sum(axis=1), 1.0)
        self.assertTrue((p > 0).all())

    def test_aucun_pari_sous_la_cote_minimale(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-08-01"]), "equipe_dom": ["A"], "equipe_ext": ["B"], "resultat": ["H"],
            "buts_dom": [1], "buts_ext": [0], "p_avgc_h": [0.5], "p_avgc_d": [0.3], "p_avgc_a": [0.2],
            "maxc_h": [3.9], "maxc_d": [100.0], "maxc_a": [100.0], "avgc_h": [2.0], "avgc_d": [3.3], "avgc_a": [5.0],
            "b365c_h": [2.0], "b365c_d": [3.3], "b365c_a": [5.0],
        })
        for p in suivi_regle.paris(df, self.params):
            self.assertGreater(p["cote_max"], self.params["cote_min"])
            self.assertGreater(p["p_modele"] * p["cote_max"], 1 + self.params["marge"])
        self.assertEqual([p["issue"] for p in suivi_regle.paris(df, self.params)], ["d", "a"])  # 3,9 exclu


if __name__ == "__main__":
    unittest.main()
