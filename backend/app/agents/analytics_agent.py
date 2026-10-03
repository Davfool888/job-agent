"""Analytics Agent (§19): lee historia, NO modifica ofertas.

Opera sobre Records (agnostico al motor): funciona igual con SQLite
y Firestore. Para Firestore existe ademas un summarize nativo en
firestore_repo (misma forma de salida).
"""
from __future__ import annotations

import json
from collections import Counter

from sqlalchemy.orm import Session

from app.services.job_service import iter_all_jobs


def _as_list(value) -> list:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def summarize(db: Session, uid: str | None = None, email: str | None = None) -> dict:
    rows = iter_all_jobs(db, limit=5000)
    
    # Filtrar por usuario si hay sesión
    if uid:
        from app.services.search_profiles import _is_guest, GUEST_OWNER
        store_uid = GUEST_OWNER if _is_guest(uid, email) else uid
        filtered_rows = []
        for row in rows:
            # Verificar si la oferta pertenece al usuario
            if getattr(row, 'owner_uid', None) == store_uid:
                filtered_rows.append(row)
                continue
            # Verificar si fue encontrada por un perfil del usuario
            profile_ids = _as_list(getattr(row, 'search_profile_ids', None))
            if profile_ids:
                from app.services import search_profiles as profiles
                for pid in profile_ids:
                    profile = profiles.get_profile(db, pid)
                    if profile and profile.get('owner_uid') == store_uid:
                        filtered_rows.append(row)
                        break
        rows = filtered_rows
    
    total = len(rows)

    by_status: Counter = Counter()
    scored = 0
    score_sum = 0.0
    companies: Counter = Counter()
    queries: Counter = Counter()
    reasons: Counter = Counter()
    categories: Counter = Counter()
    sources: Counter = Counter()
    discovery_counter: Counter = Counter()
    skill_counter: Counter = Counter()
    missing_counter: Counter = Counter()
    hidden_title_relevant = 0
    hidden_title_total = 0
    cv_count = 0

    for row in rows:
        status = row.status or "new"
        by_status[status] += 1
        if row.match_score is not None:
            scored += 1
            score_sum += row.match_score
        if (row.company or "").strip():
            companies[row.company] += 1
        if row.search_query:
            queries[row.search_query] += 1
        if status == "discarded" and row.discard_reason:
            reasons[row.discard_reason] += 1
        categories[row.category or "SIN_ANALIZAR"] += 1
        sources[row.source or "desconocida"] += 1
        for item in _as_list(row.discovered_by):
            if isinstance(item, str) and item.strip():
                discovery_counter[item] += 1
        for item in _as_list(row.matched_skills):
            if isinstance(item, str) and item.strip():
                skill_counter[item] += 1
        for item in _as_list(row.missing_skills):
            if isinstance(item, str) and item.strip():
                missing_counter[item] += 1
        if (row.match_score or 0) >= 40 or (
            row.category and row.category != "OTHER"
        ):
            hidden_title_total += 1
            title_norm = (row.title or "").lower()
            if (
                "analista de datos" not in title_norm
                and "data analyst" not in title_norm
            ):
                hidden_title_relevant += 1
        if row.cv_generated:
            cv_count += 1

    # Orden estable: recientes primero (los Records ya vienen asi).
    last = rows[0] if rows else None

    return {
        "total": total,
        "by_status": dict(by_status),
        "scored_count": scored,
        "avg_match": round(score_sum / scored, 1) if scored else None,
        "top_companies": [
            {"company": company, "count": count}
            for company, count in companies.most_common(10)
        ],
        "top_queries": [
            {"query": query, "count": count}
            for query, count in queries.most_common(10)
        ],
        "discard_reasons": [
            {"reason": reason, "count": count}
            for reason, count in reasons.most_common()
        ],
        "by_category": dict(categories),
        "by_source": dict(sources),
        "top_discovery_queries": [
            {"query": query, "count": count}
            for query, count in discovery_counter.most_common(15)
        ],
        "top_skills": [
            {"skill": skill, "count": count}
            for skill, count in skill_counter.most_common(15)
        ],
        "top_missing_skills": [
            {"skill": skill, "count": count}
            for skill, count in missing_counter.most_common(15)
        ],
        "relevant_hidden_title": hidden_title_relevant,
        "relevant_total": hidden_title_total,
        "cv_generated_count": cv_count,
        "last_job": (
            {
                "id": last.id,
                "title": last.title,
                "company": last.company,
                "created_at": last.created_at.isoformat()
                if last.created_at
                else None,
            }
            if last
            else None
        ),
    }
