/* @bruin
name: marts.agent_scores
type: duckdb.sql
description: How often each agent's calls turned out right, plus its best past decisions (used as few-shot examples).
materialization:
  type: table
depends:
  - raw.decision_scores
columns:
  - name: agent
    type: varchar
    checks:
      - name: not_null
      - name: unique
@bruin */

WITH ranked AS (
    SELECT *, row_number() OVER (PARTITION BY agent ORDER BY reward DESC, ts DESC) AS rn
    FROM raw.decision_scores
)
SELECT
    agent,
    count(*) AS decisions,
    avg(reward) AS avg_reward,
    avg(CASE WHEN reward > 0 THEN 1.0 ELSE 0.0 END) AS accuracy,
    string_agg(CASE WHEN rn <= 3 AND reward > 0
                    THEN concept || ' (' || coalesce(category, '?') || '): ' || decision || ' because ' || reason END, ' || ') AS good_examples,
    string_agg(CASE WHEN reward < 0
                    THEN concept || ' (' || coalesce(category, '?') || '): ' || decision || ' backfired' END, ' || ') AS bad_examples
FROM ranked
GROUP BY agent
