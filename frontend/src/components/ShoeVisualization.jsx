import React from 'react'

function getColors(spec) {
  const arch = spec?.arch_support || {}
  const midsole = spec?.midsole || {}
  const last = spec?.last_spec || {}
  return {
    heel: midsole.cushioning_priority === 'heel' ? '#ef4444' : '#f97316',
    arch: arch.medial_post ? '#7c3aed' : '#8b5cf6',
    forefoot: midsole.cushioning_priority === 'lateral' ? '#2563eb' : '#3b82f6',
    toe: (last.toe_box === 'wide' || last.toe_box === 'extra_wide') ? '#0d9488' : '#14b8a6',
  }
}

// Side-view silhouette of a right-foot running shoe (heel LEFT, toe RIGHT)
// ViewBox: 0 0 700 340
// This path traces: heel counter top → heel back curve → sole bottom → toe spring → shoe upper → back to start
const SHOE_PATH = "M 88,98 C 75,102 64,118 63,156 C 62,194 69,248 76,280 C 80,292 87,302 97,307 L 558,307 C 591,307 614,297 627,282 C 639,267 642,247 640,230 C 638,215 629,204 616,199 C 600,193 580,192 558,191 C 533,190 506,188 478,186 C 450,184 421,181 392,178 C 363,175 334,172 307,169 C 280,166 254,162 231,157 C 208,152 188,145 172,137 C 156,129 143,119 133,109 C 122,99 110,93 97,93 C 93,93 90,95 88,98 Z"

export default function ShoeVisualization({ prescription_spec }) {
  const spec = prescription_spec || {}
  const arch = spec?.arch_support || {}
  const midsole = spec?.midsole || {}
  const last = spec?.last_spec || {}
  const colors = getColors(spec)

  const heelDrop = midsole.heel_drop_mm ?? 8
  const archHeight = arch.height_mm ?? 18
  const archLabel = archHeight > 25 ? 'High' : archHeight > 18 ? 'Medium' : 'Low'
  const toeBoxLabel = last.toe_box ? last.toe_box.replace('_', ' ') : 'Standard'

  return (
    <div className="space-y-4">
      {/* SVG Shoe Prescription Diagram */}
      <div className="relative bg-gradient-to-b from-slate-900 to-slate-950 rounded-2xl border border-slate-700/50 overflow-visible pt-16 pb-4 px-4">
        <div className="absolute top-4 left-0 right-0 flex justify-center">
          <span className="text-xs font-bold tracking-widest text-slate-500 uppercase">
            Orthopedic Prescription Map — Lateral View
          </span>
        </div>

        <svg viewBox="0 0 700 340" className="w-full" style={{ height: 280 }}>
          <defs>
            {/* Clip entire drawing to shoe shape */}
            <clipPath id="shoeClip">
              <path d={SHOE_PATH}/>
            </clipPath>

            {/* Zone vertical band clips */}
            <clipPath id="clipHeel">    <rect x="0"   y="0" width="220" height="400"/></clipPath>
            <clipPath id="clipArch">    <rect x="220" y="0" width="150" height="400"/></clipPath>
            <clipPath id="clipForefoot"><rect x="370" y="0" width="170" height="400"/></clipPath>
            <clipPath id="clipToe">     <rect x="540" y="0" width="200" height="400"/></clipPath>

            {/* Vertical gradients per zone */}
            {[
              { id: 'gHeel',     color: colors.heel },
              { id: 'gArch',     color: colors.arch },
              { id: 'gForefoot', color: colors.forefoot },
              { id: 'gToe',      color: colors.toe },
            ].map(({ id, color }) => (
              <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={color} stopOpacity="0.25"/>
                <stop offset="70%"  stopColor={color} stopOpacity="0.60"/>
                <stop offset="100%" stopColor={color} stopOpacity="0.90"/>
              </linearGradient>
            ))}
          </defs>

          {/* ── SHOE FILL LAYERS ── */}
          <g clipPath="url(#shoeClip)">
            {/* Dark base */}
            <rect x="0" y="0" width="700" height="400" fill="#1a2332"/>

            {/* Zone colour fills (full height, gradient) */}
            <rect x="0"   y="0" width="220" height="400" fill="url(#gHeel)"     clipPath="url(#clipHeel)"/>
            <rect x="220" y="0" width="150" height="400" fill="url(#gArch)"     clipPath="url(#clipArch)"/>
            <rect x="370" y="0" width="170" height="400" fill="url(#gForefoot)" clipPath="url(#clipForefoot)"/>
            <rect x="540" y="0" width="200" height="400" fill="url(#gToe)"      clipPath="url(#clipToe)"/>

            {/* Midsole band (bottom 55px) — solid zone colours */}
            <rect x="0"   y="250" width="220" height="60" fill={colors.heel}     opacity="0.80" clipPath="url(#clipHeel)"/>
            <rect x="220" y="250" width="150" height="60" fill={colors.arch}     opacity="0.80" clipPath="url(#clipArch)"/>
            <rect x="370" y="250" width="170" height="60" fill={colors.forefoot} opacity="0.80" clipPath="url(#clipForefoot)"/>
            <rect x="540" y="250" width="200" height="60" fill={colors.toe}      opacity="0.80" clipPath="url(#clipToe)"/>

            {/* Outsole strip (very dark) */}
            <rect x="0" y="293" width="700" height="20" fill="#0a0f1a" opacity="0.95"/>

            {/* Heel counter darker shade */}
            <rect x="63" y="93" width="58" height="202" fill="#0a0f1a" opacity="0.35"/>

            {/* Upper highlight sheen */}
            <path d="M 90,103 C 150,96 280,90 420,94 C 510,97 580,110 616,130"
                  fill="none" stroke="white" strokeWidth="2" strokeOpacity="0.08"/>
          </g>

          {/* ── SHOE OUTLINE ── */}
          <path d={SHOE_PATH} fill="none" stroke="rgba(255,255,255,0.45)" strokeWidth="2.2"/>

          {/* Midsole / upper divider */}
          <path d="M 76,252 C 200,250 400,250 605,252" fill="none"
                stroke="rgba(255,255,255,0.18)" strokeWidth="1" strokeDasharray="5,3"
                clipPath="url(#shoeClip)"/>

          {/* Outsole top edge */}
          <path d="M 76,293 C 200,292 400,292 625,288" fill="none"
                stroke="rgba(255,255,255,0.10)" strokeWidth="0.8"
                clipPath="url(#shoeClip)"/>

          {/* ── ZONE DIVIDERS ── */}
          <g strokeWidth="1.3" strokeDasharray="4,4" opacity="0.55">
            <line x1="220" y1="90"  x2="220" y2="312" stroke={colors.arch}/>
            <line x1="370" y1="86"  x2="370" y2="312" stroke={colors.forefoot}/>
            <line x1="540" y1="88"  x2="540" y2="312" stroke={colors.toe}/>
          </g>

          {/* ── ZONE NAME LABELS (inside shoe) ── */}
          <text x="140" y="134" textAnchor="middle" fill={colors.heel}     fontSize="8" fontWeight="800" letterSpacing="1.5" opacity="0.9">HEEL</text>
          <text x="293" y="126" textAnchor="middle" fill={colors.arch}     fontSize="8" fontWeight="800" letterSpacing="1.5" opacity="0.9">ARCH</text>
          <text x="453" y="118" textAnchor="middle" fill={colors.forefoot} fontSize="8" fontWeight="800" letterSpacing="1.5" opacity="0.9">FOREFOOT</text>
          <text x="576" y="150" textAnchor="middle" fill={colors.toe}      fontSize="8" fontWeight="800" letterSpacing="1.5" opacity="0.9">TOE</text>

          {/* Anatomy row labels */}
          <text x="140" y="275" textAnchor="middle" fill="white" fontSize="7" opacity="0.55">MIDSOLE</text>
          <text x="140" y="304" textAnchor="middle" fill="white" fontSize="6" opacity="0.35">OUTSOLE</text>
          <text x="73"  y="185" textAnchor="middle" fill="white" fontSize="7" opacity="0.45"
                transform="rotate(-90,73,185)">UPPER</text>

          {/* ── CALLOUT LINES + ANNOTATION BOXES ── */}

          {/* Heel callout — points left-down */}
          <line x1="128" y1="140" x2="42" y2="218" stroke={colors.heel} strokeWidth="1.3" opacity="0.75"/>
          <circle cx="42" cy="218" r="2.5" fill={colors.heel}/>
          <rect x="0" y="222" width="116" height="52" rx="5"
                fill="#0c1220" stroke={colors.heel} strokeWidth="1" strokeOpacity="0.7"/>
          <text x="58" y="235" textAnchor="middle" fill={colors.heel}  fontSize="8.5" fontWeight="700">HEEL ZONE</text>
          <text x="58" y="248" textAnchor="middle" fill="#94a3b8" fontSize="7.5">Drop: {heelDrop}mm</text>
          <text x="58" y="260" textAnchor="middle" fill="#94a3b8" fontSize="7.5">Shore {midsole.medial_shore_c || 55}C midsole</text>
          <text x="58" y="269" textAnchor="middle" fill="#94a3b8" fontSize="7">{midsole.cushioning_priority === 'heel' ? '★ Cushion priority' : 'Standard cushion'}</text>

          {/* Arch callout — points up */}
          <line x1="293" y1="132" x2="250" y2="38" stroke={colors.arch} strokeWidth="1.3" opacity="0.75"/>
          <circle cx="250" cy="38" r="2.5" fill={colors.arch}/>
          <rect x="166" y="4"  width="168" height="32" rx="5"
                fill="#0c1220" stroke={colors.arch} strokeWidth="1" strokeOpacity="0.7"/>
          <text x="250" y="16" textAnchor="middle" fill={colors.arch}  fontSize="8.5" fontWeight="700">ARCH SUPPORT</text>
          <text x="250" y="29" textAnchor="middle" fill="#94a3b8" fontSize="7.5">{archLabel} ({archHeight}mm) · {arch.medial_post ? 'Medial post ✓' : 'No medial post'}</text>

          {/* Forefoot callout — points up */}
          <line x1="453" y1="124" x2="453" y2="38" stroke={colors.forefoot} strokeWidth="1.3" opacity="0.75"/>
          <circle cx="453" cy="38" r="2.5" fill={colors.forefoot}/>
          <rect x="378" y="4"  width="150" height="32" rx="5"
                fill="#0c1220" stroke={colors.forefoot} strokeWidth="1" strokeOpacity="0.7"/>
          <text x="453" y="16" textAnchor="middle" fill={colors.forefoot} fontSize="8.5" fontWeight="700">FOREFOOT</text>
          <text x="453" y="29" textAnchor="middle" fill="#94a3b8" fontSize="7.5">Lateral Shore {midsole.lateral_shore_c || 45}C · {midsole.cushioning_priority === 'lateral' ? 'Priority ✓' : 'Balanced'}</text>

          {/* Toe callout — points right-up */}
          <line x1="576" y1="157" x2="644" y2="90" stroke={colors.toe} strokeWidth="1.3" opacity="0.75"/>
          <circle cx="644" cy="90" r="2.5" fill={colors.toe}/>
          <rect x="544" y="62" width="154" height="26" rx="5"
                fill="#0c1220" stroke={colors.toe} strokeWidth="1" strokeOpacity="0.7"/>
          <text x="621" y="74" textAnchor="middle" fill={colors.toe} fontSize="8.5" fontWeight="700">TOE BOX</text>
          <text x="621" y="84" textAnchor="middle" fill="#94a3b8" fontSize="7.5">Width: {toeBoxLabel}</text>
        </svg>
      </div>

      {/* Zone detail cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          {
            label: 'Heel Zone', color: colors.heel,
            primary: `${heelDrop}mm heel drop`,
            secondary: midsole.cushioning_priority === 'heel' ? 'Extra cushioning priority' : 'Standard cushioning',
            badge: `Shore ${midsole.medial_shore_c || 55}C`,
          },
          {
            label: 'Arch Support', color: colors.arch,
            primary: `${archLabel} arch · ${archHeight}mm`,
            secondary: arch.medial_post ? 'Medial post reinforcement' : 'Natural arch contour',
            badge: arch.stiffness || 'Custom',
          },
          {
            label: 'Forefoot', color: colors.forefoot,
            primary: `Shore ${midsole.lateral_shore_c || 45}C lateral`,
            secondary: midsole.cushioning_priority === 'lateral' ? 'Lateral cushion priority' : 'Balanced cushioning',
            badge: 'Stability zone',
          },
          {
            label: 'Toe Box', color: colors.toe,
            primary: `${toeBoxLabel} width`,
            secondary: (last.toe_box === 'wide' || last.toe_box === 'extra_wide') ? 'Expanded toe space' : 'Standard toe room',
            badge: last.toe_depth || 'Standard depth',
          },
        ].map(({ label, color, primary, secondary, badge }) => (
          <div key={label}
            className="bg-slate-900/60 rounded-xl p-4 border border-slate-800 hover:border-slate-600 transition-colors"
            style={{ borderLeftColor: color, borderLeftWidth: '3px' }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }}/>
              <span className="text-xs font-bold text-white tracking-wide">{label}</span>
            </div>
            <p className="text-sm font-semibold text-white leading-snug">{primary}</p>
            <p className="text-xs text-slate-400 mt-1 leading-snug">{secondary}</p>
            <span className="inline-block mt-2 px-2 py-0.5 rounded text-xs font-mono"
                  style={{ color, backgroundColor: color + '20' }}>{badge}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
