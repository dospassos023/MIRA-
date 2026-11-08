CREATE INDEX confirmed_memory ON memory_versions(key, version DESC)
WHERE state = 'confirmed';
