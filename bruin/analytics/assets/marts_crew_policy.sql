/* @bruin
name: marts.crew_policy
type: duckdb.sql
description: >
  TRAINING OUTPUT. Per concept category: how much extra depth the crew allows before huddling
  (depth_tolerance) and how fast it steps in (time_factor), learned from the decision rewards
  and the learner profile. Loaded by the agents at the start of every session.
materialization:
  type: table
depends:
  - raw.decision_scores
  - marts.learner_profile
columns:
  - name: category
    type: varchar
    checks:
      - name: not_null
      - name: unique
  - name: depth_tolerance
    type: integer
    checks:
      - name: accepted_values
        value: [0, 1]
@bruin */

WITH parks AS (
    SELECT category,
           count(*) FILTER (WHERE decision = 'park') AS parks,
           avg(CASE WHEN decision = 'park' AND reward < 0 THEN 1.0 WHEN decision = 'park' THEN 0.0 END) AS park_fail_rate,
           avg(CASE WHEN decision IN ('one_more', 'continue') AND reward < 0 THEN 1.0
                    WHEN decision IN ('one_more', 'continue') THEN 0.0 END) AS leniency_fail_rate
    FROM raw.decision_scores GROUP BY category
)
SELECT
    p.category,
    p.sessions,
    p.over_dig_rate,
    p.override_rate,
    -- too strict before (parks overridden / quizzes failed after parks): allow one extra level
    CASE WHEN coalesce(k.park_fail_rate, 0) >= 0.5 OR p.override_rate >= 0.34 THEN 1 ELSE 0 END AS depth_tolerance,
    -- this learner over-digs this category, and being lenient cost them the finish: step in sooner
    CASE WHEN p.over_dig_rate >= 0.5 AND coalesce(k.leniency_fail_rate, 0) >= 0.5 THEN 0.6
         WHEN p.over_dig_rate >= 0.5 THEN 0.8 ELSE 1.0 END AS time_factor,
    CASE
        WHEN coalesce(k.park_fail_rate, 0) >= 0.5 OR p.override_rate >= 0.34
            THEN 'Crew learned to allow 1 extra level on ' || p.category || ' concepts'
        WHEN p.over_dig_rate >= 0.5
            THEN 'Crew learned you dig deep into ' || p.category || ' concepts, so it steps in sooner'
        ELSE 'Crew keeps the default rules for ' || p.category || ' concepts'
    END AS note
FROM marts.learner_profile p
LEFT JOIN parks k USING (category)
