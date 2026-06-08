#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    import pymysql
except ImportError as exc:  # pragma: no cover - operator guidance
    raise SystemExit(
        "Missing dependency: PyMySQL. Install it with `pip install PyMySQL` in the target environment."
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from werkzeug.utils import secure_filename

from models import CompteRendu, Photo, db
from wsgi import app


FIELD_MAP = {
    "date_premier_jour": "date-1",
    "nom_prenom": "name-1",
    "num_cheptel": "text-2",
    "animation_solo": "radio-15",
    "nom_coeleveuse": "name-2",
    "email": "email-1",
    "filiere": "radio-12",
    "enseigne": "select-1",
    "nom_magasin": "text-1",
    "code_postal": "text-4",
    "commune": "text-7",
    "nom_parrain": "name-3",
    "nom_chef_boucher": "name-4",
    "anciennete_chef_boucher": "name-5",
    "rayons_presents": "checkbox-23",
    "ls_barquettes": "checkbox-7",
    "ls_barquettes_sur_place": "checkbox-25",
    "ls_visibilite": "checkbox-24",
    "ls_lineaire": "number-1",
    "ls_precisions_lineaire": "textarea-2",
    "ls_qualite_decoupe": "checkbox-5",
    "ls_precisions_qualite": "textarea-4",
    "ls_outils_com": "checkbox-8",
    "ls_precisions_outils": "textarea-9",
    "ls_autre_veau": "checkbox-4",
    "ls_autre_veau_marque": "text-5",
    "ls_autre_veau_lineaire": "number-2",
    "trad_visibilite": "checkbox-9",
    "trad_lineaire": "number-3",
    "trad_precisions_lineaire": "textarea-5",
    "trad_qualite_decoupe": "checkbox-11",
    "trad_precisions_qualite": "textarea-7",
    "trad_outils_com": "checkbox-12",
    "trad_precisions_outils": "textarea-10",
    "trad_autre_veau": "checkbox-13",
    "trad_autre_veau_marque": "text-6",
    "morceaux_presents": "checkbox-17",
    "prix_vas_escalope": "number-5",
    "prix_autre_escalope": "number-11",
    "prix_vas_saute": "number-6",
    "prix_autre_saute": "number-12",
    "prix_vas_roti": "number-7",
    "prix_autre_roti": "number-13",
    "prix_vas_tendron": "number-8",
    "prix_autre_tendron": "number-14",
    "prix_vas_jarret": "number-9",
    "prix_autre_jarret": "number-15",
    "prix_vas_hache": "number-10",
    "prix_autre_hache": "number-16",
    "precision_prix": "select-2",
    "commentaire_prix": "textarea-17",
    "date_dernier_jour": "date-2",
    "emplacement_animation": "checkbox-14",
    "frequentation": "radio-2",
    "approvisionnement": "radio-3",
    "ruptures": "radio-4",
    "precisions_animation": "textarea-8",
    "outils_animation": "checkbox-16",
    "mise_en_avant": "checkbox-15",
    "precisions_mise_en_avant": "textarea-11",
    "ventes_supplementaires": "radio-5",
    "incident": "radio-11",
    "type_incident": "checkbox-22",
    "precisions_incident": "textarea-14",
    "tranche_age": "checkbox-18",
    "attitude_clients": "checkbox-19",
    "clients_connaissaient_vas": "radio-6",
    "type_questions": "checkbox-20",
    "precisions_clients": "textarea-15",
    "ressenti_mise_en_place": "radio-7",
    "ressenti_accroche": "radio-9",
    "ressenti_argumentaire": "radio-10",
    "interesse_formation": "radio-14",
    "kit_irva": "radio-8",
    "kit_interbev": "radio-13",
    "precisions_ressenti": "textarea-16",
    "echanges_chef_boucher": "checkbox-21",
    "remarques_chef_boucher": "textarea-12",
    "avis_eleveur": "textarea-13",
    "incident_majeur": "radio-16",
    "photos_situation": "checkbox-26",
}

LIST_FIELDS = {
    "rayons_presents",
    "ls_barquettes",
    "ls_outils_com",
    "trad_outils_com",
    "morceaux_presents",
    "emplacement_animation",
    "outils_animation",
    "mise_en_avant",
    "type_incident",
    "tranche_age",
    "attitude_clients",
    "type_questions",
    "echanges_chef_boucher",
    "photos_situation",
}

FLOAT_FIELDS = {
    "ls_lineaire",
    "ls_autre_veau_lineaire",
    "trad_lineaire",
    "prix_vas_escalope",
    "prix_autre_escalope",
    "prix_vas_saute",
    "prix_autre_saute",
    "prix_vas_roti",
    "prix_autre_roti",
    "prix_vas_tendron",
    "prix_autre_tendron",
    "prix_vas_jarret",
    "prix_autre_jarret",
    "prix_vas_hache",
    "prix_autre_hache",
}

VALUE_MAP = {
    "Approvitionnement": "Approvisionnement",
    "+ 60 ans": "+60 ans",
    "Je n'ai pas pris de photos de l'animation": "Je n'ai pas pris de photos",
    "Mon collègue a pris des photos et dois vous les envoyer": "Mon collègue a pris des photos et va les envoyer",
    "Il y avait une promotion sur les prix VAS le jour de l'animation": "Il y avait une promotion sur les prix VAS le jour de l'animation",
    "Les prix VAS reflètent ceux habituellement pratiqués dans le magasin (hors animation)": "Les prix VAS reflètent ceux habituellement pratiqués dans le magasin (hors animation)",
    "Je ne sais pas !": "Je ne sais pas !",
}

SITE_PATH_PREFIX = "/wp-content/uploads/forminator/"
URL_RE = re.compile(r"https?://[^\"]+")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Importe les anciens comptes-rendus Forminator dans la nouvelle base Flask."
    )
    parser.add_argument("--source-host", default="localhost")
    parser.add_argument("--source-port", type=int, default=3306)
    parser.add_argument("--source-user", required=True)
    parser.add_argument("--source-password", required=True)
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--form-id", type=int, default=47356)
    parser.add_argument("--wordpress-root", required=True, help="Racine locale du site WordPress source")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only-entry", type=int, action="append", default=[])
    parser.add_argument("--skip-files", action="store_true")
    return parser.parse_args()


def parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_float(value):
    value = (value or "").strip()
    if not value:
        return None
    value = value.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def normalize_value(value):
    value = (value or "").strip()
    return VALUE_MAP.get(value, value)


def first(meta, key):
    values = meta.get(key) or []
    if not values:
        return None
    return normalize_value(values[0])


def many(meta, key):
    values = meta.get(key) or []
    return [normalize_value(v) for v in values if (v or "").strip()]


def json_or_none(values):
    cleaned = [v for v in values if v]
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else None


def source_ref(form_id, entry_id):
    return f"forminator:{form_id}:{entry_id}"


def extract_urls(serialized_value):
    if not serialized_value:
        return []
    urls = URL_RE.findall(serialized_value)
    deduped = []
    seen = set()
    for url in urls:
        if SITE_PATH_PREFIX not in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def url_to_path(url, wordpress_root):
    parsed = urlparse(url)
    rel_path = parsed.path.lstrip("/")
    return Path(wordpress_root) / rel_path


def copy_into_uploads(src_path, dst_dir, prefix):
    src = Path(src_path)
    if not src.exists() or not src.is_file():
        return None
    filename = f"{prefix}_{secure_filename(src.name)}"
    target = Path(dst_dir) / filename
    counter = 1
    while target.exists():
        target = Path(dst_dir) / f"{prefix}_{counter}_{secure_filename(src.name)}"
        counter += 1
    shutil.copy2(src, target)
    return target.name


def image_to_data_url(src_path):
    src = Path(src_path)
    if not src.exists() or not src.is_file():
        return None
    mime_type = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
    data = base64.b64encode(src.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def build_compte_rendu(entry, meta, wordpress_root, upload_dir, skip_files=False):
    entry_id = entry["entry_id"]
    record = CompteRendu(
        token=f"formi_{entry['form_id']}_{entry_id}_{secrets.token_hex(8)}",
        statut="soumis",
        created_at=entry["date_created"],
        submitted_at=entry["date_created"],
        ref_animation=source_ref(entry["form_id"], entry_id),
        notes_admin=(
            f"Importé depuis Forminator form {entry['form_id']} / entry {entry_id}"
            + (f" / IP {first(meta, '_forminator_user_ip')}" if first(meta, "_forminator_user_ip") else "")
        ),
    )

    for field_name, meta_key in FIELD_MAP.items():
        if field_name in LIST_FIELDS:
            setattr(record, field_name, json_or_none(many(meta, meta_key)))
        elif field_name in FLOAT_FIELDS:
            setattr(record, field_name, parse_float(first(meta, meta_key)))
        elif field_name in {"date_premier_jour", "date_dernier_jour"}:
            setattr(record, field_name, parse_date(first(meta, meta_key)))
        else:
            value = first(meta, meta_key)
            setattr(record, field_name, value.strip() if isinstance(value, str) else value)

    if record.code_postal and not record.code_departement:
        record.code_departement = record.code_postal[:2]

    # Compat old/new field variants
    if not record.date_premier_jour:
        record.date_premier_jour = parse_date(first(meta, "date-3"))

    record.prix_moyen_vas = record.calc_prix_moyen_vas()
    record.prix_moyen_autre = record.calc_prix_moyen_autre()

    photo_urls = extract_urls(first(meta, "upload-1"))
    signature_boucher_urls = extract_urls(first(meta, "upload-2"))
    signature_eleveur_urls = extract_urls(first(meta, "signature-1")) or extract_urls(first(meta, "signature-2"))

    pending_photos = []
    if not skip_files:
        if signature_boucher_urls:
            sig_path = url_to_path(signature_boucher_urls[0], wordpress_root)
            record.signature_boucher_path = copy_into_uploads(sig_path, upload_dir, f"sig_boucher_import_{entry_id}")

        if signature_eleveur_urls:
            sig_ele_path = url_to_path(signature_eleveur_urls[0], wordpress_root)
            record.signature_eleveur_data = image_to_data_url(sig_ele_path)

        for index, photo_url in enumerate(photo_urls, start=1):
            photo_path = url_to_path(photo_url, wordpress_root)
            copied_name = copy_into_uploads(photo_path, upload_dir, f"photo_import_{entry_id}_{index}")
            if copied_name:
                pending_photos.append((copied_name, photo_path.name))

    return record, pending_photos


def fetch_entries(connection, form_id, limit=None, only_entry_ids=None):
    query = """
        SELECT entry_id, form_id, status, date_created
        FROM irva22frmt_form_entry
        WHERE form_id=%s AND status='active'
    """
    params = [form_id]
    if only_entry_ids:
        placeholders = ",".join(["%s"] * len(only_entry_ids))
        query += f" AND entry_id IN ({placeholders})"
        params.extend(only_entry_ids)
    query += " ORDER BY entry_id"
    if limit:
        query += " LIMIT %s"
        params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        entries = cursor.fetchall()
    if not entries:
        return []

    entry_ids = [entry["entry_id"] for entry in entries]
    placeholders = ",".join(["%s"] * len(entry_ids))
    meta_query = f"""
        SELECT entry_id, meta_key, meta_value
        FROM irva22frmt_form_entry_meta
        WHERE entry_id IN ({placeholders})
        ORDER BY meta_id
    """
    with connection.cursor() as cursor:
        cursor.execute(meta_query, entry_ids)
        meta_rows = cursor.fetchall()

    metas = defaultdict(lambda: defaultdict(list))
    for row in meta_rows:
        metas[row["entry_id"]][row["meta_key"]].append(row["meta_value"])

    return [(entry, metas[entry["entry_id"]]) for entry in entries]


def main():
    args = parse_args()
    wordpress_root = Path(args.wordpress_root)
    with app.app_context():
        upload_dir = Path(app.config["UPLOAD_FOLDER"])
        upload_dir.mkdir(parents=True, exist_ok=True)

        connection = pymysql.connect(
            host=args.source_host,
            port=args.source_port,
            user=args.source_user,
            password=args.source_password,
            database=args.source_db,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

        imported = 0
        skipped = 0
        planned = 0
        photo_count = 0
        errors = 0

        try:
            rows = fetch_entries(
                connection,
                args.form_id,
                limit=args.limit,
                only_entry_ids=args.only_entry or None,
            )
            print(f"Source entries fetched: {len(rows)}")
            for entry, meta in rows:
                ref = source_ref(args.form_id, entry["entry_id"])
                if CompteRendu.query.filter_by(ref_animation=ref).first():
                    skipped += 1
                    print(f"SKIP entry {entry['entry_id']} already imported ({ref})")
                    continue

                try:
                    detected_photo_count = len(extract_urls(first(meta, "upload-1")))
                    cr, pending_photos = build_compte_rendu(
                        entry,
                        meta,
                        wordpress_root=wordpress_root,
                        upload_dir=upload_dir,
                        skip_files=args.skip_files or args.dry_run,
                    )
                    planned += 1
                    photo_count += detected_photo_count
                    if args.dry_run:
                        print(
                            f"DRY entry {entry['entry_id']} -> "
                            f"{cr.nom_prenom or '—'} / {cr.nom_magasin or '—'} / "
                            f"{cr.date_premier_jour} / photos={detected_photo_count}"
                        )
                        continue

                    db.session.add(cr)
                    db.session.flush()
                    for filename, original_name in pending_photos:
                        db.session.add(Photo(cr_id=cr.id, filename=filename, original_name=original_name))
                    db.session.commit()
                    imported += 1
                    print(f"OK entry {entry['entry_id']} imported as CR #{cr.id}")
                except Exception as exc:  # pragma: no cover - operational path
                    db.session.rollback()
                    errors += 1
                    print(f"ERROR entry {entry['entry_id']}: {exc}")

        finally:
            connection.close()

        mode = "dry-run" if args.dry_run else "import"
        print(
            f"Summary ({mode}): planned={planned}, imported={imported}, "
            f"skipped={skipped}, photos={photo_count}, errors={errors}"
        )


if __name__ == "__main__":
    main()
