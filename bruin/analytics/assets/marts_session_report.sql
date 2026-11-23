/* @bruin
name: marts.session_report
type: duckdb.sql
description: The Report screen - coverage, right-depth rate, deepest hole, quizzes and the Parking Lot size.
materialization:
  type: table
depends:
  - staging.events
  - staging.concept_digs
columns:
  - name: session_id
    type: varchar
    checks:
      - name: not_null
      - name: unique
@bruin */

WITH s AS (
    SELECT session_id, min(ts) AS started_at, max(count) FILTER (WHERE type = 'session_start') AS sections_total,
           any_value(goal) FILTER (WHERE type = 'session_start') AS goal,
           count(DISTINCT section_idx) FILTER (WHERE type = 'section_finish') AS sections_finished,
           max(duration_s) FILTER (WHERE type = 'session_end') AS duration_s,
           count(*) FILTER (WHERE type = 'quiz_graded' AND grade = 'got_it') AS quiz_got,
           count(*) FILTER (WHERE type = 'quiz_graded' AND grade = 'partly') AS quiz_partly,
           count(*) FILTER (WHERE type = 'quiz_graded' AND grade = 'missed') AS quiz_missed,
           count(*) FILTER (WHERE type = 'huddle') AS huddles
    FROM staging.events GROUP BY session_id
), d AS (
    SELECT session_id,
           count(*) AS concepts_asked,
           count(*) FILTER (WHERE max_depth <= required_depth) AS right_depth,
           count(*) FILTER (WHERE max_depth > required_depth) AS over_digs,
           count(*) FILTER (WHERE parked) AS parked,
           sum(overrides) AS overrides,
           arg_max(concept, (max_depth - required_depth) * 1000 + time_s) AS deepest_concept,
           max(max_depth - required_depth) AS deepest_overdig
    FROM staging.concept_digs GROUP BY session_id
)
SELECT s.*, coalesce(d.concepts_asked, 0) AS concepts_asked, coalesce(d.right_depth, 0) AS right_depth,
       coalesce(d.over_digs, 0) AS over_digs, coalesce(d.parked, 0) AS parked, coalesce(d.overrides, 0) AS overrides,
       d.deepest_concept, coalesce(d.deepest_overdig, 0) AS deepest_overdig
FROM s LEFT JOIN d USING (session_id)
