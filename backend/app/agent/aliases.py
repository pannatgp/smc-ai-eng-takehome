"""SQL company-name aliasing.

The SQL `financial_data` table uses "Google" and "Meta" as company names, while users ask
about "Google"/"Alphabet" and "Facebook"/"Meta" interchangeably. Financial lookups resolve
through this single alias table.

Vector-store availability is NOT hardcoded here — it is tracked dynamically in
`app.registry` from the filings actually ingested into Pinecone.
"""

# user-facing name (lowercased) -> canonical SQL `company` column value
SQL_COMPANY_ALIASES: dict[str, str] = {
    "alphabet": "Google",
    "google": "Google",
    "facebook": "Meta",
    "meta": "Meta",
}


def resolve_sql_company(name: str) -> str:
    return SQL_COMPANY_ALIASES.get(name.strip().lower(), name.strip())
