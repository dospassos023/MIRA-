CREATE TABLE executive_tasks (
    id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    request TEXT NOT NULL,
    plan TEXT NOT NULL,
    digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'queued','running','awaiting_approval','completed','failed','rolled_back'
    )),
    requires_approval INTEGER NOT NULL,
    approved_until TEXT,
    started_at TEXT,
    deadline_at TEXT,
    created_at TEXT NOT NULL,
    summary TEXT NOT NULL,
    escalation INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE executive_events (
    sequence INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES executive_tasks(id),
    kind TEXT NOT NULL,
    step INTEGER,
    detail TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX executive_events_task ON executive_events(task_id, sequence);

CREATE UNIQUE INDEX executive_single_worker ON executive_tasks(state) WHERE state = 'running';
