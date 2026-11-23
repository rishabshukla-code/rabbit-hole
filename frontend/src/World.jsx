// The 3D study world: a path of stones (one per section), holes you dig with your questions,
// your avatar and the three crew characters.
import { Html, OrbitControls, useAnimations, useGLTF } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Component, Suspense, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js'
import { AGENTS, EMOJI, YOU } from './crew'

const stonePos = (i) => new THREE.Vector3(i * 4.4, 0, Math.sin(i * 0.9) * 2.4)

function holePos(hole, holesInSection) {
  const k = holesInSection.indexOf(hole.concept)
  const s = stonePos(hole.section_idx)
  const side = k % 2 === 0 ? 1 : -1
  return new THREE.Vector3(s.x + (Math.floor(k / 2) * 1.6 - 0.4), 0, s.z + side * 2.8)
}

// ------------------------------------------------------------------ ground, stones, holes
function Ground() {
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position={[9, -0.02, 0]} receiveShadow>
        <circleGeometry args={[30, 64]} />
        <meshStandardMaterial color="#86b86a" />
      </mesh>
      <mesh position={[9, -1.6, 0]}>
        <cylinderGeometry args={[30, 24, 3.1, 64]} />
        <meshStandardMaterial color="#7a5a3c" />
      </mesh>
    </group>
  )
}

function Stone({ i, title, current, done, onClick }) {
  const p = stonePos(i)
  const ref = useRef()
  useFrame(({ clock }) => {
    if (ref.current) ref.current.position.y = current ? 0.12 + Math.sin(clock.elapsedTime * 2) * 0.04 : 0.12
  })
  return (
    <group position={p}>
      <mesh ref={ref} castShadow receiveShadow onClick={(e) => { e.stopPropagation(); onClick(i) }}
        onPointerOver={() => (document.body.style.cursor = 'pointer')} onPointerOut={() => (document.body.style.cursor = '')}>
        <cylinderGeometry args={[1.15, 1.3, 0.28, 32]} />
        <meshStandardMaterial color={current ? '#2fd1a0' : done ? '#3c8f78' : '#5fb8a2'}
          emissive={current ? '#1d9e75' : '#000'} emissiveIntensity={current ? 0.45 : 0} />
      </mesh>
      <Html position={[0, 0.9, 0]} center distanceFactor={11} zIndexRange={[10, 0]}>
        <div className={`stone-label ${current ? 'is-current' : ''}`}>{i + 1}. {title}</div>
      </Html>
    </group>
  )
}

function PathLine({ n }) {
  const geo = useMemo(() => {
    const pts = Array.from({ length: n }, (_, i) => stonePos(i).setY(0.01))
    const curve = new THREE.CatmullRomCurve3(pts)
    return new THREE.TubeGeometry(curve, 64, 0.18, 6, false)
  }, [n])
  return n > 1 ? <mesh geometry={geo}><meshStandardMaterial color="#d8c79a" /></mesh> : null
}

function Hole({ hole, pos, active }) {
  const r = 0.55 + 0.2 * (hole.depth || 1)
  const rim = useRef()
  useFrame(({ clock }) => {
    if (rim.current) rim.current.material.emissiveIntensity = hole.over && !hole.parked ? 0.6 + Math.sin(clock.elapsedTime * 5) * 0.4 : 0.15
  })
  return (
    <group position={pos}>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.015, 0]}>
        <circleGeometry args={[r, 40]} />
        <meshStandardMaterial color="#120d0a" />
      </mesh>
      <mesh ref={rim} rotation-x={-Math.PI / 2} position={[0, 0.03, 0]}>
        <torusGeometry args={[r, 0.09, 8, 48]} />
        <meshStandardMaterial color={hole.over && !hole.parked ? '#ff6b3d' : '#b9874a'}
          emissive={hole.over && !hole.parked ? '#ff4a1c' : '#5a3a10'} />
      </mesh>
      {hole.parked && (
        <group position={[r * 0.8, 0, -r * 0.4]}>
          <mesh position={[0, 0.7, 0]}><cylinderGeometry args={[0.04, 0.04, 1.4, 8]} /><meshStandardMaterial color="#555" /></mesh>
          <mesh position={[0.28, 1.2, 0]}><boxGeometry args={[0.55, 0.36, 0.03]} /><meshStandardMaterial color="#3f8fe0" /></mesh>
        </group>
      )}
      <Html position={[0, 0.35, r + 0.3]} center distanceFactor={11} zIndexRange={[10, 0]}>
        <div className={`hole-label ${hole.over && !hole.parked ? 'is-over' : ''} ${active ? 'is-active' : ''}`}>
          {hole.parked ? '🅿 ' : ''}{hole.concept} · depth {hole.depth}{hole.required ? ` / needs ${hole.required}` : ''}
        </div>
      </Html>
    </group>
  )
}

// ------------------------------------------------------------------ characters
class Fallback extends Component {
  constructor(p) { super(p); this.state = { failed: false } }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

function ToyFigure({ color, walking }) {
  const legs = useRef()
  useFrame(({ clock }) => {
    if (legs.current) legs.current.rotation.x = walking.current ? Math.sin(clock.elapsedTime * 12) * 0.35 : 0
  })
  return (
    <group>
      <mesh position={[0, 0.75, 0]} castShadow>
        <capsuleGeometry args={[0.32, 0.55, 6, 16]} />
        <meshStandardMaterial color={color} />
      </mesh>
      <mesh position={[0, 1.5, 0]} castShadow>
        <sphereGeometry args={[0.3, 24, 16]} />
        <meshStandardMaterial color="#f3d2b3" />
      </mesh>
      {[-0.1, 0.1].map((x) => (
        <mesh key={x} position={[x, 1.55, 0.26]}><sphereGeometry args={[0.045, 10, 8]} /><meshStandardMaterial color="#1b1530" /></mesh>
      ))}
      <group ref={legs} position={[0, 0.35, 0]}>
        <mesh position={[0, -0.2, 0.12]}><boxGeometry args={[0.22, 0.22, 0.12]} /><meshStandardMaterial color="#333" /></mesh>
      </group>
    </group>
  )
}

function ModelFigure({ kind, walking }) {
  const { scene, animations } = useGLTF(`/characters/${kind}.glb`)
  const obj = useMemo(() => cloneSkinned(scene), [scene])
  const { actions, names } = useAnimations(animations, obj)
  const playing = useRef(null)
  useFrame(() => {
    const want = walking.current ? /walk|run/i : /idle/i
    const name = names.find((n) => want.test(n)) ?? names[0]
    if (name && playing.current !== name) {
      actions[playing.current]?.fadeOut(0.2)
      actions[name]?.reset().fadeIn(0.2).play()
      playing.current = name
    }
  })
  return <primitive object={obj} scale={0.9} />
}

function Character({ kind, label, color, target, lookAt, speaking, bubble, emotion, models, avatarRef }) {
  const g = useRef()
  const walking = useRef(false)
  const yaw = useRef(0)
  const placed = useRef(false)
  useFrame(({ clock }, dt) => {
    const o = g.current
    if (!o) return
    if (!placed.current) { o.position.copy(target); placed.current = true }
    const dist = o.position.distanceTo(target)
    walking.current = dist > 0.08
    o.position.lerp(target, Math.min(1, dt * 2.6))
    const t = clock.elapsedTime
    const bob = Math.sin(t * 2 + label.length) * 0.03
    const bounce = speaking ? Math.abs(Math.sin(t * 9)) * 0.12 : 0
    o.children[0].position.y = bob + bounce
    const look = walking.current ? target : lookAt
    const want = Math.atan2(look.x - o.position.x, look.z - o.position.z)
    let d = want - yaw.current
    d = Math.atan2(Math.sin(d), Math.cos(d))
    yaw.current += d * Math.min(1, dt * 5)
    o.rotation.y = yaw.current
    if (avatarRef) avatarRef.current.copy(o.position)
  })
  const figure = <ToyFigure color={color} walking={walking} />
  return (
    <group ref={g}>
      <group>
        {models[kind] ? (
          <Fallback fallback={figure}><Suspense fallback={figure}><ModelFigure kind={kind} walking={walking} /></Suspense></Fallback>
        ) : figure}
      </group>
      <Html position={[0, 2.25, 0]} center distanceFactor={10} zIndexRange={[20, 10]}>
        <div className="char-tag" style={{ borderColor: color }}>
          {emotion && EMOJI[emotion] ? <span className="emo">{EMOJI[emotion]}</span> : null}{label}
        </div>
      </Html>
      {bubble && (
        <Html position={[0, 3.0, 0]} center distanceFactor={9} zIndexRange={[30, 20]}>
          <div className={`bubble ${speaking ? 'is-speaking' : ''}`} style={{ borderColor: color }}>{bubble}</div>
        </Html>
      )}
    </group>
  )
}

// ------------------------------------------------------------------ camera + light
function CameraRig({ avatarRef }) {
  const { camera, controls } = useThree()
  const focus = useRef(new THREE.Vector3())
  useFrame((_, dt) => {
    if (!controls) return
    const before = focus.current.clone()
    focus.current.lerp(avatarRef.current, Math.min(1, dt * 2))
    const delta = focus.current.clone().sub(before)
    controls.target.add(delta)
    camera.position.add(delta)
  })
  return null
}

function Lights({ depth }) {
  const amb = useRef(), sun = useRef()
  const { scene } = useThree()
  useFrame((_, dt) => {
    const k = Math.min(1, dt * 2)
    const dark = Math.min(depth, 3) / 3
    if (amb.current) amb.current.intensity += ((0.9 - 0.6 * dark) - amb.current.intensity) * k
    if (sun.current) sun.current.intensity += ((1.6 - 1.1 * dark) - sun.current.intensity) * k
    const bg = new THREE.Color('#bfe3f5').lerp(new THREE.Color('#1a1630'), dark * 0.85)
    scene.background = scene.background ? scene.background.lerp(bg, k) : bg
  })
  return (
    <>
      <ambientLight ref={amb} intensity={0.9} />
      <directionalLight ref={sun} position={[8, 14, 6]} intensity={1.6} castShadow shadow-mapSize={[1024, 1024]}
        shadow-camera-left={-25} shadow-camera-right={25} shadow-camera-top={25} shadow-camera-bottom={-25} />
    </>
  )
}

// ------------------------------------------------------------------ scene
const CREW_IDLE = { professor: [-1.5, 0, 1.3], navigator: [1.5, 0, 1.1], examiner: [0.2, 0, 2.3] }
const CREW_HUDDLE = { professor: 200, navigator: 270, examiner: 340 }

export default function World({ state, send, speaking, models }) {
  const { session, cur, holes, current, huddle } = state
  const avatarRef = useRef(new THREE.Vector3())
  const sections = session?.sections ?? []
  const bySection = useMemo(() => {
    const m = {}
    Object.values(holes).forEach((h) => { (m[h.section_idx] ??= []).push(h.concept) })
    return m
  }, [holes])

  const hole = current ? holes[current] : null
  const center = hole ? holePos(hole, bySection[hole.section_idx] ?? []) : stonePos(cur)
  const youTarget = center.clone().setY(hole ? -0.42 * hole.depth : 0.26)
  const crewTarget = (a) => {
    if (huddle || hole) {
      const ang = (CREW_HUDDLE[a] * Math.PI) / 180
      const r = hole ? 0.55 + 0.2 * hole.depth + 0.9 : 1.9
      return new THREE.Vector3(center.x + Math.cos(ang) * r, 0.02, center.z - Math.sin(ang) * r)
    }
    const o = CREW_IDLE[a]
    return new THREE.Vector3(center.x + o[0], 0.02, center.z + o[2])
  }
  const lastEmotion = (a) => state.log.find((l) => l.kind === 'crew' && l.agent === a && Date.now() - l.t < 20000)?.emotion
  const speakerPos = speaking?.agent ? crewTarget(speaking.agent) : youTarget

  return (
    <Canvas shadows camera={{ position: [-7, 9, 14], fov: 50 }} dpr={[1, 2]}>
      <Lights depth={hole && !hole.parked ? hole.depth : 0} />
      <OrbitControls makeDefault enablePan={false} minDistance={6} maxDistance={26} maxPolarAngle={Math.PI / 2.15} />
      <CameraRig avatarRef={avatarRef} />
      <Ground />
      <PathLine n={sections.length} />
      {sections.map((s) => (
        <Stone key={s.idx} i={s.idx} title={s.title} current={s.idx === cur} done={s.idx < cur}
          onClick={(i) => !state.busy && send({ type: 'goto', idx: i })} />
      ))}
      {Object.values(holes).map((h) => (
        <Hole key={h.concept} hole={h} pos={holePos(h, bySection[h.section_idx] ?? [])} active={h.concept === current} />
      ))}
      <Character kind="you" label={YOU.name} color={YOU.color} target={youTarget} lookAt={speakerPos}
        models={models} avatarRef={avatarRef} />
      {Object.entries(AGENTS).map(([a, info]) => {
        const talking = speaking?.agent === a
        return (
          <Character key={a} kind={a} label={info.name} color={info.color} target={crewTarget(a)}
            lookAt={speaking?.agent && !talking ? crewTarget(speaking.agent) : youTarget}
            speaking={talking} bubble={talking ? speaking.text : null} emotion={lastEmotion(a)} models={models} />
        )
      })}
    </Canvas>
  )
}
