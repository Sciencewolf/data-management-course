"""Connection settings for the five stores; defaults match docker-compose.yml."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TESTS_DIR = ROOT / "tests" / "cases"
RESULTS_DIR = ROOT / "results"

load_dotenv(ROOT / ".env")

PG_DSN = (f"host={os.getenv('PG_HOST', 'localhost')} port={os.getenv('PG_PORT', '5432')} "
          f"dbname={os.getenv('PG_DB', 'grocery')} user={os.getenv('PG_USER', 'grocery')} "
          f"password={os.getenv('PG_PASSWORD', 'grocery_dev')}")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "grocery")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
NEO4J_AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "grocery_dev"))
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
QDRANT_COLLECTION = "recipes"
CART_TTL_SECONDS = int(os.getenv("CART_TTL_SECONDS", "1800"))
