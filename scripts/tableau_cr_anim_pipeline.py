"""
Pipeline Python reproduisant fidèlement la logique du classeur
20260129_Tableau CR Anim.xlsx.

Chaque colonne TC (Tableau calcul) est identifiée par sa lettre Excel en
commentaire pour faciliter la vérification.

Corrections majeures v2 :
  - FB (Cochez case) manquait dans compute_cr_status → statut CR faux
  - ~25 colonnes de copie directe absentes → synthèses incomplètes
  - Décompositions Trad outils / emplacement / tranche âge / attitude /
    type questions / échanges chef boucher / outils animation / mise en avant
    entièrement manquantes
  - count_non_blank : vérification source vide comme Excel IF(src=0,"",...)
  - donnee_liste chargée avec header=0 pour aligner les colonnes
  - Période : lookup dans Donnée liste!D:F (ne plus hardcoder 2025-01-01)
  - clean_price : exclut uniquement <=0 (pas 1) pour coller à AVERAGEIFS("<>0")
  - Nommage des colonnes TC aligné sur les contenus réels des cellules (pas de
    préfixes "LS -" etc. qui cassaient les COUNTIFS Python équivalents)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Helpers reproduisant les fonctions Excel
# ---------------------------------------------------------------------------

def normalize_multiselect(text: object) -> str:
    """
    Normalise une valeur multi-choix Forminator avant tout test de présence.

    Artefacts d'encodage couverts (observés sur les exports réels) :

    Règle 1 — Séparateurs HTML : <br/> et <br> → ", "
      Forminator v1.x stocke les choix multiples séparés par des balises HTML.
      Ex : "Escalope<br/>Sauté<br/>Roti" → "Escalope, Sauté, Roti"

    Règle 2 — Retours chariot Excel : _x000D_, \\r, \\n → ", "
      Ex : "Escalope_x000D_\\nSauté" → "Escalope, Sauté"

    Règle 3 — Artefact virgule-tiret : ,- → ", "
      Forminator remplace parfois ", " interne à une option par ",-" lors
      de l'export CSV (la virgule devient séparateur, l'espace devient tiret).
      Ex : "OUI,-pendant-l'animation" → "OUI, pendant-l'animation"
           "Publications..., Dépliant-publicitaire-qui-annonce-l'animation"
           → "Publications..., Dépliant publicitaire qui annonce l'animation"

    Règle 4 — Slug encoding : tirets résiduels → espaces
      Les options longues peuvent être encodées en style slug-URL, tous les
      espaces remplacés par des tirets (avant ou après règle 3).
      Ex : "Libre-service-à-l'entrée-du-magasin-(ponctuellement)"
           → "Libre service à l'entrée du magasin (ponctuellement)"
      Sécurité : les tirets LÉGITIMES dans les options (ex : "libre-service",
      "18/25 ans") sont aussi transformés en espaces, MAIS la normalisation
      s'applique aussi à l'aiguille (needle) dans excel_contains, donc le
      matching reste correct dans les deux sens.

    Règle 5 — Espaces multiples → espace simple (nettoyage final).

    POUR ÉTENDRE : ajouter une règle numérotée ici si un nouveau formulaire
    introduit un nouvel artefact. La fonction est le point d'entrée unique pour
    toute la normalisation multi-choix.
    """
    if pd.isna(text) or text == 0:
        return ""
    s = str(text).strip()
    if not s or s == "nan":
        return ""
    # Règle 1 : séparateurs HTML
    s = re.sub(r'<br\s*/?>', ', ', s, flags=re.IGNORECASE)
    # Règle 2 : retours chariot Excel
    s = re.sub(r'_x000D_|\r\n|\r|\n', ', ', s)
    # Règle 3 : artefact virgule-tiret (doit précéder la règle 4)
    s = s.replace(',-', ', ')
    # Règle 4 : slug encoding — tirets résiduels → espaces
    s = s.replace('-', ' ')
    # Règle 5 : espaces multiples → simple
    s = re.sub(r'  +', ' ', s).strip()
    return s


def excel_contains(text: object, needle: str) -> bool:
    """
    ISNUMBER(FIND(needle, text)) avec normalisation Forminator des deux côtés.
    Case-sensitive comme FIND() Excel. Les deux valeurs sont normalisées via
    normalize_multiselect avant la comparaison, ce qui rend le matching robuste
    face aux variantes d'encodage (voir normalize_multiselect).
    """
    norm = normalize_multiselect(text)
    if not norm:
        return False
    # Normaliser aussi l'aiguille (pour les needles contenant des tirets légitimes
    # comme "Rayon libre-service (LS)" → "Rayon libre service (LS)")
    norm_needle = normalize_multiselect(needle)
    return norm_needle in norm


def flag_if_contains(series: pd.Series, needle: str) -> pd.Series:
    """Retourne needle si trouvé, '' sinon. Équivalent IF(ISNUMBER(FIND(...)),...)."""
    return series.apply(lambda x: needle if excel_contains(x, needle) else "")


def count_non_blank_with_guard(source_series: pd.Series, flag_df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """
    Équivalent de : IF(source=0,"", n-COUNTBLANK(flags))
    Si la source est vide/0, retourne "" ; sinon compte les flags non vides.
    """
    def _count(idx):
        src = source_series.iloc[idx]
        if pd.isna(src) or src == 0 or str(src).strip() == "":
            return ""
        row = flag_df.iloc[idx]
        return sum(1 for v in row[cols] if not (pd.isna(v) or str(v).strip() == ""))
    return pd.Series([_count(i) for i in range(len(source_series))], index=source_series.index)


def mean_nonzero(row: pd.Series, cols: list[str]) -> object:
    """IFERROR(AVERAGEIFS(range, range, '<>0'), '') — exclut NaN et 0."""
    vals = pd.to_numeric(row[cols], errors="coerce")
    vals = vals[(vals.notna()) & (vals != 0)]
    if vals.empty:
        return ""
    return round(vals.mean(), 4)


def clean_price(series: pd.Series) -> pd.Series:
    """
    Nettoyage prix : conversion numérique, suppression <=0 (0 exclu par AVERAGEIFS).
    NB : la note de la notice dit d'exclure 0€ et 1€ pour nettoyage manuel,
    mais AVERAGEIFS Excel n'exclut que "<>0". On exclut <=0 pour coller à Excel.
    """
    s = (
        series.astype(str)
        .str.replace("\xa0", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace("€", "", regex=False)
        .str.strip()
    )
    num = pd.to_numeric(s, errors="coerce")
    num = num.mask(num <= 0)
    return num


def excel_serial_to_date(serial) -> Optional[pd.Timestamp]:
    """
    Convertit une valeur de cellule date Excel en Timestamp.
    Gère : numéro de série (float), chaîne date ISO, ou Timestamp déjà parsé.
    """
    if pd.isna(serial) or str(serial).strip() in ("", "nan"):
        return None
    # Déjà un Timestamp ou datetime
    if isinstance(serial, pd.Timestamp):
        return serial
    # Chaîne de date ISO ou datetime string (pandas charge parfois les dates déjà parsées)
    s = str(serial).strip()
    ts = pd.to_datetime(s, errors="coerce", dayfirst=False)
    if ts is not pd.NaT and not pd.isna(ts):
        return ts
    # Numéro de série Excel (float)
    try:
        n = float(s.replace(",", "."))
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(n))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Chargement des sources
# ---------------------------------------------------------------------------

def load_sources(path: str | Path) -> dict[str, pd.DataFrame]:
    """Charge les feuilles utiles du classeur."""
    xls = pd.ExcelFile(path)
    return {
        "decharge": pd.read_excel(xls, "Décharge données", dtype=str),
        # header=0 : la ligne 1 Excel est bien l'en-tête
        "donnee_liste": pd.read_excel(xls, "Donnée liste", header=0, dtype=str),
        "liste_nom_mag": pd.read_excel(xls, "Liste nom mag", header=0, dtype=str),
    }


# ---------------------------------------------------------------------------
# Lookup période depuis Donnée liste!D:F
# VLOOKUP($C$4,'Donnée liste'!$D$1:$F$98,2,FALSE) → date début
# VLOOKUP($C$4,'Donnée liste'!$D$1:$F$98,3,FALSE) → date fin
# ---------------------------------------------------------------------------

def get_period_dates(year_label: str, donnee_liste: pd.DataFrame) -> tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    """
    Retourne (date_debut, date_fin) pour une étiquette comme 'Année 2025'.
    Colonnes D:F dans l'Excel = positions 3:6 dans le DataFrame (0-indexé, header=0).
    """
    cols = list(donnee_liste.columns)
    # Cherche les colonnes D, E, F (indices 3, 4, 5 si A=0)
    if len(cols) < 6:
        return None, None
    ref = donnee_liste.iloc[:, [3, 4, 5]].copy()
    ref.columns = ["label", "start_serial", "end_serial"]
    match = ref[ref["label"].astype(str).str.strip() == year_label.strip()]
    if match.empty:
        return None, None
    row = match.iloc[0]
    return excel_serial_to_date(row["start_serial"]), excel_serial_to_date(row["end_serial"])


# ---------------------------------------------------------------------------
# Homogénisation noms magasins depuis Liste nom mag
# Colonne S de Tableau calcul (manuelle dans Excel, ici par référentiel)
# ---------------------------------------------------------------------------

def normalize_store_names(store_series: pd.Series, ref_df: Optional[pd.DataFrame]) -> pd.Series:
    """
    Remplace la colonne S manuelle de Tableau calcul.
    Liste nom mag : col A = doublon check (formula), col B = nom normalisé,
    col C,D = variantes. On construit un dict variante→normalisé.
    """
    if ref_df is None or ref_df.empty:
        return store_series.fillna("")

    cols = list(ref_df.columns)
    # La col B Excel (index 1) = nom normalisé ; A = formule doublon
    if len(cols) < 2:
        return store_series.fillna("")

    normalized_col = cols[1]   # B en Excel
    variant_cols = cols[2:]    # C, D, ... variantes

    mapping: dict[str, str] = {}
    for _, row in ref_df.iterrows():
        normalized = str(row.get(normalized_col, "") or "").strip()
        if not normalized or normalized == "nan":
            continue
        mapping[normalized.lower()] = normalized
        for vc in variant_cols:
            val = str(row.get(vc, "") or "").strip()
            if val and val != "nan":
                mapping[val.lower()] = normalized

    def _norm(x):
        if pd.isna(x) or str(x).strip() == "" or str(x) == "nan":
            return ""
        return mapping.get(str(x).strip().lower(), str(x).strip())

    return store_series.apply(_norm)


# ---------------------------------------------------------------------------
# Correspondance département → région (VLOOKUP sur Donnée liste!O:Q)
# ---------------------------------------------------------------------------

def map_department_to_region(dept_series: pd.Series, donnee_liste: Optional[pd.DataFrame]) -> pd.Series:
    """
    VLOOKUP(W2,'Donnée liste'!O:Q,3) — col O=dept, col Q=région.
    Avec header=0, colonnes O:Q = indices 14, 15, 16 dans DataFrame.
    """
    if donnee_liste is None or donnee_liste.empty or len(donnee_liste.columns) < 17:
        return pd.Series("", index=dept_series.index)

    ref = donnee_liste.iloc[:, [14, 16]].copy().dropna(how="all")
    ref.columns = ["dept", "region"]
    ref["dept"] = ref["dept"].astype(str).str.strip().str.zfill(2)
    mapping = dict(zip(ref["dept"], ref["region"].astype(str).str.strip()))

    return dept_series.astype(str).str.strip().str.zfill(2).map(mapping).fillna("")


# ---------------------------------------------------------------------------
# Statut CR — équivalent exact de la formule FF
# IF(AND(FE=0,FD=0,FC=0,FB=0),"",IF(AND(FE="",FD=""),"Brouillon","CR OK"))
# ---------------------------------------------------------------------------

def compute_cr_status(df: pd.DataFrame) -> pd.Series:
    """
    FE = Signature Eleveur,se            (TC col FE = Décharge données!CG)
    FD = Photo feuillet boucher          (TC col FD = Décharge données!CF)
    FC = Photos animation                (TC col FC = Décharge données!CE)
    FB = Cochez case correspondant...    (TC col FB = Décharge données!CD)
    """
    def _empty(v) -> bool:
        return pd.isna(v) or str(v).strip() in ("", "0", "nan") or v == 0

    results = []
    for _, row in df.iterrows():
        fe = row.get("_fe", "")
        fd = row.get("_fd", "")
        fc = row.get("_fc", "")
        fb = row.get("_fb", "")
        if all(_empty(x) for x in [fe, fd, fc, fb]):
            results.append("")
        elif _empty(fe) and _empty(fd):
            results.append("Brouillon")
        else:
            results.append("CR OK")
    return pd.Series(results, index=df.index)


# ---------------------------------------------------------------------------
# Construction du Tableau calcul — chaque ligne est une réponse questionnaire
# ---------------------------------------------------------------------------

def build_tableau_calcul(raw: pd.DataFrame, refs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Reproduit fidèlement la feuille Tableau calcul du classeur.
    Colonnes commentées par leur lettre TC (A, B, ..., FF).
    """
    out = pd.DataFrame(index=raw.index)

    donnee_liste = refs.get("donnee_liste")
    liste_nom_mag = refs.get("liste_nom_mag")

    # ── TC!H — Heure de l'envoi (soumission) ─────────────────────────────────
    out["envoi_heure"] = raw.get("Heure de l'envoi", "")

    # ── TC!I — Date premier jour animation (clé de toutes les synthèses) ──────
    # TC!I = 'Décharge données'!B — PAS col BA (_8) qui est une copie
    col_date_anim = _find_col(raw, [
        "Dates du PREMIER jour d'animation",
        "Date du PREMIER jour d'animation",
        "Dates du premier jour d'animation",
    ])
    out["date_premier_jour"] = pd.to_datetime(raw[col_date_anim], errors="coerce", dayfirst=True) if col_date_anim else pd.NaT

    # ── TC!J-N — Identité éleveur ─────────────────────────────────────────────
    out["nom_prenom"]     = raw.get("Nom / Prénom", "")                                    # TC!J
    out["num_cheptel"]    = raw.get("N° de Cheptel", "")                                   # TC!K
    out["animation_solo"] = raw.get("Vous avez réalisez l'animation ...", "")              # TC!L
    out["nom_coeleveuse"] = raw.get("Nom / Prénom de l'éleveur·se avec lequel·le vous avez réalisé·e l'animation", "") # TC!M
    out["email"]          = raw.get("Votre Adresse e-mail", "")                            # TC!N

    # ── TC!O — Filière ────────────────────────────────────────────────────────
    out["filiere"] = raw.get("Pour quelle filière commerciale réalisez-vous l'animation ?", "")  # TC!O

    # ── TC!Q-R — Enseigne / magasin ───────────────────────────────────────────
    out["enseigne"]    = raw.get("Nom de l'enseigne", "")                                  # TC!Q
    out["nom_magasin"] = raw.get("Nom du magasin (enseigne + dénomination)", "")           # TC!R

    # ── TC!S — Homogénisation nom magasin ─────────────────────────────────────
    out["magasin_norm"] = normalize_store_names(out["nom_magasin"], liste_nom_mag)         # TC!S

    # ── TC!U-V — CP / commune ─────────────────────────────────────────────────
    out["code_postal"] = raw.get("Code postal", "").astype(str).str.zfill(5)              # TC!U
    out["commune"]     = raw.get("Commune", "")                                            # TC!V

    # ── TC!Y-AA — Parrain / chef boucher ──────────────────────────────────────
    out["nom_parrain"]             = raw.get("Nom du PARRAIN du magasin", "")              # TC!Y
    out["nom_chef_boucher"]        = raw.get("Nom du chef boucher", "")                    # TC!Z
    out["anciennete_chef_boucher"] = raw.get("Ancienneté du chef boucher dans le magasin", "")  # TC!AA

    # ── TC!W — Code département ───────────────────────────────────────────────
    out["code_departement"] = out["code_postal"].str[:2]                                   # TC!W

    # ── TC!X — Région ─────────────────────────────────────────────────────────
    out["region"] = map_department_to_region(out["code_departement"], donnee_liste)        # TC!X

    # ── TC!AB — Rayons présents (source multi-choix) ──────────────────────────
    _src_rayons = raw.get("Dans quel(s) rayon(s) est présent le Veau d'Aveyron et du Ségala ?", "")  # TC!AB
    out["rayons_presents_src"] = _src_rayons

    # ── TC!AC-AF — Flags rayons ───────────────────────────────────────────────
    out["rayon_ls"]       = flag_if_contains(_src_rayons, "Rayon libre-service (LS)")         # TC!AC
    out["rayon_trad"]     = flag_if_contains(_src_rayons, "Rayon Coupe (Trad)")               # TC!AD
    out["rayon_drive"]    = flag_if_contains(_src_rayons, "Drive")                            # TC!AE
    out["rayon_ls_entree"]= flag_if_contains(_src_rayons, "Libre service à l'entrée du magasin (ponctuellement)")  # TC!AF

    # ── TC!AG — Type de barquettes LS (source) ───────────────────────────────
    _src_barquettes = raw.get("Dans quel type de barquette était présenté le V.A.S. ?", "")  # TC!AG
    out["ls_barquettes_src"] = _src_barquettes

    # ── TC!AH-AK — Flags barquettes ──────────────────────────────────────────
    out["ls_barquette_beigne"]       = flag_if_contains(_src_barquettes, "Beigne (Compostable)")     # TC!AH
    out["ls_barquette_noire"]        = flag_if_contains(_src_barquettes, "Noire (Polystyrène)")      # TC!AI
    out["ls_barquette_transparente"] = flag_if_contains(_src_barquettes, "Transparente (PET)")       # TC!AJ
    out["ls_barquette_blanche"]      = flag_if_contains(_src_barquettes, "Blanche (Polystyrène)")    # TC!AK

    # ── TC!AL — Barquettes sur place ─────────────────────────────────────────
    out["ls_barquettes_sur_place"] = raw.get("Les barquettes sont elles faite sur place dans les ateliers du magasin ?", "")  # TC!AL

    # ── TC!AM — Visibilité LS ─────────────────────────────────────────────────
    out["ls_visibilite"] = raw.get("Comment décririez vous la visibilité du V.A.S. dans le rayon libre service ?", "")  # TC!AM

    # ── TC!AN — Longueur linéaire LS ──────────────────────────────────────────
    out["ls_lineaire"] = raw.get("Longueur du linéaire où le VAS est présent (hors période d'animation)", "")  # TC!AN

    # ── TC!AP — Qualité découpe LS ────────────────────────────────────────────
    out["ls_qualite_decoupe"] = raw.get("Comment décririez-vous la qualité de la découpe / la présentation des morceaux en libre service ?", "")  # TC!AP

    # ── TC!AR — Outils com LS année (source) ──────────────────────────────────
    _src_outils_ls = raw.get("Quels outils de communication V.A.S. sont présents dans le rayon TOUTE L' ANNEE ?", "")  # TC!AR
    out["ls_outils_com_src"] = _src_outils_ls

    # ── TC!AS-AW — Flags outils LS ────────────────────────────────────────────
    out["ls_outil_etiquettes"] = flag_if_contains(_src_outils_ls, "Etiquettes spécifique VAS")  # TC!AS
    out["ls_outil_affiches"]   = flag_if_contains(_src_outils_ls, "Affiches VAS")               # TC!AT
    out["ls_outil_reglette"]   = flag_if_contains(_src_outils_ls, "Réglette linéaire VAS")      # TC!AU
    out["ls_outil_fiches"]     = flag_if_contains(_src_outils_ls, "Fiches recettes")             # TC!AV
    out["ls_outil_oriflamme"]  = flag_if_contains(_src_outils_ls, "Oriflamme / voile")           # TC!AW

    # ── TC!AX — Nb outils LS (IF(src=0,"",5-COUNTBLANK(AS:AW))) ──────────────
    _ls_outils_flags = ["ls_outil_etiquettes", "ls_outil_affiches", "ls_outil_reglette", "ls_outil_fiches", "ls_outil_oriflamme"]
    out["ls_nb_outils"] = count_non_blank_with_guard(_src_outils_ls, out, _ls_outils_flags)  # TC!AX

    # ── TC!AZ — Autre veau LS ─────────────────────────────────────────────────
    out["ls_autre_veau"] = raw.get("Il y a t'il un autre veau que le V.A.S. présent dans le rayon libre service ?", "")  # TC!AZ
    out["ls_autre_veau_marque"]   = raw.get("Dénomination / Marque de ce veau :", "")          # TC!BA

    # ── TC!BB — Longueur linéaire autre veau LS ───────────────────────────────
    out["ls_autre_veau_lineaire"] = raw.get('Longueur du linéaire "autre veau"', raw.get("Longueur du linéaire autre veau", ""))  # TC!BB

    # ── TC!BC — Visibilité Trad ────────────────────────────────────────────────
    out["trad_visibilite"] = raw.get("Comment décririez vous la visibilité du V.A.S. dans le rayon traditionnel ?", "")  # TC!BC

    # ── TC!BD — Longueur linéaire Trad ────────────────────────────────────────
    out["trad_lineaire"] = raw.get("Longueur du linéaire où le V.A.S. est présent (hors période d'animation)", "")  # TC!BD

    # ── TC!BF — Qualité découpe Trad ──────────────────────────────────────────
    out["trad_qualite_decoupe"] = raw.get("Comment décririez-vous la qualité de la découpe / la présentation des morceaux au rayon traditionnel ?", "")  # TC!BF

    # ── TC!BH — Outils com Trad année (source) ────────────────────────────────
    # Attention : libellé identique à LS mais colonne AH dans Décharge données
    # La feuille Décharge données a deux colonnes "Quels outils..." (X et AH)
    # pandas les renomme automatiquement ...X et ...AH avec suffixe .1
    _src_outils_trad = _get_trad_outils_col(raw)                                              # TC!BH
    out["trad_outils_com_src"] = _src_outils_trad

    # ── TC!BI-BM — Flags outils Trad ──────────────────────────────────────────
    out["trad_outil_etiquettes"] = flag_if_contains(_src_outils_trad, "Etiquettes spécifique VAS")  # TC!BI
    out["trad_outil_affiches"]   = flag_if_contains(_src_outils_trad, "Affiches VAS")               # TC!BJ
    out["trad_outil_reglette"]   = flag_if_contains(_src_outils_trad, "Réglette linéaire VAS")      # TC!BK
    out["trad_outil_fiches"]     = flag_if_contains(_src_outils_trad, " Fiches recettes")            # TC!BL (espace intentionnel en début)
    out["trad_outil_oriflamme"]  = flag_if_contains(_src_outils_trad, "Oriflamme / voile")           # TC!BM

    # ── TC!BN — Nb outils Trad ────────────────────────────────────────────────
    _trad_outils_flags = ["trad_outil_etiquettes", "trad_outil_affiches", "trad_outil_reglette", "trad_outil_fiches", "trad_outil_oriflamme"]
    out["trad_nb_outils"] = count_non_blank_with_guard(_src_outils_trad, out, _trad_outils_flags)  # TC!BN

    # ── TC!BR — Morceaux VAS présents (source) ────────────────────────────────
    _src_morceaux = raw.get("Morceaux de V.A.S. présents dans le magasin (au rayon LS ou tradi) :", "")  # TC!BR
    out["morceaux_presents_src"] = _src_morceaux

    # ── TC!BS-CB — Flags morceaux ─────────────────────────────────────────────
    for morceau in ["Escalope", "Sauté", "Roti", "Tendron", "Jarret / Ossobuco",
                    "Saucisse", "Steack haché", "Carparcio", "Abat", "Plats cuisinés"]:
        key = "morceau_" + re.sub(r"[^a-z0-9]+", "_", morceau.lower()).strip("_")
        out[key] = flag_if_contains(_src_morceaux, morceau)    # TC!BS-CB

    # ── TC!CC-CN — Prix (copie source avec vide si absent) ────────────────────
    # TC!CC = IF(Décharge!AM="","",Décharge!AM) etc.
    prix_map = {
        "prix_vas_escalope":  "V,A,S, - Escalope (€/kg)",          # TC!CC — Décharge!AM
        "prix_vas_saute":     "V,A,S,- Sauté (€/kg)",              # TC!CD — Décharge!AO
        "prix_vas_roti":      "V,A,S, - Roti (€/kg)",              # TC!CE — Décharge!AQ
        "prix_vas_tendron":   "V,A,S, - Tendron (€/kg)",           # TC!CF — Décharge!AS
        "prix_vas_jarret":    "V,A,S, - Jarret/ Ossobuco (€/kg)",  # TC!CG — Décharge!AU
        "prix_vas_hache":     "V,A,S, - Haché (€/kg)",             # TC!CH — Décharge!AW
        "prix_autre_escalope":"Autre veau - Escalope (€/kg)",       # TC!CI — Décharge!AN
        "prix_autre_saute":   "Autre veau - Sauté (€/kg)",          # TC!CJ — Décharge!AP
        "prix_autre_roti":    "Autre veau - Roti (€/kg)",           # TC!CK — Décharge!AR
        "prix_autre_tendron": "Autre veau - Tendron (€/kg)",        # TC!CL — Décharge!AT
        "prix_autre_jarret":  "Autre veau - Jarret/ Ossobuco (€/kg)",# TC!CM — Décharge!AV
        "prix_autre_hache":   "Autre veau - Haché (€/kg)",          # TC!CN — Décharge!AX
    }
    for field, src_col in prix_map.items():
        out[field] = clean_price(raw.get(src_col, pd.Series("", index=raw.index)))

    # ── TC!CO — Prix moyen VAS (IFERROR(AVERAGEIFS(CC:CH,CC:CH,"<>0"),"")) ────
    _vas_cols = ["prix_vas_escalope", "prix_vas_saute", "prix_vas_roti",
                 "prix_vas_tendron", "prix_vas_jarret", "prix_vas_hache"]
    out["prix_moyen_vas"] = out.apply(lambda row: mean_nonzero(row, _vas_cols), axis=1)  # TC!CO

    # ── TC!CP — Prix moyen autre veau ──────────────────────────────────────────
    _autre_cols = ["prix_autre_escalope", "prix_autre_saute", "prix_autre_roti",
                   "prix_autre_tendron", "prix_autre_jarret", "prix_autre_hache"]
    out["prix_moyen_autre_veau"] = out.apply(lambda row: mean_nonzero(row, _autre_cols), axis=1)  # TC!CP

    # ── TC!CS — Date premier jour (colonne BA Décharge = copie de B) ──────────
    _col_cs = _find_col(raw, ["Dates du PREMIER jour d'animation_8"])
    out["date_anim_ba"] = pd.to_datetime(raw[_col_cs], errors="coerce", dayfirst=True) if _col_cs else pd.NaT  # TC!CS

    # ── TC!CT — Date dernier jour ──────────────────────────────────────────────
    out["date_dernier_jour"] = pd.to_datetime(
        raw.get("Dates du DERNIER jour d'animation", ""), errors="coerce", dayfirst=True
    )  # TC!CT

    # ── TC!CU — Emplacement animation (source) ────────────────────────────────
    _src_emplacement = raw.get("Emplacement de l'animation", "")  # TC!CU
    out["emplacement_src"] = _src_emplacement

    # ── TC!CV-CY — Flags emplacement ──────────────────────────────────────────
    out["empl_entree"]   = flag_if_contains(_src_emplacement, "Entrée du magasin")                # TC!CV
    out["empl_allee"]    = flag_if_contains(_src_emplacement, "Allée centrale")                   # TC!CW
    out["empl_ls"]       = flag_if_contains(_src_emplacement, "Rayon libre service")              # TC!CX
    out["empl_trad"]     = flag_if_contains(_src_emplacement, "Rayon traditionnel (à la coupe)")  # TC!CY

    # ── TC!CZ — Fréquentation ─────────────────────────────────────────────────
    out["frequentation"] = raw.get("Fréquentation du magasin lors de l'animation", "")  # TC!CZ

    # ── TC!DA — Approvisionnement ─────────────────────────────────────────────
    out["approvisionnement"] = raw.get("Comment décririez-vous l'approvitionnement du rayon au cours de votre animation ?", "")  # TC!DA

    # ── TC!DB — Ruptures ──────────────────────────────────────────────────────
    out["ruptures"] = raw.get("Il y a t'il eu des ruptures pour certains morceaux de VAS au cours de l'animation ?", "")  # TC!DB

    # ── TC!DD — Outils animation spécifiques (source) ────────────────────────
    _src_outils_anim = raw.get("Indiquer quels outils / animations spécifiques étaient présentent lors de votre animation", "")  # TC!DD
    out["outils_animation_src"] = _src_outils_anim

    # ── TC!DE-DJ — Flags outils animation ─────────────────────────────────────
    out["outils_depliant"]     = flag_if_contains(_src_outils_anim, "Dépliant recettes")                    # TC!DE
    out["outils_oriflamme"]    = flag_if_contains(_src_outils_anim, "Oriflamme / voile")                    # TC!DF
    out["outils_ballon"]       = flag_if_contains(_src_outils_anim, "Ballon enfant / porte clé")            # TC!DG
    out["outils_degustation_chef"] = flag_if_contains(_src_outils_anim, "Dégustation avec un chef cuisinier")  # TC!DH
    out["outils_degustation_elev"] = flag_if_contains(_src_outils_anim, "Dégustation réalisée par éleveur")  # TC!DI
    out["outils_autres"]       = flag_if_contains(_src_outils_anim, "Autres")                               # TC!DJ

    # ── TC!DK — Mise en avant magasin (source) ────────────────────────────────
    _src_mise_avant = raw.get("Indiquer quels types de mise en avant particulière de l'animation a été faite par le magasin ?", "")  # TC!DK
    out["mise_en_avant_src"] = _src_mise_avant

    # ── TC!DL-DQ — Flags mise en avant ────────────────────────────────────────
    out["avant_reseaux"]    = flag_if_contains(_src_mise_avant, "Publications sur les réseaux sociaux")        # TC!DL
    out["avant_affiches"]   = flag_if_contains(_src_mise_avant, "Affiches spécifiques dans le magasin pour l'animation")  # TC!DM
    out["avant_depliant"]   = flag_if_contains(_src_mise_avant, "Dépliant publicitaire qui annonce l'animation")  # TC!DN
    out["avant_annonces"]   = flag_if_contains(_src_mise_avant, "Annonces micro par l'animateur du magasin")  # TC!DO
    out["avant_autres"]     = flag_if_contains(_src_mise_avant, "Autres")                                     # TC!DP
    out["avant_aucun"]      = flag_if_contains(_src_mise_avant, "Aucune mise en avant particulière")          # TC!DQ

    # ── TC!DS — Ventes supplémentaires ────────────────────────────────────────
    out["ventes_supplementaires"] = raw.get("L'animation a t'elle entrainé des ventes supplémentaires ?", "")  # TC!DS

    # ── TC!DT — Incident ──────────────────────────────────────────────────────
    out["incident"] = raw.get("Il y a t'il eu un soucis, un contre-temps au cours de l'animation", "")  # TC!DT

    # ── TC!DW — Tranche âge (source) ──────────────────────────────────────────
    _src_tranche_age = raw.get("Tranche d'âge majoritairement rencontrée", "")  # TC!DW
    out["tranche_age_src"] = _src_tranche_age

    # ── TC!DX-EA — Flags tranche âge ──────────────────────────────────────────
    out["age_18_25"] = flag_if_contains(_src_tranche_age, "18/25 ans")   # TC!DX
    out["age_25_40"] = flag_if_contains(_src_tranche_age, "25/40 ans")   # TC!DY (espace possible en début)
    out["age_40_60"] = flag_if_contains(_src_tranche_age, "40/60 ans")   # TC!DZ
    out["age_60p"]   = flag_if_contains(_src_tranche_age, "+ 60 ans")    # TC!EA

    # ── TC!EB — Attitude clients (source) ─────────────────────────────────────
    _src_attitude = raw.get("Attitude des personnes rencontrées", "")  # TC!EB
    out["attitude_src"] = _src_attitude

    # ── TC!EC-EE — Flags attitude ─────────────────────────────────────────────
    out["attitude_positive"]      = flag_if_contains(_src_attitude, "Positive")       # TC!EC
    out["attitude_pas_interesse"]  = flag_if_contains(_src_attitude, "Pas intéressé")  # TC!ED
    out["attitude_agressive"]     = flag_if_contains(_src_attitude, "Agressives")     # TC!EE

    # ── TC!EF — Clients connaissaient VAS ─────────────────────────────────────
    out["clients_connaissaient_vas"] = raw.get("Majoritairement, les clients connaissaient-ils le V,A,S, ?", "")  # TC!EF

    # ── TC!EG — Type questions (source) ───────────────────────────────────────
    _src_questions = raw.get("Type de questions posées", "")  # TC!EG
    out["type_questions_src"] = _src_questions

    # ── TC!EH-EL — Flags type questions ───────────────────────────────────────
    out["question_elevage"]   = flag_if_contains(_src_questions, "Elevage")              # TC!EH
    out["question_abattage"]  = flag_if_contains(_src_questions, "Abattage")             # TC!EI
    out["question_cuisson"]   = flag_if_contains(_src_questions, "Cuisson / recette")    # TC!EJ
    out["question_environnement"] = flag_if_contains(_src_questions, "Environnement")    # TC!EK
    out["question_aucune"]    = flag_if_contains(_src_questions, "Pas de question")      # TC!EL

    # ── TC!EN-EP — Ressentis ──────────────────────────────────────────────────
    out["ressenti_mise_en_place"]  = raw.get("Votre ressenti pour la mise en place de l'animation", "")      # TC!EN
    out["ressenti_accroche"]       = raw.get("Votre ressenti pour l'accroche des consommateurs", "")          # TC!EO
    out["ressenti_argumentaire"]   = raw.get("Votre ressenti pour le développement de l'argumentaire V,A,S,", "")  # TC!EP

    # ── TC!EQ — Intérêt formation ─────────────────────────────────────────────
    out["interesse_formation"] = raw.get("Seriez-vous intéresser pour participer à une formation (1 jour) pour être plus à l'aise lors des animations ?", "")  # TC!EQ

    # ── TC!ER-ES — Kits ───────────────────────────────────────────────────────
    out["kit_irva"]    = raw.get("Kit animation IRVA", "")                              # TC!ER
    out["kit_interbev"]= raw.get("Kit animation Interbev (si présent)", "")             # TC!ES

    # ── TC!EU — Échanges chef boucher (source) ────────────────────────────────
    _src_echanges = raw.get("Echanges avec le chef boucher / équipe du magasin", "")  # TC!EU
    out["echanges_cb_src"] = _src_echanges

    # ── TC!EV-EY — Flags échanges ─────────────────────────────────────────────
    out["echange_amont"]    = flag_if_contains(_src_echanges, "OUI, en amont pour préparer l'animation")     # TC!EV
    out["echange_pendant"]  = flag_if_contains(_src_echanges, "OUI, pendant l'animation")                    # TC!EW
    out["echange_cloture"]  = flag_if_contains(_src_echanges, "OUI, en clôture de l'animation")              # TC!EX
    out["echange_non"]      = flag_if_contains(_src_echanges, "NON")                                          # TC!EY

    # ── TC!FB-FE — Fichiers / signature (pour statut CR) ─────────────────────
    out["_fb"] = raw.get("Cochez la case correspondant à votre situation :", "")                              # TC!FB
    out["_fc"] = raw.get("Téléchargez ici les photos de votre animation", "")                                 # TC!FC
    out["_fd"] = raw.get("Téléchargez ICI la photo du feuillet avec la signature et le caché du chef boucher", "")  # TC!FD
    # TC!FE : Forminator exporte "Signature Eleveur.se" (point) ou "Signature Eleveur,se" (virgule)
    # selon la version. On prend la première colonne non-vide parmi les deux noms.
    _sig_col = _find_col(raw, ["Signature Eleveur.se", "Signature Eleveur,se"])
    _sig_series = raw[_sig_col] if _sig_col else pd.Series("", index=raw.index)
    # Une deuxième colonne signature (Unnamed: 85) peut contenir des signatures du 2ème formulaire
    _sig2_col = _find_col(raw, ["Unnamed: 85"])
    if _sig2_col:
        _sig2 = raw[_sig2_col]
        # Fusionner : garder _fe principale, compléter avec la 2ème si vide
        _sig_series = _sig_series.combine_first(_sig2)
    out["_fe"] = _sig_series                                                                                  # TC!FE

    # ── TC!FF — Statut CR (formule clé de toutes les synthèses) ──────────────
    out["statut_cr"] = compute_cr_status(out)  # TC!FF

    # Nettoyage colonnes internes
    out = out.drop(columns=["_fb", "_fc", "_fd", "_fe"])

    # ── TC!P — Ref animation ──────────────────────────────────────────────────
    out["ref_animation"] = (
        out["date_premier_jour"].astype(str)
        + "_" + out["magasin_norm"].astype(str)
        + "_" + out["statut_cr"].astype(str)
    )  # TC!P

    return out


# ---------------------------------------------------------------------------
# Helpers de chargement colonne
# ---------------------------------------------------------------------------

def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Retourne le premier nom de colonne trouvé dans df."""
    for name in candidates:
        if name in df.columns:
            return name
    return None


def _get_trad_outils_col(raw: pd.DataFrame) -> pd.Series:
    """
    Dans Décharge données, il y a deux colonnes 'Quels outils de communication...' :
    - col X (LS)  — TC!AR
    - col AH (Trad) — TC!BH
    Pandas les renomme avec suffixe .1 lors du chargement si les en-têtes sont dupliqués.
    On cherche la deuxième occurrence.
    """
    base = "Quels outils de communication V.A.S. sont présents dans le rayon TOUTE L' ANNEE ?"
    variant = base + ".1"
    if variant in raw.columns:
        return raw[variant]
    # Parfois pandas utilise _1 ou un suffixe différent — cherche par pattern
    for col in raw.columns:
        if base in col and col != base:
            return raw[col]
    # Fallback: colonne vide
    return pd.Series("", index=raw.index)


# ---------------------------------------------------------------------------
# Synthèses reproduisant les feuilles de résumé Excel
# ---------------------------------------------------------------------------

def filter_cr_ok(tc: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    Équivalent du filtre commun à toutes les COUNTIFS de synthèse :
      FF="CR OK"  AND  I>=start  AND  I<end
    """
    mask = (
        (tc["statut_cr"] == "CR OK") &
        (tc["date_premier_jour"] >= start) &
        (tc["date_premier_jour"] < end)
    )
    return tc[mask]


def build_global_summary(tc: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """
    Synthèse Global — reproduit les COUNTIFS de la feuille éponyme.
    Attendu pour Année 2025 : L4=205 au total.
    """
    cr = filter_cr_ok(tc, start, end)
    total = len(cr)

    # Par filière (TC!O)
    par_filiere = cr.groupby("filiere").size().to_dict()

    # Par enseigne (TC!Q)
    par_enseigne = cr.groupby("enseigne").size().sort_values(ascending=False).head(15).to_dict()

    # Rayons (TC!AC-AF)
    def _count_flag(col, val):
        return int((cr[col] == val).sum())

    rayons = {
        "ls":    _count_flag("rayon_ls",        "Rayon libre-service (LS)"),
        "trad":  _count_flag("rayon_trad",       "Rayon Coupe (Trad)"),
        "drive": _count_flag("rayon_drive",      "Drive"),
        "entree":_count_flag("rayon_ls_entree",  "Libre service à l'entrée du magasin (ponctuellement)"),
    }

    # Barquettes (TC!AH-AK)
    barquettes = {
        "beigne":       _count_flag("ls_barquette_beigne",        "Beigne (Compostable)"),
        "noire":        _count_flag("ls_barquette_noire",         "Noire (Polystyrène)"),
        "transparente": _count_flag("ls_barquette_transparente",   "Transparente (PET)"),
        "blanche":      _count_flag("ls_barquette_blanche",        "Blanche (Polystyrène)"),
    }

    # Outils LS (TC!AS-AW)
    outils_ls = {
        "etiquettes": _count_flag("ls_outil_etiquettes", "Etiquettes spécifique VAS"),
        "affiches":   _count_flag("ls_outil_affiches",   "Affiches VAS"),
        "reglette":   _count_flag("ls_outil_reglette",   "Réglette linéaire VAS"),
        "fiches":     _count_flag("ls_outil_fiches",     "Fiches recettes"),
        "oriflamme":  _count_flag("ls_outil_oriflamme",  "Oriflamme / voile"),
    }

    # Qualité découpe LS (TC!AP)
    qualite_ls = cr["ls_qualite_decoupe"].value_counts().to_dict()

    # Visibilité LS (TC!AM)
    visibilite_ls = cr["ls_visibilite"].value_counts().to_dict()

    # Approvisionnement (TC!DA) et ventes (TC!DS)
    appro = cr["approvisionnement"].value_counts().to_dict()
    ventes = cr["ventes_supplementaires"].value_counts().to_dict()

    # Clients connaissaient VAS (TC!EF)
    clients_vas = cr["clients_connaissaient_vas"].value_counts().to_dict()

    # Kits (TC!ER-ES)
    kits = {
        "irva":     cr["kit_irva"].value_counts().to_dict(),
        "interbev": cr["kit_interbev"].value_counts().to_dict(),
    }

    # Prix moyens (TC!CO-CP)
    prix_vas_num = pd.to_numeric(cr["prix_moyen_vas"].replace("", pd.NA), errors="coerce")
    prix_autre_num = pd.to_numeric(cr["prix_moyen_autre_veau"].replace("", pd.NA), errors="coerce")

    # Prix par morceau (AVERAGEIFS sur CC:CH individuellement)
    def _avg_prix(col):
        vals = pd.to_numeric(cr[col], errors="coerce")
        vals = vals[(vals.notna()) & (vals != 0)]
        return round(float(vals.mean()), 2) if not vals.empty else None

    prix_par_morceau_vas = {
        "Escalope":  _avg_prix("prix_vas_escalope"),
        "Sauté":     _avg_prix("prix_vas_saute"),
        "Rôti":      _avg_prix("prix_vas_roti"),
        "Tendron":   _avg_prix("prix_vas_tendron"),
        "Jarret":    _avg_prix("prix_vas_jarret"),
        "Haché":     _avg_prix("prix_vas_hache"),
    }
    prix_par_morceau_autre = {
        "Escalope":  _avg_prix("prix_autre_escalope"),
        "Sauté":     _avg_prix("prix_autre_saute"),
        "Rôti":      _avg_prix("prix_autre_roti"),
        "Tendron":   _avg_prix("prix_autre_tendron"),
        "Jarret":    _avg_prix("prix_autre_jarret"),
        "Haché":     _avg_prix("prix_autre_hache"),
    }

    # Tranche âge (TC!DX-EA)
    tranches_age = {
        "18/25 ans": _count_flag("age_18_25", "18/25 ans"),
        "25/40 ans": _count_flag("age_25_40", "25/40 ans"),
        "40/60 ans": _count_flag("age_40_60", "40/60 ans"),
        "+ 60 ans":  _count_flag("age_60p",   "+ 60 ans"),
    }

    # Échanges chef boucher (TC!EV-EY)
    # Les valeurs doivent correspondre aux needles passées à flag_if_contains (TC!EV-EY)
    echanges = {
        "amont":   _count_flag("echange_amont",   "OUI, en amont pour préparer l'animation"),
        "pendant": _count_flag("echange_pendant",  "OUI, pendant l'animation"),
        "cloture": _count_flag("echange_cloture",  "OUI, en clôture de l'animation"),
        "non":     _count_flag("echange_non",      "NON"),
    }

    return {
        "periode": f"{start.date()} → {end.date()}",
        "total_cr_ok": total,                     # L4 dans Synthèse Global
        "par_filiere": par_filiere,               # B9:B14
        "par_enseigne": par_enseigne,
        "rayons": rayons,
        "barquettes": barquettes,
        "outils_ls": outils_ls,
        "qualite_decoupe_ls": qualite_ls,
        "visibilite_ls": visibilite_ls,
        "approvisionnement": appro,
        "ventes_supplementaires": ventes,
        "clients_connaissaient_vas": clients_vas,
        "kits": kits,
        "prix_moyen_vas_global": round(float(prix_vas_num.mean()), 2) if prix_vas_num.notna().any() else None,
        "prix_moyen_autre_veau_global": round(float(prix_autre_num.mean()), 2) if prix_autre_num.notna().any() else None,
        "prix_par_morceau_vas": prix_par_morceau_vas,
        "prix_par_morceau_autre": prix_par_morceau_autre,
        "tranches_age": tranches_age,
        "echanges_chef_boucher": echanges,
    }


def build_filiere_summary(tc: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Synthèse par filière — reproduit la feuille éponyme."""
    result = {}
    filieres = tc["filiere"].dropna().unique()
    for f in sorted(filieres):
        cr = filter_cr_ok(tc, start, end)
        cr = cr[cr["filiere"] == f]
        result[f] = {
            "total_cr_ok": len(cr),
            "par_enseigne": cr.groupby("enseigne").size().to_dict(),
            "prix_moyen_vas": round(float(pd.to_numeric(cr["prix_moyen_vas"].replace("", pd.NA), errors="coerce").mean()), 2)
                              if not cr.empty else None,
        }
    return result


def pivot_prices_by_region(tc: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Remplace le TCD Prix par région."""
    cr = filter_cr_ok(tc, start, end)
    price_cols = ["prix_vas_escalope", "prix_vas_saute", "prix_vas_roti",
                  "prix_vas_tendron", "prix_vas_jarret", "prix_vas_hache"]
    for col in price_cols:
        cr = cr.copy()
        cr[col] = pd.to_numeric(cr[col], errors="coerce")
    # Exclure 0 comme Excel AVERAGEIFS("<>0")
    for col in price_cols:
        cr[col] = cr[col].mask(cr[col] == 0)
    return cr.groupby("region")[price_cols].mean().round(2)


def pivot_anim_by_store(tc: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Remplace le TCD Anim par Mag."""
    cr = filter_cr_ok(tc, start, end)
    return (
        cr.groupby("magasin_norm")
        .size()
        .reset_index(name="nb_animations")
        .sort_values("nb_animations", ascending=False)
    )


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main(
    xlsx_path: str = "20260129_Tableau CR Anim.xlsx",
    year_label: str = "Année 2025",
    output_csv: bool = True,
):
    print(f"Chargement : {xlsx_path}")
    sources = load_sources(xlsx_path)

    raw = sources["decharge"]
    print(f"  → Décharge données : {len(raw)} lignes, {len(raw.columns)} colonnes")

    # Dates de la période depuis le référentiel
    start, end = get_period_dates(year_label, sources["donnee_liste"])
    if start is None:
        print(f"  ⚠ Période '{year_label}' introuvable dans Donnée liste. "
              "Fallback 2025-01-01 / 2026-01-01")
        start = pd.Timestamp("2025-01-01")
        end   = pd.Timestamp("2026-01-01")
    print(f"  → Période '{year_label}' : {start.date()} → {end.date()}")

    print("Construction Tableau calcul…")
    tc = build_tableau_calcul(raw, sources)
    total_cr_ok = (tc["statut_cr"] == "CR OK").sum()
    total_brouillon = (tc["statut_cr"] == "Brouillon").sum()
    print(f"  → {len(tc)} lignes  |  CR OK={total_cr_ok}  |  Brouillon={total_brouillon}")

    print("Synthèses…")
    summary = build_global_summary(tc, start, end)

    print(f"\n{'='*60}")
    print(f"  Période : {summary['periode']}")
    print(f"  Total CR OK : {summary['total_cr_ok']}  (Excel attendu : 205 pour 2025)")
    print(f"\n  Par filière :")
    for f, n in sorted(summary["par_filiere"].items(), key=lambda x: -x[1]):
        print(f"    {f or '(vide)':<20} {n:>4}")

    print(f"\n  Prix moyen VAS (tout morceau) : {summary['prix_moyen_vas_global']} €/kg")
    print(f"  Prix moyen autre veau        : {summary['prix_moyen_autre_veau_global']} €/kg")
    print(f"\n  Prix VAS par morceau :")
    for m, p in summary["prix_par_morceau_vas"].items():
        print(f"    {m:<20} {str(p):>8} €/kg")

    print(f"\n  Tranche âge :")
    for t, n in summary["tranches_age"].items():
        print(f"    {t:<15} {n:>4}")

    print(f"\n  Échanges chef boucher :")
    for k, n in summary["echanges_chef_boucher"].items():
        print(f"    {k:<10} {n:>4}")

    if output_csv:
        out_path = Path(xlsx_path).parent / "tableau_calcul_reconstruit.csv"
        tc.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"\n  → Export CSV : {out_path}")

        prices_region = pivot_prices_by_region(tc, start, end)
        prices_region.to_csv(Path(xlsx_path).parent / "prix_par_region.csv", encoding="utf-8-sig")

        anim_store = pivot_anim_by_store(tc, start, end)
        anim_store.to_csv(Path(xlsx_path).parent / "anim_par_mag.csv", index=False, encoding="utf-8-sig")

    return tc, summary


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "20260129_Tableau CR Anim.xlsx"
    label = sys.argv[2] if len(sys.argv) > 2 else "Année 2025"
    main(xlsx_path=path, year_label=label)
