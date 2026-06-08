import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class CompteRendu(db.Model):
    __tablename__ = 'compte_rendu'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)  # pour reprise brouillon
    statut = db.Column(db.String(20), default='brouillon')  # brouillon | soumis | valide
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)

    # ── ÉTAPE 1 : Éleveur ─────────────────────────────────────────────
    date_premier_jour = db.Column(db.Date)
    nom_prenom = db.Column(db.String(200))
    num_cheptel = db.Column(db.String(50))
    email = db.Column(db.String(200))
    animation_solo = db.Column(db.String(50))       # Seul | Avec un autre éleveur·se
    nom_coeleveuse = db.Column(db.String(200))
    filiere = db.Column(db.String(50))              # SA4R | Natera | Sudries | Cadars | Autre

    # ── ÉTAPE 2 : Magasin ─────────────────────────────────────────────
    enseigne = db.Column(db.String(100))
    nom_magasin = db.Column(db.String(200))
    code_postal = db.Column(db.String(10))
    commune = db.Column(db.String(100))
    code_departement = db.Column(db.String(5))
    region = db.Column(db.String(100))
    nom_parrain = db.Column(db.String(200))
    nom_chef_boucher = db.Column(db.String(200))
    anciennete_chef_boucher = db.Column(db.String(100))

    # ── ÉTAPE 3 : Rayons ──────────────────────────────────────────────
    rayons_presents = db.Column(db.Text)            # JSON list
    # Rayon LS
    ls_barquettes = db.Column(db.Text)
    ls_barquettes_sur_place = db.Column(db.String(10))
    ls_visibilite = db.Column(db.String(50))
    ls_lineaire = db.Column(db.Float)
    ls_precisions_lineaire = db.Column(db.Text)
    ls_qualite_decoupe = db.Column(db.String(50))
    ls_precisions_qualite = db.Column(db.Text)
    ls_outils_com = db.Column(db.Text)              # JSON list
    ls_precisions_outils = db.Column(db.Text)
    ls_autre_veau = db.Column(db.String(10))
    ls_autre_veau_marque = db.Column(db.String(200))
    ls_autre_veau_lineaire = db.Column(db.Float)
    # Rayon Trad
    trad_visibilite = db.Column(db.String(50))
    trad_lineaire = db.Column(db.Float)
    trad_precisions_lineaire = db.Column(db.Text)
    trad_qualite_decoupe = db.Column(db.String(50))
    trad_precisions_qualite = db.Column(db.Text)
    trad_outils_com = db.Column(db.Text)
    trad_precisions_outils = db.Column(db.Text)
    trad_autre_veau = db.Column(db.String(10))
    trad_autre_veau_marque = db.Column(db.String(200))

    # ── ÉTAPE 4 : Morceaux & Prix ──────────────────────────────────────
    morceaux_presents = db.Column(db.Text)          # JSON list
    prix_vas_escalope = db.Column(db.Float)
    prix_vas_saute = db.Column(db.Float)
    prix_vas_roti = db.Column(db.Float)
    prix_vas_tendron = db.Column(db.Float)
    prix_vas_jarret = db.Column(db.Float)
    prix_vas_hache = db.Column(db.Float)
    prix_autre_escalope = db.Column(db.Float)
    prix_autre_saute = db.Column(db.Float)
    prix_autre_roti = db.Column(db.Float)
    prix_autre_tendron = db.Column(db.Float)
    prix_autre_jarret = db.Column(db.Float)
    prix_autre_hache = db.Column(db.Float)
    precision_prix = db.Column(db.String(200))
    commentaire_prix = db.Column(db.Text)

    # ── ÉTAPE 5 : Animation ───────────────────────────────────────────
    date_dernier_jour = db.Column(db.Date)
    emplacement_animation = db.Column(db.Text)      # JSON list
    frequentation = db.Column(db.String(50))
    approvisionnement = db.Column(db.String(50))
    ruptures = db.Column(db.String(10))
    precisions_animation = db.Column(db.Text)
    outils_animation = db.Column(db.Text)           # JSON list
    mise_en_avant = db.Column(db.Text)              # JSON list
    precisions_mise_en_avant = db.Column(db.Text)
    ventes_supplementaires = db.Column(db.String(10))
    incident = db.Column(db.String(10))
    type_incident = db.Column(db.Text)
    precisions_incident = db.Column(db.Text)

    # ── ÉTAPE 6 : Clients ─────────────────────────────────────────────
    tranche_age = db.Column(db.Text)                # JSON list
    attitude_clients = db.Column(db.Text)
    clients_connaissaient_vas = db.Column(db.String(50))
    type_questions = db.Column(db.Text)
    precisions_clients = db.Column(db.Text)

    # ── ÉTAPE 7 : Ressenti éleveur ─────────────────────────────────────
    ressenti_mise_en_place = db.Column(db.String(50))
    ressenti_accroche = db.Column(db.String(50))
    ressenti_argumentaire = db.Column(db.String(50))
    interesse_formation = db.Column(db.String(10))
    kit_irva = db.Column(db.String(50))
    kit_interbev = db.Column(db.String(50))
    precisions_ressenti = db.Column(db.Text)
    echanges_chef_boucher = db.Column(db.Text)
    remarques_chef_boucher = db.Column(db.Text)
    avis_eleveur = db.Column(db.Text)
    incident_majeur = db.Column(db.String(10))

    # ── ÉTAPE 8 : Fichiers ─────────────────────────────────────────────
    photos_situation = db.Column(db.Text)           # JSON list
    signature_boucher_path = db.Column(db.String(500))
    signature_eleveur_data = db.Column(db.Text)     # base64 PNG
    pdf_path = db.Column(db.String(500))

    # ── Computed / admin ──────────────────────────────────────────────
    prix_moyen_vas = db.Column(db.Float)
    prix_moyen_autre = db.Column(db.Float)
    ref_animation = db.Column(db.String(50))
    notes_admin = db.Column(db.Text)

    photos = db.relationship('Photo', backref='cr', lazy=True, cascade='all, delete-orphan')

    @property
    def nb_jours(self):
        if self.date_premier_jour and self.date_dernier_jour:
            return (self.date_dernier_jour - self.date_premier_jour).days + 1
        return 1

    def calc_prix_moyen_vas(self):
        # Exclut 0, None et valeurs aberrantes (> 300 EUR/kg = typo certain)
        vals = [v for v in [
            self.prix_vas_escalope, self.prix_vas_saute, self.prix_vas_roti,
            self.prix_vas_tendron, self.prix_vas_jarret, self.prix_vas_hache
        ] if v and 0 < v <= 300]
        return round(sum(vals) / len(vals), 2) if vals else None

    def calc_prix_moyen_autre(self):
        # Exclut 0, None et valeurs aberrantes (> 300 EUR/kg = typo certain)
        vals = [v for v in [
            self.prix_autre_escalope, self.prix_autre_saute, self.prix_autre_roti,
            self.prix_autre_tendron, self.prix_autre_jarret, self.prix_autre_hache
        ] if v and 0 < v <= 300]
        return round(sum(vals) / len(vals), 2) if vals else None


class Photo(db.Model):
    __tablename__ = 'photo'
    id = db.Column(db.Integer, primary_key=True)
    cr_id = db.Column(db.Integer, db.ForeignKey('compte_rendu.id'), nullable=False)
    filename = db.Column(db.String(500))
    original_name = db.Column(db.String(500))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
