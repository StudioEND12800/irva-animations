import unittest
from types import SimpleNamespace

from app.views.submit import (
    _blocked_step_number,
    _etape_courante,
    _extract_resume_token,
    _is_valid_email,
    _step1_complete,
    _step_errors,
)


class SubmitResumeTests(unittest.TestCase):
    def test_extract_resume_token_accepts_link_or_raw_token(self):
        token = "abcDEF_123-token"
        self.assertEqual(_extract_resume_token(token), token)
        self.assertEqual(
            _extract_resume_token(f"https://app.veau-aveyron.fr/reprendre/{token}"),
            token,
        )

    def test_extract_resume_token_rejects_invalid_values(self):
        self.assertEqual(_extract_resume_token(""), "")
        self.assertEqual(_extract_resume_token("javascript:alert(1)"), "")

    def test_step1_completion_requires_all_fields(self):
        complete = SimpleNamespace(
            date_premier_jour=object(),
            nom_prenom="Marie Dupont",
            num_cheptel="12059081",
            email="marie@example.fr",
            animation_solo="Seul",
            nom_coeleveuse="",
            filiere="SA4R",
        )
        missing_email = SimpleNamespace(**{**complete.__dict__, "email": ""})
        invalid_email = SimpleNamespace(**{**complete.__dict__, "email": "marie"})
        with_partner_missing_name = SimpleNamespace(
            **{**complete.__dict__, "animation_solo": "Avec un autre éleveur·se", "nom_coeleveuse": ""}
        )

        self.assertTrue(_step1_complete(complete))
        self.assertFalse(_step1_complete(missing_email))
        self.assertFalse(_step1_complete(invalid_email))
        self.assertFalse(_step1_complete(with_partner_missing_name))

    def test_current_step_stays_on_step1_until_it_is_complete(self):
        partial = SimpleNamespace(
            date_premier_jour=object(),
            nom_prenom="Marie Dupont",
            num_cheptel="12059081",
            email="",
            animation_solo="Seul",
            nom_coeleveuse="",
            filiere="SA4R",
            nom_magasin="Auchan Rodez",
            rayons_presents='["Rayon libre-service (LS)"]',
            morceaux_presents='["Escalope"]',
            frequentation="Bonne",
            attitude_clients='["Curieux"]',
            ressenti_mise_en_place="Facile",
        )
        complete = SimpleNamespace(**{**partial.__dict__, "email": "marie@example.fr", "nom_magasin": ""})

        self.assertEqual(_etape_courante(partial), 1)
        self.assertEqual(_blocked_step_number(partial, 2), 1)
        self.assertEqual(_etape_courante(complete), 2)
        self.assertIsNone(_blocked_step_number(complete, 2))

    def test_step1_errors_explain_missing_fields(self):
        cr = SimpleNamespace(
            date_premier_jour=None,
            nom_prenom="",
            num_cheptel="",
            email="bad",
            animation_solo="Avec un autre éleveur·se",
            nom_coeleveuse="",
            filiere="",
        )

        errors = _step_errors(cr, 1)

        self.assertGreaterEqual(len(errors), 6)
        self.assertIn("Renseignez une adresse e-mail valide.", errors)
        self.assertIn("Renseignez le nom du ou de la co-éleveur·se.", errors)

    def test_email_validation_is_basic_but_strict(self):
        self.assertTrue(_is_valid_email("a@b.fr"))
        self.assertFalse(_is_valid_email("ab.fr"))
        self.assertFalse(_is_valid_email("a@b"))


if __name__ == "__main__":
    unittest.main()
