/* @bruin
name: marts.learner_profile
type: duckdb.sql
description: Across ALL sessions - which kinds of concepts this learner over-digs, and how often they override the crew.
materialization:
  type: table
depends:
  - staging.concept_digs
columns:
  - name: category
    type: varchar
    checks:
      - name: unique
  - name: over_dig_rate
    type: double
    checks:
      - name: non_negative
@bruin */

SELECT
    category,
    count(DISTINCT session_id) AS sessions,
    count(*) AS concepts,
    avg(CASE WHEN max_depth > required_depth THEN 1.0 ELSE 0.0 END) AS over_dig_rate,
    avg(followups) AS avg_followups,
    sum(overrides) * 1.0 / count(*) AS override_rate,
    avg(time_s) AS avg_time_s
FROM staging.concept_digs
WHERE category IS NOT NULL
GROUP BY category
