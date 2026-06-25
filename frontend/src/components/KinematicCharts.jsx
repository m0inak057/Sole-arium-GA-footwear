import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ReferenceLine, ResponsiveContainer, Cell, LabelList, LineChart, Line, PieChart, Pie
} from 'recharts'

function ChartCard({ title, children }) {
  return (
    <div className="bg-slate-900/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-sm p-5">
      <h3 className="text-xs font-bold text-slate-400 mb-4 uppercase tracking-widest">{title}</h3>
      {children}
    </div>
  )
}

function MetricBox({ label, value, unit = '', status = 'neutral' }) {
  const statusColor = {
    good: 'bg-emerald-900/40 border-emerald-600/50 text-emerald-300',
    warning: 'bg-amber-900/40 border-amber-600/50 text-amber-300',
    alert: 'bg-red-900/40 border-red-600/50 text-red-300',
    neutral: 'bg-slate-800 border-slate-700 text-slate-300',
  }
  const colors = statusColor[status]
  return (
    <div className={`rounded-xl border p-3 text-center ${colors}`}>
      <p className="text-xs text-slate-400 font-medium mb-1">{label}</p>
      <p className="text-lg font-bold text-white">{value} <span className="text-xs text-slate-400">{unit}</span></p>
    </div>
  )
}

// ── Spatiotemporal Metrics ────────────────────────────────────────────────
function SpatiotemporalChart({ spatiotemporal }) {
  const st = spatiotemporal || {}

  const cadence = st.cadence_spm ?? 0
  const speed = st.speed_mps ?? 0
  const strideLength = st.stride_length_m ?? 0
  const stepWidth = st.step_width_m ?? 0

  const data = [
    { metric: 'Cadence', value: cadence, unit: 'spm', normal: 110 },
    { metric: 'Speed', value: (speed * 3.6).toFixed(2), unit: 'km/h', normal: 1.4 },
    { metric: 'Stride', value: (strideLength * 100).toFixed(0), unit: 'cm', normal: 155 },
    { metric: 'Step Width', value: (stepWidth * 100).toFixed(1), unit: 'cm', normal: 8 },
  ]

  return (
    <ChartCard title="Spatiotemporal Parameters">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <MetricBox label="Cadence" value={cadence.toFixed(0)} unit="spm" status={cadence > 100 && cadence < 130 ? 'good' : 'warning'} />
        <MetricBox label="Speed" value={speed.toFixed(2)} unit="m/s" status={speed > 1.0 ? 'good' : 'warning'} />
        <MetricBox label="Stride Length" value={strideLength.toFixed(2)} unit="m" status={strideLength > 1.4 ? 'good' : 'warning'} />
        <MetricBox label="Step Width" value={stepWidth.toFixed(3)} unit="m" status={stepWidth < 0.15 ? 'good' : 'warning'} />
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="metric" tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '8px' }} />
          <Bar dataKey="value" fill="#10b981" radius={[4, 4, 0, 0]}>
            <Cell fill="#10b981" />
            <LabelList dataKey="value" position="top" formatter={(v) => `${v}`} style={{ fontSize: 10, fill: '#e2e8f0' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

function StepLengthChart({ spatiotemporal }) {
  const left = spatiotemporal?.step_length_left_m ?? 0
  const right = spatiotemporal?.step_length_right_m ?? 0
  const mean = left && right ? (left + right) / 2 : null
  const asymmetry = mean ? Math.abs(left - right) / mean * 100 : 0

  const data = [
    { side: 'Left', value: parseFloat(left.toFixed(3)) },
    { side: 'Right', value: parseFloat(right.toFixed(3)) },
  ]

  return (
    <ChartCard title="Step Length Comparison (m)">
      {asymmetry > 10 && (
        <div className="mb-3 px-3 py-1.5 bg-amber-900/40 border border-amber-600/50 rounded-lg text-amber-300 text-xs font-medium">
          ⚠️ Asymmetry: {asymmetry.toFixed(1)}% (threshold: 10%)
        </div>
      )}
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="side" tick={{ fontSize: 12, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} domain={[0, 'auto']} unit="m" />
          <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '8px' }} formatter={(v) => [`${v} m`, 'Step Length']} />
          {mean && <ReferenceLine y={mean} stroke="#9ca3af" strokeDasharray="4 2" label={{ value: 'mean', position: 'right', fontSize: 10, fill: '#cbd5e1' }} />}
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            <Cell fill="#3b82f6" />
            <Cell fill="#f97316" />
            <LabelList dataKey="value" position="top" formatter={(v) => `${v}m`} style={{ fontSize: 11, fill: '#e2e8f0' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

function FootProgressionChart({ spatiotemporal }) {
  const left = spatiotemporal?.foot_progression_angle_left_deg ?? 0
  const right = spatiotemporal?.foot_progression_angle_right_deg ?? 0

  const getColor = (angle) => {
    if (angle < -5) return '#dc2626'
    if (angle > 10) return '#d97706'
    return '#16a34a'
  }

  const data = [
    { side: 'Left', value: parseFloat(left.toFixed(1)) },
    { side: 'Right', value: parseFloat(right.toFixed(1)) },
  ]

  return (
    <ChartCard title="Foot Progression Angle (°)">
      <div className="flex gap-3 mb-3 text-xs">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> Toe-in (&lt; -5°)</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-600 inline-block" /> Neutral</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500 inline-block" /> Toe-out (&gt; 10°)</span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="side" tick={{ fontSize: 12, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} unit="°" domain={[-15, 20]} />
          <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '8px' }} formatter={(v) => [`${v}°`, 'FPA']} />
          <ReferenceLine y={-5} stroke="#dc2626" strokeDasharray="4 2" label={{ value: '-5° toe-in', position: 'insideTopRight', fontSize: 9, fill: '#dc2626' }} />
          <ReferenceLine y={10} stroke="#d97706" strokeDasharray="4 2" label={{ value: '10° toe-out', position: 'insideTopRight', fontSize: 9, fill: '#d97706' }} />
          <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="2 2" />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            <Cell fill={getColor(left)} />
            <Cell fill={getColor(right)} />
            <LabelList dataKey="value" position="top" formatter={(v) => `${v}°`} style={{ fontSize: 11, fill: '#e2e8f0' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

function FrontalPlaneChart({ pronation }) {
  const left = pronation?.frontal_plane_excursion_left_deg ?? 0
  const right = pronation?.frontal_plane_excursion_right_deg ?? 0
  const THRESHOLD = 8

  const data = [
    { side: 'Left', value: parseFloat(left.toFixed(1)) },
    { side: 'Right', value: parseFloat(right.toFixed(1)) },
  ]

  return (
    <ChartCard title="Frontal Plane Excursion (°)">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="side" tick={{ fontSize: 12, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} unit="°" domain={[0, 'auto']} />
          <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '8px' }} formatter={(v) => [`${v}°`, 'Excursion']} />
          <ReferenceLine y={THRESHOLD} stroke="#dc2626" strokeDasharray="4 2" label={{ value: '8° threshold', position: 'insideTopRight', fontSize: 9, fill: '#dc2626' }} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            <Cell fill={left > THRESHOLD ? '#dc2626' : '#16a34a'} />
            <Cell fill={right > THRESHOLD ? '#dc2626' : '#16a34a'} />
            <LabelList dataKey="value" position="top" formatter={(v) => `${v}°`} style={{ fontSize: 11, fill: '#e2e8f0' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

function PronationChart({ pronation }) {
  const left = pronation?.rearfoot_angle_at_midstance_deg?.L ?? 0
  const right = pronation?.rearfoot_angle_at_midstance_deg?.R ?? 0
  const NORMAL_MIN = 0
  const NORMAL_MAX = 4

  const isAbnormal = (v) => v < NORMAL_MIN || v > NORMAL_MAX

  const data = [
    { side: 'Left', value: parseFloat(left.toFixed(1)) },
    { side: 'Right', value: parseFloat(right.toFixed(1)) },
  ]

  return (
    <ChartCard title="Rearfoot Eversion Angle (°)">
      <div className="text-xs text-slate-500 mb-3">Normal range: 0° – 4°</div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="side" tick={{ fontSize: 12, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} unit="°" domain={[-6, 'auto']} />
          <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '8px' }} formatter={(v) => [`${v}°`, 'Rearfoot angle']} />
          <ReferenceLine y={NORMAL_MIN} stroke="#9ca3af" strokeDasharray="3 2" label={{ value: '0°', position: 'right', fontSize: 9, fill: '#cbd5e1' }} />
          <ReferenceLine y={NORMAL_MAX} stroke="#9ca3af" strokeDasharray="3 2" label={{ value: '4° (max normal)', position: 'right', fontSize: 9, fill: '#cbd5e1' }} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            <Cell fill={isAbnormal(left) ? '#dc2626' : '#16a34a'} />
            <Cell fill={isAbnormal(right) ? '#dc2626' : '#16a34a'} />
            <LabelList dataKey="value" position="top" formatter={(v) => `${v}°`} style={{ fontSize: 11, fill: '#e2e8f0' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

function SymmetryIndexChart({ spatiotemporal, pronation }) {
  const st = spatiotemporal || {}

  const stepLengthAsymmetry = st.step_length_left_m && st.step_length_right_m
    ? Math.abs(st.step_length_left_m - st.step_length_right_m) / ((st.step_length_left_m + st.step_length_right_m) / 2) * 100
    : 0

  const footProgAsymmetry = Math.abs((st.foot_progression_angle_left_deg ?? 0) - (st.foot_progression_angle_right_deg ?? 0))

  const data = [
    { metric: 'Step Length', value: stepLengthAsymmetry.toFixed(1), threshold: 10 },
    { metric: 'Foot Progression', value: footProgAsymmetry.toFixed(1), threshold: 5 },
  ]

  return (
    <ChartCard title="Symmetry Index (%)">
      <div className="space-y-2">
        {data.map(({ metric, value, threshold }) => (
          <div key={metric}>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-medium text-slate-600">{metric}</span>
              <span className={`font-bold ${parseFloat(value) < threshold ? 'text-emerald-600' : 'text-amber-600'}`}>{value}%</span>
            </div>
            <div className="w-full h-2 rounded-full bg-slate-200 overflow-hidden">
              <div
                className={`h-full rounded-full ${parseFloat(value) < threshold ? 'bg-emerald-500' : 'bg-amber-500'}`}
                style={{ width: `${Math.min(parseFloat(value), 100)}%` }}
              />
            </div>
            <p className="text-xs text-slate-400 mt-0.5">Threshold: {threshold}%</p>
          </div>
        ))}
      </div>
    </ChartCard>
  )
}

function GaitCycleChart({ spatiotemporal }) {
  const st = spatiotemporal || {}

  const stancePhase = st.stance_phase_percent ?? 60
  const swingPhase = 100 - stancePhase
  const doubleSupport = st.double_support_time_percent ?? 10

  const data = [
    { name: 'Stance Phase', value: stancePhase, fill: '#3b82f6' },
    { name: 'Swing Phase', value: swingPhase, fill: '#10b981' },
  ]

  return (
    <ChartCard title="Gait Cycle Phases (%)">
      <div className="grid grid-cols-3 gap-2 mb-4">
        <MetricBox label="Stance" value={stancePhase.toFixed(0)} unit="%" status={stancePhase > 55 && stancePhase < 65 ? 'good' : 'warning'} />
        <MetricBox label="Swing" value={swingPhase.toFixed(0)} unit="%" status={swingPhase > 35 && swingPhase < 45 ? 'good' : 'warning'} />
        <MetricBox label="Double Support" value={doubleSupport.toFixed(0)} unit="%" status={doubleSupport < 15 ? 'good' : 'warning'} />
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={({ name, value }) => `${name}: ${value.toFixed(0)}%`}
            outerRadius={80}
            fill="#8884d8"
            dataKey="value"
          />
          <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '8px' }} formatter={(v) => `${v.toFixed(0)}%`} />
        </PieChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

function JointRangeChart({ pronation, spatiotemporal }) {
  const st = spatiotemporal || {}

  const kneeFlexion = st.knee_flexion_angle_deg ?? 0
  const ankleDF = st.ankle_dorsiflexion_angle_deg ?? 0
  const hipFlexion = st.hip_flexion_angle_deg ?? 0

  const data = [
    { joint: 'Knee Flexion', value: kneeFlexion, unit: '°', normal: 65 },
    { joint: 'Ankle DF', value: ankleDF, unit: '°', normal: 10 },
    { joint: 'Hip Flexion', value: hipFlexion, unit: '°', normal: 30 },
  ]

  return (
    <ChartCard title="Joint Range of Motion (°)">
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="joint" tick={{ fontSize: 10 }} angle={-15} textAnchor="end" height={60} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '8px' }} formatter={(v) => [`${v}°`, 'ROM']} />
          <Bar dataKey="value" fill="#8b5cf6" radius={[4, 4, 0, 0]}>
            <Cell fill="#8b5cf6" />
            <LabelList dataKey="value" position="top" formatter={(v) => `${v}°`} style={{ fontSize: 10, fill: '#e2e8f0' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

export default function KinematicCharts({ profile }) {
  if (!profile) return null

  const st = profile.spatiotemporal || {}
  const pro = profile.pronation || {}

  return (
    <div className="space-y-6">
      {/* Row 1: Spatiotemporal Overview */}
      <SpatiotemporalChart spatiotemporal={st} />

      {/* Row 2: Step Analysis */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StepLengthChart spatiotemporal={st} />
        <FootProgressionChart spatiotemporal={st} />
      </div>

      {/* Row 3: Pronation Analysis */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FrontalPlaneChart pronation={pro} />
        <PronationChart pronation={pro} />
      </div>

      {/* Row 4: Symmetry & Gait Cycle */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SymmetryIndexChart spatiotemporal={st} pronation={pro} />
        <GaitCycleChart spatiotemporal={st} />
      </div>

      {/* Row 5: Joint Mechanics */}
      <JointRangeChart pronation={pro} spatiotemporal={st} />
    </div>
  )
}
