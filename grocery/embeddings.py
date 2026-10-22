"""all-MiniLM-L6-v2 sentence embeddings, L2-normalised so cosine = dot product."""
from functools import lru_cache

from grocery.config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


def embed(texts):
    return model().encode(list(texts), normalize_embeddings=True, batch_size=64,
                          show_progress_bar=False, convert_to_numpy=True)


def recipe_text(recipe):
    return f"{recipe['title']}. {recipe['description']}"
