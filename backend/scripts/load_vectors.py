"""Seed the local Pinecone index from the provided fixture.

pinecone-local has no persistence, so this script must be re-run after every
`docker compose up`. It upserts data/pinecone_vectors.jsonl.gz as-is (Option A from the
take-home brief) rather than re-embedding the PDFs, to preserve OpenAI budget.

One deliberate transform: the fixture's `source` metadata is an absolute path from the
machine that generated it (e.g. "/Users/.../10k_filings/Alphabet_10K_FY2025.pdf"). We
rewrite it to just the basename ("Alphabet_10K_FY2025.pdf") on upsert so the backend can
filter vector search by an exact-match metadata filter instead of a path prefix it can't
know in advance.
"""

import gzip
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

# imported after load_dotenv so app.config picks up the environment
from app.registry import register_sources  # noqa: E402

FIXTURE_PATH = REPO_ROOT / "data" / "pinecone_vectors.jsonl.gz"
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "pclocal")
PINECONE_HOST = os.environ.get("PINECONE_HOST", "http://localhost:5080")
INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "sec-filings")
DIMENSION = 512
BATCH_SIZE = 100


def ensure_index(pc: Pinecone) -> str:
    if not pc.has_index(INDEX_NAME):
        print(f"Creating index '{INDEX_NAME}' (dim={DIMENSION}, metric=cosine)...")
        pc.create_index(
            name=INDEX_NAME,
            vector_type="dense",
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            deletion_protection="disabled",
        )
    host = pc.describe_index(INDEX_NAME).host
    # pinecone-local advertises the index host as https:// but serves plaintext http.
    if PINECONE_HOST.startswith("http://") and host.startswith("https://"):
        host = "http://" + host[len("https://") :]
    return host


def load_records():
    with gzip.open(FIXTURE_PATH, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            metadata = record.get("metadata", {})
            if "source" in metadata:
                metadata["source"] = Path(metadata["source"]).name
            yield {
                "id": record["id"],
                "values": record["values"],
                "metadata": metadata,
            }, record.get("namespace", "__default__")


def main() -> None:
    pc = Pinecone(api_key=PINECONE_API_KEY, host=PINECONE_HOST)
    index_host = ensure_index(pc)
    index = pc.Index(host=index_host)

    batch: list[dict] = []
    namespace = "__default__"
    total = 0
    sources: set[str] = set()

    for vector, ns in load_records():
        namespace = ns
        source = vector["metadata"].get("source")
        if source:
            sources.add(source)
        batch.append(vector)
        if len(batch) >= BATCH_SIZE:
            index.upsert(vectors=batch, namespace=namespace)
            total += len(batch)
            print(f"Upserted {total} vectors...")
            batch = []

    if batch:
        index.upsert(vectors=batch, namespace=namespace)
        total += len(batch)

    # Register what we ingested so the app's router knows which companies are searchable,
    # without hardcoding a company list. This is the ingest path a future upload endpoint
    # would reuse: upsert to Pinecone + register the source, together.
    register_sources(sources)

    stats = index.describe_index_stats()
    print(f"Done. Upserted {total} vectors this run. Registered sources: {sorted(sources)}")
    print(f"Index stats: {stats}")


if __name__ == "__main__":
    main()
