import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// 본문/답변/미리보기 공용 Markdown 뷰어. react-markdown 은 기본적으로 원시 HTML 을
// 렌더하지 않아 안전하고, remark-gfm 으로 표·체크박스·취소선까지 지원한다.
export default function MarkdownView({ children, className = 'md-body' }) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children || ''}</ReactMarkdown>
    </div>
  )
}
