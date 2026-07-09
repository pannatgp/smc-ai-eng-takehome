"""Dynamic registry of which companies have 10-K text in the vector store.

Single source of truth for "does this company have a filing we can search?". It is
populated by the ingest path (scripts/load_vectors.py) from the sources actually upserted
into Pinecone — so it can never claim a filing that isn't in the index. The router reads
it instead of a hardcoded company list, so adding a new filing (e.g. a surprise 5th PDF)
requires no code change: ingest it, and it registers itself.

The only hardcoded knowledge is the brand->filer alias for companies whose consumer brand
differs from their SEC filer name (Google is filed under Alphabet, Facebook under Meta).
That is irreducible domain knowledge, not derivable from any data source. Every other name
maps to itself, so new filers work automatically.
"""

import re
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import Base, engine
from app.models import VectorRegistry, _now

# consumer brand (lowercased) -> SEC filer key used in the 10-K filename
_BRAND_TO_FILER: dict[str, str] = {
    "google": "alphabet",
    "facebook": "meta",
}


def ensure_table() -> None:
    Base.metadata.create_all(bind=engine, tables=[VectorRegistry.__table__])


def company_key_from_source(source: str) -> str:
    """'Alphabet_10K_FY2025.pdf' -> 'alphabet'."""
    match = re.match(r"^([A-Za-z0-9]+)", source)
    return (match.group(1) if match else source).lower()


def register_sources(sources: set[str]) -> None:
    """Upsert the given 10-K source filenames into the registry (idempotent)."""
    ensure_table()
    with engine.begin() as conn:
        for source in sorted(sources):
            key = company_key_from_source(source)
            stmt = pg_insert(VectorRegistry).values(company_key=key, source=source)
            stmt = stmt.on_conflict_do_update(
                index_elements=["company_key"],
                set_={"source": source, "updated_at": _now()},
            )
            conn.execute(stmt)
    refresh()


def _filer_key(name: str) -> str:
    normalized = name.strip().lower()
    return _BRAND_TO_FILER.get(normalized, normalized)


@lru_cache(maxsize=1)
def _registry() -> dict[str, str]:
    """company_key -> source filename, loaded once and cached."""
    ensure_table()
    with engine.connect() as conn:
        rows = conn.execute(select(VectorRegistry.company_key, VectorRegistry.source)).all()
    return {key: source for key, source in rows}


def refresh() -> None:
    """Drop the cache so newly registered filings become visible without a restart."""
    _registry.cache_clear()


def available_sources() -> dict[str, str]:
    return dict(_registry())


def resolve_source(name: str) -> str | None:
    """Resolve a user-facing company name to its 10-K source, or None if no filing exists."""
    return _registry().get(_filer_key(name))
