import axios from 'axios'

const BASE = '/api/v1'

const client = axios.create({
  baseURL: BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

export async function createSession(patientId) {
  const { data } = await client.post('/sessions', {
    patient_id: patientId,
    trial_condition: 'barefoot',
    anthropometrics: {
      height_cm: 170,
      mass_kg: 70,
      foot_length_mm: { L: 260, R: 260 },
      foot_width_mm: { L: 95, R: 95 },
    },
  })
  return data
}

export async function uploadVideos(sessionId, anteriorFile, sagittalFile, posteriorFile) {
  const uploads = [
    { file: anteriorFile, view: 'anterior' },
    { file: sagittalFile, view: 'sagittal' },
    { file: posteriorFile, view: 'posterior' },
  ]

  for (const { file, view } of uploads) {
    const form = new FormData()
    form.append('file', file)
    await client.post(
      `/sessions/${sessionId}/uploads?camera_view=${view}`,
      form,
      { headers: { 'Content-Type': undefined }, timeout: 120000 }
    )
  }
}

export async function triggerProcessing(sessionId) {
  const { data } = await client.post(`/sessions/${sessionId}/process`, {})
  return data
}

export async function pollStatus(sessionId) {
  const { data } = await client.get(`/sessions/${sessionId}/status`)
  return data
}

export async function fetchProfile(sessionId) {
  const { data } = await client.get(`/sessions/${sessionId}/profile`)
  // ProfileResponse wraps the GaitPatientProfile under a 'profile' key.
  // Flatten it so callers get one consistent object with all gait fields.
  if (data.profile) {
    return {
      ...data.profile,
      session_id: data.session_id,
      patient_id: data.patient_id,
      status: data.status,
    }
  }
  return data
}
