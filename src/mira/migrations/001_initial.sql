CREATE TABLE profile_imports (
    profile_version TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    consent_reference TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE memory_versions (
    key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    value TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('explicit', 'hypothesis')),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    sensitive INTEGER NOT NULL CHECK (sensitive IN (0, 1)),
    evidence TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'confirmed', 'superseded')),
    contradicts_version INTEGER,
    reviewed_from INTEGER,
    valid_from TEXT,
    valid_until TEXT,
    created_at TEXT NOT NULL,
    profile_version TEXT REFERENCES profile_imports(profile_version),
    PRIMARY KEY (key, version),
    FOREIGN KEY (key, contradicts_version) REFERENCES memory_versions(key, version),
    FOREIGN KEY (key, reviewed_from) REFERENCES memory_versions(key, version)
);

CREATE TABLE observations (
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    reference TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (key, reference)
);

CREATE INDEX observation_pattern ON observations(key, value);
