import { useRef, useState } from 'react'
import MarkdownView from './Markdown.jsx'

// 선택 영역에 마크다운 문법을 적용하는 툴바 정의
// wrap: [앞, 뒤] 감싸기 / block: 줄 앞에 prefix 부착 / insert: 통째 삽입
const TOOLS = [
  { key: 'h2', label: 'H', title: '제목', wrap: ['## ', ''], block: true },
  { key: 'bold', label: 'B', title: '굵게', wrap: ['**', '**'] },
  { key: 'italic', label: 'I', title: '기울임', wrap: ['*', '*'] },
  { key: 'code', label: '</>', title: '인라인 코드', wrap: ['`', '`'] },
  { key: 'ul', label: '• 목록', title: '목록', wrap: ['- ', ''], block: true },
  { key: 'quote', label: '" 인용', title: '인용', wrap: ['> ', ''], block: true },
  { key: 'link', label: '🔗', title: '링크', wrap: ['[', '](url)'] },
  { key: 'table', label: '▦ 표', title: '표', insert: '\n| 헤더1 | 헤더2 |\n|------|------|\n| 셀 | 셀 |\n' },
]

const VIEWS = [['edit', '편집'], ['split', '분할'], ['preview', '미리보기']]

export default function MdEditor({ value, onChange, minHeight = 360, placeholder = '마크다운으로 본문을 작성하세요' }) {
  const ref = useRef(null)
  const [view, setView] = useState('split')

  function apply(tool) {
    const ta = ref.current
    if (!ta) return
    const s = ta.selectionStart, e = ta.selectionEnd
    const before = value.slice(0, s), sel = value.slice(s, e), after = value.slice(e)
    let next, caret
    if (tool.insert) {
      next = before + tool.insert + after
      caret = s + tool.insert.length
    } else if (tool.block) {
      const [pfx] = tool.wrap
      const block = (sel || '내용').split('\n').map((l) => pfx + l).join('\n')
      next = before + block + after
      caret = s + block.length
    } else {
      const [l, r] = tool.wrap
      const inner = sel || '텍스트'
      next = before + l + inner + r + after
      caret = s + l.length + inner.length
    }
    onChange(next)
    requestAnimationFrame(() => { ta.focus(); ta.setSelectionRange(caret, caret) })
  }

  return (
    <div className="md-editor">
      <div className="md-editor-bar">
        <div className="md-tools">
          {TOOLS.map((t) => (
            <button key={t.key} type="button" className="md-tool" title={t.title}
              onMouseDown={(ev) => ev.preventDefault()} onClick={() => apply(t)}>{t.label}</button>
          ))}
        </div>
        <div className="md-views" role="tablist" aria-label="편집기 보기 모드">
          {VIEWS.map(([v, label]) => (
            <button key={v} type="button" role="tab" aria-selected={view === v}
              className={`md-viewbtn ${view === v ? 'active' : ''}`} onClick={() => setView(v)}>{label}</button>
          ))}
        </div>
      </div>
      <div className={`md-editor-body md-${view}`} style={{ minHeight }}>
        {view !== 'preview' && (
          <textarea ref={ref} className="md-editor-ta" value={value} placeholder={placeholder}
            onChange={(e) => onChange(e.target.value)} spellCheck={false} />
        )}
        {view !== 'edit' && (
          <div className="md-editor-preview">
            {value.trim()
              ? <MarkdownView>{value}</MarkdownView>
              : <p className="muted" style={{ padding: '14px 4px', margin: 0 }}>미리볼 내용이 없습니다.</p>}
          </div>
        )}
      </div>
    </div>
  )
}
