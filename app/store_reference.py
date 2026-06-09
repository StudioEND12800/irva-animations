from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import selectinload

from app.utils import compact_spaces, guess_enseigne_from_store_name, normalize_store_name
from models import MagasinAlias, MagasinReference, db


def _reference_names(reference: MagasinReference) -> list[str]:
    names = [reference.nom_reference]
    names.extend(alias.alias for alias in reference.aliases)
    return [compact_spaces(name) for name in names if compact_spaces(name)]


def _score_reference(
    reference: MagasinReference,
    query: str = '',
    enseigne: str = '',
    code_postal: str = '',
    commune: str = '',
) -> int:
    score = 0
    normalized_query = normalize_store_name(query)
    normalized_commune = normalize_store_name(commune)
    expected_postal = compact_spaces(code_postal)
    expected_enseigne = compact_spaces(enseigne)
    names = _reference_names(reference)
    normalized_names = [normalize_store_name(name) for name in names]

    if expected_enseigne:
        if compact_spaces(reference.enseigne) == expected_enseigne:
            score += 25
        elif reference.enseigne:
            score -= 6

    if expected_postal:
        ref_postal = compact_spaces(reference.code_postal)
        if ref_postal == expected_postal:
            score += 70
        elif ref_postal:
            score -= 14

    if normalized_commune and normalized_commune != 'non-renseigne':
        ref_commune = normalize_store_name(reference.commune)
        if ref_commune == normalized_commune:
            score += 45
        elif normalized_commune in ref_commune or ref_commune in normalized_commune:
            score += 18

    if normalized_query and normalized_query != 'non-renseigne':
        if normalized_query in normalized_names:
            score += 160
        elif any(normalized_query in candidate for candidate in normalized_names):
            score += 105

        query_tokens = normalized_query.split()
        best_token_hits = 0
        for candidate in normalized_names:
            candidate_tokens = set(candidate.split())
            best_token_hits = max(best_token_hits, sum(token in candidate_tokens for token in query_tokens))
        score += best_token_hits * 14
        if best_token_hits == 0:
            score -= 40
    elif not expected_postal and not normalized_commune and not expected_enseigne:
        return -1

    if reference.code_postal:
        score += 3
    if reference.commune:
        score += 3
    if reference.region:
        score += 1

    return score


def store_reference_payload(reference: MagasinReference) -> dict[str, object]:
    aliases = [compact_spaces(alias.alias) for alias in reference.aliases if compact_spaces(alias.alias)]
    return {
        'id': reference.id,
        'enseigne': compact_spaces(reference.enseigne),
        'nom_magasin': compact_spaces(reference.nom_reference),
        'code_postal': compact_spaces(reference.code_postal),
        'commune': compact_spaces(reference.commune),
        'code_departement': compact_spaces(reference.code_departement),
        'region': compact_spaces(reference.region),
        'adresse': compact_spaces(reference.adresse),
        'aliases': aliases,
        'label': compact_spaces(reference.nom_reference),
    }


def find_store_reference_matches(
    query: str = '',
    enseigne: str = '',
    code_postal: str = '',
    commune: str = '',
    limit: int = 8,
    include_inactive: bool = False,
) -> list[MagasinReference]:
    query_builder = MagasinReference.query
    if not include_inactive:
        query_builder = query_builder.filter_by(actif=True)
    refs = (
        query_builder
        .options(selectinload(MagasinReference.aliases))
        .order_by(MagasinReference.enseigne.asc(), MagasinReference.nom_reference.asc())
        .all()
    )

    scored: list[tuple[int, MagasinReference]] = []
    for reference in refs:
        score = _score_reference(reference, query=query, enseigne=enseigne, code_postal=code_postal, commune=commune)
        if score > 0:
            scored.append((score, reference))

    scored.sort(
        key=lambda item: (
            -item[0],
            compact_spaces(item[1].enseigne).lower(),
            compact_spaces(item[1].nom_reference).lower(),
        )
    )
    return [reference for _score, reference in scored[:limit]]


def find_exact_store_reference(
    nom_magasin: str = '',
    enseigne: str = '',
    code_postal: str = '',
    commune: str = '',
) -> MagasinReference | None:
    normalized_name = normalize_store_name(nom_magasin)
    if not normalized_name or normalized_name == 'non-renseigne':
        return None

    refs = (
        MagasinReference.query
        .filter_by(actif=True)
        .options(selectinload(MagasinReference.aliases))
        .all()
    )

    matches = []
    expected_enseigne = compact_spaces(enseigne)
    expected_postal = compact_spaces(code_postal)
    expected_commune = normalize_store_name(commune)

    for reference in refs:
        names = {reference.nom_normalise}
        names.update(alias.alias_normalise for alias in reference.aliases)
        if normalized_name not in names:
            continue
        if expected_enseigne and compact_spaces(reference.enseigne) not in ('', expected_enseigne):
            continue
        matches.append(reference)

    if not matches:
        return None

    if expected_postal:
        postal_matches = [reference for reference in matches if compact_spaces(reference.code_postal) == expected_postal]
        if len(postal_matches) == 1:
            return postal_matches[0]

    if expected_commune and expected_commune != 'non-renseigne':
        commune_matches = [
            reference
            for reference in matches
            if normalize_store_name(reference.commune) == expected_commune
        ]
        if len(commune_matches) == 1:
            return commune_matches[0]

    if len(matches) == 1:
        return matches[0]

    return None


def aliases_text(reference: MagasinReference | None) -> str:
    if not reference:
        return ''
    aliases = [compact_spaces(alias.alias) for alias in reference.aliases if compact_spaces(alias.alias)]
    return '\n'.join(sorted(dict.fromkeys(aliases)))


def sync_store_reference(
    *,
    reference_id: str | int | None = None,
    enseigne: str = '',
    nom_magasin: str = '',
    code_postal: str = '',
    commune: str = '',
    code_departement: str = '',
    region: str = '',
    adresse: str = '',
    aliases: Iterable[str] = (),
) -> tuple[MagasinReference | None, bool]:
    canonical_name = compact_spaces(nom_magasin)
    if not canonical_name:
        return None, False

    reference = None
    if reference_id not in (None, ''):
        reference = MagasinReference.query.get(int(reference_id))

    if reference is None:
        reference = find_exact_store_reference(
            nom_magasin=canonical_name,
            enseigne=enseigne,
            code_postal=code_postal,
            commune=commune,
        )

    created = False
    if reference is None:
        reference = MagasinReference()
        db.session.add(reference)
        created = True

    reference.enseigne = compact_spaces(enseigne) or compact_spaces(reference.enseigne) or guess_enseigne_from_store_name(canonical_name)
    reference.nom_reference = canonical_name
    reference.nom_normalise = normalize_store_name(canonical_name)
    reference.code_postal = compact_spaces(code_postal) or reference.code_postal
    reference.commune = compact_spaces(commune) or reference.commune
    reference.code_departement = compact_spaces(code_departement) or reference.code_departement
    reference.region = compact_spaces(region) or reference.region
    reference.adresse = compact_spaces(adresse) or reference.adresse
    reference.actif = True

    alias_values = [canonical_name]
    alias_values.extend(compact_spaces(value) for value in aliases if compact_spaces(value))
    existing = {alias.alias_normalise: alias for alias in reference.aliases}
    for alias_value in dict.fromkeys(alias_values):
        normalized_alias = normalize_store_name(alias_value)
        if normalized_alias in ('', 'non-renseigne', reference.nom_normalise):
            continue
        if normalized_alias in existing:
            existing[normalized_alias].alias = alias_value
            continue
        reference.aliases.append(
            MagasinAlias(alias=alias_value, alias_normalise=normalized_alias)
        )

    return reference, created
