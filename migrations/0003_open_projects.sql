-- Open project creation. Any active registered contributor may create projects and challenges,
-- within a per-tier daily quota; the creator becomes the project's maintainer. Global maintainers
-- moderate (locks, tiers, tombstones) but never approve. See docs/data-model.md, invariants 24-26.

ALTER TABLE quota_policies ADD COLUMN projects_per_day INTEGER NOT NULL DEFAULT 1;
UPDATE quota_policies SET projects_per_day = CASE tier
  WHEN 'new' THEN 1
  WHEN 'established' THEN 3
  WHEN 'verified' THEN 10
  WHEN 'maintainer' THEN 10
  ELSE 1 END;

ALTER TABLE quota_usage ADD COLUMN projects INTEGER NOT NULL DEFAULT 0;

INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', '2');
INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('api_version', '1.2.0');
INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('skill_version', '1.2.0');
