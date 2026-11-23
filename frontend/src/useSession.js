// WebSocket connection to the backend + all session state in one reducer.
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { say } from './voices'

export const initial = {
  phase: 'start', status: '', error: '',
  session: null, startedAt: 0, cur: 0,
  holes: {}, current: null,
  answer: null, quiz: null, quizResult: null,
  log: [], huddle: null, thinking: null, busy: false,
  parking: [], blocked: null, report: null, explore: {},
}

let nextId = 1
const addLog = (s, entry) => ({ ...s, log: [{ id: nextId++, t: Date.now(), ...entry }, ...s.log].slice(0, 60) })

function reducer(s, m) {
  switch (m.type) {
    case 'status': return { ...s, phase: s.phase === 'start' ? 'loading' : s.phase, status: m.text }
    case 'error': return { ...s, error: m.text, phase: s.phase === 'loading' ? 'start' : s.phase, thinking: null }
    case 'session':
      return { ...initial, phase: 'study', session: m, startedAt: Date.now(), cur: 0,
        log: [{ id: nextId++, t: Date.now(), kind: 'system',
          text: `Bruin built your map: ${m.sections.length} sections, ${m.concepts.length} concepts` +
            (m.pipeline?.checks ? `, ${m.pipeline.checks} quality checks passed` : '') + '.' },
          ...(m.band?.enabled ? [{ id: nextId++, t: Date.now(), kind: 'system',
            text: `Crew connected to a BAND room as ${Object.values(m.band.handles).join(', ')}.` }] : [])] }
    case 'thinking': return { ...s, thinking: m.agent }
    case 'busy': return s
    case 'answer': {
      const hole = { concept: m.concept, depth: m.depth, required: m.required, limit: m.limit, category: m.category,
        section_idx: m.section_idx, parked: false, over: m.over }
      return addLog({ ...s, thinking: null, current: m.concept, holes: { ...s.holes, [m.concept]: { ...s.holes[m.concept], ...hole } },
        answer: m, quiz: null, quizResult: null, blocked: null },
        { kind: 'answer', agent: 'professor', text: `${m.concept} · depth ${m.depth}: ${m.answer}` })
    }
    case 'huddle_start': return addLog({ ...s, busy: true, huddle: { ...m, speakers: [] } },
      { kind: 'system', text: `Huddle: ${m.trigger.replace('_', ' ')}${m.concept ? ` on "${m.concept}"` : ''}` })
    case 'crew_msg':
      return addLog({ ...s, huddle: s.huddle ? { ...s.huddle, speakers: [...s.huddle.speakers, m.agent] } : s.huddle },
        { kind: 'crew', agent: m.agent, to: m.to, text: m.text, vote: m.vote, emotion: m.emotion, via: m.via })
    case 'decision': return addLog({ ...s, decision: m },
      { kind: 'decision', text: m.decision, say: m.say, reason: m.reason, agreed_by: m.agreed_by })
    case 'huddle_end': return { ...s, busy: false, huddle: null }
    case 'park': {
      const h = s.holes[m.concept] ?? { concept: m.concept }
      return { ...s, holes: { ...s.holes, [m.concept]: { ...h, parked: true } }, parking: m.parking_lot,
        current: s.current === m.concept ? null : s.current }
    }
    case 'parked_blocked': return { ...s, blocked: m.concept }
    case 'override_ok': {
      const h = s.holes[m.concept]
      return { ...s, blocked: null, parking: m.parking_lot, current: m.concept,
        holes: { ...s.holes, [m.concept]: { ...h, parked: false } } }
    }
    case 'avatar': return m.action === 'climb_out' ? { ...s, current: null } : s
    case 'moved': return { ...s, cur: m.idx, current: null, answer: null, quizResult: null }
    case 'quiz': return addLog({ ...s, thinking: null, quiz: m, quizResult: null },
      { kind: 'crew', agent: 'examiner', to: 'user', text: m.question })
    case 'quiz_result': return addLog({ ...s, thinking: null, quizResult: m },
      { kind: 'crew', agent: 'examiner', to: 'user', text: `${m.grade.replace('_', ' ')}: ${m.feedback}` })
    case 'ending': return { ...s, phase: 'ending', status: m.text, current: null }
    case 'report': return { ...s, phase: 'report', report: m }
    case 'explore_answer': return { ...s, explore: { ...s.explore, [m.concept]: m.answer } }
    case '_local_quiz_sent': return { ...s, quiz: null, thinking: 'examiner' }
    case '_reset': return { ...initial }
    default: return s
  }
}

function speak(m) {
  // answers can be long: speak only the first sentence so huddle lines never queue behind them
  if (m.type === 'answer') say('professor', (m.answer.match(/^.*?[.!?](\s|$)/)?.[0] ?? m.answer).trim())
  else if (m.type === 'crew_msg') say(m.agent, m.text)
  else if (m.type === 'decision') say(m.by_agent, m.say)
  else if (m.type === 'quiz') say('examiner', m.question)
  else if (m.type === 'quiz_result') say('examiner', m.feedback)
}

export function useSession() {
  const [state, dispatch] = useReducer(reducer, initial)
  const ws = useRef(null)
  const pending = useRef([])

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const sock = new WebSocket(`${proto}://${location.host}/ws`)
    sock.onopen = () => { pending.current.splice(0).forEach((p) => sock.send(p)) }
    sock.onmessage = (e) => { const m = JSON.parse(e.data); dispatch(m); speak(m) }
    sock.onclose = () => { ws.current = null }
    ws.current = sock
  }, [])

  useEffect(() => () => ws.current?.close(), [])

  const send = useCallback((msg) => {
    const raw = JSON.stringify(msg)
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(raw)
    else { pending.current.push(raw); if (!ws.current) connect() }
  }, [connect])

  const start = useCallback((material, goal, minutes) => {
    ws.current?.close()
    ws.current = null
    dispatch({ type: 'status', text: 'Connecting to the crew...' })
    send({ type: 'start', material, goal, minutes })
  }, [send])

  return { state, dispatch, send, start }
}
