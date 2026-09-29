"""Analytics Agent (§19): lee historia, NO modifica ofertas."""
from __future__ import annotations

import json
from collections import Counter

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import Job


def summarize(db: Session) -> dict:
    total = db.query(func.count(Job.id)).scalar() or 0

    by_status = {
        status: count
        for status, count in db.query(Job.status, func.count(Job.id))
        .group_by(Job.status)
        .all()
    }

    scored = (
        db.query(func.count(Job.id), func.avg(Job.match_score))
        .filter(Job.match_score.isnot(None))
        .first()
    )

    top_companies = [
        {"company": company, "count": count}
        for company, count in db.query(Job.company, func.count(Job.id))
        .filter(Job.company != "")
        .group_by(Job.company)
        .order_by(func.count(Job.id).desc())
        .limit(10)
        .all()
    ]

    top_queries = [
        {"query": query, "count": count}
        for query, count in db.query(Job.search_query, func.count(Job.id))
        .filter(Job.search_query.isnot(None))
        .group_by(Job.search_query)
        .order_by(func.count(Job.id).desc())
        .limit(10)
        .all()
    ]

    discard_reasons = [
        {"reason": reason, "count": count}
        for reason, count in db.query(
            Job.discard_reason, func.count(Job.id))
        .filter(Job.status == "discarded", Job.discard_reason.isnot(None))
        .group_by(Job.discard_reason)
        .order_by(func.count(Job.id).desc())
        .all()
    ]

    by_category = {
        category or "SIN_ANALIZAR": count
        for category, count in db.query(Job.category, func.count(Job.id))
        .group_by(Job.category)
        .all()
    }

    by_source = {
        source or "desconocida": count
        for source, count in db.query(Job.source, func.count(Job.id))
        .group_by(Job.source)
        .all()
    }

    discovery_counter: Counter[str] = Counter()
    skill_counter: Counter[str] = Counter()
    missing_counter: Counter[str] = Counter()
    hidden_title_relevant = 0
    hidden_title_total = 0
    cv_count = 0
    recent = db.query(Job).order_by(Job.id.desc()).limit(2000).all()
    for row in recent:
        for field, counter in (
            ("discovered_by", discovery_counter),
            ("matched_skills", skill_counter),
            ("missing_skills", missing_counter),
        ):
            try:
                items = json.loads(getattr(row, field) or "[]")
            except ValueError:
                items = []
            for item in items:
                if isinstance(item, str) and item.strip():
                    counter[item] += 1
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

    last = db.query(Job).order_by(Job.id.desc()).first()

    return {
        "total": total,
        "by_status": by_status,
        "scored_count": scored[0] or 0,
        "avg_match": round(scored[1], 1) if scored[1] is not None else None,
        "top_companies": top_companies,
        "top_queries": top_queries,
        "discard_reasons": discard_reasons,
        "by_category": by_category,
        "by_source": by_source,
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
