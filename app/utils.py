"""
Utilitaires partagés — normalisation des valeurs multi-choix Forminator.

Forminator peut encoder les sélections multiples de plusieurs façons selon
la version du plugin, le mode d'export (PDF, CSV, Excel) ou la méthode
d'envoi du formulaire. Ce module centralise la normalisation pour garantir
que le matching fonctionne quel que soit le formulaire source.

Règles documentées (voir normalize_multiselect) :
  1. <br/> / <br>   → ", "  (séparateur HTML Forminator v1.x)
  2. \\r\\n / \\n    → ", "  (retours chariot Excel / _x000D_)
  3. ,-              → ", "  (artefact virgule-tiret)
  4. tirets résiduels → espaces  (slug encoding des options longues)
  5. espaces multiples → simple  (nettoyage final)

POUR ÉTENDRE : ajouter une règle numérotée dans normalize_multiselect
si un nouveau formulaire introduit un nouvel artefact.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Union

DEPARTMENT_TO_REGION = {
    # Auvergne-Rhone-Alpes
    "01": "Auvergne-Rhone-Alpes", "03": "Auvergne-Rhone-Alpes", "07": "Auvergne-Rhone-Alpes",
    "15": "Auvergne-Rhone-Alpes", "26": "Auvergne-Rhone-Alpes", "38": "Auvergne-Rhone-Alpes",
    "42": "Auvergne-Rhone-Alpes", "43": "Auvergne-Rhone-Alpes", "63": "Auvergne-Rhone-Alpes",
    "69": "Auvergne-Rhone-Alpes", "73": "Auvergne-Rhone-Alpes", "74": "Auvergne-Rhone-Alpes",
    # Bourgogne-Franche-Comte
    "21": "Bourgogne-Franche-Comte", "25": "Bourgogne-Franche-Comte", "39": "Bourgogne-Franche-Comte",
    "58": "Bourgogne-Franche-Comte", "70": "Bourgogne-Franche-Comte", "71": "Bourgogne-Franche-Comte",
    "89": "Bourgogne-Franche-Comte", "90": "Bourgogne-Franche-Comte",
    # Bretagne
    "22": "Bretagne", "29": "Bretagne", "35": "Bretagne", "56": "Bretagne",
    # Centre-Val de Loire
    "18": "Centre-Val de Loire", "28": "Centre-Val de Loire", "36": "Centre-Val de Loire",
    "37": "Centre-Val de Loire", "41": "Centre-Val de Loire", "45": "Centre-Val de Loire",
    # Corse
    "20": "Corse", "2A": "Corse", "2B": "Corse",
    # Grand Est
    "08": "Grand Est", "10": "Grand Est", "51": "Grand Est", "52": "Grand Est",
    "54": "Grand Est", "55": "Grand Est", "57": "Grand Est", "67": "Grand Est",
    "68": "Grand Est", "88": "Grand Est",
    # Hauts-de-France
    "02": "Hauts-de-France", "59": "Hauts-de-France", "60": "Hauts-de-France",
    "62": "Hauts-de-France", "80": "Hauts-de-France",
    # Ile-de-France
    "75": "Ile-de-France", "77": "Ile-de-France", "78": "Ile-de-France", "91": "Ile-de-France",
    "92": "Ile-de-France", "93": "Ile-de-France", "94": "Ile-de-France", "95": "Ile-de-France",
    # Normandie
    "14": "Normandie", "27": "Normandie", "50": "Normandie", "61": "Normandie", "76": "Normandie",
    # Nouvelle-Aquitaine
    "16": "Nouvelle-Aquitaine", "17": "Nouvelle-Aquitaine", "19": "Nouvelle-Aquitaine",
    "23": "Nouvelle-Aquitaine", "24": "Nouvelle-Aquitaine", "33": "Nouvelle-Aquitaine",
    "40": "Nouvelle-Aquitaine", "47": "Nouvelle-Aquitaine", "64": "Nouvelle-Aquitaine",
    "79": "Nouvelle-Aquitaine", "86": "Nouvelle-Aquitaine", "87": "Nouvelle-Aquitaine",
    # Occitanie
    "09": "Occitanie", "11": "Occitanie", "12": "Occitanie", "30": "Occitanie", "31": "Occitanie",
    "32": "Occitanie", "34": "Occitanie", "46": "Occitanie", "48": "Occitanie", "65": "Occitanie",
    "66": "Occitanie", "81": "Occitanie", "82": "Occitanie",
    # Pays de la Loire
    "44": "Pays de la Loire", "49": "Pays de la Loire", "53": "Pays de la Loire",
    "72": "Pays de la Loire", "85": "Pays de la Loire",
    # Provence-Alpes-Cote d'Azur
    "04": "Provence-Alpes-Cote d'Azur", "05": "Provence-Alpes-Cote d'Azur",
    "06": "Provence-Alpes-Cote d'Azur", "13": "Provence-Alpes-Cote d'Azur",
    "83": "Provence-Alpes-Cote d'Azur", "84": "Provence-Alpes-Cote d'Azur",
    # DOM
    "971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Reunion",
    "976": "Mayotte",
}


def normalize_multiselect(text: object) -> str:
    """
    Normalise une valeur multi-choix brute (chaîne ou autre) en une chaîne
    propre avec les options séparées par ", ".

    Règle 1 — Séparateurs HTML : <br/> et <br> → ", "
    Règle 2 — Retours chariot : _x000D_, \\r\\n, \\n → ", "
    Règle 3 — Artefact virgule-tiret : ,- → ", "
    Règle 4 — Slug encoding : tirets → espaces
    Règle 5 — Espaces multiples → simple

    Retourne "" si la valeur est vide/None/0.
    """
    if text is None or text == 0:
        return ""
    s = str(text).strip()
    if not s or s == "nan":
        return ""
    # Règle 1
    s = re.sub(r'<br\s*/?>', ', ', s, flags=re.IGNORECASE)
    # Règle 2
    s = re.sub(r'_x000D_|\r\n|\r|\n', ', ', s)
    # Règle 3
    s = s.replace(',-', ', ')
    # Règle 4
    s = s.replace('-', ' ')
    # Règle 5
    s = re.sub(r'  +', ' ', s).strip()
    return s


def parse_multiselect(value: object) -> list[str]:
    """
    Désérialise une valeur multi-choix stockée en DB en liste Python.

    Stratégie (par ordre de priorité) :
      1. JSON valide → list directement
      2. Chaîne brute → normalisation Forminator puis split sur ", "
      3. Vide/None → []

    C'est le point d'entrée unique pour tout accès aux champs multi-choix
    dans les vues, templates et exports.
    """
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    if not s or s == "nan":
        return []
    # Tentative JSON
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        if parsed in (None, ""):
            return []
        return [str(parsed).strip()]
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback : normalisation Forminator + split
    normalized = normalize_multiselect(s)
    if not normalized:
        return []
    return [part.strip() for part in normalized.split(',') if part.strip()]


def parse_multiselect_str(value: object) -> str:
    """
    Raccourci pour les exports : retourne les options jointes par ", ".
    Équivalent de ', '.join(parse_multiselect(value)).
    """
    items = parse_multiselect(value)
    return ', '.join(items)


def infer_department_code(postal_code: object) -> str:
    """
    Déduit un code département à partir d'un code postal ou d'une saisie approchante.

    Règles :
      1. 97x/98x -> 3 premiers chiffres
      2. 20xxx -> "20" (suffisant pour déduire la région Corse)
      3. sinon -> 2 premiers chiffres significatifs

    Retourne "" si aucune déduction fiable n'est possible.
    """
    if postal_code is None:
        return ""

    raw = str(postal_code).strip().upper()
    if not raw or raw == "NAN":
        return ""

    five_digit = re.search(r'(\d{5})', raw)
    digits = five_digit.group(1) if five_digit else ""

    if not digits:
        groups = re.findall(r'\d+', raw)
        digits = groups[0] if groups else ""

    if not digits:
        return ""

    if digits.startswith(("97", "98")) and len(digits) >= 3:
        return digits[:3]
    if digits.startswith("20"):
        return "20"
    if len(digits) >= 2:
        return digits[:2]
    return ""


def infer_region(postal_code: object = None, code_departement: object = None) -> str:
    """
    Déduit la région à partir du code département ou, à défaut, du code postal.
    """
    dept = str(code_departement).strip().upper() if code_departement not in (None, "") else ""
    if not dept:
        dept = infer_department_code(postal_code)
    return DEPARTMENT_TO_REGION.get(dept, "")


def compact_spaces(value: object) -> str:
    """
    Réduit les espaces multiples à un seul espace et retire les bords.
    """
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def normalize_store_name(name: object) -> str:
    """
    Normalise un nom de magasin pour les correspondances techniques.
    """
    normalized = unicodedata.normalize('NFKD', str(name or ''))
    normalized = normalized.encode('ascii', 'ignore').decode('ascii').lower()
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip() or 'non-renseigne'


def guess_enseigne_from_store_name(name: object) -> str:
    """
    Déduit une enseigne probable depuis un nom magasin libre.
    """
    normalized = normalize_store_name(name)
    if not normalized or normalized == 'non-renseigne':
        return ''

    if 'leclerc' in normalized:
        return 'E.Leclerc'
    if normalized.startswith('auchan'):
        return 'Auchan'
    if normalized.startswith('carrefour'):
        return 'Carrefour'
    if normalized.startswith('metro'):
        return 'Metro'
    if normalized.startswith('halle de l aveyron'):
        return "Halle de l'Aveyron"
    if normalized.startswith('boucherie'):
        return 'Boucherie indépendante'
    return 'Autre'
