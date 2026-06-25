import { Suspense, useRef, useMemo, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { useGLTF, OrbitControls, Environment, Html } from '@react-three/drei'
import * as THREE from 'three'

// Zone definitions in the shoe's local Z-axis space (heel = negative Z, toe = positive Z)
// Derived from Footbed_R_internal accessor bounds: Z [-0.133, +0.147]
const ZONES = [
  { id: 'heel',     label: 'Heel',     zMin: -0.133, zMax: -0.048, xHalf: 0.042, y: 0.032, h: 0.012 },
  { id: 'arch',     label: 'Arch',     zMin: -0.048, zMax:  0.022, xHalf: 0.038, y: 0.034, h: 0.010 },
  { id: 'forefoot', label: 'Forefoot', zMin:  0.022, zMax:  0.094, xHalf: 0.044, y: 0.033, h: 0.011 },
  { id: 'toe',      label: 'Toe',      zMin:  0.094, zMax:  0.147, xHalf: 0.036, y: 0.031, h: 0.009 },
]

function zoneColor(spec, zoneId) {
  const arch    = spec?.arch_support  || {}
  const midsole = spec?.midsole       || {}
  const last    = spec?.last_spec     || {}
  switch (zoneId) {
    case 'heel':
      return midsole.cushioning_priority === 'heel' ? '#ef4444' : '#f97316'
    case 'arch':
      return arch.medial_post ? '#7c3aed' : '#8b5cf6'
    case 'forefoot':
      return midsole.cushioning_priority === 'lateral' ? '#2563eb' : '#3b82f6'
    case 'toe':
      return (last.toe_box === 'wide' || last.toe_box === 'extra_wide') ? '#0d9488' : '#14b8a6'
    default:
      return '#ffffff'
  }
}

function zoneLabel(spec, zoneId) {
  const arch    = spec?.arch_support  || {}
  const midsole = spec?.midsole       || {}
  const last    = spec?.last_spec     || {}
  switch (zoneId) {
    case 'heel':
      return midsole.cushioning_priority === 'heel'
        ? `Extra cushion · ${midsole.heel_drop_mm ?? 8}mm drop`
        : `Standard · ${midsole.heel_drop_mm ?? 8}mm drop`
    case 'arch':
      return arch.medial_post
        ? `Medial post · ${arch.height_mm ?? 18}mm`
        : `No post · ${arch.height_mm ?? 18}mm arch`
    case 'forefoot':
      return midsole.cushioning_priority === 'lateral'
        ? `Lateral priority · Shore ${midsole.lateral_shore_c ?? 45}C`
        : `Balanced · Shore ${midsole.lateral_shore_c ?? 45}C`
    case 'toe':
      return last.toe_box
        ? `${last.toe_box.replace('_', ' ')} toe box`
        : 'Standard toe box'
    default:
      return ''
  }
}

// Single foam cushion pad mesh
function CushionPad({ zone, color, hovered, onPointerOver, onPointerOut }) {
  const meshRef = useRef()
  const zCenter = (zone.zMin + zone.zMax) / 2
  const zLen    = zone.zMax - zone.zMin

  useFrame(({ clock }) => {
    if (meshRef.current && hovered) {
      meshRef.current.position.y = zone.y + Math.sin(clock.elapsedTime * 3) * 0.002
    } else if (meshRef.current) {
      meshRef.current.position.y = zone.y
    }
  })

  return (
    <mesh
      ref={meshRef}
      position={[0, zone.y, zCenter]}
      onPointerOver={onPointerOver}
      onPointerOut={onPointerOut}
    >
      <boxGeometry args={[zone.xHalf * 2, zone.h, zLen * 0.92]} />
      <meshStandardMaterial
        color={color}
        transparent
        opacity={hovered ? 0.82 : 0.62}
        roughness={0.6}
        metalness={0.0}
        emissive={color}
        emissiveIntensity={hovered ? 0.35 : 0.15}
      />
    </mesh>
  )
}

// Tooltip label rendered in 3D space
function ZoneTooltip({ zone, label, color }) {
  const zCenter = (zone.zMin + zone.zMax) / 2
  return (
    <Html
      position={[0, zone.y + zone.h + 0.03, zCenter]}
      center
      distanceFactor={0.4}
      style={{ pointerEvents: 'none' }}
    >
      <div style={{
        background: 'rgba(10,15,26,0.92)',
        border: `1.5px solid ${color}`,
        borderRadius: 8,
        padding: '5px 10px',
        color,
        fontSize: 11,
        fontWeight: 700,
        whiteSpace: 'nowrap',
        letterSpacing: '0.04em',
        boxShadow: `0 0 12px ${color}55`,
      }}>
        {zone.label.toUpperCase()}
        <div style={{ color: '#94a3b8', fontWeight: 400, fontSize: 10, marginTop: 2 }}>{label}</div>
      </div>
    </Html>
  )
}

// The actual shoe model + overlays
function ShoeModel({ spec }) {
  const { scene } = useGLTF('/Shoe.glb')
  const hoveredRef = useRef(null)
  const [hovered, setHovered] = useState(null)

  const clonedScene = useMemo(() => {
    const clone = scene.clone(true)
    // Center the shoe horizontally and sit it at y=0
    const box = new THREE.Box3().setFromObject(clone)
    const center = new THREE.Vector3()
    box.getCenter(center)
    clone.position.set(-center.x, -box.min.y, -center.z)
    return clone
  }, [scene])

  return (
    <group>
      {/* The shoe */}
      <primitive object={clonedScene} />

      {/* Cushion zone overlays */}
      {ZONES.map(zone => {
        const color = zoneColor(spec, zone.id)
        const label = zoneLabel(spec, zone.id)
        const isHovered = hovered === zone.id
        return (
          <group key={zone.id}>
            <CushionPad
              zone={zone}
              color={color}
              hovered={isHovered}
              onPointerOver={() => setHovered(zone.id)}
              onPointerOut={() => setHovered(null)}
            />
            {isHovered && <ZoneTooltip zone={zone} label={label} color={color} />}
          </group>
        )
      })}
    </group>
  )
}

function LoadingFallback() {
  return (
    <Html center>
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
        color: '#94a3b8', fontFamily: 'sans-serif',
      }}>
        <div style={{
          width: 40, height: 40, border: '3px solid #334155',
          borderTop: '3px solid #10b981', borderRadius: '50%',
          animation: 'spin 1s linear infinite',
        }} />
        <span style={{ fontSize: 13, fontWeight: 600 }}>Loading 3D shoe model…</span>
        <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
      </div>
    </Html>
  )
}

export default function Shoe3DVisualization({ prescription_spec }) {
  const spec = prescription_spec || {}

  return (
    <div className="space-y-4">
      {/* 3D Canvas */}
      <div
        className="relative rounded-2xl border border-slate-700/50 overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)', height: 440 }}
      >
        <div className="absolute top-4 left-0 right-0 flex justify-center z-10 pointer-events-none">
          <span className="text-xs font-bold tracking-widest text-slate-500 uppercase">
            Orthopedic Prescription Map — 3D View · Drag to rotate · Scroll to zoom
          </span>
        </div>

        <Canvas
          camera={{ position: [0.18, 0.14, 0.28], fov: 38, near: 0.001, far: 100 }}
          gl={{ antialias: true, alpha: true }}
          style={{ width: '100%', height: '100%' }}
        >
          <ambientLight intensity={0.6} />
          <directionalLight position={[0.5, 1, 0.5]} intensity={1.2} castShadow />
          <directionalLight position={[-0.5, 0.5, -0.5]} intensity={0.4} />

          <Suspense fallback={<LoadingFallback />}>
            <Environment preset="studio" />
            <ShoeModel spec={spec} />
            <OrbitControls
              enablePan={false}
              minDistance={0.12}
              maxDistance={0.7}
              minPolarAngle={Math.PI / 6}
              maxPolarAngle={Math.PI / 1.8}
              autoRotate
              autoRotateSpeed={0.6}
            />
          </Suspense>
        </Canvas>
      </div>

      {/* Zone legend cards — same as before but sourced from 3D zones */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {ZONES.map(zone => {
          const color  = zoneColor(spec, zone.id)
          const label  = zoneLabel(spec, zone.id)
          const arch    = spec?.arch_support  || {}
          const midsole = spec?.midsole       || {}
          const last    = spec?.last_spec     || {}

          const badge = {
            heel:     `Shore ${midsole.medial_shore_c || 55}C`,
            arch:     arch.stiffness || 'Custom',
            forefoot: 'Stability zone',
            toe:      last.toe_depth || 'Standard depth',
          }[zone.id]

          return (
            <div
              key={zone.id}
              className="bg-slate-900/60 rounded-xl p-4 border border-slate-800 hover:border-slate-600 transition-colors"
              style={{ borderLeftColor: color, borderLeftWidth: '3px' }}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-xs font-bold text-white tracking-wide">{zone.label} Zone</span>
              </div>
              <p className="text-sm font-semibold text-white leading-snug">{label}</p>
              <span
                className="inline-block mt-2 px-2 py-0.5 rounded text-xs font-mono"
                style={{ color, backgroundColor: color + '20' }}
              >
                {badge}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

useGLTF.preload('/Shoe.glb')
