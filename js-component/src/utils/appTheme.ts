/**
 * The app's theme inside the component's frame: its fonts and its primary colour.
 *
 * Streamlit sends the theme's font family with every render, but the font
 * files are declared by @font-face rules in the app's page, which the frame
 * does not see. A family the frame cannot load falls back to the browser's
 * default, so text in the components did not match the app around them.
 *
 * The frame is served by the same Streamlit server as the page, so it can
 * read the page's style sheets. `adoptAppFonts` copies the @font-face rules of
 * the families it is given into the frame, with their URLs made absolute
 * against the style sheet (or page) that declared them.
 */

const STYLE_ID = 'insight-app-fonts'

/** The family names in a CSS font-family list, without quotes and generic families. */
export function fontFamilies(list: string | undefined): string[] {
  if (!list) return []
  const generic = new Set(['serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui', 'ui-sans-serif', 'ui-serif', 'ui-monospace', 'math', 'emoji'])
  return list
    .split(',')
    .map((name) => name.trim().replace(/^["']|["']$/g, '').trim())
    .filter((name) => name && !generic.has(name.toLowerCase()))
}

/** A @font-face rule's text with every relative url(...) made absolute against `base`. */
export function absoluteFontUrls(cssText: string, base: string): string {
  return cssText.replace(/url\(\s*(["']?)([^"')]+)\1\s*\)/g, (match, quote: string, url: string) => {
    if (/^(data:|blob:|[a-z][a-z0-9+.-]*:\/\/)/i.test(url)) return match
    try {
      return `url("${new URL(url, base).href}")`
    } catch {
      return match
    }
  })
}

interface FontRule {
  family: string
  cssText: string
  base: string
}

function parentFontRules(): FontRule[] {
  let doc: Document
  try {
    if (window.parent === window) return []
    doc = window.parent.document
  } catch {
    return [] // another origin: the page's style sheets are not ours to read
  }
  const rules: FontRule[] = []
  for (const sheet of Array.from(doc.styleSheets)) {
    let cssRules: CSSRuleList
    try {
      cssRules = sheet.cssRules
    } catch {
      continue
    }
    const base = sheet.href || doc.baseURI
    for (const rule of Array.from(cssRules)) {
      if (rule.type !== CSSRule.FONT_FACE_RULE) continue
      const family = (rule as CSSFontFaceRule).style.getPropertyValue('font-family')
      rules.push({ family: fontFamilies(family)[0] ?? '', cssText: rule.cssText, base })
    }
  }
  return rules
}

let adopted = ''

/**
 * Copy the app's @font-face rules for `families` into this frame. Calling it
 * again with the same families does nothing; other families replace the rules.
 */
export function adoptAppFonts(families: string[]): void {
  const wanted = new Set(families.map((f) => f.toLowerCase()))
  const key = [...wanted].sort().join('|')
  if (!key || key === adopted) return
  const css = parentFontRules()
    .filter((rule) => wanted.has(rule.family.toLowerCase()))
    .map((rule) => absoluteFontUrls(rule.cssText, rule.base))
    .join('\n')
  adopted = key
  let style = document.getElementById(STYLE_ID)
  if (!css) {
    style?.remove()
    return
  }
  if (!style) {
    style = document.createElement('style')
    style.id = STYLE_ID
    document.head.appendChild(style)
  }
  style.textContent = css
}

export interface AppTheme {
  font?: string
  codeFont?: string
  headingFont?: string
  primaryColor?: string
}

/**
 * Use the app's theme in this frame: load its fonts and make the text font the
 * default, and publish its primary colour as --insight-primary. With a primary
 * colour the frame's root gets data-insight-themed, which the styles in App.vue
 * key on, so a frame without a theme keeps its own colours.
 */
export function applyAppTheme(theme: AppTheme | undefined): void {
  if (!theme) return
  adoptAppFonts([...fontFamilies(theme.font), ...fontFamilies(theme.codeFont), ...fontFamilies(theme.headingFont)])
  const root = document.documentElement
  if (theme.font) root.style.setProperty('--insight-font', theme.font)
  if (theme.primaryColor) {
    root.style.setProperty('--insight-primary', theme.primaryColor)
    root.dataset.insightThemed = ''
  }
}
