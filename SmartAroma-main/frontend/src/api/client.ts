/** REST helpers — paths go through Vite proxy in dev. */

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!r.ok) {
    const t = await r.text()
    throw new Error(t || r.statusText)
  }
  return r.json() as Promise<T>
}

export async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(await r.text())
  return r.json() as Promise<T>
}

export function statusWebSocketUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/ws/status`
}
