import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS items (
  id BIGSERIAL PRIMARY KEY,
  source_id VARCHAR(64) NOT NULL,
  external_id VARCHAR(256) NOT NULL,
  url TEXT,
  url_hash CHAR(32) NOT NULL,
  title VARCHAR(512),
  title_simhash BIGINT,
  content TEXT,
  snippet TEXT,
  published_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL,
  category VARCHAR(16),
  lang VARCHAR(8),
  status VARCHAR(16) DEFAULT 'new',
  cluster_id BIGINT,
  raw_meta JSONB,
  low_confidence_time BOOLEAN DEFAULT FALSE,
  embedding vector(1536),
  UNIQUE (source_id, external_id),
  UNIQUE (url_hash)
);

CREATE INDEX IF NOT EXISTS idx_cat_pub ON items (category, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_status ON items (status);
CREATE INDEX IF NOT EXISTS idx_meta_gin ON items USING gin (raw_meta);

CREATE TABLE IF NOT EXISTS item_scores (
  item_id BIGINT PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
  rule_score FLOAT,
  model_score FLOAT,
  personal_score FLOAT,
  final_score FLOAT,
  reason VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS clusters (
  id BIGSERIAL PRIMARY KEY,
  category VARCHAR(16),
  rep_item_id BIGINT,
  member_ids JSONB,
  centroid_vec vector(1536),
  created_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_cluster_created ON clusters (created_at);

CREATE TABLE IF NOT EXISTS digests (
  id BIGSERIAL PRIMARY KEY,
  date DATE UNIQUE,
  category VARCHAR(16),
  content_md TEXT,
  item_count INT,
  cost_tokens INT,
  generated_at TIMESTAMPTZ
);
"""

def get_conn() -> psycopg.Connection:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is missing")

    return psycopg.connect(db_url,autocommit=False)

def init_db():
    conn = get_conn()
    with conn.cursor() as cursor:
        cursor.execute(SCHEMA_SQL)
    conn.commit()
    conn.close()