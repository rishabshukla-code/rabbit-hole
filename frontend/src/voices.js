// Browser text-to-speech with one voice per agent, queued so voices never overlap.
import { AGENTS } from './crew'

let voices = []
let muted = false
const queue = []
let speaking = false
let onSpeak = () => {}

function loadVoices() {
  const all = window.speechSynthesis?.getVoices() ?? []
  const en = all.filter((v) => v.lang?.toLowerCase().startsWith('en'))
  voices = en.length >= 3 ? en : all
}
if (typeof window !== 'undefined' && window.speechSynthesis) {
  loadVoices()
  window.speechSynthesis.onvoiceschanged = loadVoices
}

export function setSpeakListener(fn) { onSpeak = fn }
export function setMuted(m) {
  muted = m
  if (m) { queue.length = 0; window.speechSynthesis?.cancel(); speaking = false; onSpeak(null) }
}
export function isMuted() { return muted }

function next() {
  if (speaking || !queue.length) return
  const { agent, text } = queue.shift()
  const synth = window.speechSynthesis
  if (!synth || muted) { onSpeak(agent, text); setTimeout(() => { onSpeak(null); next() }, 2500); return }
  const a = AGENTS[agent] ?? AGENTS.professor
  const u = new SpeechSynthesisUtterance(text.replace(/@(\w+)/g, '$1'))
  if (voices.length) u.voice = voices[a.voiceIdx % voices.length]
  u.pitch = a.pitch
  u.rate = a.rate
  speaking = true
  u.onstart = () => onSpeak(agent, text)
  const done = () => { speaking = false; onSpeak(null); setTimeout(next, 150) }
  u.onend = done
  u.onerror = done
  synth.speak(u)
}

export function say(agent, text) {
  if (!text) return
  queue.push({ agent, text })
  next()
}
