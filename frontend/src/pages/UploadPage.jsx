import { useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { createSession, uploadVideos, triggerProcessing, pollStatus } from '../services/api.js'

const CAMERAS = [
  {
    key: 'anterior', label: 'Front View', subtitle: 'Anterior',
    gradient: 'from-emerald-500 to-green-600',
    activeBorder: 'border-emerald-400 bg-emerald-900/30',
    hoverBorder: 'hover:border-emerald-400 hover:bg-emerald-900/20',
    step: '01',
  },
  {
    key: 'sagittal', label: 'Side View', subtitle: 'Sagittal',
    gradient: 'from-teal-500 to-cyan-600',
    activeBorder: 'border-teal-400 bg-teal-900/30',
    hoverBorder: 'hover:border-teal-400 hover:bg-teal-900/20',
    step: '02',
  },
  {
    key: 'posterior', label: 'Back View', subtitle: 'Posterior',
    gradient: 'from-green-500 to-emerald-600',
    activeBorder: 'border-green-400 bg-green-900/30',
    hoverBorder: 'hover:border-green-400 hover:bg-green-900/20',
    step: '03',
  },
]

const STATUS_MESSAGES = [
  'Uploading videos…',
  'Synchronising cameras…',
  'Detecting pose keypoints…',
  'Computing biomechanics…',
  'Generating your health assessment…',
]

const ACCEPTED_TYPES = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/avi']
const ACCEPTED_EXTS = ['.mp4', '.mov', '.avi']
const MAX_POLL_RETRIES = 40

function UploadIcon() {
  return (
    <svg className="w-6 h-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
    </svg>
  )
}

function VideoIcon() {
  return (
    <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.069A1 1 0 0121 8.882v6.236a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
    </svg>
  )
}

function DropZone({ camera, file, onFile }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const validate = (f) => {
    if (!f) return false
    const ext = '.' + f.name.split('.').pop().toLowerCase()
    return ACCEPTED_TYPES.includes(f.type) || ACCEPTED_EXTS.includes(ext)
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f && validate(f)) onFile(camera.key, f)
  }, [camera.key, onFile])

  const handleDragOver = (e) => { e.preventDefault(); setDragging(true) }
  const handleDragLeave = () => setDragging(false)
  const handleClick = () => inputRef.current?.click()
  const handleChange = (e) => {
    const f = e.target.files[0]
    if (f && validate(f)) onFile(camera.key, f)
    e.target.value = ''
  }

  const zoneClass = dragging
    ? camera.activeBorder
    : file
    ? 'border-emerald-400 bg-emerald-900/40'
    : `border-slate-700 bg-slate-800/50 ${camera.hoverBorder}`

  return (
    <div className="flex-1 min-w-0">
      <div className="text-center mb-3">
        <div className={`w-11 h-11 mx-auto mb-2.5 rounded-xl bg-gradient-to-br ${camera.gradient} flex items-center justify-center shadow-lg shadow-emerald-500/30`}>
          <VideoIcon />
        </div>
        <p className="text-sm font-semibold text-white">{camera.label}</p>
        <p className="text-xs text-slate-400 mt-0.5 font-mono">{camera.subtitle}</p>
      </div>

      <div
        onClick={handleClick}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`border-2 border-dashed rounded-2xl p-5 cursor-pointer transition-all duration-200 min-h-44 flex flex-col items-center justify-center ${zoneClass}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTS.join(',')}
          className="hidden"
          onChange={handleChange}
        />
        {file ? (
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-emerald-900/60 flex items-center justify-center">
              <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-emerald-300 break-all px-2 leading-snug">{file.name}</p>
            <p className="text-xs text-slate-400 mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
            <p className="text-xs text-emerald-400 mt-2.5 font-medium">Click to replace</p>
          </div>
        ) : (
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-slate-700 flex items-center justify-center">
              <UploadIcon />
            </div>
            <p className="text-sm font-medium text-slate-200">Drop video here</p>
            <p className="text-xs text-slate-400 mt-1">or click to browse</p>
            <p className="text-xs text-slate-500 mt-2 font-mono tracking-wide">.mp4 · .mov · .avi</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function UploadPage() {
  const navigate = useNavigate()
  const [files, setFiles] = useState({ anterior: null, sagittal: null, posterior: null })
  const [analysing, setAnalysing] = useState(false)
  const [statusIdx, setStatusIdx] = useState(0)
  const [error, setError] = useState(null)
  const cycleRef = useRef(null)

  const allSelected = files.anterior && files.sagittal && files.posterior
  const selectedCount = Object.values(files).filter(Boolean).length

  const handleFile = useCallback((key, file) => {
    setFiles(prev => ({ ...prev, [key]: file }))
  }, [])

  const startCycle = () => {
    let idx = 0
    setStatusIdx(0)
    cycleRef.current = setInterval(() => {
      idx = (idx + 1) % STATUS_MESSAGES.length
      setStatusIdx(idx)
    }, 10000)
  }

  const stopCycle = () => {
    if (cycleRef.current) clearInterval(cycleRef.current)
  }

  const handleAnalyse = async () => {
    setError(null)
    setAnalysing(true)
    startCycle()

    try {
      const patientId = `patient_${Date.now()}`
      const session = await createSession(patientId)
      const sessionId = session.session_id || session.id || session.sessionId

      await uploadVideos(sessionId, files.anterior, files.sagittal, files.posterior)
      await triggerProcessing(sessionId)

      await new Promise((resolve, reject) => {
        let retries = 0
        const poll = setInterval(async () => {
          retries += 1
          if (retries > MAX_POLL_RETRIES) {
            clearInterval(poll)
            reject(new Error('Analysis is taking longer than expected. Please refresh or contact support.'))
            return
          }
          try {
            const { status } = await pollStatus(sessionId)
            if (status === 'completed' || status === 'COMPLETED') {
              clearInterval(poll)
              resolve()
            } else if (status === 'failed' || status === 'FAILED') {
              clearInterval(poll)
              reject(new Error('Analysis failed on server'))
            }
          } catch (e) {
            clearInterval(poll)
            reject(e)
          }
        }, 3000)
      })

      stopCycle()
      navigate(`/results/${sessionId}`)
    } catch (e) {
      stopCycle()
      setAnalysing(false)
      setError(e.message || 'Something went wrong. Please try again.')
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Hero */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-900/40 border border-emerald-500/50 text-emerald-300 text-xs font-semibold mb-5 tracking-widest uppercase">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          AI-Powered Biomechanical Analysis
        </div>
        <h2 className="text-4xl font-bold text-white mb-4 tracking-tight leading-tight">
          Analyse Your{' '}
          <span className="bg-gradient-to-r from-emerald-400 to-green-500 bg-clip-text text-transparent">
            Walking Pattern
          </span>
        </h2>
        <p className="text-slate-400 text-base max-w-xl mx-auto leading-relaxed">
          Upload videos from three camera angles to receive a personalised biomechanical
          assessment and custom orthopedic shoe prescription.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-6 p-5 bg-red-900/30 border border-red-500/40 rounded-2xl flex items-start gap-3">
          <svg className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div className="flex-1">
            <p className="text-red-300 text-sm font-medium mb-2">{error}</p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Upload card */}
      <div className="bg-slate-900/50 backdrop-blur-md rounded-3xl shadow-2xl shadow-black/50 border border-slate-700/50 p-8">
        {/* Step labels */}
        <div className="flex items-center gap-2 mb-6">
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-slate-700 to-transparent" />
          <p className="text-xs font-semibold text-slate-400 tracking-widest uppercase px-3">Upload 3 Camera Angles</p>
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-slate-700 to-transparent" />
        </div>

        <div className="flex gap-4 mb-8">
          {CAMERAS.map(cam => (
            <DropZone key={cam.key} camera={cam} file={files[cam.key]} onFile={handleFile} />
          ))}
        </div>

        {/* Progress pills */}
        <div className="flex justify-center gap-2 mb-7">
          {CAMERAS.map((cam, i) => (
            <div
              key={cam.key}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all duration-300 ${
                files[cam.key]
                  ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-500/60'
                  : 'bg-slate-800 text-slate-400 border border-slate-700'
              }`}
            >
              {files[cam.key] ? (
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              ) : (
                <span className="w-3 h-3 rounded-full border border-slate-500 inline-block" />
              )}
              {cam.label}
            </div>
          ))}
        </div>

        {/* CTA */}
        <div className="text-center">
          {analysing ? (
            <div className="py-4">
              <div className="flex items-center justify-center gap-3 mb-4">
                <svg className="animate-spin w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span className="text-slate-200 font-medium text-base">{STATUS_MESSAGES[statusIdx]}</span>
              </div>
              <div className="flex justify-center gap-1.5">
                {STATUS_MESSAGES.map((_, i) => (
                  <div
                    key={i}
                    className={`h-1.5 rounded-full transition-all duration-500 ${i === statusIdx ? 'w-7 bg-gradient-to-r from-emerald-400 to-green-500' : 'w-2 bg-slate-700'}`}
                  />
                ))}
              </div>
            </div>
          ) : (
            <button
              onClick={handleAnalyse}
              disabled={!allSelected}
              className={`px-10 py-4 rounded-2xl text-white font-semibold text-base transition-all duration-200 ${
                allSelected
                  ? 'bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-500 hover:to-green-500 shadow-lg shadow-emerald-500/40 hover:shadow-xl hover:shadow-emerald-500/50 hover:-translate-y-0.5 cursor-pointer'
                  : 'bg-slate-700 text-slate-400 cursor-not-allowed shadow-none'
              }`}
            >
              {allSelected
                ? 'Analyse My Walk'
                : `Select all 3 videos to continue (${selectedCount}/3)`}
            </button>
          )}
        </div>
      </div>

      <p className="text-center text-xs text-slate-500 mt-5 flex items-center justify-center gap-1.5">
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        All videos processed securely. Faces automatically blurred for privacy (DPDP Act 2023).
      </p>
    </div>
  )
}
