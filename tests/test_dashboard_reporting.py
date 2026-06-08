import unittest
from types import SimpleNamespace

from app.views.dashboard import (
    _json_list,
    _rayon_rows,
    _scope_rule,
    _store_duplicate_rows,
    _yearly_activity_chart,
)


class DashboardReportingTests(unittest.TestCase):
    def test_scope_rule_with_all_filters(self):
        filters = {
            "filiere": "SA4R",
            "annee": "2025",
            "mois": "3",
            "statut": "complet",
            "q": "Auchan",
        }
        rule = _scope_rule(filters)
        self.assertIn("statut IN ('soumis', 'valide')", rule)
        self.assertIn("filiere = 'SA4R'", rule)
        self.assertIn("YEAR(date_premier_jour) = 2025", rule)
        self.assertIn("MONTH(date_premier_jour) = 3", rule)
        self.assertIn("recherche LIKE '%Auchan%'", rule)

    def test_json_list_supports_json_and_csv_fallback(self):
        self.assertEqual(_json_list('["A", "B"]'), ["A", "B"])
        self.assertEqual(_json_list("A, B , C"), ["A", "B", "C"])
        self.assertEqual(_json_list(None), [])

    def test_rayon_rows_count_each_flag_exactly(self):
        records = [
            SimpleNamespace(
                enseigne="Auchan",
                rayons_presents='["Rayon libre-service (LS)", "Drive"]',
            ),
            SimpleNamespace(
                enseigne="Auchan",
                rayons_presents='["Rayon Coupe (Trad)", "Libre service entree (ponctuel)"]',
            ),
            SimpleNamespace(
                enseigne="Carrefour",
                rayons_presents='["Rayon libre-service (LS)"]',
            ),
        ]
        rows = _rayon_rows(records)
        self.assertEqual(rows[0], ["Auchan", "1", "1", "1", "1", "2"])
        self.assertEqual(rows[1], ["Carrefour", "1", "0", "0", "0", "1"])

    def test_store_duplicate_rows_group_normalized_variants(self):
        records = [
            SimpleNamespace(nom_magasin="Auchan Bordeaux-Lac"),
            SimpleNamespace(nom_magasin="AUCHAN Bordeaux Lac"),
            SimpleNamespace(nom_magasin="Carrefour Millau"),
        ]
        rows = _store_duplicate_rows(records)
        self.assertEqual(rows[0][0], "auchan bordeaux lac")
        self.assertEqual(rows[0][1], 2)
        self.assertEqual(rows[0][2], 2)

    def test_yearly_activity_chart_sorts_without_mixing_types(self):
        records = [
            SimpleNamespace(date_premier_jour=None),
            SimpleNamespace(date_premier_jour=SimpleNamespace(year=2025)),
            SimpleNamespace(date_premier_jour=SimpleNamespace(year=2024)),
            SimpleNamespace(date_premier_jour=SimpleNamespace(year=2025)),
        ]
        chart = _yearly_activity_chart(records)
        self.assertEqual(chart["data"]["labels"], ["2024", "2025", "Sans date"])
        self.assertEqual(chart["data"]["datasets"][0]["data"], [1, 2, 1])


if __name__ == "__main__":
    unittest.main()
