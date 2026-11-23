// Who is who: colors, labels and voices for the three agents and the learner.
export const AGENTS = {
  professor: { name: 'Professor', icon: '👩‍🏫', color: '#e0a83a', voiceIdx: 0, pitch: 1.05, rate: 1.0 },
  navigator: { name: 'Navigator', icon: '🧭', color: '#3f8fe0', voiceIdx: 1, pitch: 0.9, rate: 1.1 },
  examiner: { name: 'Examiner', icon: '📝', color: '#d4557e', voiceIdx: 2, pitch: 1.0, rate: 0.95 },
}
export const YOU = { name: 'You', color: '#7b6cf0' }

export const EMOJI = { worried: '😟', excited: '💡', skeptical: '🤔', agree: '✅', neutral: '' }

export const DECISION_LABEL = {
  park: 'Park it for later',
  one_more: 'One more answer, then park',
  quiz: 'Quick check first',
  continue: 'Keep digging, it\'s justified',
}

export const GOALS = [
  { id: 'gist', label: 'Get the gist' },
  { id: 'task', label: 'Do the task' },
  { id: 'exam', label: 'Exam prep' },
]

export const DEPTH_LABEL = { 1: 'What it is', 2: 'How to use it', 3: 'How it works inside' }
