"""Tests de cotes_historiques / dataset_cotes.csv. Usage : .venv/bin/python -m unittest modele_d.tests.test_cotes -v"""
import os
import unittest

import numpy as np
import pandas as pd

from modele_d import cotes_historiques as ch

DATASET = "modele_d/donnees/dataset_cotes.csv"

TOL = 1e-9


class TestProbas(unittest.TestCase):
    def test_somme_a_un_sur_cas_simple(self):
        df = pd.DataFrame({"psc_h": [2.0], "psc_d": [3.5], "psc_a": [4.0]})
        out = ch.compute_probs(df, "psc")
        self.assertAlmostEqual(out[["p_psc_h", "p_psc_d", "p_psc_a"]].sum(axis=1).iloc[0], 1.0, delta=TOL)
        self.assertAlmostEqual(out["marge_psc"].iloc[0], 1 / 2 + 1 / 3.5 + 1 / 4 - 1, delta=TOL)

    def test_cote_manquante_ou_invalide_donne_nan(self):
        df = pd.DataFrame({"psc_h": [np.nan, 0.9], "psc_d": [3.0, 3.0], "psc_a": [3.0, 3.0]})
        out = ch.compute_probs(df, "psc")
        self.assertTrue(out["p_psc_h"].isna().all())


@unittest.skipUnless(os.path.exists(DATASET), "dataset_cotes.csv non genere")
class TestDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(DATASET, low_memory=False)

    def test_probas_somment_a_un_pour_chaque_match(self):
        for p in ch.COLS_1X2:
            cols = [f"p_{p}_{x}" for x in "hda"]
            sommes = self.df[cols].dropna().sum(axis=1)
            self.assertTrue((sommes - 1).abs().max() < 1e-9, p)

    def test_chaque_match_a_au_moins_une_cote(self):
        cols = [f"{p}_{x}" for p in ch.COLS_1X2 for x in "hda"]
        self.assertFalse(self.df[cols].isna().all(axis=1).any())

    def test_resultat_coherent_avec_les_buts(self):
        attendu = np.where(self.df.buts_dom > self.df.buts_ext, "H", np.where(self.df.buts_dom < self.df.buts_ext, "A", "D"))
        self.assertTrue((self.df.resultat.values == attendu).all())

    def test_pas_de_doublon(self):
        self.assertFalse(self.df.duplicated(["ligue", "date", "equipe_dom", "equipe_ext"]).any())


if __name__ == "__main__":
    unittest.main()
