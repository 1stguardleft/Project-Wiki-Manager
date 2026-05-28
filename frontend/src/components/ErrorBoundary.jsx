import { Component } from 'react'

// 한 화면의 렌더 오류가 앱 전체를 blank로 만들지 않도록 격리한다.
// (location.pathname을 key로 주면 라우트 이동 시 자동으로 리셋됨)
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error) {
    return { error }
  }
  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info)
  }
  render() {
    if (this.state.error) {
      const msg = this.state.error?.message || String(this.state.error)
      return (
        <div className="card" style={{ margin: 8 }} role="alert">
          <h3 style={{ marginTop: 0 }}>화면을 표시하는 중 오류가 발생했습니다</h3>
          <p className="muted" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{msg}</p>
          <button className="secondary" onClick={() => this.setState({ error: null })}>다시 시도</button>
        </div>
      )
    }
    return this.props.children
  }
}
