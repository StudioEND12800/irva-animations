import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from functools import wraps

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from models import CompteRendu, Photo, db
from app.utils import infer_department_code, infer_region
from sqlalchemy import extract, func, or_
from sqlalchemy.orm import load_only

dashboard_bp = Blueprint('dashboard', __name__)

COMPLETE_STATUSES = ('soumis', 'valide')
MONTH_LABELS = {
    1: 'janv',
    2: 'fevr',
    3: 'mars',
    4: 'avr',
    5: 'mai',
    6: 'juin',
    7: 'juil',
    8: 'aout',
    9: 'sept',
    10: 'oct',
    11: 'nov',
    12: 'dec',
}
PRICE_FIELDS = [
    ('prix_vas_escalope', 'Escalope VAS'),
    ('prix_vas_saute', 'Saute VAS'),
    ('prix_vas_roti', 'Roti VAS'),
    ('prix_vas_tendron', 'Tendron VAS'),
    ('prix_vas_jarret', 'Jarret VAS'),
    ('prix_vas_hache', 'Hache VAS'),
]
PRICE_COMPARISON_FIELDS = [
    ('escalope', 'Escalope'),
    ('saute', 'Saute'),
    ('roti', 'Roti'),
    ('tendron', 'Tendron'),
    ('jarret', 'Jarret'),
    ('hache', 'Hache'),
]
ADMIN_LIST_FIELDS = [
    ('rayons_presents', 'Rayons presents'),
    ('ls_barquettes', 'Barquettes LS'),
    ('ls_outils_com', 'Outils com LS'),
    ('trad_outils_com', 'Outils com trad'),
    ('morceaux_presents', 'Morceaux presents'),
    ('emplacement_animation', 'Emplacements animation'),
    ('outils_animation', 'Outils animation'),
    ('mise_en_avant', 'Mises en avant'),
    ('type_incident', 'Types d incident'),
    ('tranche_age', 'Tranches d age'),
    ('attitude_clients', 'Attitudes clients'),
    ('type_questions', 'Types de questions'),
    ('echanges_chef_boucher', 'Echanges chef boucher'),
    ('photos_situation', 'Situation photos'),
]
ADMIN_TEXT_FIELDS = [
    'statut',
    'ref_animation',
    'notes_admin',
    'nom_prenom',
    'num_cheptel',
    'email',
    'animation_solo',
    'nom_coeleveuse',
    'filiere',
    'enseigne',
    'nom_magasin',
    'code_postal',
    'commune',
    'nom_parrain',
    'nom_chef_boucher',
    'anciennete_chef_boucher',
    'frequentation',
    'approvisionnement',
    'ruptures',
    'ventes_supplementaires',
    'incident',
    'incident_majeur',
    'clients_connaissaient_vas',
    'ressenti_mise_en_place',
    'ressenti_accroche',
    'ressenti_argumentaire',
    'interesse_formation',
    'kit_irva',
    'kit_interbev',
    'precision_prix',
    'commentaire_prix',
    'precisions_animation',
    'precisions_mise_en_avant',
    'precisions_incident',
    'precisions_clients',
    'precisions_ressenti',
    'remarques_chef_boucher',
    'avis_eleveur',
    'ls_barquettes_sur_place',
    'ls_visibilite',
    'ls_precisions_lineaire',
    'ls_qualite_decoupe',
    'ls_precisions_qualite',
    'ls_precisions_outils',
    'ls_autre_veau',
    'ls_autre_veau_marque',
    'trad_visibilite',
    'trad_precisions_lineaire',
    'trad_qualite_decoupe',
    'trad_precisions_qualite',
    'trad_precisions_outils',
    'trad_autre_veau',
    'trad_autre_veau_marque',
]
ADMIN_FLOAT_FIELDS = [
    'prix_vas_escalope',
    'prix_vas_saute',
    'prix_vas_roti',
    'prix_vas_tendron',
    'prix_vas_jarret',
    'prix_vas_hache',
    'prix_autre_escalope',
    'prix_autre_saute',
    'prix_autre_roti',
    'prix_autre_tendron',
    'prix_autre_jarret',
    'prix_autre_hache',
    'ls_lineaire',
    'ls_autre_veau_lineaire',
    'trad_lineaire',
]
ADMIN_DATE_FIELDS = ['date_premier_jour', 'date_dernier_jour']
ADMIN_STATUT_OPTIONS = ['brouillon', 'soumis', 'valide']
ADMIN_FILIERE_OPTIONS = ['SA4R', 'Natera', 'Sudries', 'Cadars', 'Autre']
ADMIN_ENSEIGNE_OPTIONS = [
    'Auchan',
    'Carrefour',
    'E.Leclerc',
    "Halle de l'Aveyron",
    'Metro',
    'Boucherie indépendante',
    'Autre',
]
ADMIN_SOLO_OPTIONS = ['Seul', 'Avec un autre éleveur·se']
WORKBOOK_SHEETS = [
    {
        'key': 'decharge-donnees',
        'sheet_name': 'Décharge données',
        'title': 'Décharge des comptes-rendus',
        'description': 'Liste brute des formulaires avec accès rapide aux fiches individuelles.',
        'category': 'Source',
    },
    {
        'key': 'notice-decharge',
        'sheet_name': 'Notice décharge',
        'title': 'Notice et controles',
        'description': 'Rappels de lecture et points de vigilance sur les données.',
        'category': 'Controle',
    },
    {
        'key': 'synthese-global',
        'sheet_name': 'Synthèse Global',
        'title': 'Synthèse globale',
        'description': 'Vue d’ensemble des animations, filieres, rayons et qualite de saisie.',
        'category': 'Analyse',
    },
    {
        'key': 'evolution-prix-2024',
        'sheet_name': 'Evolution prix 2024',
        'title': 'Evolution des prix',
        'description': 'Suivi dynamique des prix moyens VAS et autre veau.',
        'category': 'Prix',
    },
    {
        'key': 'synthese-par-filiere',
        'sheet_name': 'Synthèse par filière',
        'title': 'Synthèse par filiere',
        'description': 'Comparaison d’une filiere avec le global IRVA.',
        'category': 'Analyse',
    },
    {
        'key': 'prix-par-region',
        'sheet_name': 'Prix par région',
        'title': 'Prix par region',
        'description': 'Moyennes par region et couverture territoriale.',
        'category': 'Prix',
    },
    {
        'key': 'detail-prix-filiere',
        'sheet_name': 'Détail prix filière',
        'title': 'Detail prix filiere',
        'description': 'Comparaison VAS / autre veau par filiere et par morceau.',
        'category': 'Prix',
    },
    {
        'key': 'anim-par-mag',
        'sheet_name': 'Anim par Mag',
        'title': 'Animations par magasin',
        'description': 'Classement des magasins, repetition des animations et dernier passage.',
        'category': 'Reseau',
    },
    {
        'key': 'brouillon',
        'sheet_name': 'Brouillon',
        'title': 'Brouillons',
        'description': 'Suivi des formulaires incomplets et reprise des saisies.',
        'category': 'Controle',
    },
    {
        'key': 'tableau-calcul',
        'sheet_name': 'Tableau calcul',
        'title': 'Tableau calcule',
        'description': 'Version normalisee des formulaires pour controle et export.',
        'category': 'Technique',
    },
    {
        'key': 'tdc',
        'sheet_name': 'TDC',
        'title': 'Retours terrain',
        'description': 'Commentaires eleveurs et remarques magasins consolides.',
        'category': 'Qualitatif',
    },
    {
        'key': 'analyse-rh-25',
        'sheet_name': 'Analyse RH 25',
        'title': 'Analyse RH',
        'description': 'Charge d’animation par mois, enseigne et participant.',
        'category': 'Pilotage',
    },
    {
        'key': 'donnee-liste',
        'sheet_name': 'Donnée liste',
        'title': 'Donnees de reference',
        'description': 'Listes vivantes des filieres, annees, regions et departements.',
        'category': 'Reference',
    },
    {
        'key': 'liste-nom-mag',
        'sheet_name': 'Liste nom mag',
        'title': 'Liste des magasins',
        'description': 'Liste dynamique des noms magasins et detection de doublons.',
        'category': 'Reference',
    },
    {
        'key': 'synthese-des-donnees',
        'sheet_name': 'Synthèse des données',
        'title': 'Synthèse des donnees',
        'description': 'Croisement enseigne x filiere et totaux consolides.',
        'category': 'Analyse',
    },
]
SHEET_AUDIT_RULES = {
    'decharge-donnees': [
        "Lignes = enregistrements `compte_rendu` correspondant exactement aux filtres actifs.",
        "Tri = `date_premier_jour` DESC, puis `submitted_at` DESC, puis `id` DESC.",
        "Prix VAS = champ stocké `prix_moyen_vas`, sans recalcul au rendu.",
    ],
    'notice-decharge': [
        "Les compteurs contrôlent uniquement les champs bruts présents ou absents dans `compte_rendu`.",
        "Aucune valeur n’est déduite à partir du texte libre.",
        "Région = déduction automatique depuis le code postal quand il est exploitable.",
    ],
    'synthese-global': [
        "Répartition filière = `GROUP BY filiere` sur le périmètre filtré.",
        "Binôme = `animation_solo` contenant `autre`, `Seul` = valeur exacte `Seul`.",
        "Moyenne prix = moyenne arithmétique des valeurs non nulles et non nulles à zéro.",
    ],
    'evolution-prix-2024': [
        "Série mensuelle = regroupement `(année, mois)` sur `date_premier_jour`.",
        "Les courbes prix utilisent les champs déjà stockés `prix_moyen_vas` et `prix_moyen_autre`.",
    ],
    'synthese-par-filiere': [
        "Sans filtre `filiere`, la vue reste exhaustive et n’applique aucun focus implicite.",
        "Avec filtre `filiere`, le périmètre est strictement réduit à cette valeur.",
    ],
    'prix-par-region': [
        "Région = valeur stockée dans le champ `region`.",
        "Les moyennes par morceau ignorent `NULL` et `0` comme dans les pivots Excel.",
    ],
    'detail-prix-filiere': [
        "La comparaison VAS / autre veau s’appuie directement sur les colonnes `prix_vas_*` et `prix_autre_*`.",
        "Sans filtre `filiere`, toutes les filières sont conservées dans le périmètre.",
    ],
    'anim-par-mag': [
        "Magasin = regroupement exact sur `nom_magasin` brut, sans fusion métier.",
        "Dernière animation = `MAX(date_premier_jour)` par groupe magasin.",
    ],
    'brouillon': [
        "Brouillon = `statut = 'brouillon'` uniquement.",
        "Aucun brouillon n’est inclus dans le mode `CR complets`.",
    ],
    'tableau-calcul': [
        "Etat Excel `CR OK` = `statut IN ('soumis', 'valide')`.",
        "Année et mois proviennent exclusivement de `date_premier_jour`.",
    ],
    'tdc': [
        "Les verbatims sont listés sans analyse sémantique ni classement automatique.",
        "Une ligne = un champ texte non vide parmi les sources déclarées.",
    ],
    'analyse-rh-25': [
        "Animateur = regroupement exact sur `nom_prenom`.",
        "Le ratio `CR par animateur` = `nombre de CR / nombre d’animateurs distincts`.",
    ],
    'donnee-liste': [
        "Les listes de référence sont extraites des valeurs réellement présentes en base.",
        "Aucune liste statique Excel n’est recopiée en dur.",
    ],
    'liste-nom-mag': [
        "La clé normalisée magasin = ASCII minuscule, accents/punctuation supprimés, espaces réduits.",
        "Ce contrôle est technique: il signale des variantes possibles, pas une fusion métier automatique.",
    ],
    'synthese-des-donnees': [
        "Croisement enseigne x filière = comptage exact des lignes du périmètre actif.",
        "Le total de ligne d’une enseigne = somme des colonnes filière de cette enseigne.",
    ],
}
DASHBOARD_LOAD_FIELDS = (
    CompteRendu.id,
    CompteRendu.statut,
    CompteRendu.created_at,
    CompteRendu.submitted_at,
    CompteRendu.date_premier_jour,
    CompteRendu.nom_prenom,
    CompteRendu.animation_solo,
    CompteRendu.filiere,
    CompteRendu.enseigne,
    CompteRendu.nom_magasin,
    CompteRendu.region,
    CompteRendu.code_departement,
    CompteRendu.rayons_presents,
    CompteRendu.ls_qualite_decoupe,
    CompteRendu.prix_moyen_vas,
    CompteRendu.prix_moyen_autre,
    CompteRendu.prix_vas_escalope,
    CompteRendu.prix_vas_saute,
    CompteRendu.prix_vas_roti,
    CompteRendu.prix_vas_tendron,
    CompteRendu.prix_vas_jarret,
    CompteRendu.prix_vas_hache,
    CompteRendu.prix_autre_escalope,
    CompteRendu.prix_autre_saute,
    CompteRendu.prix_autre_roti,
    CompteRendu.prix_autre_tendron,
    CompteRendu.prix_autre_jarret,
    CompteRendu.prix_autre_hache,
    CompteRendu.ref_animation,
    CompteRendu.avis_eleveur,
    CompteRendu.remarques_chef_boucher,
    CompteRendu.precisions_clients,
    CompteRendu.precisions_ressenti,
    CompteRendu.precisions_animation,
)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('dashboard.login'))
        return f(*args, **kwargs)

    return decorated


def _parse_admin_date(raw):
    value = (raw or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_admin_float(raw):
    value = (raw or '').strip().replace(',', '.')
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _multiline_field_value(raw):
    return '\n'.join(_json_list(raw))


def _parse_multiline_field(raw):
    items = [line.strip() for line in (raw or '').splitlines() if line.strip()]
    return json.dumps(items)


def _draft_resume_payload(cr):
    return {
        'token': cr.token,
        'url': url_for('submit.reprendre', token=cr.token, _external=True),
    }


def _draft_step_number(cr):
    if not cr.filiere:
        return 1
    if not cr.nom_magasin:
        return 2
    if not cr.rayons_presents:
        return 3
    if not cr.morceaux_presents:
        return 4
    if not cr.frequentation:
        return 5
    if not cr.attitude_clients:
        return 6
    if not cr.ressenti_mise_en_place:
        return 7
    return 8


@dashboard_bp.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next', '').strip()
    if request.method == 'POST':
        if request.form.get('password') == current_app.config['ADMIN_PASSWORD']:
            session['admin'] = True
            next_url = request.form.get('next', '').strip()
            if next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('dashboard.index'))
        flash('Mot de passe incorrect', 'error')
    elif session.get('admin'):
        if next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('dashboard.index'))

    return render_template('dashboard/login.html', next_url=next_url)


@dashboard_bp.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('dashboard.login'))


@dashboard_bp.route('/')
@admin_required
def index():
    filters = _get_filters()
    dataset = _build_dataset(filters)
    cards = _overview_cards(dataset['active'], dataset['drafts'])
    overview_chart = _monthly_activity_chart(dataset['active'], 'Activite sur la selection')
    widgets = _build_widgets(dataset, filters)
    recent_crs = dataset['all'][:8]
    filter_options = _filter_options()

    return render_template(
        'dashboard/index.html',
        filtres=filters,
        widgets=widgets,
        cards=cards,
        overview_chart=overview_chart,
        recent_crs=recent_crs,
        has_filters=_has_filters(filters),
        **filter_options,
    )


@dashboard_bp.route('/workbook/<sheet_key>')
@admin_required
def sheet_view(sheet_key):
    filters = _get_filters()
    dataset = _build_dataset(filters)
    page = _build_sheet_page(sheet_key, dataset, filters)
    if not page:
        abort(404)

    return render_template(
        'dashboard/sheet.html',
        page=page,
        filtres=filters,
        has_filters=_has_filters(filters),
        **_filter_options(),
    )


@dashboard_bp.route('/cr/<int:cr_id>')
@admin_required
def detail(cr_id):
    cr = CompteRendu.query.get_or_404(cr_id)
    photos = Photo.query.filter_by(cr_id=cr_id).all()
    resume_link = _draft_resume_payload(cr) if cr.statut == 'brouillon' else None

    data = {k: _json_list(getattr(cr, k)) for k in [
        'rayons_presents',
        'ls_barquettes',
        'ls_outils_com',
        'trad_outils_com',
        'morceaux_presents',
        'emplacement_animation',
        'outils_animation',
        'mise_en_avant',
        'tranche_age',
        'attitude_clients',
        'type_questions',
        'echanges_chef_boucher',
        'type_incident',
    ]}

    return render_template('dashboard/detail.html', cr=cr, photos=photos, data=data, resume_link=resume_link)


@dashboard_bp.route('/cr/<int:cr_id>/valider', methods=['POST'])
@admin_required
def valider(cr_id):
    cr = CompteRendu.query.get_or_404(cr_id)
    cr.statut = 'valide'
    cr.notes_admin = request.form.get('notes_admin', cr.notes_admin)
    db.session.commit()
    flash('Compte-rendu validé.', 'success')
    return redirect(url_for('dashboard.detail', cr_id=cr_id))


@dashboard_bp.route('/cr/<int:cr_id>/modifier', methods=['GET', 'POST'])
@admin_required
def modifier(cr_id):
    cr = CompteRendu.query.get_or_404(cr_id)
    next_url = request.args.get('next', '').strip() or url_for('dashboard.detail', cr_id=cr_id)
    if request.method == 'POST':
        for field in ADMIN_TEXT_FIELDS:
            setattr(cr, field, request.form.get(field, '').strip())

        for field in ADMIN_DATE_FIELDS:
            setattr(cr, field, _parse_admin_date(request.form.get(field)))

        for field in ADMIN_FLOAT_FIELDS:
            setattr(cr, field, _parse_admin_float(request.form.get(field)))

        for field, _label in ADMIN_LIST_FIELDS:
            setattr(cr, field, _parse_multiline_field(request.form.get(field)))

        manual_departement = request.form.get('code_departement', '').strip().upper()
        cr.code_departement = manual_departement or infer_department_code(cr.code_postal)
        manual_region = request.form.get('region', '').strip()
        cr.region = manual_region or infer_region(cr.code_postal, cr.code_departement)
        cr.prix_moyen_vas = cr.calc_prix_moyen_vas()
        cr.prix_moyen_autre = cr.calc_prix_moyen_autre()
        db.session.commit()
        flash('Compte-rendu modifié.', 'success')
        return redirect(request.form.get('next') or next_url)

    return render_template(
        'dashboard/edit.html',
        cr=cr,
        next_url=next_url,
        resume_link=_draft_resume_payload(cr) if cr.statut == 'brouillon' else None,
        list_fields=ADMIN_LIST_FIELDS,
        list_values={field: _multiline_field_value(getattr(cr, field)) for field, _label in ADMIN_LIST_FIELDS},
        price_fields=PRICE_COMPARISON_FIELDS,
        statut_options=ADMIN_STATUT_OPTIONS,
        filiere_options=ADMIN_FILIERE_OPTIONS,
        enseigne_options=ADMIN_ENSEIGNE_OPTIONS,
        solo_options=ADMIN_SOLO_OPTIONS,
    )


@dashboard_bp.route('/cr/<int:cr_id>/supprimer', methods=['POST'])
@admin_required
def supprimer(cr_id):
    cr = CompteRendu.query.get_or_404(cr_id)

    upload_dir = current_app.config['UPLOAD_FOLDER']
    for photo in cr.photos:
        fpath = os.path.join(upload_dir, photo.filename)
        if os.path.exists(fpath):
            os.remove(fpath)
    if cr.signature_boucher_path:
        fpath = os.path.join(upload_dir, cr.signature_boucher_path)
        if os.path.exists(fpath):
            os.remove(fpath)

    db.session.delete(cr)
    db.session.commit()
    flash('Compte-rendu supprimé.', 'success')
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/stats')
@admin_required
def stats():
    filters = _get_filters()
    records = _build_dataset(filters)['active']
    chart = _price_timeline_chart(records, 'Prix moyens par mois')
    return jsonify(chart['data'])


@dashboard_bp.route('/test-mail')
@admin_required
def test_mail():
    """Route de diagnostic : envoie un mail de test à l'adresse admin."""
    dest = current_app.config.get('ADMIN_EMAIL', 'contact@irva.fr')
    cfg = {
        'MAIL_SERVER': current_app.config.get('MAIL_SERVER'),
        'MAIL_PORT': current_app.config.get('MAIL_PORT'),
        'MAIL_USERNAME': current_app.config.get('MAIL_USERNAME'),
        'MAIL_USE_SSL': current_app.config.get('MAIL_USE_SSL'),
        'MAIL_DEFAULT_SENDER': current_app.config.get('MAIL_DEFAULT_SENDER'),
        'password_set': bool(current_app.config.get('MAIL_PASSWORD')),
    }
    try:
        from flask_mail import Mail, Message
        mail = Mail(current_app)
        msg = Message(
            subject='[IRVA] Test mail — configuration OK',
            recipients=[dest],
            html=(
                '<p>Ce mail de test confirme que la configuration SMTP de '
                'l\'application IRVA Animations est fonctionnelle.</p>'
                f'<pre style="font-size:11px;color:#555">{cfg}</pre>'
            ),
        )
        mail.send(msg)
        flash(f'Mail de test envoyé à {dest}. Vérifie ta boîte de réception.', 'success')
    except Exception as e:
        flash(f'Erreur mail : {e}', 'error')
    return redirect(url_for('dashboard.index'))


def _get_filters():
    return {
        'filiere': request.args.get('filiere', '').strip(),
        'annee': request.args.get('annee', '').strip(),
        'mois': request.args.get('mois', '').strip(),
        'statut': request.args.get('statut', 'complet').strip() or 'complet',
        'q': request.args.get('q', '').strip(),
    }


def _filter_options():
    filieres = [
        fil
        for (fil,) in db.session.query(CompteRendu.filiere)
        .filter(CompteRendu.filiere.isnot(None))
        .distinct()
        .order_by(CompteRendu.filiere)
        .all()
        if fil
    ]
    annees = [
        int(year)
        for (year,) in db.session.query(extract('year', CompteRendu.date_premier_jour))
        .filter(CompteRendu.date_premier_jour.isnot(None))
        .distinct()
        .order_by(extract('year', CompteRendu.date_premier_jour).desc())
        .all()
        if year
    ]
    return {
        'filieres_dispo': filieres,
        'annees_dispo': annees,
        'statuts_dispo': [
            ('complet', 'CR complets'),
            ('soumis', 'Soumis'),
            ('valide', 'Valides'),
            ('brouillon', 'Brouillons'),
            ('tous', 'Tous'),
        ],
    }


def _has_filters(filters):
    return any(filters.get(key) not in ('', 'complet') for key in filters)


def _build_dataset(filters):
    all_filters = dict(filters, statut='tous')
    draft_filters = dict(filters, statut='brouillon')
    return {
        'active': _query_records(filters),
        'all': _query_records(all_filters),
        'drafts': _query_records(draft_filters),
    }


def _query_records(filters):
    q = CompteRendu.query.options(load_only(*DASHBOARD_LOAD_FIELDS))

    status_mode = filters.get('statut') or 'complet'
    if status_mode == 'complet':
        q = q.filter(CompteRendu.statut.in_(COMPLETE_STATUSES))
    elif status_mode != 'tous':
        q = q.filter(CompteRendu.statut == status_mode)

    if filters.get('filiere'):
        q = q.filter(CompteRendu.filiere == filters['filiere'])
    if filters.get('annee'):
        q = q.filter(extract('year', CompteRendu.date_premier_jour) == int(filters['annee']))
    if filters.get('mois'):
        q = q.filter(extract('month', CompteRendu.date_premier_jour) == int(filters['mois']))
    if filters.get('q'):
        needle = f"%{filters['q']}%"
        q = q.filter(
            or_(
                CompteRendu.nom_prenom.ilike(needle),
                CompteRendu.nom_magasin.ilike(needle),
                CompteRendu.commune.ilike(needle),
                CompteRendu.region.ilike(needle),
                CompteRendu.ref_animation.ilike(needle),
            )
        )

    return q.order_by(
        CompteRendu.date_premier_jour.desc(),
        CompteRendu.submitted_at.desc(),
        CompteRendu.id.desc(),
    ).all()


def _overview_cards(active_records, draft_records):
    unique_stores = len({(cr.nom_magasin or '').strip() for cr in active_records if cr.nom_magasin})
    regions = len({(cr.region or '').strip() for cr in active_records if cr.region})
    return [
        {'value': _fmt_int(len(active_records)), 'label': 'CR analyses'},
        {'value': _fmt_int(len(draft_records)), 'label': 'Brouillons en cours'},
        {'value': _fmt_int(unique_stores), 'label': 'Magasins uniques'},
        {'value': _fmt_money(_avg([cr.prix_moyen_vas for cr in active_records], max_val=_PRIX_MAX), 'EUR/kg'), 'label': 'Prix moyen VAS'},
        {'value': _fmt_int(regions), 'label': 'Regions couvertes'},
    ]


def _build_widgets(dataset, filters):
    active_records = dataset['active']
    draft_records = dataset['drafts']
    all_records = dataset['all']

    unique_regions = len({cr.region for cr in active_records if cr.region})
    unique_stores = len({cr.nom_magasin for cr in active_records if cr.nom_magasin})
    comment_count = len(_comment_rows(active_records))
    duplicate_groups = len([g for g in _store_duplicate_rows(all_records) if g[2] > 1])
    active_filieres = len({cr.filiere for cr in active_records if cr.filiere})

    summary = {
        'decharge-donnees': (_fmt_int(len(all_records)), 'lignes filtrees'),
        'notice-decharge': ('4', 'controles de base'),
        'synthese-global': (_fmt_int(len(active_records)), 'CR complets'),
        'evolution-prix-2024': (_fmt_money(_avg([cr.prix_moyen_vas for cr in active_records], max_val=_PRIX_MAX), 'EUR/kg'), 'moyenne VAS'),
        'synthese-par-filiere': (_fmt_int(active_filieres), 'filieres actives'),
        'prix-par-region': (_fmt_int(unique_regions), 'regions actives'),
        'detail-prix-filiere': (_fmt_int(len([cr for cr in active_records if cr.prix_moyen_autre])), 'comparaisons VAS/autre'),
        'anim-par-mag': (_fmt_int(unique_stores), 'magasins animes'),
        'brouillon': (_fmt_int(len(draft_records)), 'saisies a reprendre'),
        'tableau-calcul': (_fmt_int(len(all_records)), 'lignes normalisees'),
        'tdc': (_fmt_int(comment_count), 'retours terrain'),
        'analyse-rh-25': (_fmt_int(len({cr.nom_prenom for cr in active_records if cr.nom_prenom})), 'animateurs uniques'),
        'donnee-liste': (_fmt_int(len(_department_rows(all_records))), 'departements actifs'),
        'liste-nom-mag': (_fmt_int(duplicate_groups), 'groupes normalises'),
        'synthese-des-donnees': (_fmt_int(len(active_records)), 'lignes consolidees'),
    }

    params = _query_params(filters)
    widgets = []
    for sheet in WORKBOOK_SHEETS:
        value, label = summary[sheet['key']]
        widgets.append({
            **sheet,
            'value': value,
            'value_label': label,
            'href': url_for('dashboard.sheet_view', sheet_key=sheet['key'], **params),
        })
    return widgets


def _build_sheet_page(sheet_key, dataset, filters):
    meta = next((sheet for sheet in WORKBOOK_SHEETS if sheet['key'] == sheet_key), None)
    if not meta:
        return None

    builders = {
        'decharge-donnees': _page_decharge,
        'notice-decharge': _page_notice,
        'synthese-global': _page_synthese_global,
        'evolution-prix-2024': _page_evolution_prix,
        'synthese-par-filiere': _page_synthese_filiere,
        'prix-par-region': _page_prix_region,
        'detail-prix-filiere': _page_detail_prix_filiere,
        'anim-par-mag': _page_anim_par_mag,
        'brouillon': _page_brouillons,
        'tableau-calcul': _page_tableau_calcul,
        'tdc': _page_tdc,
        'analyse-rh-25': _page_analyse_rh,
        'donnee-liste': _page_donnee_liste,
        'liste-nom-mag': _page_liste_mag,
        'synthese-des-donnees': _page_synthese_donnees,
    }
    page = builders[sheet_key](dataset, filters)
    page.update({
        'key': meta['key'],
        'sheet_name': meta['sheet_name'],
        'title': meta['title'],
        'description': meta['description'],
        'category': meta['category'],
        'audit_rules': _sheet_audit_rules(meta['key'], filters),
    })
    return page


def _page_notice(dataset, filters):
    records = dataset['active']
    missing_region = sum(1 for cr in records if not (cr.region or '').strip())
    missing_price = sum(1 for cr in records if cr.prix_moyen_vas is None)
    missing_store = sum(1 for cr in records if not (cr.nom_magasin or '').strip())
    sections = [
        {
            'type': 'cards',
            'title': 'Points de controle',
            'cards': [
                {'value': _fmt_int(len(records)), 'label': 'formulaires du périmètre'},
                {'value': _fmt_int(missing_region), 'label': 'regions manquantes'},
                {'value': _fmt_int(missing_store), 'label': 'magasins manquants'},
                {'value': _fmt_int(missing_price), 'label': 'prix VAS absents'},
            ],
        },
        {
            'type': 'notes',
            'title': 'Lecture du dashboard',
            'items': [
                'Le périmètre suit le filtre de statut courant; par défaut, le mode "CR complets" correspond aux formulaires soumis ou valides et reproduit la logique "CR OK" du fichier Excel.',
                'Toutes les vues se recalculent directement depuis la base: chaque nouveau formulaire apparait ici sans export manuel.',
                'Les champs multi-choix (rayons, barquettes, outils, questions) sont decomposes pour reconstituer les tableaux croises du classeur.',
                'Les moyennes de prix ignorent les valeurs vides ou nulles afin de rester comparables avec les pivots Excel.',
                'La region n’est pas demandee dans le formulaire: elle est deduite automatiquement depuis le code postal lorsqu’il est exploitable; sinon elle reste vide.',
                'Les noms magasins restent affiches tels qu’ils ont ete saisis, mais la vue "Liste des magasins" aide a repérer les doublons proches.',
            ],
        },
        {
            'type': 'table',
            'title': 'Raccourcis utiles',
            'columns': ['Vue', 'Ce que l’on y retrouve'],
            'rows': [
                ['Décharge données', 'La liste brute des CR et le lien direct vers chaque fiche'],
                ['Synthèse globale', 'Volumes, repartitions filieres, rayons et qualite de saisie'],
                ['Retours terrain', 'Les verbatims eleveurs et remarques magasins'],
                ['Tableau calcule', 'Les colonnes derivees utiles pour controler les exports'],
            ],
        },
        {
            'type': 'chart',
            'title': 'Activite de la selection',
            'chart': _monthly_activity_chart(records, 'CR sur la selection active')['chart'],
        },
    ]
    return {'summary': 'Mode d’emploi du dashboard et controle de la qualite de saisie.', 'sections': sections}


def _page_decharge(dataset, filters):
    records = dataset['all']
    sections = [
        {
            'type': 'cards',
            'title': 'Synthese rapide',
            'cards': [
                {'value': _fmt_int(len(records)), 'label': 'lignes affichees'},
                {'value': _fmt_int(len([cr for cr in records if cr.statut in COMPLETE_STATUSES])), 'label': 'CR complets'},
                {'value': _fmt_int(len([cr for cr in records if cr.statut == "brouillon"])), 'label': 'brouillons'},
                {'value': _fmt_int(len({cr.nom_magasin for cr in records if cr.nom_magasin})), 'label': 'magasins uniques'},
            ],
        },
        {
            'type': 'table',
            'title': 'Formulaires',
            'columns': ['Date anim.', 'Eleveur', 'Filiere', 'Enseigne', 'Magasin', 'Region', 'Prix VAS', 'Statut', 'Fiche', 'Actions'],
            'rows': [
                [
                    _fmt_date(cr.date_premier_jour),
                    cr.nom_prenom or '—',
                    cr.filiere or '—',
                    cr.enseigne or '—',
                    cr.nom_magasin or '—',
                    cr.region or '—',
                    _fmt_money(cr.prix_moyen_vas, 'EUR/kg'),
                    _status_label(cr.statut),
                    {'text': 'Ouvrir', 'href': url_for('dashboard.detail', cr_id=cr.id)},
                    {'type': 'actions', 'cr_id': cr.id,
                     'delete_url': url_for('dashboard.supprimer', cr_id=cr.id),
                     'edit_url': url_for('dashboard.modifier', cr_id=cr.id, next=request.full_path)},
                ]
                for cr in records
            ],
            'empty': 'Aucun formulaire sur cette selection.',
        },
    ]
    return {'summary': 'Equivalent live de la feuille source du classeur.', 'sections': sections}


def _page_synthese_global(dataset, filters):
    records = dataset['active']
    filiere_rows = [[label, _fmt_int(count)] for label, count in _counts_by(records, lambda cr: cr.filiere or 'Non renseignee')]
    solo_rows = []
    for label, group in _grouped(records, lambda cr: cr.filiere or 'Non renseignee'):
        total = len(group)
        solo = sum(1 for cr in group if (cr.animation_solo or '').strip() == 'Seul')
        duo = sum(1 for cr in group if 'autre' in (cr.animation_solo or '').lower())
        solo_rows.append([label, _fmt_int(solo), _fmt_int(duo), _fmt_percent(_safe_div(duo, total))])

    sections = [
        {
            'type': 'cards',
            'title': 'Vue globale',
            'cards': [
                {'value': _fmt_int(len(records)), 'label': 'CR analyses'},
                {'value': _fmt_int(len({cr.nom_magasin for cr in records if cr.nom_magasin})), 'label': 'magasins uniques'},
                {'value': _fmt_money(_avg([cr.prix_moyen_vas for cr in records], max_val=_PRIX_MAX), 'EUR/kg'), 'label': 'prix moyen VAS'},
                {'value': _fmt_money(_avg([cr.prix_moyen_autre for cr in records], max_val=_PRIX_MAX), 'EUR/kg'), 'label': 'prix moyen autre veau'},
            ],
        },
        {
            'type': 'chart',
            'title': 'Activite mensuelle',
            'chart': _monthly_activity_chart(records, 'Nombre de CR par mois')['chart'],
        },
        {
            'type': 'table',
            'title': 'Repartition par filiere',
            'columns': ['Filiere', 'CR'],
            'rows': filiere_rows,
        },
        {
            'type': 'table',
            'title': 'Seul ou en binome',
            'columns': ['Filiere', 'Seul', 'Binome', 'Part du binome'],
            'rows': solo_rows,
        },
        {
            'type': 'table',
            'title': 'Rayons presents par enseigne',
            'columns': ['Enseigne', 'LS', 'Trad', 'Drive', 'Entree magasin', 'Total CR'],
            'rows': _rayon_rows(records),
        },
        {
            'type': 'table',
            'title': 'Qualite de decoupe LS',
            'columns': ['Qualite', 'CR'],
            'rows': [[label, _fmt_int(count)] for label, count in _counts_by(records, lambda cr: cr.ls_qualite_decoupe or 'Non renseignee')],
        },
    ]
    return {'summary': 'Equivalent de la synthese globale Excel, alimentee en direct.', 'sections': sections}


def _page_evolution_prix(dataset, filters):
    records = dataset['active']
    sections = [
        {
            'type': 'cards',
            'title': 'Repere prix',
            'cards': [
                {'value': _fmt_money(_avg([cr.prix_moyen_vas for cr in records], max_val=_PRIX_MAX), 'EUR/kg'), 'label': 'prix moyen VAS'},
                {'value': _fmt_money(_avg([cr.prix_moyen_autre for cr in records], max_val=_PRIX_MAX), 'EUR/kg'), 'label': 'prix moyen autre veau'},
                {'value': _fmt_int(len([cr for cr in records if cr.prix_moyen_autre])), 'label': 'CR comparables'},
            ],
        },
        {
            'type': 'chart',
            'title': 'Evolution mensuelle des prix',
            'chart': _price_timeline_chart(records, 'Prix moyens par mois')['chart'],
        },
        {
            'type': 'table',
            'title': 'Prix moyens par enseigne',
            'columns': ['Enseigne', 'Escalope', 'Saute', 'Roti', 'Tendron', 'Jarret', 'Hache', 'Moyenne VAS'],
            'rows': _price_rows_by_group(records, lambda cr: cr.enseigne or 'Autre'),
        },
    ]
    return {'summary': 'Suivi des prix moyens par periode et par enseigne.', 'sections': sections}


def _page_synthese_filiere(dataset, filters):
    records = dataset['active']
    selected_filiere = filters.get('filiere')
    focus = selected_filiere or 'Toutes les filieres'
    focus_records = [cr for cr in records if (cr.filiere or 'Non renseignee') == selected_filiere] if selected_filiere else records

    sections = [
        {
            'type': 'cards',
            'title': f'Focus filiere: {focus or "—"}',
            'cards': [
                {'value': focus or '—', 'label': 'filiere'},
                {'value': _fmt_int(len(focus_records)), 'label': 'CR de la filiere'},
                {'value': _fmt_percent(_safe_div(len(focus_records), len(records))), 'label': 'part du global'},
                {'value': _fmt_money(_avg([cr.prix_moyen_vas for cr in focus_records], max_val=_PRIX_MAX), 'EUR/kg'), 'label': 'prix moyen VAS'},
            ],
        },
        {
            'type': 'chart',
            'title': 'Activite mensuelle de la filiere',
            'chart': _monthly_activity_chart(focus_records, f'CR {focus or "filiere"}')['chart'],
        },
        {
            'type': 'table',
            'title': 'Enseignes de la filiere',
            'columns': ['Enseigne', 'CR filiere', 'Derniere animation'],
            'rows': [
                [label, _fmt_int(len(group)), _fmt_date(max((cr.date_premier_jour for cr in group if cr.date_premier_jour), default=None))]
                for label, group in _grouped(focus_records, lambda cr: cr.enseigne or 'Autre')
            ],
        },
        {
            'type': 'table',
            'title': 'Rayons de la filiere',
            'columns': ['Enseigne', 'LS', 'Trad', 'Drive', 'Entree magasin', 'Total CR'],
            'rows': _rayon_rows(focus_records),
        },
        {
            'type': 'table',
            'title': 'Seul ou en binome',
            'columns': ['Mode', 'CR'],
            'rows': [[label, _fmt_int(count)] for label, count in _counts_by(focus_records, lambda cr: cr.animation_solo or 'Non renseigne')],
        },
    ]
    return {'summary': 'Equivalent de la feuille filiere avec focus dynamique sur la selection.', 'sections': sections}


def _page_prix_region(dataset, filters):
    records = dataset['active']
    sections = [
        {
            'type': 'cards',
            'title': 'Couverture territoriale',
            'cards': [
                {'value': _fmt_int(len({cr.region for cr in records if cr.region})), 'label': 'regions'},
                {'value': _fmt_int(len({cr.code_departement for cr in records if cr.code_departement})), 'label': 'departements'},
                {'value': _fmt_money(_avg([cr.prix_moyen_vas for cr in records], max_val=_PRIX_MAX), 'EUR/kg'), 'label': 'prix moyen VAS'},
            ],
        },
        {
            'type': 'table',
            'title': 'Prix moyens par region',
            'columns': ['Region', 'Escalope', 'Saute', 'Roti', 'Tendron', 'Jarret', 'Hache', 'Moyenne VAS', 'CR'],
            'rows': _price_rows_by_group(records, lambda cr: cr.region or 'Non renseignee', include_count=True),
        },
    ]
    return {'summary': 'Lecture regionale des prix et du maillage terrain.', 'sections': sections}


def _page_detail_prix_filiere(dataset, filters):
    records = dataset['active']
    selected_filiere = filters.get('filiere')
    focus = selected_filiere or 'Toutes les filieres'
    focus_records = [cr for cr in records if (cr.filiere or 'Non renseignee') == selected_filiere] if selected_filiere else records

    chart_labels = []
    chart_vas = []
    chart_autre = []
    chart_gap = []
    for suffix, label in PRICE_COMPARISON_FIELDS:
        vas_values = [getattr(cr, f'prix_vas_{suffix}') for cr in focus_records if getattr(cr, f'prix_vas_{suffix}') not in (None, 0)]
        autre_values = [getattr(cr, f'prix_autre_{suffix}') for cr in focus_records if getattr(cr, f'prix_autre_{suffix}') not in (None, 0)]
        avg_vas = _avg(vas_values, max_val=_PRIX_MAX)
        avg_autre = _avg(autre_values, max_val=_PRIX_MAX)
        chart_labels.append(label)
        chart_vas.append(avg_vas or 0)
        chart_autre.append(avg_autre or 0)
        chart_gap.append((avg_vas - avg_autre) if avg_vas is not None and avg_autre is not None else 0)

    sections = [
        {
            'type': 'cards',
            'title': 'Comparaison prix',
            'cards': [
                {'value': focus or '—', 'label': 'filiere'},
                {'value': _fmt_int(len([cr for cr in focus_records if cr.prix_moyen_autre])), 'label': 'CR avec autre veau'},
                {'value': _fmt_money(_avg([cr.prix_moyen_vas for cr in focus_records], max_val=_PRIX_MAX), 'EUR/kg'), 'label': 'prix moyen VAS'},
                {'value': _fmt_money(_avg([cr.prix_moyen_autre for cr in focus_records], max_val=_PRIX_MAX), 'EUR/kg'), 'label': 'prix moyen autre'},
            ],
        },
        {
            'type': 'chart',
            'title': 'VAS vs autre veau par morceau',
            'chart': _chart_config(
                'bar',
                chart_labels,
                [
                    _dataset_config('VAS', chart_vas, '#4F7942', 'rgba(79,121,66,0.15)'),
                    _dataset_config('Autre veau', chart_autre, '#E8732A', 'rgba(232,115,42,0.15)'),
                ],
            ),
        },
        {
            'type': 'table',
            'title': 'Detail par morceau',
            'columns': ['Morceau', 'Prix moyen VAS', 'Prix moyen autre', 'Ecart'],
            'rows': [
                [label, _fmt_money(chart_vas[idx], 'EUR/kg'), _fmt_money(chart_autre[idx], 'EUR/kg'), _fmt_money(chart_gap[idx], 'EUR/kg')]
                for idx, label in enumerate(chart_labels)
            ],
        },
        {
            'type': 'table',
            'title': 'Comparaison par filiere',
            'columns': ['Filiere', 'Prix moyen VAS', 'Prix moyen autre', 'CR comparables'],
            'rows': [
                [
                    label,
                    _fmt_money(_avg([cr.prix_moyen_vas for cr in group], max_val=_PRIX_MAX), 'EUR/kg'),
                    _fmt_money(_avg([cr.prix_moyen_autre for cr in group], max_val=_PRIX_MAX), 'EUR/kg'),
                    _fmt_int(len([cr for cr in group if cr.prix_moyen_autre])),
                ]
                for label, group in _grouped(records, lambda cr: cr.filiere or 'Non renseignee')
            ],
        },
    ]
    return {'summary': 'Equivalent du comparatif VAS / autre veau par filiere.', 'sections': sections}


def _page_anim_par_mag(dataset, filters):
    records = dataset['active']
    grouped = _grouped(records, lambda cr: cr.nom_magasin or 'Magasin non renseigne')
    rows = []
    for store, group in grouped:
        latest = max((cr.date_premier_jour for cr in group if cr.date_premier_jour), default=None)
        filieres = ', '.join(sorted({cr.filiere for cr in group if cr.filiere})) or '—'
        enseignes = ', '.join(sorted({cr.enseigne for cr in group if cr.enseigne})) or '—'
        rows.append([store, enseignes, filieres, _fmt_int(len(group)), _fmt_date(latest), group[0].region or '—'])

    rows.sort(key=lambda row: (-int(row[3].replace(' ', '')), row[0]))

    sections = [
        {
            'type': 'cards',
            'title': 'Reseau magasins',
            'cards': [
                {'value': _fmt_int(len(grouped)), 'label': 'magasins uniques'},
                {'value': _fmt_int(sum(1 for _, group in grouped if len(group) > 1)), 'label': 'magasins revisites'},
                {'value': _fmt_int(len(records)), 'label': 'animations / CR'},
            ],
        },
        {
            'type': 'chart',
            'title': 'Activite par annee',
            'chart': _yearly_activity_chart(records),
        },
        {
            'type': 'table',
            'title': 'Classement magasins',
            'columns': ['Magasin', 'Enseigne', 'Filiere(s)', 'CR', 'Derniere animation', 'Region'],
            'rows': rows,
        },
    ]
    return {'summary': 'Suivi des magasins et repetition des animations.', 'sections': sections}


def _page_brouillons(dataset, filters):
    records = dataset['drafts']
    sections = [
        {
            'type': 'cards',
            'title': 'Reprises a effectuer',
            'cards': [
                {'value': _fmt_int(len(records)), 'label': 'brouillons'},
                {'value': _fmt_int(sum(1 for cr in records if cr.nom_prenom)), 'label': 'avec nom eleveur'},
                {'value': _fmt_int(sum(1 for cr in records if cr.nom_magasin)), 'label': 'avec magasin'},
            ],
        },
        {
            'type': 'chart',
            'title': 'Brouillons par mois',
            'chart': _monthly_activity_chart(records, 'Brouillons par mois')['chart'],
        },
        {
            'type': 'table',
            'title': 'Brouillons ouverts',
            'columns': ['Creation', 'Eleveur', 'Email', 'Magasin', 'Filiere', 'Etape estimee', 'Code reprise', 'Derniere date animation', 'Fiche', 'Actions'],
            'rows': [
                [
                    _fmt_datetime(cr.created_at),
                    cr.nom_prenom or '—',
                    cr.email or '—',
                    cr.nom_magasin or '—',
                    cr.filiere or '—',
                    f'Etape {_draft_step_number(cr)}/8',
                    cr.token,
                    _fmt_date(cr.date_premier_jour),
                    {'text': 'Ouvrir', 'href': url_for('dashboard.detail', cr_id=cr.id)},
                    {'type': 'actions', 'cr_id': cr.id,
                     'delete_url': url_for('dashboard.supprimer', cr_id=cr.id),
                     'edit_url': url_for('dashboard.modifier', cr_id=cr.id, next=request.full_path)},
                ]
                for cr in records
            ],
            'empty': 'Aucun brouillon sur cette selection.',
        },
    ]
    return {'summary': 'Suivi des formulaires non finalises.', 'sections': sections}


def _page_tableau_calcul(dataset, filters):
    records = dataset['all']
    sections = [
        {
            'type': 'cards',
            'title': 'Normalisation',
            'cards': [
                {'value': _fmt_int(len(records)), 'label': 'lignes calculees'},
                {'value': _fmt_int(len({cr.ref_animation or f"cr-{cr.id}" for cr in records})), 'label': 'refs animation'},
                {'value': _fmt_int(len({cr.region for cr in records if cr.region})), 'label': 'regions reperees'},
            ],
        },
        {
            'type': 'table',
            'title': 'Vue normalisee',
            'columns': ['Ref', 'Etat', 'Date', 'Annee', 'Mois', 'Eleveur', 'Magasin', 'Enseigne', 'Filiere', 'Region', 'Prix VAS'],
            'rows': [
                [
                    cr.ref_animation or f'cr-{cr.id}',
                    'CR OK' if cr.statut in COMPLETE_STATUSES else 'Brouillon',
                    _fmt_date(cr.date_premier_jour),
                    str(cr.date_premier_jour.year) if cr.date_premier_jour else '—',
                    _month_label(cr.date_premier_jour.month) if cr.date_premier_jour else '—',
                    cr.nom_prenom or '—',
                    cr.nom_magasin or '—',
                    cr.enseigne or '—',
                    cr.filiere or '—',
                    cr.region or '—',
                    _fmt_money(cr.prix_moyen_vas, 'EUR/kg'),
                ]
                for cr in records
            ],
        },
    ]
    return {'summary': 'Equivalent vivant de la feuille technique de calcul.', 'sections': sections}


def _page_tdc(dataset, filters):
    records = dataset['active']
    comment_rows = _comment_rows(records)
    sections = [
        {
            'type': 'cards',
            'title': 'Verbatims',
            'cards': [
                {'value': _fmt_int(len(comment_rows)), 'label': 'retours collectes'},
                {'value': _fmt_int(len({row[1] for row in comment_rows if row[1] != "—"})), 'label': 'magasins cites'},
            ],
        },
        {
            'type': 'table',
            'title': 'Retours terrain consolides',
            'columns': ['Date', 'Magasin', 'Eleveur', 'Source', 'Commentaire'],
            'rows': comment_rows,
            'empty': 'Aucun retour terrain textuel sur cette selection.',
        },
    ]
    return {'summary': 'Compilation dynamique des commentaires eleveurs et magasin.', 'sections': sections}


def _page_analyse_rh(dataset, filters):
    records = dataset['active']
    participants = _grouped(records, lambda cr: cr.nom_prenom or 'Non renseigne')
    participant_rows = []
    for name, group in participants:
        participant_rows.append([
            name,
            _fmt_int(len(group)),
            ', '.join(sorted({cr.filiere for cr in group if cr.filiere})) or '—',
            ', '.join(sorted({cr.enseigne for cr in group if cr.enseigne})) or '—',
            _fmt_date(max((cr.date_premier_jour for cr in group if cr.date_premier_jour), default=None)),
        ])
    participant_rows.sort(key=lambda row: (-int(row[1].replace(' ', '')), row[0]))

    sections = [
        {
            'type': 'cards',
            'title': 'Charge d’animation',
            'cards': [
                {'value': _fmt_int(len(records)), 'label': 'CR / animations'},
                {'value': _fmt_int(len(participants)), 'label': 'animateurs uniques'},
                {'value': _fmt_number(_safe_div(len(records), max(len(participants), 1))), 'label': 'CR par animateur'},
            ],
        },
        {
            'type': 'chart',
            'title': 'Volume par mois',
            'chart': _monthly_activity_chart(records, 'CR par mois')['chart'],
        },
        {
            'type': 'table',
            'title': 'Top animateurs',
            'columns': ['Eleveur', 'CR', 'Filiere(s)', 'Enseigne(s)', 'Derniere animation'],
            'rows': participant_rows[:50],
        },
        {
            'type': 'table',
            'title': 'Couverture departementale',
            'columns': ['Departement', 'CR'],
            'rows': _department_rows(records),
        },
    ]
    return {'summary': 'Vision RH des animations, inspiree de l’onglet analyse du classeur.', 'sections': sections}


def _page_donnee_liste(dataset, filters):
    records = dataset['all']
    sections = [
        {
            'type': 'cards',
            'title': 'Listes de reference',
            'cards': [
                {'value': _fmt_int(len({cr.filiere for cr in records if cr.filiere})), 'label': 'filieres actives'},
                {'value': _fmt_int(len({cr.enseigne for cr in records if cr.enseigne})), 'label': 'enseignes'},
                {'value': _fmt_int(len({cr.region for cr in records if cr.region})), 'label': 'regions'},
                {'value': _fmt_int(len({cr.code_departement for cr in records if cr.code_departement})), 'label': 'departements'},
            ],
        },
        {
            'type': 'table',
            'title': 'Filieres',
            'columns': ['Filiere', 'CR'],
            'rows': [[label, _fmt_int(count)] for label, count in _counts_by(records, lambda cr: cr.filiere or 'Non renseignee')],
        },
        {
            'type': 'table',
            'title': 'Annees disponibles',
            'columns': ['Annee', 'CR'],
            'rows': [[label, _fmt_int(count)] for label, count in _counts_by(records, lambda cr: cr.date_premier_jour.year if cr.date_premier_jour else 'Sans date')],
        },
        {
            'type': 'table',
            'title': 'Regions',
            'columns': ['Region', 'CR'],
            'rows': [[label, _fmt_int(count)] for label, count in _counts_by(records, lambda cr: cr.region or 'Non renseignee')],
        },
        {
            'type': 'table',
            'title': 'Departements',
            'columns': ['Departement', 'CR'],
            'rows': [[label, _fmt_int(count)] for label, count in _counts_by(records, lambda cr: cr.code_departement or 'Non renseigne')],
        },
    ]
    return {'summary': 'Remplace les listes fixes Excel par des references tirees du live.', 'sections': sections}


def _page_liste_mag(dataset, filters):
    records = dataset['all']
    duplicate_rows = _store_duplicate_rows(records)
    sections = [
        {
            'type': 'cards',
            'title': 'Controle magasins',
            'cards': [
                {'value': _fmt_int(len({cr.nom_magasin for cr in records if cr.nom_magasin})), 'label': 'noms distincts'},
                {'value': _fmt_int(len([row for row in duplicate_rows if row[2] > 1])), 'label': 'doublons potentiels'},
            ],
        },
        {
            'type': 'table',
            'title': 'Normalisation des magasins',
            'columns': ['Cle normalisee', 'Variantes', 'CR', 'Exemples'],
            'rows': [
                [key, _fmt_int(variant_count), _fmt_int(total_count), ', '.join(examples)]
                for key, variant_count, total_count, examples in duplicate_rows
            ],
        },
    ]
    return {'summary': 'Detection des variantes de nom magasin pour fiabiliser les regroupements.', 'sections': sections}


def _page_synthese_donnees(dataset, filters):
    records = dataset['active']
    filieres = sorted({cr.filiere or 'Non renseignee' for cr in records})
    rows = []
    for enseigne, group in _grouped(records, lambda cr: cr.enseigne or 'Autre'):
        row = [enseigne]
        for filiere in filieres:
            row.append(_fmt_int(sum(1 for cr in group if (cr.filiere or 'Non renseignee') == filiere)))
        row.append(_fmt_int(len(group)))
        rows.append(row)

    sections = [
        {
            'type': 'cards',
            'title': 'Consolidation',
            'cards': [
                {'value': _fmt_int(len(records)), 'label': 'CR consolides'},
                {'value': _fmt_int(len({cr.nom_magasin for cr in records if cr.nom_magasin})), 'label': 'magasins'},
                {'value': _fmt_int(len({cr.filiere for cr in records if cr.filiere})), 'label': 'filieres'},
            ],
        },
        {
            'type': 'chart',
            'title': 'Mix filieres',
            'chart': _chart_config(
                'doughnut',
                [label for label, _ in _counts_by(records, lambda cr: cr.filiere or 'Non renseignee')],
                [
                    {
                        'label': 'CR',
                        'data': [count for _, count in _counts_by(records, lambda cr: cr.filiere or 'Non renseignee')],
                        'backgroundColor': ['#4F7942', '#E7B64A', '#E8732A', '#6997C2', '#A75D5D', '#6C7A89'],
                        'borderWidth': 0,
                    }
                ],
                begin_at_zero=False,
            ),
        },
        {
            'type': 'table',
            'title': 'Croisement enseigne x filiere',
            'columns': ['Enseigne', *filieres, 'Total'],
            'rows': rows,
        },
    ]
    return {'summary': 'Equivalent du tableau de synthese consolide de fin de classeur.', 'sections': sections}


def _json_list(raw_value):
    from app.utils import parse_multiselect
    return parse_multiselect(raw_value)


def _grouped(records, keyfunc):
    grouped = defaultdict(list)
    for record in records:
        grouped[keyfunc(record)].append(record)
    return sorted(grouped.items(), key=lambda item: (-len(item[1]), str(item[0]).lower()))


def _counts_by(records, keyfunc):
    counter = Counter(keyfunc(record) for record in records)
    return sorted(counter.items(), key=lambda item: (-item[1], str(item[0]).lower()))


def _month_label(month):
    return MONTH_LABELS.get(month, '—')


# Seuil au-delà duquel un prix €/kg est considéré aberrant (typo décimale)
_PRIX_MAX = 300.0


def _avg(values, max_val=None):
    nums = [v for v in values if v not in (None, '', 0)]
    if max_val is not None:
        nums = [v for v in nums if v <= max_val]
    return round(sum(nums) / len(nums), 2) if nums else None


def _safe_div(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def _fmt_int(value):
    return f'{int(value):,}'.replace(',', ' ')


def _fmt_number(value):
    if value is None:
        return '—'
    return f'{value:.2f}'.replace('.', ',')


def _fmt_percent(value):
    if value is None:
        return '—'
    return f'{value * 100:.1f} %'.replace('.', ',')


def _fmt_money(value, unit='EUR'):
    if value in (None, ''):
        return '—'
    suffix = f' {unit}' if unit else ''
    return f'{value:.2f}{suffix}'.replace('.', ',')


def _fmt_date(value):
    return value.strftime('%d/%m/%Y') if value else '—'


def _fmt_datetime(value):
    return value.strftime('%d/%m/%Y %H:%M') if value else '—'


def _status_label(value):
    return {
        'soumis': 'Soumis',
        'valide': 'Valide',
        'brouillon': 'Brouillon',
    }.get(value or '', value or '—')


def _query_params(filters):
    return {key: value for key, value in filters.items() if value and not (key == 'statut' and value == 'complet')}


def _sheet_audit_rules(sheet_key, filters):
    return [
        f"Source = table `compte_rendu`; périmètre = {_scope_rule(filters)}.",
        *SHEET_AUDIT_RULES.get(sheet_key, []),
    ]


def _scope_rule(filters):
    status_mode = filters.get('statut') or 'complet'
    status_rule = {
        'complet': "statut IN ('soumis', 'valide')",
        'soumis': "statut = 'soumis'",
        'valide': "statut = 'valide'",
        'brouillon': "statut = 'brouillon'",
        'tous': "aucun filtre de statut",
    }.get(status_mode, f"statut = '{status_mode}'")

    extra_rules = []
    if filters.get('filiere'):
        extra_rules.append(f"filiere = '{filters['filiere']}'")
    if filters.get('annee'):
        extra_rules.append(f"YEAR(date_premier_jour) = {filters['annee']}")
    if filters.get('mois'):
        extra_rules.append(f"MONTH(date_premier_jour) = {filters['mois']}")
    if filters.get('q'):
        extra_rules.append(f"recherche LIKE '%{filters['q']}%' sur nom_prenom, nom_magasin, commune, region, ref_animation")

    if not extra_rules:
        return status_rule
    return status_rule + ' AND ' + ' AND '.join(extra_rules)


def _monthly_activity_chart(records, title):
    monthly = Counter()
    for cr in records:
        if cr.date_premier_jour:
            monthly[(cr.date_premier_jour.year, cr.date_premier_jour.month)] += 1
    labels = []
    values = []
    for (year, month), count in sorted(monthly.items()):
        labels.append(f'{_month_label(month)} {year}')
        values.append(count)
    return {
        'title': title,
        'chart': _chart_config(
            'bar',
            labels,
            [_dataset_config('CR', values, '#4F7942', 'rgba(79,121,66,0.18)')],
        ),
    }


def _price_timeline_chart(records, title):
    monthly = defaultdict(lambda: {'vas': [], 'autre': []})
    for cr in records:
        if not cr.date_premier_jour:
            continue
        key = (cr.date_premier_jour.year, cr.date_premier_jour.month)
        if cr.prix_moyen_vas not in (None, 0):
            monthly[key]['vas'].append(cr.prix_moyen_vas)
        if cr.prix_moyen_autre not in (None, 0):
            monthly[key]['autre'].append(cr.prix_moyen_autre)

    labels = []
    vas = []
    autre = []
    for key in sorted(monthly):
        labels.append(f'{_month_label(key[1])} {key[0]}')
        vas.append(_avg(monthly[key]['vas']) or 0)
        autre.append(_avg(monthly[key]['autre']) or 0)

    return {
        'title': title,
        'chart': _chart_config(
            'line',
            labels,
            [
                _dataset_config('VAS', vas, '#4F7942', 'rgba(79,121,66,0.12)', fill=True),
                _dataset_config('Autre veau', autre, '#E8732A', 'rgba(232,115,42,0.10)', fill=True),
            ],
            begin_at_zero=False,
        ),
        'data': {'labels': labels, 'vas': vas, 'autre': autre},
    }


def _yearly_activity_chart(records):
    counter = Counter()
    for cr in records:
        year = str(cr.date_premier_jour.year) if cr.date_premier_jour else 'Sans date'
        counter[year] += 1
    ordered = sorted(
        counter.items(),
        key=lambda item: (item[0] == 'Sans date', int(item[0]) if item[0] != 'Sans date' else 9999),
    )
    labels = [year for year, _ in ordered]
    values = [count for _, count in ordered]
    return _chart_config('bar', labels, [_dataset_config('CR', values, '#6997C2', 'rgba(105,151,194,0.18)')])


def _dataset_config(label, data, border_color, background_color, fill=False):
    return {
        'label': label,
        'data': data,
        'borderColor': border_color,
        'backgroundColor': background_color,
        'fill': fill,
        'tension': 0.25,
    }


def _chart_config(chart_type, labels, datasets, begin_at_zero=True):
    return {
        'type': chart_type,
        'data': {'labels': labels, 'datasets': datasets},
        'options': {
            'responsive': True,
            'maintainAspectRatio': False,
            'plugins': {'legend': {'position': 'top'}},
            'scales': {'y': {'beginAtZero': begin_at_zero}},
        },
    }


def _rayon_rows(records):
    rayon_labels = [
        'Rayon libre-service (LS)',
        'Rayon Coupe (Trad)',
        'Drive',
        "Libre service à l'entrée du magasin (ponctuellement)",
        'Libre service entree (ponctuel)',
    ]
    rows = []
    for enseigne, group in _grouped(records, lambda cr: cr.enseigne or 'Autre'):
        counts = [0, 0, 0, 0]
        for cr in group:
            values = _json_list(cr.rayons_presents)
            counts[0] += int(rayon_labels[0] in values)
            counts[1] += int(rayon_labels[1] in values)
            counts[2] += int(rayon_labels[2] in values)
            counts[3] += int(rayon_labels[3] in values or rayon_labels[4] in values)
        rows.append([enseigne, *[_fmt_int(count) for count in counts], _fmt_int(len(group))])
    return rows


def _price_rows_by_group(records, keyfunc, include_count=False):
    rows = []
    for label, group in _grouped(records, keyfunc):
        row = [label]
        averages = []
        for attr, _piece_label in PRICE_FIELDS:
            avg_price = _avg([getattr(cr, attr) for cr in group])
            averages.append(avg_price)
            row.append(_fmt_money(avg_price, 'EUR/kg'))
        row.append(_fmt_money(_avg([cr.prix_moyen_vas for cr in group], max_val=_PRIX_MAX), 'EUR/kg'))
        if include_count:
            row.append(_fmt_int(len(group)))
        rows.append(row)
    return rows


def _comment_rows(records):
    rows = []
    mapping = [
        ('avis_eleveur', 'Avis eleveur'),
        ('remarques_chef_boucher', 'Remarque chef boucher'),
        ('precisions_clients', 'Clients'),
        ('precisions_ressenti', 'Ressenti'),
        ('precisions_animation', 'Animation'),
    ]
    for cr in records:
        for field_name, label in mapping:
            content = (getattr(cr, field_name) or '').strip()
            if content:
                rows.append([
                    _fmt_date(cr.date_premier_jour),
                    cr.nom_magasin or '—',
                    cr.nom_prenom or '—',
                    label,
                    content,
                ])
    rows.sort(key=lambda row: row[0], reverse=True)
    return rows


def _department_rows(records):
    return [[label, _fmt_int(count)] for label, count in _counts_by(records, lambda cr: cr.code_departement or 'Non renseigne')]


def _normalize_store_name(name):
    normalized = unicodedata.normalize('NFKD', name or '')
    normalized = normalized.encode('ascii', 'ignore').decode('ascii').lower()
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip() or 'non-renseigne'


def _store_duplicate_rows(records):
    grouped = defaultdict(list)
    for cr in records:
        if not cr.nom_magasin:
            continue
        grouped[_normalize_store_name(cr.nom_magasin)].append(cr.nom_magasin.strip())

    rows = []
    for key, variants in grouped.items():
        variant_counter = Counter(variants)
        rows.append([
            key,
            len(variant_counter),
            len(variants),
            list(variant_counter.keys())[:4],
        ])
    rows.sort(key=lambda row: (-row[1], -row[2], row[0]))
    return rows
