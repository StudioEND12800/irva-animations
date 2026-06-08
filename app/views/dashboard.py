import json
import os
from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, current_app, jsonify, abort)
from models import db, CompteRendu, Photo
from sqlalchemy import func, extract

dashboard_bp = Blueprint('dashboard', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('dashboard.login'))
        return f(*args, **kwargs)
    return decorated


@dashboard_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == current_app.config['ADMIN_PASSWORD']:
            session['admin'] = True
            return redirect(url_for('dashboard.index'))
        flash('Mot de passe incorrect', 'error')
    return render_template('dashboard/login.html')


@dashboard_bp.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('dashboard.login'))


@dashboard_bp.route('/')
@admin_required
def index():
    # Filtres
    filiere = request.args.get('filiere', '')
    annee = request.args.get('annee', '')
    mois = request.args.get('mois', '')
    statut = request.args.get('statut', 'soumis')
    search = request.args.get('q', '')

    q = CompteRendu.query
    if statut:
        q = q.filter_by(statut=statut)
    if filiere:
        q = q.filter_by(filiere=filiere)
    if annee:
        q = q.filter(extract('year', CompteRendu.date_premier_jour) == int(annee))
    if mois:
        q = q.filter(extract('month', CompteRendu.date_premier_jour) == int(mois))
    if search:
        q = q.filter(
            db.or_(
                CompteRendu.nom_prenom.ilike(f'%{search}%'),
                CompteRendu.nom_magasin.ilike(f'%{search}%'),
                CompteRendu.commune.ilike(f'%{search}%'),
            )
        )

    crs = q.order_by(CompteRendu.submitted_at.desc()).all()

    # KPIs
    total = CompteRendu.query.filter_by(statut='soumis').count()
    filieres = db.session.query(
        CompteRendu.filiere, func.count(CompteRendu.id)
    ).filter_by(statut='soumis').group_by(CompteRendu.filiere).all()

    prix_moyen = db.session.query(
        func.avg(CompteRendu.prix_moyen_vas)
    ).filter_by(statut='soumis').scalar()

    enseignes = db.session.query(
        CompteRendu.enseigne, func.count(CompteRendu.id)
    ).filter_by(statut='soumis').group_by(CompteRendu.enseigne).order_by(
        func.count(CompteRendu.id).desc()
    ).limit(10).all()

    annees_dispo = db.session.query(
        extract('year', CompteRendu.date_premier_jour)
    ).distinct().order_by(
        extract('year', CompteRendu.date_premier_jour).desc()
    ).all()

    return render_template('dashboard/index.html',
        crs=crs,
        total=total,
        filieres=filieres,
        prix_moyen=prix_moyen,
        enseignes=enseignes,
        annees_dispo=[int(a[0]) for a in annees_dispo if a[0]],
        filtres={'filiere': filiere, 'annee': annee, 'mois': mois, 'statut': statut, 'q': search},
    )


@dashboard_bp.route('/cr/<int:cr_id>')
@admin_required
def detail(cr_id):
    cr = CompteRendu.query.get_or_404(cr_id)
    photos = Photo.query.filter_by(cr_id=cr_id).all()

    # Désérialiser les JSON
    def jload(s):
        if not s:
            return []
        try:
            return json.loads(s)
        except Exception:
            return [s]

    data = {k: jload(getattr(cr, k)) for k in [
        'rayons_presents', 'ls_barquettes', 'ls_outils_com', 'trad_outils_com',
        'morceaux_presents', 'emplacement_animation', 'outils_animation', 'mise_en_avant',
        'tranche_age', 'attitude_clients', 'type_questions', 'echanges_chef_boucher',
        'type_incident',
    ]}

    return render_template('dashboard/detail.html', cr=cr, photos=photos, data=data)


@dashboard_bp.route('/cr/<int:cr_id>/valider', methods=['POST'])
@admin_required
def valider(cr_id):
    cr = CompteRendu.query.get_or_404(cr_id)
    cr.statut = 'valide'
    cr.notes_admin = request.form.get('notes_admin', cr.notes_admin)
    db.session.commit()
    flash('Compte-rendu validé.', 'success')
    return redirect(url_for('dashboard.detail', cr_id=cr_id))


@dashboard_bp.route('/cr/<int:cr_id>/supprimer', methods=['POST'])
@admin_required
def supprimer(cr_id):
    cr = CompteRendu.query.get_or_404(cr_id)
    # Supprimer les fichiers
    upload_dir = current_app.config['UPLOAD_FOLDER']
    for p in cr.photos:
        fpath = os.path.join(upload_dir, p.filename)
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
    """Données JSON pour les graphes Chart.js."""
    # Prix moyens par mois
    prix_par_mois = db.session.query(
        extract('year', CompteRendu.date_premier_jour).label('annee'),
        extract('month', CompteRendu.date_premier_jour).label('mois'),
        func.avg(CompteRendu.prix_moyen_vas).label('prix_vas'),
        func.avg(CompteRendu.prix_moyen_autre).label('prix_autre'),
        func.count(CompteRendu.id).label('nb'),
    ).filter_by(statut='soumis').group_by('annee', 'mois').order_by('annee', 'mois').all()

    return jsonify({
        'prix_par_mois': [
            {'annee': int(r.annee), 'mois': int(r.mois),
             'prix_vas': round(r.prix_vas, 2) if r.prix_vas else None,
             'prix_autre': round(r.prix_autre, 2) if r.prix_autre else None,
             'nb': r.nb}
            for r in prix_par_mois
        ],
    })
