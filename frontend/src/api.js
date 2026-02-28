const BASE = '/api'

async function request(method, path, body = null) {
  const controller = new AbortController()
  // GET requests time out after 30 s; POST (analysis) after 300 s
  const timeoutMs = method === 'GET' ? 30_000 : 300_000
  const timerId = setTimeout(() => controller.abort(), timeoutMs)

  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    signal: controller.signal,
  }
  if (body) opts.body = JSON.stringify(body)

  try {
    const res = await fetch(`${BASE}${path}`, opts)
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`${res.status}: ${text}`)
    }
    return res.json()
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Превышено время ожидания')
    }
    throw err
  } finally {
    clearTimeout(timerId)
  }
}

export async function getPresets() {
  return request('GET', '/presets')
}

export async function getHealth() {
  return request('GET', '/health')
}

export async function analyze(params) {
  return request('POST', '/analyze', { ...params, async_mode: true })
}

export async function getJobResult(jobId) {
  return request('GET', `/analyze/${jobId}`)
}

export async function analyzeDrift(params) {
  return request('POST', '/drift', params)
}

export async function analyzeRoute(params) {
  return request('POST', '/route', params)
}

export async function pollJob(jobId, onProgress, intervalMs = 2000, maxAttempts = 150) {
  for (let i = 0; i < maxAttempts; i++) {
    const result = await getJobResult(jobId)
    if (result.status === 'done') return result.result
    if (result.status === 'error') throw new Error(result.error || 'Analysis failed')
    if (onProgress) onProgress(result.status, i)
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  throw new Error('Analysis timed out')
}

export function downloadBase64(b64, filename, mime) {
  const bytes = atob(b64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const blob = new Blob([arr], { type: mime })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}
