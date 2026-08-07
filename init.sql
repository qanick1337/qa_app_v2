CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS kb_chunks;

CREATE TABLE kb_chunks (
    id          SERIAL PRIMARY KEY,
    article_id  TEXT,
    title       TEXT,
    url         TEXT,
    source      TEXT,
    chunk_index INTEGER,
    content     TEXT,
    embedding   vector(1024),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ON kb_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);


CREATE TABLE topic_centroids (
    section   TEXT PRIMARY KEY,
    centroid  vector(1024)
);


CREATE TABLE qa_evaluations (
    id                      SERIAL PRIMARY KEY,
    ticket_id               BIGINT NOT NULL UNIQUE,

    -- === Результат оцінки ===
    result                  VARCHAR(20) NOT NULL
                             CHECK (result IN ('correct', 'partially_correct', 'incorrect')),
    content_quality_score   SMALLINT NOT NULL CHECK (content_quality_score BETWEEN 1 AND 5),
    communication_score     SMALLINT NOT NULL CHECK (communication_score BETWEEN 1 AND 5),
    overall_score           NUMERIC(2,1) NOT NULL CHECK (overall_score BETWEEN 1.0 AND 5.0),

    -- === KB джерело (може бути відсутнім) ===
    kb_source_title          TEXT,
    kb_source_url            TEXT,

    -- === Деталізація (масиви рядків, рідко фільтруються — JSONB) ===
    correct_points           JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_points           JSONB NOT NULL DEFAULT '[]'::jsonb,
    incorrect_points         JSONB NOT NULL DEFAULT '[]'::jsonb,
    communication_issues     JSONB NOT NULL DEFAULT '[]'::jsonb,

    qa_comment               TEXT,
    recommendation           TEXT,

    -- === Тема (поки текстом, без FK) ===
    raw_issue_topic           TEXT,
    canonical_topic_id        VARCHAR(64),   -- напр. "users"
    canonical_topic            VARCHAR(128), -- напр. "USERS"
    topic_confidence           VARCHAR(10)
                                CHECK (topic_confidence IN ('High', 'Medium', 'Low')),

    -- === SLA метрики (з preprocessing_info) ===
    first_response_time_sec    INT,
    handling_time_sec          INT,
    longest_agent_gap_sec      INT,

    -- === Метадані запуску ===
    llm_model                  VARCHAR(64),   -- напр. "gpt-5-mini", для відстеження версій
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_qa_evaluations_canonical_topic_id ON qa_evaluations(canonical_topic_id);
CREATE INDEX idx_qa_evaluations_created_at ON qa_evaluations(created_at);

-- Автооновлення updated_at при UPSERT
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_qa_evaluations_updated_at
BEFORE UPDATE ON qa_evaluations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE agent_accounts (
    id          SERIAL PRIMARY KEY,
    agent_id  TEXT,
    zendesk_title   TEXT,
);

