import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchProfile, fetchVideoBlobUrl } from '../services/api.js'
import KinematicCharts from '../components/KinematicCharts.jsx'
import Shoe3DVisualization from '../components/Shoe3DVisualization.jsx'

// ── Severity badge ────────────────────────────────────────────────────────────
function SeverityBadge({ severity }) {
  const map = {
    mild: 'bg-yellow-900/40 text-yellow-300 border-yellow-600/50',
    moderate: 'bg-orange-900/40 text-orange-300 border-orange-600/50',
    severe: 'bg-red-900/40 text-red-300 border-red-600/50',
  }
  const cls = map[severity?.toLowerCase()] || 'bg-slate-700 text-slate-300 border-slate-600'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {severity}
    </span>
  )
}

// ── Side tag ──────────────────────────────────────────────────────────────────
function SideTag({ side }) {
  const map = {
    left: 'bg-blue-900/40 text-blue-300 border-blue-600/50',
    right: 'bg-emerald-900/40 text-emerald-300 border-emerald-600/50',
    bilateral: 'bg-purple-900/40 text-purple-300 border-purple-600/50',
  }
  const cls = map[side?.toLowerCase()] || 'bg-slate-700 text-slate-300 border-slate-600'
  return <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${cls}`}>{side}</span>
}

// ── Gait Quality Banner ───────────────────────────────────────────────────────
function GaitQualityBanner({ profile }) {
  if (!profile) return null

  const defects = profile.health_assessment?.defects_found || []
  const flags   = profile.symmetry_flags || []
  const st      = profile.spatiotemporal || {}

  const severeCount   = defects.filter(d => d.severity?.toLowerCase() === 'severe').length
  const moderateCount = defects.filter(d => d.severity?.toLowerCase() === 'moderate').length

  let quality, colorCls, bgCls, icon
  if (severeCount > 0 || moderateCount >= 2) {
    quality  = 'Requires Attention'
    colorCls = 'text-red-400'
    bgCls    = 'bg-gradient-to-br from-red-900/40 to-rose-900/40 border-red-600/50'
    icon     = (
      <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    )
  } else if (moderateCount === 1 || defects.length > 0 || flags.length > 0) {
    quality  = 'Needs Improvement'
    colorCls = 'text-yellow-400'
    bgCls    = 'bg-gradient-to-br from-yellow-900/40 to-yellow-800/40 border-yellow-600/50'
    icon     = (
      <svg className="w-8 h-8 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    )
  } else {
    quality  = 'Good Gait Pattern'
    colorCls = 'text-emerald-400'
    bgCls    = 'bg-gradient-to-br from-emerald-900/40 to-green-900/40 border-emerald-600/50'
    icon     = (
      <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    )
  }

  const stats = [
    { label: 'Cadence',      value: st.cadence_spm      ? `${st.cadence_spm.toFixed(0)} spm`     : '—' },
    { label: 'Speed',        value: st.speed_mps        ? `${st.speed_mps.toFixed(2)} m/s`        : '—' },
    { label: 'Stride',       value: st.stride_length_m  ? `${st.stride_length_m.toFixed(2)} m`    : '—' },
    { label: 'Step width',   value: st.step_width_m     ? `${st.step_width_m.toFixed(3)} m`       : '—' },
    { label: 'Issues found', value: defects.length === 0 ? 'None' : `${defects.length}` },
    { label: 'Asymmetry flags', value: flags.length === 0 ? 'None' : `${flags.length}` },
  ]

  return (
    <section className={`rounded-2xl border p-6 mb-2 shadow-sm ${bgCls}`}>
      <div className="flex items-center gap-4 mb-5">
        <div className="p-2 rounded-xl bg-slate-800/60 shadow-sm">{icon}</div>
        <div>
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-0.5">Overall Assessment</p>
          <h3 className={`text-2xl font-bold tracking-tight ${colorCls}`}>{quality}</h3>
        </div>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
        {stats.map(({ label, value }) => (
          <div key={label} className="bg-slate-800/50 backdrop-blur-sm rounded-xl px-3 py-2.5 text-center border border-slate-700/50">
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-0.5">{label}</p>
            <p className="text-sm font-bold text-slate-200">{value}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

// ── Section A: Synchronized Video Player ─────────────────────────────────────
function VideoPlayer({ sessionId }) {
  const videoRefs = useRef([null, null, null])
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  // Per-camera blob URL + load state. Native <video src="..."> can't send the
  // X-API-Key header the backend now requires, so each video is fetched via
  // api.js (which does send it) and converted to a blob: URL instead.
  const [videoUrls, setVideoUrls] = useState({})
  const [videoStatus, setVideoStatus] = useState({})

  const cameras = [
    { label: 'Anterior (Front)', key: 'anterior' },
    { label: 'Sagittal (Side)', key: 'sagittal' },
    { label: 'Posterior (Back)', key: 'posterior' },
  ]

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    const createdUrls = []

    setVideoUrls({})
    setVideoStatus(Object.fromEntries(cameras.map(cam => [cam.key, 'loading'])))

    cameras.forEach(async (cam) => {
      try {
        const blobUrl = await fetchVideoBlobUrl(sessionId, cam.key)
        if (cancelled) {
          URL.revokeObjectURL(blobUrl)
          return
        }
        createdUrls.push(blobUrl)
        setVideoUrls(prev => ({ ...prev, [cam.key]: blobUrl }))
        setVideoStatus(prev => ({ ...prev, [cam.key]: 'ready' }))
      } catch (e) {
        if (!cancelled) setVideoStatus(prev => ({ ...prev, [cam.key]: 'error' }))
      }
    })

    return () => {
      cancelled = true
      createdUrls.forEach(url => URL.revokeObjectURL(url))
    }
  }, [sessionId])

  const handlePlayPause = () => {
    const videos = videoRefs.current.filter(Boolean)
    if (playing) {
      videos.forEach(v => v.pause())
    } else {
      videos.forEach(v => v.play().catch(() => {}))
    }
    setPlaying(!playing)
  }

  const handleSeek = (e) => {
    const val = parseFloat(e.target.value)
    const videos = videoRefs.current.filter(Boolean)
    videos.forEach(v => { v.currentTime = val })
    setProgress(val)
    setCurrentTime(val)
  }

  const handleTimeUpdate = () => {
    const v = videoRefs.current.find(Boolean)
    if (v) {
      setCurrentTime(v.currentTime)
      if (v.duration) setProgress(v.currentTime)
    }
  }

  const handleLoadedMetadata = () => {
    const v = videoRefs.current.find(Boolean)
    if (v && v.duration) setDuration(v.duration)
  }

  const fmt = (s) => {
    if (!s || isNaN(s)) return '0:00'
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  return (
    <section className="bg-slate-900/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-sm p-6 mb-6">
      <h2 className="text-base font-bold text-white mb-5 flex items-center gap-2.5">
        <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-500 to-green-600 text-white flex items-center justify-center text-xs font-bold shadow-sm shadow-emerald-500/30">A</span>
        Synchronized Video Player
      </h2>

      <div className="grid grid-cols-3 gap-3 mb-4">
        {cameras.map((cam, i) => (
          <div key={cam.key} className="text-center">
            <p className="text-xs font-medium text-gray-500 mb-1">{cam.label}</p>
            {videoStatus[cam.key] === 'error' ? (
              <div className="w-full rounded-lg bg-gray-900 aspect-video flex flex-col items-center justify-center gap-2 text-slate-500">
                <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
                </svg>
                <p className="text-xs">Video unavailable</p>
              </div>
            ) : videoStatus[cam.key] !== 'ready' ? (
              <div className="w-full rounded-lg bg-gray-900 aspect-video animate-pulse flex items-center justify-center">
                <svg className="w-8 h-8 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.069A1 1 0 0121 8.882v6.236a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </div>
            ) : (
              <video
                ref={el => videoRefs.current[i] = el}
                className="w-full rounded-lg bg-gray-900 aspect-video object-contain"
                src={videoUrls[cam.key]}
                onTimeUpdate={handleTimeUpdate}
                onLoadedMetadata={handleLoadedMetadata}
                muted
                playsInline
              />
            )}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-4 mt-2">
        <button
          onClick={handlePlayPause}
          className="w-10 h-10 rounded-full bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-500 hover:to-green-500 text-white flex items-center justify-center transition-all shadow-lg shadow-emerald-500/40 flex-shrink-0 no-print"
        >
          {playing ? (
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>
          ) : (
            <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
          )}
        </button>
        <div className="flex-1">
          <input
            type="range"
            min={0}
            max={duration || 100}
            step={0.1}
            value={progress}
            onChange={handleSeek}
            className="w-full h-2 bg-slate-700 rounded-full appearance-none cursor-pointer accent-emerald-500 no-print"
          />
          <div className="flex justify-between text-xs text-slate-400 mt-1">
            <span>{fmt(currentTime)}</span>
            <span>{fmt(duration)}</span>
          </div>
        </div>
      </div>
    </section>
  )
}

// ── Section B: Health Assessment Cards ───────────────────────────────────────
function WhatWentRightCard({ items }) {
  return (
    <div className="flex-1 bg-gradient-to-br from-emerald-900/30 to-green-900/30 border border-emerald-600/40 rounded-2xl p-5 shadow-sm">
      <h3 className="font-bold text-emerald-300 mb-3 flex items-center gap-2">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        What You Did Right
      </h3>
      {items && items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-emerald-300">
              <svg className="w-4 h-4 mt-0.5 flex-shrink-0 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-emerald-400 italic">No positives recorded.</p>
      )}
    </div>
  )
}

function DefectsCard({ defects }) {
  const [openIdx, setOpenIdx] = useState(null)
  const toggle = (i) => setOpenIdx(openIdx === i ? null : i)

  return (
    <div className="flex-1 bg-slate-900/50 border border-red-600/40 rounded-2xl p-5 shadow-sm">
      <h3 className="font-bold text-red-300 mb-3 flex items-center gap-2">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        Defects &amp; Posture Issues
      </h3>

      {!defects || defects.length === 0 ? (
        <div className="flex items-center gap-2 py-4 px-3 bg-emerald-900/40 border border-emerald-600/40 rounded-lg">
          <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span className="text-emerald-300 text-sm font-medium">No issues detected</span>
        </div>
      ) : (
        <div className="space-y-2">
          {defects.map((defect, i) => (
            <div key={i} className="border border-slate-700 rounded-lg overflow-hidden">
              <button
                onClick={() => toggle(i)}
                className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-800 transition-colors"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-slate-200">{defect.name}</span>
                  <SeverityBadge severity={defect.severity} />
                  <SideTag side={defect.affected_side} />
                </div>
                <svg className={`w-4 h-4 text-slate-400 transition-transform flex-shrink-0 ml-2 ${openIdx === i ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {openIdx === i && (
                <div className="px-4 py-3 border-t border-slate-700 bg-slate-800/50 text-sm text-slate-300 space-y-2">
                  {defect.biomechanical_cause && <p>{defect.biomechanical_cause}</p>}
                  {defect.gait_cycle_phase && (
                    <p className="italic text-slate-400 text-xs">Phase: {defect.gait_cycle_phase}</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ImprovementPlanCard({ actions }) {
  return (
    <div className="flex-1 bg-gradient-to-br from-slate-900/50 to-slate-800/30 border border-emerald-600/40 rounded-2xl p-5 shadow-sm">
      <h3 className="font-bold text-emerald-300 mb-3 flex items-center gap-2">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        Your Improvement Plan
      </h3>
      {!actions || actions.length === 0 ? (
        <p className="text-sm text-emerald-400 italic">No exercises prescribed.</p>
      ) : (
        <div className="space-y-3">
          {actions.map((action, i) => (
            <div key={i} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="w-6 h-6 rounded-full bg-gradient-to-r from-emerald-600 to-green-600 text-white text-xs flex items-center justify-center font-bold flex-shrink-0">{i + 1}</span>
                <span className="font-semibold text-slate-200 text-sm">{action.exercise_name}</span>
              </div>
              {action.target_area && <p className="text-xs text-slate-400 ml-8 mb-1">{action.target_area}</p>}
              {action.frequency && (
                <span className="ml-8 inline-block px-2 py-0.5 bg-emerald-900/50 text-emerald-300 text-xs rounded-full font-medium mb-2 border border-emerald-600/40">{action.frequency}</span>
              )}
              {action.instructions && <p className="text-xs text-slate-400 ml-8 mb-2">{action.instructions}</p>}
              {action.addresses_defect && (
                <p className="text-xs text-emerald-400 ml-8 mt-1">↳ Addresses: {action.addresses_defect}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Section C helpers: Prescription Specification ────────────────────────────

function YesNoBadge({ value }) {
  return value ? (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-200">YES</span>
  ) : (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">NO</span>
  )
}

const SPEC_CARD_SCHEMES = {
  indigo: 'bg-indigo-50 border-indigo-200',
  purple: 'bg-purple-50 border-purple-200',
  blue: 'bg-blue-50 border-blue-200',
  slate: 'bg-slate-50 border-slate-200',
  zinc: 'bg-zinc-50 border-zinc-200',
  rose: 'bg-rose-50 border-rose-200',
}

function SpecCard({ title, colorScheme, children }) {
  const cls = SPEC_CARD_SCHEMES[colorScheme] || 'bg-gray-50 border-gray-200'
  return (
    <div className={`rounded-xl border p-5 ${cls}`}>
      <h4 className="font-semibold text-gray-700 mb-3 text-xs uppercase tracking-wider">{title}</h4>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function SpecRow({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-gray-500 flex-shrink-0">{label}</span>
      <span className="text-sm font-semibold text-gray-800 text-right">{children}</span>
    </div>
  )
}

function CushioningBadge({ priority }) {
  const map = {
    heel: 'bg-orange-100 text-orange-800 border-orange-200',
    forefoot: 'bg-blue-100 text-blue-800 border-blue-200',
    full_length: 'bg-green-100 text-green-800 border-green-200',
    lateral: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  }
  const cls = map[priority] || 'bg-gray-100 text-gray-700 border-gray-200'
  const label = priority ? priority.replace('_', ' ') : '—'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border capitalize ${cls}`}>
      {label}
    </span>
  )
}

function ShoreCBar({ medial, lateral }) {
  const total = (medial || 0) + (lateral || 0)
  if (!total) return null
  const mPct = Math.round((medial / total) * 100)
  const lPct = 100 - mPct
  return (
    <div className="mt-3 pt-2 border-t border-purple-100">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>Medial ({medial})</span>
        <span>Lateral ({lateral})</span>
      </div>
      <div className="flex h-3 rounded-full overflow-hidden">
        <div className="bg-indigo-500 transition-all" style={{ width: `${mPct}%` }} />
        <div className="bg-gray-300 transition-all" style={{ width: `${lPct}%` }} />
      </div>
    </div>
  )
}

// ── Wedging & Alignment (Section C, between Arch Support and Outsole) ────────

function alignmentZone(angleDeg) {
  if (angleDeg == null || isNaN(angleDeg)) return { label: 'Unknown', cls: 'bg-gray-300', text: 'text-gray-500' }
  if (angleDeg > 8 || angleDeg < -4) return { label: 'Severe', cls: 'bg-red-500', text: 'text-red-700' }
  if (angleDeg > 4 || angleDeg < 0) return { label: 'Mild', cls: 'bg-amber-500', text: 'text-amber-700' }
  return { label: 'Normal', cls: 'bg-green-500', text: 'text-green-700' }
}

function RearfootAlignmentDial({ side, angleDeg }) {
  const zone = alignmentZone(angleDeg)
  // Map -10..+10 deg onto a 0-100% bar position.
  const clamped = angleDeg == null ? 0 : Math.max(-10, Math.min(10, angleDeg))
  const pct = angleDeg == null ? 50 : ((clamped + 10) / 20) * 100

  return (
    <div className="bg-white rounded-lg border border-blue-100 p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-gray-600">{side} Foot</span>
        <span className={`text-xs font-bold ${zone.text}`}>
          {angleDeg != null ? `${angleDeg.toFixed(1)}°` : '—'} ({zone.label})
        </span>
      </div>
      <div className="relative h-3 rounded-full bg-gradient-to-r from-red-300 via-green-300 to-red-300 overflow-hidden">
        <div
          className={`absolute top-0 bottom-0 w-1.5 rounded-full ${zone.cls} border border-white shadow`}
          style={{ left: `calc(${pct}% - 3px)` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-gray-400 mt-1">
        <span>-10° Supination</span>
        <span>0°</span>
        <span>+10° Eversion</span>
      </div>
    </div>
  )
}

function WedgeSummary({ side, wedgeType, wedgeDegree, wedgePlacement }) {
  const hasWedge = !!wedgeType
  return (
    <div className="bg-white rounded-lg border border-blue-100 p-3">
      <p className="text-xs font-semibold text-gray-600 mb-1">{side} Wedge</p>
      {hasWedge ? (
        <>
          <p className="text-sm font-bold text-gray-800 capitalize">
            {wedgeType} &middot; {wedgeDegree != null ? `${wedgeDegree}°` : '—'}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">{wedgePlacement || '—'}</p>
        </>
      ) : (
        <p className="text-sm text-gray-500">No wedge required</p>
      )}
    </div>
  )
}

function WedgingAlignmentSection({ wedging, rearfootAlignment }) {
  if (!wedging && !rearfootAlignment) return null

  const angleL = rearfootAlignment?.angle_deg?.L ?? null
  const angleR = rearfootAlignment?.angle_deg?.R ?? null

  const cushionSide = wedging?.primary_cushioning_side || 'balanced'
  const cushionLabel = { left: 'Left', right: 'Right', balanced: 'Balanced' }[cushionSide] || 'Balanced'
  const cushionExplain = {
    left: 'The left foot needs more cushioning to offset the measured alignment deviation.',
    right: 'The right foot needs more cushioning to offset the measured alignment deviation.',
    balanced: 'Both feet show acceptable alignment; cushioning is distributed evenly.',
  }[cushionSide]

  return (
    <SpecCard title="Wedging & Alignment" colorScheme="blue">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <RearfootAlignmentDial side="Left" angleDeg={angleL} />
        <RearfootAlignmentDial side="Right" angleDeg={angleR} />
        <WedgeSummary
          side="Left"
          wedgeType={wedging?.left_wedge_type}
          wedgeDegree={wedging?.left_wedge_degree_deg}
          wedgePlacement={wedging?.left_wedge_placement}
        />
        <WedgeSummary
          side="Right"
          wedgeType={wedging?.right_wedge_type}
          wedgeDegree={wedging?.right_wedge_degree_deg}
          wedgePlacement={wedging?.right_wedge_placement}
        />
      </div>

      <div className="mt-3 pt-2 border-t border-blue-100 flex items-center justify-between gap-2 flex-wrap">
        <span className="text-xs text-gray-500">Primary cushioning side</span>
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 border border-blue-200">
          {cushionLabel}
        </span>
      </div>
      <p className="text-xs text-gray-500 mt-1">{cushionExplain}</p>

      {wedging?.clinical_rationale && (
        <p className="text-xs text-gray-600 mt-3 pt-2 border-t border-blue-100 italic">
          {wedging.clinical_rationale}
        </p>
      )}
    </SpecCard>
  )
}

function PrescriptionSpecSection({ spec, wedging, rearfootAlignment }) {
  const [show3D, setShow3D] = useState(false)

  if (!spec) {
    return (
      <div className="p-8 text-center">
        <p className="text-gray-400 text-sm">Prescription specification not available for this session.</p>
      </div>
    )
  }

  const fmtLabel = (s) =>
    s ? s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—'

  const last = spec.last_spec || {}
  const arch = spec.arch_support || {}
  const midsole = spec.midsole || {}
  const outsole = spec.outsole || {}
  const upper = spec.upper || {}
  const lift = spec.foot_lift || {}
  const notes = spec.clinician_referral_notes || []
  const hasLift = lift.heel_lift_left_mm > 0 || lift.heel_lift_right_mm > 0

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <div>
          <h3 className="text-lg font-bold text-gray-900">Your Custom Shoe Specification</h3>
          <p className="text-sm text-gray-500 mt-0.5">For your orthotist or shoe designer</p>
        </div>
        {spec.primary_condition_addressed && (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-indigo-100 text-indigo-800 border border-indigo-200">
            {spec.primary_condition_addressed}
          </span>
        )}
      </div>

      {/* Card grid — 2 columns on desktop */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Card 1 — Last & Structure */}
        <SpecCard title="Last & Structure" colorScheme="indigo">
          <SpecRow label="Last shape">
            <span className="text-indigo-700">{fmtLabel(last.shape)}</span>
          </SpecRow>
          <SpecRow label="Toe box">{fmtLabel(last.toe_box)}</SpecRow>
          <SpecRow label="Heel counter">{fmtLabel(last.heel_counter)}</SpecRow>
        </SpecCard>

        {/* Card 2 — Midsole Specification */}
        <SpecCard title="Midsole Specification" colorScheme="purple">
          <SpecRow label="Medial density">{midsole.medial_shore_c} Shore C</SpecRow>
          <SpecRow label="Lateral density">{midsole.lateral_shore_c} Shore C</SpecRow>
          <SpecRow label="Heel drop">{midsole.heel_drop_mm} mm</SpecRow>
          <SpecRow label="Cushioning priority">
            <CushioningBadge priority={midsole.cushioning_priority} />
          </SpecRow>
          <ShoreCBar medial={midsole.medial_shore_c} lateral={midsole.lateral_shore_c} />
        </SpecCard>

        {/* Card 3 — Arch Support */}
        <SpecCard title="Arch Support" colorScheme="blue">
          <SpecRow label="Support height">{arch.height_mm} mm</SpecRow>
          <SpecRow label="Type">{fmtLabel(arch.type)}</SpecRow>
          <SpecRow label="Medial post"><YesNoBadge value={arch.medial_post} /></SpecRow>
          {arch.medial_post && arch.medial_post_shore_c != null && (
            <SpecRow label="Post density">{arch.medial_post_shore_c} Shore C</SpecRow>
          )}
        </SpecCard>

        {/* Card 3b — Wedging & Alignment (measured posterior-camera rearfoot angle) */}
        <WedgingAlignmentSection wedging={wedging} rearfootAlignment={rearfootAlignment} />

        {/* Card 4 — Outsole */}
        <SpecCard title="Outsole" colorScheme="slate">
          <SpecRow label="Base">{fmtLabel(outsole.base)}</SpecRow>
          {outsole.base === 'rocker' && outsole.rocker_apex_position && (
            <SpecRow label="Apex position">{fmtLabel(outsole.rocker_apex_position)}</SpecRow>
          )}
          <SpecRow label="Lateral reinforcement">
            <YesNoBadge value={outsole.lateral_reinforcement} />
          </SpecRow>
        </SpecCard>

        {/* Card 5 — Upper Construction */}
        <SpecCard title="Upper Construction" colorScheme="zinc">
          <SpecRow label="Construction">{fmtLabel(upper.construction)}</SpecRow>
          <SpecRow label="Material">{fmtLabel(upper.material)}</SpecRow>
          <SpecRow label="Closure">{fmtLabel(upper.closure)}</SpecRow>
          <SpecRow label="Extra depth"><YesNoBadge value={upper.extra_depth} /></SpecRow>
        </SpecCard>

        {/* Card 6 — Heel Lift (only when lift > 0 on either side) */}
        {hasLift && (
          <SpecCard title="Heel Lift" colorScheme="rose">
            <SpecRow label="Left heel lift">{lift.heel_lift_left_mm} mm</SpecRow>
            <SpecRow label="Right heel lift">{lift.heel_lift_right_mm} mm</SpecRow>
            <p className="text-xs text-gray-500 mt-2 italic pt-1 border-t border-rose-100">
              Confirm leg length discrepancy before applying
            </p>
          </SpecCard>
        )}
      </div>

      {/* Full-width orthotist notes (only when notes exist) */}
      {notes.length > 0 && (
        <div className="mt-4 bg-amber-50 border border-amber-300 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <svg className="w-5 h-5 text-amber-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <h4 className="font-semibold text-amber-800 text-sm">Notes for Your Orthotist</h4>
          </div>
          <ul className="space-y-1.5 mb-3">
            {notes.map((note, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-amber-800">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-600 flex-shrink-0" />
                {note}
              </li>
            ))}
          </ul>
          <p className="text-xs text-amber-600 italic">
            Share this section with your orthotist or podiatrist before shoe fabrication begins.
          </p>
        </div>
      )}

      {/* ── 3D toggle button ─────────────────────────────────────────────── */}
      <div className="px-6 pb-6 mt-4">
        <button
          onClick={() => setShow3D((v) => !v)}
          className="w-full flex items-center justify-between px-6 py-3 bg-white border-2 border-indigo-300 hover:border-indigo-500 text-indigo-700 hover:text-indigo-900 text-base font-semibold rounded-lg transition-colors"
        >
          <span>View Correct Shoe Structure</span>
          <svg
            className={`w-5 h-5 transition-transform duration-200 ${show3D ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {/* ── Section D: 3D Shoe Preview ─────────────────────────────────── */}
        {show3D && (
          <div className="mt-3 bg-white rounded-lg shadow-md p-6">
            <h3 className="text-base font-bold text-gray-900 mb-1">
              Your Prescription Shoe — 3D Preview
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Colour zones show where your shoe differs from a standard shoe based on your gait analysis
            </p>
            <Shoe3DVisualization prescription_spec={spec} />
            <p className="mt-4 text-xs text-gray-400 italic text-center">
              This is a schematic representation. Actual shoe appearance will vary based on materials and manufacturing.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Glossary ──────────────────────────────────────────────────────────────────
const GLOSSARY = [
  {
    group: 'How You Walk',
    items: [
      { term: 'Cadence (spm)', meaning: 'How many steps you take in one minute. A healthy walking pace is usually 100–120 steps per minute.' },
      { term: 'Stride length', meaning: 'The distance covered in one full step cycle — from when your left foot hits the ground to the next time it hits the ground. Think of it as one "lap" of your walk.' },
      { term: 'Step width', meaning: 'How far apart your two feet land side-by-side. Too narrow or too wide can signal balance issues.' },
      { term: 'Speed (m/s)', meaning: 'How fast you are walking, measured in metres per second. Normal everyday walking is around 1.2–1.4 m/s.' },
      { term: 'Gait cycle', meaning: 'One complete sequence of movements that happens every time you take a step — heel strike, mid-stance, push-off, and swing. Your whole walking pattern repeats this loop continuously.' },
      { term: 'Asymmetry flag', meaning: 'A warning that your left and right sides are moving noticeably differently from each other. Some difference is normal, but large gaps can cause pain over time.' },
      { term: 'Spatiotemporal', meaning: 'A fancy word for measurements that involve both space (distances) and time (speed, timing). Cadence, stride length, and speed all fall under this.' },
      { term: 'Biomechanical cause', meaning: 'The physical reason behind a problem — for example, why your knee hurts may come down to how your ankle rotates when you land.' },
    ],
  },
  {
    group: 'Foot Movement Terms',
    items: [
      { term: 'Pronation', meaning: 'The natural inward roll of your foot when it lands. A small amount is healthy and acts as a shock absorber. Too much is called "overpronation" and can cause pain in your knees, hips, and back.' },
      { term: 'Supination (Underpronation)', meaning: 'When your foot rolls outward instead of inward when landing. This puts extra stress on the outer edge of your foot.' },
      { term: 'Medial', meaning: 'The inner side — the side closest to the centre of your body. Your big toe is on the medial side.' },
      { term: 'Lateral', meaning: 'The outer side — the side away from the centre of your body. Your little toe is on the lateral side.' },
    ],
  },
  {
    group: 'Shoe Parts Explained',
    items: [
      { term: 'Midsole', meaning: 'The cushioning layer sandwiched between the bottom of your foot and the hard outer sole. This is where most of the shock absorption happens. Think of it as the foam padding inside the shoe.' },
      { term: 'Outsole', meaning: 'The very bottom of the shoe — the part that touches the ground. Usually made of rubber for grip and durability.' },
      { term: 'Upper', meaning: 'Everything above the sole — the fabric or leather part that wraps around your foot and keeps it inside the shoe.' },
      { term: 'Heel counter', meaning: 'The stiff cup at the back of the shoe that wraps around your heel. It keeps your heel locked in place and stops it from rolling sideways.' },
      { term: 'Toe box', meaning: 'The front section of the shoe where your toes sit. A wide toe box gives your toes room to spread naturally; a narrow one squeezes them together.' },
      { term: 'Footbed / Insole', meaning: 'The inner layer your foot actually rests on inside the shoe. It can be flat or shaped to support your arch.' },
      { term: 'Last shape', meaning: 'The 3D mould the shoe is built around. It determines the overall shape of the shoe — straight, curved, or semi-curved — and affects how the shoe fits your foot type.' },
    ],
  },
  {
    group: 'Shoe Specification Terms',
    items: [
      { term: 'Shore C (hardness)', meaning: 'A number that tells you how soft or firm the foam cushioning is. Lower Shore C = softer and more cushioning. Higher Shore C = firmer and more supportive. Most running shoes sit between 40–65 Shore C.' },
      { term: 'Heel drop (mm)', meaning: 'The height difference between the heel and the toe of the shoe. A 10mm heel drop means your heel sits 10mm higher than your toes. Higher drop suits heel-strikers; lower drop is more natural/barefoot-like.' },
      { term: 'Medial post', meaning: 'An extra firm section built into the inner (medial) side of the midsole. It stops your foot from rolling too far inward and is commonly recommended for flat feet or overpronation.' },
      { term: 'Arch support', meaning: 'Built-in padding or a raised ridge under the arch of your foot (the curved part on the inside). It helps distribute your body weight evenly and reduces strain.' },
      { term: 'Cushioning priority', meaning: 'The zone of the shoe where extra soft foam has been added. "Heel priority" means more cushion under your heel; "lateral priority" means more cushion on the outer edge.' },
      { term: 'Rocker sole', meaning: 'A curved outsole that rocks forward like a rocking chair when you walk. It takes pressure off the ball of your foot and helps people with stiff ankles or forefoot pain.' },
      { term: 'Lateral reinforcement', meaning: 'Extra material added to the outer edge of the outsole to prevent the shoe from wearing down unevenly on that side.' },
      { term: 'Extra depth', meaning: 'A shoe that is built slightly taller inside than normal, giving more room for thick insoles, orthotics, or swollen feet.' },
      { term: 'Heel lift', meaning: 'A wedge added inside the heel to raise it slightly. Often used when one leg is a little shorter than the other, to level out your hips while walking.' },
    ],
  },
  {
    group: 'People & Specialists',
    items: [
      { term: 'Orthotist', meaning: 'A healthcare professional who designs and fits custom shoe insoles, braces, and supports to correct how you walk or stand.' },
      { term: 'Podiatrist', meaning: 'A foot doctor who diagnoses and treats foot and ankle problems, and can prescribe custom orthotics or footwear changes.' },
    ],
  },
]

function GlossarySection() {
  const [open, setOpen] = useState(false)

  return (
    <section className="bg-slate-900/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-sm overflow-hidden mt-6">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-slate-800/40 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-500 to-orange-500 text-white flex items-center justify-center text-xs font-bold shadow-sm shadow-amber-500/30">?</span>
          <div>
            <p className="text-base font-bold text-white">Glossary — What do these words mean?</p>
            <p className="text-xs text-slate-400 mt-0.5">Plain-English explanations of every technical term used in this report</p>
          </div>
        </div>
        <svg className={`w-5 h-5 text-slate-400 transition-transform flex-shrink-0 ml-4 ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="px-6 pb-8 border-t border-slate-700/50">
          <p className="text-sm text-slate-400 mt-5 mb-6">
            This report uses medical and technical language. Here is what each term means in simple words.
          </p>
          <div className="space-y-8">
            {GLOSSARY.map(({ group, items }) => (
              <div key={group}>
                <h4 className="text-xs font-bold text-amber-400 uppercase tracking-widest mb-3 pb-2 border-b border-slate-700/60">
                  {group}
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {items.map(({ term, meaning }) => (
                    <div key={term} className="flex gap-3 bg-slate-800/40 rounded-xl p-4 border border-slate-700/40">
                      <div className="w-1.5 rounded-full bg-amber-500/60 flex-shrink-0 mt-1" />
                      <div>
                        <p className="text-sm font-bold text-white mb-1">{term}</p>
                        <p className="text-xs text-slate-400 leading-relaxed">{meaning}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

// ── Section E: Summary Footer ─────────────────────────────────────────────────
function SummaryFooter({ profile, sessionId }) {
  return (
    <section className="bg-slate-900/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6 mt-6 flex items-center justify-between flex-wrap gap-4">
      <div className="space-y-1">
        <div className="text-xs text-slate-400">
          <span className="font-medium text-slate-300">Session ID:</span> {sessionId}
        </div>
        <div className="text-xs text-slate-400">
          <span className="font-medium text-slate-300">Patient:</span> {profile?.patient_id}
        </div>
        <div className="text-xs text-slate-400">
          <span className="font-medium text-slate-300">Analysed:</span>{' '}
          {profile?.session_timestamp ? new Date(profile.session_timestamp).toLocaleString() : '—'}
        </div>
      </div>
      <div className="flex items-center gap-3 no-print">
        {profile?.face_blur_applied && (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-900/40 border border-emerald-600/40 text-emerald-300 text-xs font-medium rounded-full">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            Privacy Protected
          </span>
        )}
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-500 hover:to-green-500 text-white text-sm font-semibold rounded-xl transition-all shadow-md shadow-emerald-500/30 hover:shadow-lg"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Download Report
        </button>
      </div>
    </section>
  )
}

// ── Video Quality Banner ─────────────────────────────────────────────────────
function VideoQualityBanner({ profile }) {
  if (!profile) return null

  const vq = profile.video_quality || {}
  const qm = profile.quality_metrics || {}
  const ra = profile.rearfoot_alignment || {}
  const duration = vq.duration_sec
  const width = vq.width
  const height = vq.height
  const cycleL = qm.cycle_count_L
  const cycleR = qm.cycle_count_R
  const rearfootFrameCountL = ra.frame_count?.L
  const rearfootFrameCountR = ra.frame_count?.R

  const shortVideo = typeof duration === 'number' && duration < 5
  const lowRes = typeof width === 'number' && typeof height === 'number' && Math.min(width, height) < 360
  const fewCycles = (typeof cycleL === 'number' && cycleL < 4) || (typeof cycleR === 'number' && cycleR < 4)
  const flaggedByBackend = vq.is_low_quality === true || qm.is_low_confidence === true
  const rearfootUnmeasurable =
    (typeof rearfootFrameCountL !== 'number' || rearfootFrameCountL < 3) &&
    (typeof rearfootFrameCountR !== 'number' || rearfootFrameCountR < 3)

  if (!shortVideo && !lowRes && !fewCycles && !flaggedByBackend && !rearfootUnmeasurable) return null

  return (
    <div className="rounded-2xl border border-amber-500/40 bg-gradient-to-br from-amber-900/30 to-orange-900/20 px-5 py-4 flex items-start gap-3 shadow-sm">
      <svg className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <div className="text-sm text-amber-200 leading-relaxed space-y-1.5">
        {(shortVideo || lowRes || fewCycles || flaggedByBackend) && (
          <p>
            <span className="font-semibold">Note:</span> This analysis was performed on a short or
            low-resolution video. Results may be less accurate than analyses performed with higher
            quality recordings. For clinical use, we recommend videos of at least 10 seconds at 720p
            or higher.
          </p>
        )}
        {rearfootUnmeasurable && (
          <p>
            <span className="font-semibold">Note:</span> Rearfoot alignment could not be measured — insufficient posterior camera data.
          </p>
        )}
      </div>
    </div>
  )
}

// ── ResultsPage ───────────────────────────────────────────────────────────────
export default function ResultsPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showPrescription, setShowPrescription] = useState(false)

  useEffect(() => {
    fetchProfile(sessionId)
      .then(data => { setProfile(data); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [sessionId])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-4">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-green-600 flex items-center justify-center shadow-xl shadow-emerald-500/40 animate-pulse">
          <svg className="animate-spin w-8 h-8 text-white" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
        <p className="text-slate-400 text-sm font-medium">Loading your results…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-lg mx-auto py-16 text-center">
        <div className="p-6 bg-red-900/30 border border-red-600/40 rounded-2xl shadow-sm">
          <p className="text-red-300 font-semibold mb-2">Failed to load results</p>
          <p className="text-sm text-red-400 mb-4">{error}</p>
          <button onClick={() => navigate('/')} className="px-5 py-2.5 bg-gradient-to-r from-emerald-600 to-green-600 text-white text-sm font-semibold rounded-xl hover:from-emerald-500 hover:to-green-500 transition-all shadow-md shadow-emerald-500/30">
            Start New Analysis
          </button>
        </div>
      </div>
    )
  }

  // ── Re-record state ───────────────────────────────────────────────────────────
  if (profile?.__rerecord__) {
    return (
      <div className="max-w-2xl mx-auto py-16">
        <div className="rounded-2xl border border-amber-600/40 bg-gradient-to-br from-amber-900/40 to-orange-900/30 p-8 shadow-xl shadow-amber-500/10 text-center">
          <div className="flex justify-center mb-5">
            <div className="w-16 h-16 rounded-2xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center">
              <svg className="w-8 h-8 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.362a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              </svg>
            </div>
          </div>

          <h2 className="text-2xl font-bold text-amber-300 mb-2">Re-Record Required</h2>
          <p className="text-sm text-slate-400 mb-5">Session {sessionId}</p>

          <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-4 mb-6 text-left">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">What went wrong</p>
            <p className="text-sm text-amber-200 leading-relaxed">
              {profile.reason || 'The pipeline could not detect enough walking cycles from the uploaded video. This usually means the subject was not clearly visible, the camera angle was obstructed, or the video was too short.'}
            </p>
          </div>

          <div className="bg-slate-900/60 border border-slate-700/50 rounded-xl p-4 mb-6 text-left">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">Tips for a successful recording</p>
            <ul className="space-y-2 text-sm text-slate-300">
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5 flex-shrink-0">✓</span>
                Ensure the subject walks completely through the camera frame at a steady pace
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5 flex-shrink-0">✓</span>
                Record at least 10 seconds of continuous walking (3–5 full strides)
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5 flex-shrink-0">✓</span>
                Make sure the camera is steady and the subject is well-lit
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5 flex-shrink-0">✓</span>
                Do not obstruct the camera with objects or other people
              </li>
            </ul>
          </div>

          <button
            id="rerecord-start-new-btn"
            onClick={() => navigate('/')}
            className="w-full flex items-center justify-center gap-2 px-6 py-3.5 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-white font-semibold rounded-xl transition-all shadow-lg shadow-amber-500/30 hover:shadow-xl"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Upload New Recording
          </button>
        </div>
      </div>
    )
  }

  const ha = profile?.health_assessment || {}
  const defects = ha.defects_found || []
  const improvements = ha.improvement_plan || ha.improvements || []
  const whatWentRight = ha.what_went_right || []

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Your Gait Analysis Results</h2>
          <p className="text-sm text-slate-400 mt-0.5">Session {sessionId}</p>
        </div>
        <button onClick={() => navigate('/')} className="flex items-center gap-1.5 text-sm text-emerald-400 hover:text-emerald-300 font-medium transition-colors no-print">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          New Analysis
        </button>
      </div>

      {/* Gait Quality Banner */}
      <GaitQualityBanner profile={profile} />

      {/* Section A — Video Player */}
      <VideoPlayer sessionId={sessionId} />

      {/* Section B — Health Assessment Cards */}
      <section className="bg-slate-900/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-sm p-6">
        <h2 className="text-base font-bold text-white mb-5 flex items-center gap-2.5">
          <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600 text-white flex items-center justify-center text-xs font-bold shadow-sm shadow-emerald-500/30">B</span>
          Health Assessment
        </h2>
        <div className="flex gap-4 flex-wrap">
          <WhatWentRightCard items={whatWentRight} />
          <DefectsCard defects={defects} />
          <ImprovementPlanCard actions={improvements} />
        </div>
      </section>

      {/* Toggle: View Shoe Prescription (Section C) */}
      <div>
        <button
          onClick={() => setShowPrescription(prev => !prev)}
          className="w-full flex items-center justify-between px-6 py-4 bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-500 hover:to-green-500 text-white font-semibold rounded-2xl transition-all duration-200 shadow-lg shadow-emerald-500/40 hover:shadow-xl no-print"
        >
          <span>View Your Custom Shoe Specification</span>
          <svg
            className={`w-5 h-5 transition-transform duration-200 ${showPrescription ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {showPrescription && (
          <div className="mt-2 bg-slate-900/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-sm overflow-hidden">
            <div className="px-6 pt-5 pb-4 border-b border-slate-700 flex items-center gap-2.5">
              <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 text-white flex items-center justify-center text-xs font-bold flex-shrink-0 shadow-sm shadow-purple-500/30">C</span>
              <span className="text-base font-bold text-white">Shoe Prescription</span>
            </div>
            <PrescriptionSpecSection
              spec={profile?.prescription_spec ?? null}
              wedging={profile?.wedging_prescription ?? null}
              rearfootAlignment={profile?.rearfoot_alignment ?? null}
            />
          </div>
        )}
      </div>

      {/* Section D — Kinematic Charts */}
      <section className="bg-slate-900/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-sm p-6">
        <h2 className="text-base font-bold text-white mb-5 flex items-center gap-2.5">
          <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-600 text-white flex items-center justify-center text-xs font-bold shadow-sm shadow-blue-500/30">D</span>
          Kinematic Analysis
        </h2>
        <KinematicCharts profile={profile} />
      </section>

      {/* Section E — Summary Footer */}
      <SummaryFooter profile={profile} sessionId={sessionId} />

      {/* Glossary */}
      <GlossarySection />

      {/* Video quality disclaimer — non-blocking, shown after all results */}
      <VideoQualityBanner profile={profile} />
    </div>
  )
}
