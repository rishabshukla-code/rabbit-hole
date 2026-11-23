import { useEffect, useReducer, useState } from 'react'
import './App.css'
import { AGENTS, GOALS } from './crew'
import Panel, { TopBar, toggleMute } from './Panel'
import { useSession } from './useSession'
import { setSpeakListener } from './voices'
import World from './World'

function Start({ onStart, state }) {
  const [text, setText] = useState('')
  const [goal, setGoal] = useState('task')
  const [minutes, setMinutes] = useState(5)
  const [memory, setMemory] = useState(null)
  useEffect(() => { fetch('/api/memory').then((r) => r.json()).then(setMemory).catch(() => {}) }, [])
  const demo = () => fetch('/api/demo').then((r) => r.text()).then(setText)
  const loading = state.phase === 'loading'
  return (
    <div className="start">
      <h1>🕳️ Rabbit Hole</h1>
      <p className="tagline">Finish what matters. Park the rest for later.</p>
      {memory?.sessions > 0 && (
        <div className="card welcome">
          <div className="card-head">Welcome back · crew trained on {memory.sessions} session{memory.sessions > 1 ? 's' : ''}</div>
          <ul>{memory.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          <div className="muted">{Object.entries(memory.scores).map(([a, s]) => `${AGENTS[a]?.name} right ${s}% of the time`).join(' · ')}</div>
        </div>
      )}
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste what you're studying..." />
      <div className="row">
        <button onClick={demo}>Load demo chapter</button>
        <span className="spacer" />
        <span className="muted">Goal</span>
        {GOALS.map((g) => <button key={g.id} className={goal === g.id ? 'on' : ''} onClick={() => setGoal(g.id)}>{g.label}</button>)}
        <span className="muted">Time</span>
        {[5, 10, 15].map((m) => <button key={m} className={minutes === m ? 'on' : ''} onClick={() => setMinutes(m)}>{m} min</button>)}
      </div>
      {state.error && <div className="danger">{state.error}</div>}
      <button className="primary big" disabled={!text.trim() || loading} onClick={() => onStart(text, goal, minutes)}>
        {loading ? state.status || 'Building your map...' : 'Start'}
      </button>
    </div>
  )
}

function Report({ state, send, onNew }) {
  const { report: r } = state
  const rep = r.report ?? {}
  const [q, setQ] = useState({})
  return (
    <div className="report">
      <h1>Your session</h1>
      <div className="tiles">
        <div className="tile"><div className="muted">Sections covered</div><b>{rep.sections_finished ?? 0} / {rep.sections_total ?? 0}</b></div>
        <div className="tile"><div className="muted">Time used</div><b>{Math.round((rep.duration_s ?? 0) / 60 * 10) / 10} min</b></div>
        <div className="tile"><div className="muted">Stopped at the right depth</div><b>{rep.right_depth ?? 0} / {rep.concepts_asked ?? 0}</b></div>
        <div className="tile"><div className="muted">Quiz</div><b>✅ {rep.quiz_got ?? 0} · 🟡 {rep.quiz_partly ?? 0} · ❌ {rep.quiz_missed ?? 0}</b></div>
      </div>
      <div className="cols">
        <div className="card">
          <div className="card-head">Your holes</div>
          {r.holes.length === 0 && <p className="muted">No rabbit holes this time.</p>}
          {r.holes.map((h) => (
            <div key={h.concept} className={`holebar ${h.max_depth > h.required_depth ? 'over' : ''}`}>
              <span className="name">{h.parked ? '🅿 ' : ''}{h.concept}</span>
              <span className="bar">{[1, 2, 3].map((d) => <i key={d} className={d <= h.max_depth ? (d > h.required_depth ? 'over' : 'ok') : ''} />)}</span>
              <span className="muted">reached {h.max_depth}, needed {h.required_depth} · {Math.round(h.time_s)}s</span>
            </div>
          ))}
        </div>
        <div className="card">
          <div className="card-head">The crew says</div>
          {r.comments.map((c) => (
            <p key={c.agent}><span style={{ color: AGENTS[c.agent].color }}>{AGENTS[c.agent].icon} <b>{AGENTS[c.agent].name}:</b></span> {c.comment}</p>
          ))}
        </div>
      </div>
      <div className="cols">
        <div className="card">
          <div className="card-head">🅿 Parking Lot · explore freely now, no interruptions</div>
          {r.parking_lot.length === 0 && <p className="muted">Nothing parked.</p>}
          {r.parking_lot.map((p) => (
            <div key={p.concept} className="park-item">
              <b>{p.concept}</b>: "{p.question}"
              {state.explore[p.concept]
                ? <p>{state.explore[p.concept]}</p>
                : <button className="small" disabled={q[p.concept]} onClick={() => { setQ({ ...q, [p.concept]: 1 }); send({ type: 'explore', concept: p.concept, text: p.question }) }}>{q[p.concept] ? 'Digging...' : 'Explore now'}</button>}
            </div>
          ))}
        </div>
        <div className="card">
          <div className="card-head">Next time · the crew trained on this session</div>
          <ul>{r.next_time.map((n) => <li key={n}>{n}</li>)}</ul>
          <div className="muted">{Object.entries(r.scores).map(([a, s]) => `${AGENTS[a]?.name}: right ${s.accuracy}% of ${s.decisions} calls`).join(' · ')}</div>
          <div className="muted small">Bruin: {r.pipeline?.assets} assets{r.pipeline?.checks ? `, ${r.pipeline.checks} quality checks passed` : ''} ({r.pipeline?.runner}, {r.pipeline?.seconds}s)</div>
        </div>
      </div>
      <button className="primary big" onClick={onNew}>New session</button>
    </div>
  )
}

export default function App() {
  const { state, dispatch, send, start } = useSession()
  const [speaking, setSpeaking] = useState(null)
  const [, rerender] = useReducer((x) => x + 1, 0)
  const [models, setModels] = useState({})
  useEffect(() => { setSpeakListener((agent, text) => setSpeaking(agent ? { agent, text } : null)) }, [])
  useEffect(() => { fetch('/characters/manifest.json').then((r) => (r.ok ? r.json() : {})).then(setModels).catch(() => setModels({})) }, [])

  if (state.phase === 'start' || state.phase === 'loading') return <Start onStart={start} state={state} />
  if (state.phase === 'report') return <Report state={state} send={send} onNew={() => dispatch({ type: '_reset' })} />
  return (
    <div className="study">
      <TopBar state={state} onMute={() => toggleMute(rerender)} />
      <div className="study-main">
        <div className="world">
          <World state={state} send={send} speaking={speaking} models={models} />
          {state.huddle && <div className="huddle-banner">The crew is huddling…</div>}
          {state.phase === 'ending' && <div className="overlay">{state.status}</div>}
        </div>
        <Panel state={state} send={send} />
      </div>
    </div>
  )
}
