CREATE TABLE evidence_ledger (
    id TEXT PRIMARY KEY,
    claim TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('supported','disputed','unknown','retracted')),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    sources TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE cognitive_runs (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    plan TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('planned','running','verified','failed','escalated','rolled_back')),
    feedback TEXT,
    created_at TEXT NOT NULL
);
