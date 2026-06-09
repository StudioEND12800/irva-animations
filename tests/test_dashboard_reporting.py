import unittest
from types import SimpleNamespace

from app.views.dashboard import (
    _draft_step_number,
    _json_list,
    _page_notice,
    _parse_multiline_field,
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

    def test_page_notice_uses_filtered_scope_not_all_records(self):
        active = [
            SimpleNamespace(region="Occitanie", prix_moyen_vas=10, nom_magasin="Magasin A", date_premier_jour=None),
            SimpleNamespace(region="", prix_moyen_vas=12, nom_magasin="Magasin B", date_premier_jour=None),
        ]
        dataset = {
            "active": active,
            "all": active + [SimpleNamespace(region="", prix_moyen_vas=None, nom_magasin="", date_premier_jour=None)],
            "drafts": [],
        }

        page = _page_notice(dataset, {"statut": "complet"})
        cards = {card["label"]: card["value"] for card in page["sections"][0]["cards"]}

        self.assertEqual(cards["formulaires du périmètre"], "2")
        self.assertEqual(cards["regions manquantes"], "1")
        self.assertEqual(cards["magasins manquants"], "0")
        self.assertEqual(cards["prix VAS absents"], "0")

    def test_parse_multiline_field_returns_json_list(self):
        self.assertEqual(_parse_multiline_field("A\nB\n\nC"), '["A", "B", "C"]')
        self.assertEqual(_parse_multiline_field(""), "[]")

    def test_draft_step_number_follows_form_progression(self):
        draft = SimpleNamespace(
            filiere="SA4R",
            nom_magasin="Auchan Rodez",
            rayons_presents='["Rayon libre-service (LS)"]',
            morceaux_presents='["Escalope"]',
            frequentation="Bonne",
            attitude_clients='["Curieux"]',
            ressenti_mise_en_place="Facile",
        )
        self.assertEqual(_draft_step_number(SimpleNamespace(
            filiere=None,
            nom_magasin=None,
            rayons_presents=None,
            morceaux_presents=None,
            frequentation=None,
            attitude_clients=None,
            ressenti_mise_en_place=None,
        )), 1)
        self.assertEqual(_draft_step_number(draft), 8)


if __name__ == "__main__":
    unittest.main()
