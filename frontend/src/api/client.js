// Thin API client for the FastAPI backend (proxied via Vite at /api).

async function jget(path) {
  const r = await fetch(`/api${path}`)
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json()
}
async function jpost(path, body) {
  const r = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json()
}

export const api = {
  health: () => jget('/health'),
  stats: () => jget('/stats'),
  ingest: (payload) => jpost('/ingest', payload),
  sourceFiles: (subdir) => jget(`/sources/files${subdir ? `?subdir=${encodeURIComponent(subdir)}` : ''}`),
  ingestBatch: (paths, conflict_policy) => jpost('/ingest/batch', { paths, conflict_policy }),
  phases: () => jget('/wiki/phases'),
  pages: (phase) => jget(`/wiki/pages${phase ? `?phase=${phase}` : ''}`),
  page: (slug) => jget(`/wiki/pages/${encodeURIComponent(slug)}`),
  graph: () => jget('/wiki/graph'),
  log: () => jget('/wiki/log'),
  search: (q, phase) =>
    jget(`/search?q=${encodeURIComponent(q)}${phase ? `&phase=${phase}` : ''}`),
  query: (question) => jpost('/query', { question }),
  merges: () => jget('/merges'),
  diff: (id) => jget(`/merges/${id}/diff`),
  acceptMerge: (id) => jpost(`/merges/${id}/accept`, {}),
  revertMerge: (id) => jpost(`/merges/${id}/revert`, {}),
}
