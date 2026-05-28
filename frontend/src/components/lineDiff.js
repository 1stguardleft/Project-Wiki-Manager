// Line-level diff for the side-by-side (GitHub/GitLab style) merge viewer.
// Returns aligned rows: { type: 'equal'|'add'|'del'|'mod', left, right, leftNo, rightNo }.
// `left`/`right` are null when that side has no line for the row.
// Compare lines ignoring cosmetic-only differences so the LLM re-flowing a
// markdown table (cell padding, separator dash counts) is NOT flagged as a real
// change. Whitespace is collapsed and dash runs (table rules) are normalized;
// the ORIGINAL text is still what gets displayed.
const cmpKey = (s) => s.replace(/\s+/g, ' ').replace(/-{2,}/g, '--').trim()

export function diffRows(before, after) {
  const a = (before || '').replace(/\n$/, '').split('\n')
  const b = (after || '').replace(/\n$/, '').split('\n')
  const ka = a.map(cmpKey)
  const kb = b.map(cmpKey)
  const m = a.length
  const n = b.length

  // LCS length table (suffix DP) — compared on normalized keys
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] = ka[i] === kb[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }

  // backtrack into a linear op list (display original lines)
  const ops = []
  let i = 0
  let j = 0
  while (i < m && j < n) {
    if (ka[i] === kb[j]) { ops.push({ t: 'equal', l: a[i], r: b[j] }); i++; j++ }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push({ t: 'del', l: a[i] }); i++ }
    else { ops.push({ t: 'add', r: b[j] }); j++ }
  }
  while (i < m) ops.push({ t: 'del', l: a[i++] })
  while (j < n) ops.push({ t: 'add', r: b[j++] })

  // pair consecutive del/add runs onto the same rows so changes sit left↔right
  const rows = []
  let k = 0
  while (k < ops.length) {
    if (ops[k].t === 'equal') { rows.push({ type: 'equal', left: ops[k].l, right: ops[k].r }); k++; continue }
    const dels = []
    const adds = []
    while (k < ops.length && ops[k].t !== 'equal') {
      if (ops[k].t === 'del') dels.push(ops[k].l)
      else adds.push(ops[k].r)
      k++
    }
    const max = Math.max(dels.length, adds.length)
    for (let x = 0; x < max; x++) {
      const hasL = x < dels.length
      const hasR = x < adds.length
      rows.push({
        type: hasL && hasR ? 'mod' : hasL ? 'del' : 'add',
        left: hasL ? dels[x] : null,
        right: hasR ? adds[x] : null,
      })
    }
  }

  let ln = 0
  let rn = 0
  for (const r of rows) {
    if (r.left != null) r.leftNo = ++ln
    if (r.right != null) r.rightNo = ++rn
  }
  return rows
}
