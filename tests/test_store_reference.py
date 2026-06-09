import importlib
import os
import tempfile
import unittest

from app.store_reference import (
    find_exact_store_reference,
    find_store_reference_matches,
    sync_store_reference,
)
from models import CompteRendu, MagasinAlias, MagasinReference, db


class StoreReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, 'test.db')
        os.environ['DATABASE_URL'] = f"sqlite:///{self.db_path}"
        wsgi = importlib.import_module('wsgi')
        importlib.reload(wsgi)
        self.app = wsgi.create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        os.environ.pop('DATABASE_URL', None)
        self.temp_dir.cleanup()

    def test_lookup_matches_alias_and_localisation(self):
        with self.app.app_context():
            reference, _created = sync_store_reference(
                enseigne='Auchan',
                nom_magasin='Auchan Champ des Fleurs',
                code_postal='82000',
                commune='Montauban',
                code_departement='82',
                region='Occitanie',
                aliases=['Auchan Montauban'],
            )
            db.session.commit()

            matches = find_store_reference_matches(
                query='Auchan Montauban',
                enseigne='Auchan',
                code_postal='82000',
            )

            self.assertTrue(matches)
            self.assertEqual(matches[0].id, reference.id)
            self.assertEqual(
                find_exact_store_reference(
                    nom_magasin='Auchan Montauban',
                    enseigne='Auchan',
                    code_postal='82000',
                ).id,
                reference.id,
            )

    def test_public_search_endpoint_returns_reference_payload(self):
        with self.app.app_context():
            sync_store_reference(
                enseigne='Auchan',
                nom_magasin='Auchan Champ des Fleurs',
                code_postal='82000',
                commune='Montauban',
                aliases=['Auchan Montauban'],
            )
            db.session.commit()

        response = self.client.get('/magasins/recherche?q=Auchan%20Montauban&enseigne=Auchan')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['results'][0]['nom_magasin'], 'Auchan Champ des Fleurs')
        self.assertIn('Auchan Montauban', payload['results'][0]['aliases'])

    def test_admin_edit_can_update_received_form_and_sync_reference(self):
        with self.app.app_context():
            cr = CompteRendu(token='token-admin', statut='soumis', nom_magasin='Auchan Montauban')
            db.session.add(cr)
            db.session.commit()
            cr_id = cr.id

        with self.client.session_transaction() as session:
            session['admin'] = True

        response = self.client.post(
            f'/admin/cr/{cr_id}/modifier',
            data={
                'statut': 'soumis',
                'nom_magasin': 'Auchan Champ des Fleurs',
                'enseigne': 'Auchan',
                'code_postal': '82000',
                'commune': 'Montauban',
                'region': '',
                'store_reference_aliases': 'Auchan Montauban\nAuchan Champ des Fleurs',
                'sync_store_reference': '1',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            cr = CompteRendu.query.get(cr_id)
            self.assertEqual(cr.nom_magasin, 'Auchan Champ des Fleurs')
            self.assertEqual(cr.code_postal, '82000')
            self.assertEqual(cr.region, 'Occitanie')

            references = MagasinReference.query.all()
            self.assertEqual(len(references), 1)
            self.assertEqual(references[0].nom_reference, 'Auchan Champ des Fleurs')
            aliases = [alias.alias for alias in MagasinAlias.query.all()]
            self.assertIn('Auchan Montauban', aliases)

    def test_manual_reference_routes_can_create_and_edit_reference(self):
        with self.client.session_transaction() as session:
            session['admin'] = True

        create_response = self.client.post(
            '/admin/magasins/nouveau',
            data={
                'nom_reference': 'Carrefour Grand Centre',
                'enseigne': 'Carrefour',
                'code_postal': '31000',
                'commune': 'Toulouse',
                'code_departement': '',
                'region': '',
                'adresse': '12 avenue du Test',
                'actif': '1',
                'aliases': 'Carrefour Toulouse Centre\nCarrefour Grand Centre',
            },
            follow_redirects=False,
        )

        self.assertEqual(create_response.status_code, 302)

        with self.app.app_context():
            reference = MagasinReference.query.one()
            self.assertEqual(reference.nom_reference, 'Carrefour Grand Centre')
            self.assertEqual(reference.region, 'Occitanie')
            self.assertTrue(reference.actif)
            self.assertEqual(
                sorted(alias.alias for alias in reference.aliases),
                ['Carrefour Toulouse Centre'],
            )
            reference_id = reference.id

        edit_response = self.client.post(
            f'/admin/magasins/{reference_id}/modifier',
            data={
                'nom_reference': 'Carrefour Grand Centre',
                'enseigne': 'Carrefour',
                'code_postal': '31000',
                'commune': 'Toulouse',
                'code_departement': '31',
                'region': 'Occitanie',
                'adresse': '99 avenue du Test',
                'actif': '0',
                'aliases': 'Carrefour Toulouse Centre\nCarrefour Hyper Centre',
            },
            follow_redirects=False,
        )

        self.assertEqual(edit_response.status_code, 302)

        with self.app.app_context():
            reference = MagasinReference.query.get(reference_id)
            self.assertFalse(reference.actif)
            self.assertEqual(reference.adresse, '99 avenue du Test')
            self.assertEqual(
                sorted(alias.alias for alias in reference.aliases),
                ['Carrefour Hyper Centre', 'Carrefour Toulouse Centre'],
            )

            public_matches = find_store_reference_matches(query='Hyper Centre', enseigne='Carrefour')
            admin_matches = find_store_reference_matches(
                query='Hyper Centre',
                enseigne='Carrefour',
                include_inactive=True,
            )
            self.assertEqual(public_matches, [])
            self.assertEqual(len(admin_matches), 1)


if __name__ == '__main__':
    unittest.main()
