/* @bruin
name: raw.material_sections
type: duckdb.sql
description: Sections of the current study material, loaded from the ingest step.
materialization:
  type: table
depends:
  - ingest.sections
columns:
  - name: idx
    type: integer
    checks:
      - name: not_null
      - name: unique
      - name: non_negative
  - name: title
    type: varchar
    checks:
      - name: not_null
  - name: word_count
    type: integer
    checks:
      - name: positive
@bruin */

SELECT session_id, CAST(idx AS INTEGER) AS idx, title, text, CAST(word_count AS INTEGER) AS word_count, is_key
FROM read_json_auto('data/work/sections.json')
ORDER BY idx
