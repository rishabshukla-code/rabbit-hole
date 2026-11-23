/* @bruin
name: raw.decision_scores
type: duckdb.sql
description: Rewards from the Python scoring step, typed and checked.
materialization:
  type: table
depends:
  - ingest.decision_scores
columns:
  - name: agent
    type: varchar
    checks:
      - name: accepted_values
        value: ["professor", "navigator", "examiner"]
  - name: reward
    type: integer
    checks:
      - name: accepted_values
        value: [-1, 0, 1]
@bruin */

SELECT *
FROM read_json('data/work/decision_scores.json', format = 'array', columns = {
    session_id: 'VARCHAR', ts: 'DOUBLE', agent: 'VARCHAR', "trigger": 'VARCHAR', decision: 'VARCHAR',
    concept: 'VARCHAR', category: 'VARCHAR', reason: 'VARCHAR', overridden: 'BOOLEAN',
    quiz_grade: 'VARCHAR', coverage: 'DOUBLE', reward: 'INTEGER'
})
