from functools import lru_cache

from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone

from app.config import settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 512

_embeddings = OpenAIEmbeddings(
    model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS, api_key=settings.openai_api_key
)


@lru_cache(maxsize=1)
def get_index():
    pc = Pinecone(api_key=settings.pinecone_api_key, host=settings.pinecone_host)
    index_host = pc.describe_index(settings.pinecone_index_name).host
    return pc.Index(host=index_host)


def embed_query(text: str) -> list[float]:
    return _embeddings.embed_query(text)
