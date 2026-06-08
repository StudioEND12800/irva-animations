import os
import json
import secrets
import base64
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, current_app, jsonify)
from werkzeug.utils import secure_filename
from models import db, CompteRendu, Photo

submit_bp = Blueprint('submit', __name__)

ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def get_or_create_cr(token=None):
    """Récupère le CR en cours depuis la session ou en crée un nouveau."""
    if token:
        cr = CompteRendu.query.filter_by(token=token).first()
        if cr:
            session['cr_token'] = cr.token
            return cr
    if 'cr_token' in session:
        cr = CompteRendu.query.filter_by(token=session['cr_token']).first()
        if cr and cr.statut == 'brouillon':
            return cr
    # Nouveau CR
    cr = CompteRendu(token=secrets.token_urlsafe(32), statut='brouillon')
    db.session.add(cr)
    db.session.commit()
    session['cr_token'] = cr.token
    return cr


# ── Page d'accueil / reprise ──────────────────────────────────────────────────

@submit_bp.route('/')
def index():
    return render_template('form/index.html')


@submit_bp.route('/reprendre/<token>')
def reprendre(token):
    cr = CompteRendu.query.filter_by(token=token).first_or_404()
    if cr.statut == 'soumis':
        flash('Ce compte-rendu a déjà été soumis.', 'info')
        return render_template('form/confirme.html', cr=cr)
    session['cr_token'] = cr.token
    return redirect(url_for('submit.etape', num=_etape_courante(cr)))


def _etape_courante(cr):
    """Retourne l'étape où l'éleveur s'est arrêté."""
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


# ── Étapes du formulaire ──────────────────────────────────────────────────────

@submit_bp.route('/formulaire/<int:num>', methods=['GET', 'POST'])
def etape(num):
    cr = get_or_create_cr()

    if request.method == 'POST':
        _save_etape(cr, num, request.form, request.files)
        db.session.commit()

        if request.form.get('action') == 'sauvegarder':
            mail_sent = _envoyer_lien_reprise(cr)
            session['resume_notice'] = {
                'token': cr.token,
                'mail_sent': mail_sent,
            }
            if mail_sent:
                flash('Brouillon sauvegardé. Le lien de reprise a été envoyé par e-mail.', 'success')
            else:
                flash('Brouillon sauvegardé. Le mail de reprise n’a pas pu être envoyé ; copiez le lien ci-dessous.', 'warning')
            return redirect(url_for('submit.etape', num=num))

        if num < 8:
            return redirect(url_for('submit.etape', num=num + 1))
        else:
            return redirect(url_for('submit.soumettre'))

    resume_notice = _resume_notice_payload(session.pop('resume_notice', None))
    draft_resume = _resume_link_payload(cr) if cr.statut == 'brouillon' and cr.email else None
    return render_template(
        f'form/etape{num}.html',
        cr=cr,
        num=num,
        total=8,
        resume_notice=resume_notice,
        draft_resume=draft_resume,
    )


@submit_bp.route('/soumettre', methods=['GET', 'POST'])
def soumettre():
    cr = get_or_create_cr()
    if request.method == 'POST':
        # Sauvegarde finale
        invalid_signature_file = _has_invalid_signature_file(request.files)
        _save_etape(cr, 8, request.form, request.files)

        errors = _final_submission_errors(cr, invalid_signature_file)
        if errors:
            db.session.commit()
            for error in errors:
                flash(error, 'error')
            return render_template('form/etape8.html', cr=cr, num=8, total=8, final=True)

        cr.statut = 'soumis'
        cr.submitted_at = datetime.utcnow()
        cr.prix_moyen_vas = cr.calc_prix_moyen_vas()
        cr.prix_moyen_autre = cr.calc_prix_moyen_autre()
        db.session.commit()

        # Générer le PDF
        from app.views.export import generate_pdf
        pdf_path = generate_pdf(cr)
        cr.pdf_path = pdf_path
        db.session.commit()

        # Envoyer les e-mails
        _envoyer_notifications(cr)

        session.pop('cr_token', None)
        return redirect(url_for('submit.confirme', token=cr.token))

    return render_template('form/etape8.html', cr=cr, num=8, total=8, final=True)


@submit_bp.route('/confirme/<token>')
def confirme(token):
    cr = CompteRendu.query.filter_by(token=token).first_or_404()
    return render_template('form/confirme.html', cr=cr)


# ── Sauvegarde par étape ──────────────────────────────────────────────────────

def _save_etape(cr, num, form, files):
    if num == 1:
        cr.date_premier_jour = _parse_date(form.get('date_premier_jour'))
        cr.nom_prenom = form.get('nom_prenom', '').strip()
        cr.num_cheptel = form.get('num_cheptel', '').strip()
        cr.email = form.get('email', '').strip()
        cr.animation_solo = form.get('animation_solo')
        cr.nom_coeleveuse = form.get('nom_coeleveuse', '').strip()
        cr.filiere = form.get('filiere')

    elif num == 2:
        cr.enseigne = form.get('enseigne')
        cr.nom_magasin = form.get('nom_magasin', '').strip()
        cr.code_postal = form.get('code_postal', '').strip()
        cr.commune = form.get('commune', '').strip()
        cr.code_departement = (cr.code_postal[:2] if cr.code_postal else '')
        cr.nom_parrain = form.get('nom_parrain', '').strip()
        cr.nom_chef_boucher = form.get('nom_chef_boucher', '').strip()
        cr.anciennete_chef_boucher = form.get('anciennete_chef_boucher', '').strip()

    elif num == 3:
        cr.rayons_presents = json.dumps(form.getlist('rayons_presents'))
        cr.ls_barquettes = json.dumps(form.getlist('ls_barquettes'))
        cr.ls_barquettes_sur_place = form.get('ls_barquettes_sur_place')
        cr.ls_visibilite = form.get('ls_visibilite')
        cr.ls_lineaire = _parse_float(form.get('ls_lineaire'))
        cr.ls_precisions_lineaire = form.get('ls_precisions_lineaire', '').strip()
        cr.ls_qualite_decoupe = form.get('ls_qualite_decoupe')
        cr.ls_precisions_qualite = form.get('ls_precisions_qualite', '').strip()
        cr.ls_outils_com = json.dumps(form.getlist('ls_outils_com'))
        cr.ls_precisions_outils = form.get('ls_precisions_outils', '').strip()
        cr.ls_autre_veau = form.get('ls_autre_veau')
        cr.ls_autre_veau_marque = form.get('ls_autre_veau_marque', '').strip()
        cr.ls_autre_veau_lineaire = _parse_float(form.get('ls_autre_veau_lineaire'))
        cr.trad_visibilite = form.get('trad_visibilite')
        cr.trad_lineaire = _parse_float(form.get('trad_lineaire'))
        cr.trad_precisions_lineaire = form.get('trad_precisions_lineaire', '').strip()
        cr.trad_qualite_decoupe = form.get('trad_qualite_decoupe')
        cr.trad_precisions_qualite = form.get('trad_precisions_qualite', '').strip()
        cr.trad_outils_com = json.dumps(form.getlist('trad_outils_com'))
        cr.trad_precisions_outils = form.get('trad_precisions_outils', '').strip()
        cr.trad_autre_veau = form.get('trad_autre_veau')
        cr.trad_autre_veau_marque = form.get('trad_autre_veau_marque', '').strip()

    elif num == 4:
        cr.morceaux_presents = json.dumps(form.getlist('morceaux_presents'))
        for field in ['escalope', 'saute', 'roti', 'tendron', 'jarret', 'hache']:
            setattr(cr, f'prix_vas_{field}', _parse_float(form.get(f'prix_vas_{field}')))
            setattr(cr, f'prix_autre_{field}', _parse_float(form.get(f'prix_autre_{field}')))
        cr.precision_prix = form.get('precision_prix')
        cr.commentaire_prix = form.get('commentaire_prix', '').strip()

    elif num == 5:
        cr.date_dernier_jour = _parse_date(form.get('date_dernier_jour'))
        cr.emplacement_animation = json.dumps(form.getlist('emplacement_animation'))
        cr.frequentation = form.get('frequentation')
        cr.approvisionnement = form.get('approvisionnement')
        cr.ruptures = form.get('ruptures')
        cr.precisions_animation = form.get('precisions_animation', '').strip()
        cr.outils_animation = json.dumps(form.getlist('outils_animation'))
        cr.mise_en_avant = json.dumps(form.getlist('mise_en_avant'))
        cr.precisions_mise_en_avant = form.get('precisions_mise_en_avant', '').strip()
        cr.ventes_supplementaires = form.get('ventes_supplementaires')
        cr.incident = form.get('incident')
        cr.type_incident = json.dumps(form.getlist('type_incident'))
        cr.precisions_incident = form.get('precisions_incident', '').strip()

    elif num == 6:
        cr.tranche_age = json.dumps(form.getlist('tranche_age'))
        cr.attitude_clients = json.dumps(form.getlist('attitude_clients'))
        cr.clients_connaissaient_vas = form.get('clients_connaissaient_vas')
        cr.type_questions = json.dumps(form.getlist('type_questions'))
        cr.precisions_clients = form.get('precisions_clients', '').strip()

    elif num == 7:
        cr.ressenti_mise_en_place = form.get('ressenti_mise_en_place')
        cr.ressenti_accroche = form.get('ressenti_accroche')
        cr.ressenti_argumentaire = form.get('ressenti_argumentaire')
        cr.interesse_formation = form.get('interesse_formation')
        cr.kit_irva = form.get('kit_irva')
        cr.kit_interbev = form.get('kit_interbev')
        cr.precisions_ressenti = form.get('precisions_ressenti', '').strip()
        cr.echanges_chef_boucher = json.dumps(form.getlist('echanges_chef_boucher'))
        cr.remarques_chef_boucher = form.get('remarques_chef_boucher', '').strip()
        cr.avis_eleveur = form.get('avis_eleveur', '').strip()
        cr.incident_majeur = form.get('incident_majeur')

    elif num == 8:
        cr.photos_situation = json.dumps(form.getlist('photos_situation_check'))
        # Signature éleveur (base64)
        sig = form.get('signature_eleveur_data', '').strip()
        if sig and sig != 'data:,':
            cr.signature_eleveur_data = sig
        # Signature boucher (fichier upload)
        if 'signature_boucher' in files:
            f = files['signature_boucher']
            if f and f.filename and allowed_file(f.filename):
                fname = f'sig_boucher_{cr.id}_{secure_filename(f.filename)}'
                fpath = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
                f.save(fpath)
                cr.signature_boucher_path = fname
        # Photos animation
        for photo_file in files.getlist('photos_animation'):
            if photo_file and photo_file.filename and allowed_file(photo_file.filename):
                fname = f'photo_{cr.id}_{secrets.token_hex(8)}_{secure_filename(photo_file.filename)}'
                fpath = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
                photo_file.save(fpath)
                p = Photo(cr_id=cr.id, filename=fname, original_name=photo_file.filename)
                db.session.add(p)


def _has_invalid_signature_file(files):
    signature_file = files.get('signature_boucher')
    return bool(
        signature_file
        and signature_file.filename
        and not allowed_file(signature_file.filename)
    )


def _final_submission_errors(cr, invalid_signature_file=False):
    errors = []

    if invalid_signature_file:
        errors.append("Le feuillet signé du chef boucher doit être au format image ou PDF.")
    if not cr.signature_boucher_path:
        errors.append("Ajoutez la photo ou le PDF du feuillet signé et tamponné par le chef boucher.")
    if not cr.signature_eleveur_data or cr.signature_eleveur_data == 'data:,':
        errors.append("Ajoutez votre signature avant d'envoyer le compte-rendu.")

    return errors


# ── Upload AJAX de photo ──────────────────────────────────────────────────────

@submit_bp.route('/upload-photo', methods=['POST'])
def upload_photo():
    cr = get_or_create_cr()
    f = request.files.get('file')
    if not f or not allowed_file(f.filename):
        return jsonify({'error': 'Fichier non autorisé'}), 400
    fname = f'photo_{cr.id}_{secrets.token_hex(8)}_{secure_filename(f.filename)}'
    fpath = os.path.join(current_app.config['UPLOAD_FOLDER'], fname)
    f.save(fpath)
    p = Photo(cr_id=cr.id, filename=fname, original_name=f.filename)
    db.session.add(p)
    db.session.commit()
    return jsonify({'id': p.id, 'name': f.filename, 'url': url_for('submit.photo', filename=fname)})


@submit_bp.route('/upload-photo/<int:photo_id>', methods=['DELETE'])
def delete_photo(photo_id):
    photo = Photo.query.get_or_404(photo_id)
    if not _can_manage_photo(photo):
        return jsonify({'error': 'Suppression non autorisée'}), 403

    fpath = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
    if os.path.exists(fpath):
        os.remove(fpath)

    db.session.delete(photo)
    db.session.commit()
    return jsonify({'ok': True})


@submit_bp.route('/uploads/<path:filename>')
def photo(filename):
    from flask import send_from_directory
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(s):
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            pass
    return None


def _parse_float(s):
    if not s:
        return None
    try:
        return float(str(s).replace(',', '.'))
    except (ValueError, TypeError):
        return None


def _can_manage_photo(photo):
    if session.get('admin'):
        return True
    token = session.get('cr_token')
    return bool(token and photo.cr and photo.cr.token == token)


def _envoyer_lien_reprise(cr):
    if not cr.email:
        return False
    try:
        from flask_mail import Mail, Message
        mail = Mail(current_app)
        url = _resume_url(cr)
        msg = Message(
            subject='Votre compte-rendu IRVA — lien de reprise',
            recipients=[cr.email],
            html=render_template('emails/reprise.html', cr=cr, url=url),
        )
        mail.send(msg)
        current_app.logger.info('Resume email sent for CR #%s to %s', cr.id, cr.email)
        return True
    except Exception:
        current_app.logger.exception('Resume email failed for CR #%s to %s', cr.id, cr.email)
        return False


def _envoyer_notifications(cr):
    from flask_mail import Mail, Message

    mail = Mail(current_app)
    irva_emails = current_app.config['IRVA_EMAILS']
    dest = irva_emails.get(cr.filiere, irva_emails['Autre'])
    pdf_path = os.path.join(current_app.config['UPLOAD_FOLDER'], cr.pdf_path) if cr.pdf_path else None

    try:
        msg_irva = Message(
            subject=f'Compte-rendu Animation — {cr.nom_magasin} — {cr.nom_prenom}',
            recipients=[e.strip() for e in dest.split(',')],
            html=render_template('emails/notification_irva.html', cr=cr),
        )
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as fp:
                msg_irva.attach(f'CR_{cr.nom_magasin}.pdf', 'application/pdf', fp.read())
        mail.send(msg_irva)
        current_app.logger.info('IRVA notification sent for CR #%s to %s', cr.id, dest)
    except Exception:
        current_app.logger.exception('IRVA notification failed for CR #%s', cr.id)

    if cr.email:
        try:
            msg_elev = Message(
                subject=f'Votre compte-rendu "{cr.nom_magasin}" a bien été enregistré',
                recipients=[cr.email],
                html=render_template('emails/confirmation_eleveur.html', cr=cr),
            )
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as fp:
                    msg_elev.attach(f'CR_{cr.nom_magasin}.pdf', 'application/pdf', fp.read())
            mail.send(msg_elev)
            current_app.logger.info('Farmer confirmation sent for CR #%s to %s', cr.id, cr.email)
        except Exception:
            current_app.logger.exception('Farmer confirmation failed for CR #%s to %s', cr.id, cr.email)


def _resume_url(cr):
    return url_for('submit.reprendre', token=cr.token, _external=True)


def _resume_link_payload(cr):
    return {
        'token': cr.token,
        'url': _resume_url(cr),
        'mail_sent': None,
    }


def _resume_notice_payload(notice):
    if not notice or not notice.get('token'):
        return None
    return {
        'token': notice['token'],
        'url': url_for('submit.reprendre', token=notice['token'], _external=True),
        'mail_sent': bool(notice.get('mail_sent')),
    }
