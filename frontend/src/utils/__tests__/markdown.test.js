import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '../markdown'

describe('renderMarkdown 白名单渲染', () => {
  it('空输入返回空串', () => {
    expect(renderMarkdown(null)).toBe('')
    expect(renderMarkdown('')).toBe('')
  })

  it('段落与单换行（<br />）', () => {
    const html = renderMarkdown('第一行\n第二行')
    expect(html).toBe('<p>第一行<br />第二行</p>')
  })

  it('空行分段', () => {
    const html = renderMarkdown('段一\n\n段二')
    expect(html).toBe('<p>段一</p>\n<p>段二</p>')
  })

  it('标题映射：# → h3 / ## → h4 / ### → h5', () => {
    const html = renderMarkdown('# 一\n## 二\n### 三')
    expect(html).toContain('<h3>一</h3>')
    expect(html).toContain('<h4>二</h4>')
    expect(html).toContain('<h5>三</h5>')
  })

  it('粗体与斜体', () => {
    const html = renderMarkdown('**重点**和*次要*')
    expect(html).toContain('<strong>重点</strong>')
    expect(html).toContain('<em>次要</em>')
  })

  it('行内代码内部不解析其他语法', () => {
    const html = renderMarkdown('`**不是粗体**`')
    expect(html).toContain('<code>**不是粗体**</code>')
    expect(html).not.toContain('<strong>')
  })

  it('http/https 链接渲染为带 noopener 的 <a>', () => {
    const html = renderMarkdown('[官网](https://example.com)')
    expect(html).toBe('<p><a href="https://example.com" target="_blank" rel="noopener noreferrer">官网</a></p>')
  })

  it('javascript: 链接不渲染为 <a>（白名单外保持原文）', () => {
    const html = renderMarkdown('[点我](javascript:alert(1))')
    expect(html).not.toContain('<a ')
    expect(html).toContain('javascript:alert(1)')
  })

  it('<script> 被转义为纯文本', () => {
    const html = renderMarkdown('<script>alert(1)</script>')
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
  })

  it('<img onerror> 被转义', () => {
    const html = renderMarkdown('<img src=x onerror=alert(1)>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;')
  })

  it('链接 URL 中的引号被转义，无法逃逸 href 属性', () => {
    const html = renderMarkdown('[x](https://a.com/"onmouseover="alert(1))')
    expect(html).not.toContain('"onmouseover')
  })

  it('无序与有序列表及相邻切换', () => {
    const html = renderMarkdown('- 甲\n- 乙\n\n1. 一\n2. 二')
    expect(html).toContain('<ul>\n<li>甲</li>\n<li>乙</li>\n</ul>')
    expect(html).toContain('<ol>\n<li>一</li>\n<li>二</li>\n</ol>')
  })

  it('代码块内容转义且不解析行内语法', () => {
    const html = renderMarkdown('```\n<script>**x**</script>\n```')
    expect(html).toBe('<pre><code>&lt;script&gt;**x**&lt;/script&gt;</code></pre>')
  })

  it('未闭合代码块兜底输出', () => {
    const html = renderMarkdown('```\n代码')
    expect(html).toContain('<pre><code>代码</code></pre>')
  })

  it('列表项内支持行内语法', () => {
    const html = renderMarkdown('- **重点**见[来源](https://a.com)')
    expect(html).toContain('<li><strong>重点</strong>见<a href="https://a.com"')
  })
})
