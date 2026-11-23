/* @bruin
name: staging.concept_digs
type: duckdb.sql
description: One row per hole the learner dug - how deep they went vs. how deep the material needed.
materialization:
  type: table
depends:
  - staging.events
columns:
  - name: max_depth
    type: integer
    checks:
      - name: accepted_values
        value: [1, 2, 3]
  - name: time_s
    type: double
    checks:
      - name: non_negative
@bruin */

SELECT
    session_id,
    concept,
    any_value(category) AS category,
    min(section_idx) AS section_idx,
    max(depth) AS max_depth,
    max(required_depth) AS required_depth,
    count(*) FILTER (WHERE type = 'question_asked') AS questions,
    count(*) FILTER (WHERE type = 'question_asked' AND is_followup) AS followups,
    bool_or(type = 'park') AS parked,
    count(*) FILTER (WHERE type = 'override') AS overrides,
    coalesce(sum(duration_s) FILTER (WHERE type = 'hole_exit'), 0) AS time_s
FROM staging.events
WHERE concept IS NOT NULL AND type IN ('question_asked', 'park', 'override', 'hole_exit')
GROUP BY session_id, concept
HAVING max(depth) IS NOT NULL
