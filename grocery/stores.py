"""One place that opens a connection to each store."""
import psycopg
import redis
from neo4j import GraphDatabase
from pgvector.psycopg import register_vector
from pymongo import MongoClient
from qdrant_client import QdrantClient

from grocery import config


def postgres(vector=True):
    conn = psycopg.connect(config.PG_DSN, autocommit=True)
    if vector:
        register_vector(conn)
    return conn


def mongo():
    return MongoClient(config.MONGO_URL)[config.MONGO_DB]


def redis_client():
    return redis.Redis.from_url(config.REDIS_URL, decode_responses=True)


def neo4j():
    return GraphDatabase.driver(config.NEO4J_URL, auth=config.NEO4J_AUTH)


def qdrant():
    return QdrantClient(url=config.QDRANT_URL)
