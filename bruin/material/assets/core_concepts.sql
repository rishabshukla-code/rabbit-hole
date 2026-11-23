/* @bruin
name: core.concepts
type: duckdb.sql
description: >
  The concepts the crew uses to judge "too deep". Written by Claude upstream, so the checks
  below make sure the crew never acts on bad AI-generated data.
materialization:
  type: table
depends:
  - ingest.concepts
  - raw.material_sections
columns:
  - name: concept_id
    type: varchar
    checks:
      - name: not_null
      - name: unique
  - name: name
    type: varchar
    checks:
      - name: not_null
  - name: category
    type: varchar
    checks:
      - name: accepted_values
        value: ["tooling", "theory", "history", "math", "other"]
  - name: required_depth
    type: integer
    checks:
      - name: accepted_values
        value: [1, 2, 3]
custom_checks:
  - name: every concept points at a real section
    query: SELECT count(*) FROM core.concepts c LEFT JOIN raw.material_sections s ON c.section_idx = s.idx WHERE s.idx IS NULL
    value: 0
  - name: one-line answers stay short
    query: SELECT count(*) FROM core.concepts WHERE length(depth1_answer) > 300
    value: 0
@bruin */

WITH src AS (
    SELECT *, row_number() OVER (PARTITION BY lower(trim(name)) ORDER BY section_idx) AS rn
    FROM read_json_auto('data/work/concepts.json')
)
SELECT
    session_id,
    concept_id,
    lower(trim(name)) AS name,
    aliases,
    -- clamp the section to a real one (guards against an off-by-one from the model)
    least(greatest(CAST(section_idx AS INTEGER), 0), (SELECT max(idx) FROM raw.material_sections)) AS section_idx,
    category,
    CAST(required_depth AS INTEGER) AS required_depth,
    used_later,
    depth1_answer,
    source
FROM src
WHERE rn = 1
