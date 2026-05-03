CREATE TABLE IF NOT EXISTS transcripts (
    id SERIAL PRIMARY KEY,
    text TEXT,
    language VARCHAR(20),
    confidence FLOAT,
    reviewed BOOLEAN DEFAULT FALSE,
    human_reviewed BOOLEAN DEFAULT FALSE,
    human_feedback TEXT,
    reviewer VARCHAR(100)
);
