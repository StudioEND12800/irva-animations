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
from typing import Union


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
