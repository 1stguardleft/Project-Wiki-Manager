// Thin API client for the FastAPI backend (proxied via Vite at /api).

async function jget(path) {
  const r = await fetch(`/api${path}`)
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json()
}
async function jpost(path, body) {
  return jsend('POST', path, body)
}
async function jput(path, body) {
  return jsend('PUT', path, body)
}
async function jdel(path) {
  return jsend('DELETE', path)
}
async function jsend(method, path, body) {
  const r = await fetch(`/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json()
}

export const api = {
  health: () => jget('/health'),
  stats: () => jget('/stats'),
  ingest: (payload) => jpost('/ingest', payload),
  sourceFiles: (subdir) => jget(`/sources/files${subdir ? `?subdir=${encodeURIComponent(subdir)}` : ''}`),
  sourceFile: (path) => jget(`/sources/file?path=${encodeURIComponent(path)}`),
  ingestBatch: (paths, conflict_policy) => jpost('/ingest/batch', { paths, conflict_policy }),
  phases: () => jget('/wiki/phases'),
  pages: (phase) => jget(`/wiki/pages${phase ? `?phase=${phase}` : ''}`),
  page: (slug) => jget(`/wiki/pages/${encodeURIComponent(slug)}`),
  updatePage: (slug, payload) => jput(`/wiki/pages/${encodeURIComponent(slug)}`, payload),
  deletePage: (slug) => jdel(`/wiki/pages/${encodeURIComponent(slug)}`),
  graph: () => jget('/wiki/graph'),
  structure: () => jget('/wiki/structure'),
  resetWiki: () => jpost('/wiki/reset', {}),
  // slug 지정 시 해당 페이지 이력만 (서버가 전체 log.md 에서 필터해 반환)
  log: ({ slug, limit } = {}) => {
    const q = new URLSearchParams()
    if (slug) q.set('slug', slug)
    if (limit) q.set('limit', String(limit))
    const qs = q.toString()
    return jget(`/wiki/log${qs ? '?' + qs : ''}`)
  },
  search: (q, phase) =>
    jget(`/search?q=${encodeURIComponent(q)}${phase ? `&phase=${phase}` : ''}`),
  query: (question) => jpost('/query', { question }),
  kpi: () => jget('/kpi'),
  merges: () => jget('/merges'),
  diff: (id) => jget(`/merges/${id}/diff`),
  revertMerge: (id) => jpost(`/merges/${id}/revert`, {}),
}
