// Right-hand panel: top bar, reading card, answer/quiz card, ask box, crew log.
import { useEffect, useRef, useState } from 'react'
import { AGENTS, DECISION_LABEL, DEPTH_LABEL, GOALS } from './crew'
import { isMuted, setMuted } from './voices'

function fmt(s) {
  s = Math.max(0, Math.round(s))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function TopBar({ state, onMute }) {
  const { session, cur, holes, current, parking, startedAt } = state
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t) }, [])
  const left = session ? session.budget_s - (now - startedAt) / 1000 : 0
  const hole = current ? holes[current] : null
  const goal = GOALS.find((g) => g.id === session?.goal)?.label
  return (
    <div className="topbar">
      <span>🎯 {goal}</span>
      <span className={left < 60 ? 'warn' : ''}>⏱ {fmt(left)} left</span>
      <span>Section {cur + 1} / {session?.sections.length}</span>
      {hole ? (
        <span className={hole.over ? 'danger' : ''}>
          Depth <b>{'▓'.repeat(hole.depth)}{'░'.repeat(3 - hole.depth)}</b> {hole.depth} / needs {hole.required}
        </span>
      ) : <span className="muted">On the path</span>}
      <span>🅿 {parking.length}</span>
      <button className="ghost" onClick={onMute}>{isMuted() ? '🔇' : '🔊'}</button>
    </div>
  )
}

function Reading({ state, send, disabled }) {
  const { session, cur } = state
  const sec = session.sections[cur]
  const last = cur === session.sections.length - 1
  const [sel, setSel] = useState(null)
  const box = useRef()
  const onUp = () => {
    const t = window.getSelection()?.toString().trim()
    if (t && t.length < 60 && box.current?.contains(window.getSelection().anchorNode)) setSel(t)
    else setSel(null)
  }
  const reread = state.quizResult?.reread
  const html = reread && sec.text.includes(reread)
    ? sec.text.split(reread).flatMap((p, i, a) => (i < a.length - 1 ? [p, <mark key={i}>{reread}</mark>] : [p]))
    : sec.text
  return (
    <div className="card reading">
      <div className="card-head">Reading · {cur + 1}. {sec.title} {sec.is_key ? <span className="chip">key</span> : null}</div>
      <div className="reading-text" ref={box} onMouseUp={onUp}>{html}</div>
      <div className="row">
        {sel && (
          <button className="small" disabled={disabled} onClick={() => { send({ type: 'ask', text: `What is ${sel}?` }); setSel(null) }}>
            Ask about "{sel}"
          </button>
        )}
        <span className="spacer" />
        {last
          ? <button className="primary" disabled={disabled} onClick={() => send({ type: 'finish' })}>Finish ✓</button>
          : <button className="primary" disabled={disabled} onClick={() => send({ type: 'goto', idx: cur + 1 })}>Next →</button>}
      </div>
    </div>
  )
}

function AnswerCard({ state, send, disabled }) {
  const { answer, quiz, quizResult, thinking, blocked, parking } = state
  const [reply, setReply] = useState('')
  if (thinking) {
    const a = AGENTS[thinking]
    return <div className="card answer"><div className="card-head">{a.icon} {a.name}</div><div className="thinking">thinking<span>.</span><span>.</span><span>.</span></div></div>
  }
  if (quiz) {
    return (
      <div className="card answer quiz">
        <div className="card-head">📝 Examiner · quick check</div>
        <p>{quiz.question}</p>
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (!reply.trim()) return; send({ type: 'quiz_answer', text: reply }); setReply('') }}>
          <input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Answer in one sentence" autoFocus />
          <button className="primary" type="submit">Answer</button>
        </form>
      </div>
    )
  }
  if (quizResult) {
    const g = { got_it: '✅ Got it', partly: '🟡 Partly', missed: '❌ Missed' }[quizResult.grade]
    return <div className="card answer"><div className="card-head">📝 Examiner · {g}</div><p>{quizResult.feedback}</p>
      {quizResult.reread ? <p className="muted">Re-read the highlighted bit.</p> : null}</div>
  }
  if (blocked) {
    return (
      <div className="card answer">
        <div className="card-head">🧭 Navigator · parked</div>
        <p>"{blocked}" is in your Parking Lot for after the session.</p>
        <button className="small" disabled={disabled} onClick={() => send({ type: 'override', concept: blocked })}>I really need this</button>
      </div>
    )
  }
  if (answer) {
    const lastPark = parking.find((p) => p.concept === answer.concept)
    return (
      <div className="card answer">
        <div className="card-head">👩‍🏫 Professor · {answer.concept} · depth {answer.depth} ({DEPTH_LABEL[answer.depth]})</div>
        <p>{answer.answer}</p>
        <p className={`hint ${answer.over ? 'danger' : ''}`}>{answer.depth_hint}</p>
        {lastPark && <button className="small" disabled={disabled} onClick={() => send({ type: 'override', concept: answer.concept })}>I really need this</button>}
      </div>
    )
  }
  return <div className="card answer empty">Something unfamiliar? Ask the crew instead of opening a new tab.</div>
}

function AskBox({ send, disabled, busy }) {
  const [text, setText] = useState('')
  const [listening, setListening] = useState(false)
  const rec = useRef(null)
  const submit = (t) => { if (!t.trim() || disabled) return; send({ type: 'ask', text: t.trim() }); setText('') }
  const mic = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return alert('Voice input needs Chrome.')
    if (listening) { rec.current?.stop(); return }
    const r = new SR()
    r.lang = 'en-US'
    r.interimResults = false
    r.onresult = (e) => submit(e.results[0][0].transcript)
    r.onend = () => setListening(false)
    rec.current = r
    setListening(true)
    r.start()
  }
  return (
    <form className="askbox" onSubmit={(e) => { e.preventDefault(); submit(text) }}>
      <input value={text} onChange={(e) => setText(e.target.value)} disabled={disabled}
        placeholder={busy ? 'The crew is huddling...' : 'Ask about anything unfamiliar...'} />
      <button type="button" className={`ghost ${listening ? 'rec' : ''}`} onClick={mic} disabled={disabled} title="Ask by voice">🎤</button>
      <button type="submit" className="primary" disabled={disabled || !text.trim()}>Ask</button>
    </form>
  )
}

function CrewLog({ log }) {
  return (
    <div className="card log">
      <div className="card-head">Crew log</div>
      <div className="log-list">
        {log.map((l) => {
          if (l.kind === 'decision') {
            return (
              <div key={l.id} className="log-item decision">
                ✅ <b>Decision: {DECISION_LABEL[l.text] ?? l.text}</b>
                <div className="muted">Why: {l.reason} · agreed by {l.agreed_by.map((a) => AGENTS[a]?.name).join(' + ')}</div>
              </div>
            )
          }
          if (l.kind === 'system') return <div key={l.id} className="log-item system">{l.text}</div>
          const a = AGENTS[l.agent]
          return (
            <div key={l.id} className="log-item">
              <span style={{ color: a?.color }}>{a?.icon} <b>{a?.name}</b></span>
              {l.to && l.to !== 'user' ? <span className="muted"> → {l.to === 'all' ? 'crew' : AGENTS[l.to]?.name}</span> : null}: {l.text}
              {l.vote ? <span className="chip">votes {l.vote.replace('_', ' ')}</span> : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function Panel({ state, send }) {
  const disabled = state.busy || !!state.thinking || state.phase !== 'study'
  return (
    <div className="panel">
      <Reading state={state} send={send} disabled={disabled} />
      <AnswerCard state={state} send={send} disabled={disabled} />
      <AskBox send={send} disabled={disabled || !!state.quiz} busy={state.busy} />
      <CrewLog log={state.log} />
    </div>
  )
}

export function toggleMute(rerender) { setMuted(!isMuted()); rerender() }
