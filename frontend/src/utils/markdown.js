/**
 * 白名单 Markdown 渲染器（web-frontend-plan D5 安全红线）。
 *
 * LLM 输出不可信：先对输入整体 HTML 转义，再仅按白名单语法生成受控标签——
 * 任何非白名单内容（<script>、内联事件、javascript: 链接等）都保持纯文本。
 * 输入为字符串，输出为安全 HTML 片段（供 v-html 使用，使用处须注明依据本模块）。
 *
 * 支持：标题 #/##/###、段落与换行、无序/有序列表、代码块 ```、
 *       行内代码 `x`、链接 [text](http…)、粗体 **x**、斜体 *x*。
 */

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    // eslint-disable-next-line no-control-regex -- 占位符保留字符，输入中直接剔除
    .replace(/\u0000/g, '')
}

/** 行内语法：入参必须是已转义文本 */
function renderInline(escaped) {
  // 行内代码最先处理并用占位符保护，内部不再解析其他语法
  const codes = []
  // \u0000 作占位符：escapeHtml 已剔除输入中的 \u0000，不存在与原文碰撞
   
  let s = escaped.replace(/`([^`]+)`/g, (_m, code) => {
    codes.push(code)
    return `\u0000${codes.length - 1}\u0000`
  })
  // 链接白名单：仅 http/https，其余（javascript:/data:/…）保持原文
  s = s.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  )
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  // eslint-disable-next-line no-control-regex
  s = s.replace(/\u0000(\d+)\u0000/g, (_m, i) => `<code>${codes[Number(i)]}</code>`)
  return s
}

export function renderMarkdown(src) {
  if (src == null) return ''
  const lines = String(src)
    .replace(/\r\n?/g, '\n')
    .split('\n')

  const html = []
  let para = [] // 段落缓冲（单换行 → <br />）
  let listTag = null // 'ul' | 'ol'
  let inCode = false
  let codeLines = []

  const flushPara = () => {
    if (para.length) {
      html.push(`<p>${para.map(renderInline).join('<br />')}</p>`)
      para = []
    }
  }
  const closeList = () => {
    if (listTag) {
      html.push(`</${listTag}>`)
      listTag = null
    }
  }
  const openList = (tag) => {
    if (listTag !== tag) {
      closeList()
      html.push(`<${tag}>`)
      listTag = tag
    }
  }

  for (const raw of lines) {
    const line = escapeHtml(raw) // 一切匹配都在转义后的文本上进行
    const trimmed = raw.trim()

    if (inCode) {
      if (trimmed.startsWith('```')) {
        html.push(`<pre><code>${codeLines.join('\n')}</code></pre>`)
        codeLines = []
        inCode = false
      } else {
        codeLines.push(line)
      }
      continue
    }

    if (trimmed.startsWith('```')) {
      flushPara()
      closeList()
      inCode = true
      continue
    }
    if (!trimmed) {
      flushPara()
      closeList()
      continue
    }

    // 标题：# → h3 / ## → h4 / ### → h5（h1/h2 保留给页面结构）
    const heading = /^(#{1,3})\s+(.+)$/.exec(line)
    if (heading) {
      flushPara()
      closeList()
      const level = heading[1].length + 2
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      continue
    }

    const bullet = /^\s*[-*]\s+(.+)$/.exec(line)
    if (bullet) {
      flushPara()
      openList('ul')
      html.push(`<li>${renderInline(bullet[1])}</li>`)
      continue
    }

    const ordered = /^\s*\d+\.\s+(.+)$/.exec(line)
    if (ordered) {
      flushPara()
      openList('ol')
      html.push(`<li>${renderInline(ordered[1])}</li>`)
      continue
    }

    para.push(line)
  }

  if (inCode) {
    html.push(`<pre><code>${codeLines.join('\n')}</code></pre>`) // 未闭合代码块兜底
  }
  flushPara()
  closeList()
  return html.join('\n')
}
