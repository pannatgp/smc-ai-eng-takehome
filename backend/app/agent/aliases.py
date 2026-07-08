"""Company name aliasing.

The SQL `financial_data` table uses "Google" and "Meta" as company names, while the
Pinecone metadata's `source` field uses the actual 10-K filer names ("Alphabet",
"Meta"). Users ask about "Google"/"Alphabet" and "Facebook"/"Meta" interchangeably, so
both tools resolve through this single alias table.
"""

# user-facing name (lowercased) -> canonical SQL `company` column value
SQL_COMPANY_ALIASES: dict[str, str] = {
    "alphabet": "Google",
    "google": "Google",
    "facebook": "Meta",
    "meta": "Meta",
}

# user-facing name (lowercased) -> 10-K filename in the vector store's `source` metadata
# Only these four companies have any 10-K text at all.
VECTOR_SOURCE_ALIASES: dict[str, str] = {
    "alphabet": "Alphabet_10K_FY2025.pdf",
    "google": "Alphabet_10K_FY2025.pdf",
    "facebook": "Meta_10K_FY2025.pdf",
    "meta": "Meta_10K_FY2025.pdf",
    "apple": "Apple_10K_FY2025.pdf",
    "amazon": "Amazon_10K_FY2025.pdf",
}


def resolve_sql_company(name: str) -> str:
    return SQL_COMPANY_ALIASES.get(name.strip().lower(), name.strip())


def resolve_vector_source(name: str) -> str | None:
    return VECTOR_SOURCE_ALIASES.get(name.strip().lower())
