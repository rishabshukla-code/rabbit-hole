/* @bruin
name: staging.events
type: duckdb.sql
description: Every event the app logged (questions, digs, huddles, parks, quizzes), typed and validated.
materialization:
  type: table
columns:
  - name: session_id
    type: varchar
    checks:
      - name: not_null
  - name: type
    type: varchar
    checks:
      - name: not_null
      - name: accepted_values
        value: ["session_start", "section_enter", "section_finish", "question_asked", "huddle", "override", "park", "hole_exit", "quiz_asked", "quiz_graded", "session_end"]
  - name: duration_s
    type: double
    checks:
      - name: non_negative
@bruin */

SELECT *
FROM read_json('data/events.jsonl', format = 'newline_delimited', columns = {
    session_id: 'VARCHAR', ts: 'DOUBLE', type: 'VARCHAR', section_idx: 'INTEGER', concept: 'VARCHAR',
    category: 'VARCHAR', depth: 'INTEGER', required_depth: 'INTEGER', is_followup: 'BOOLEAN',
    "trigger": 'VARCHAR', decision: 'VARCHAR', agreed_by: 'VARCHAR', grade: 'VARCHAR',
    duration_s: 'DOUBLE', count: 'INTEGER', text: 'VARCHAR', agent: 'VARCHAR', goal: 'VARCHAR'
})
