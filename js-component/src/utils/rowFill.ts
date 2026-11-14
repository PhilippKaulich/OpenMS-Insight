/**
 * Row fill: a component placed in a Streamlit column next to taller columns
 * (`st.columns`) grows so that its column ends where the tallest column of the
 * row ends, instead of leaving empty space below it.
 *
 * The component frame is a same-origin iframe, so the row it sits in can be
 * measured from `window.frameElement`. Every frame that can fill carries
 * `data-insight-row-fill` with the pixels it currently adds; a column is
 * measured without those pixels, so two filling components side by side settle
 * on the natural height of the taller one and shrink again when it shrinks.
 */

const FILL_ATTRIBUTE = 'data-insight-row-fill'
const COLUMN_SELECTOR = '[data-testid="stColumn"], [data-testid="column"]'

function frameElement(): HTMLElement | null {
  try {
    return (window.frameElement as HTMLElement | null) ?? null
  } catch {
    // A cross-origin parent: nothing to measure
    return null
  }
}

/** Pixels the filling frames inside an element currently add. */
function addedPixels(element: Element): number {
  let total = 0
  element.querySelectorAll(`iframe[${FILL_ATTRIBUTE}]`).forEach((frame) => {
    total += Number(frame.getAttribute(FILL_ATTRIBUTE)) || 0
  })
  return total
}

/** Bottom of what a column shows (columns themselves stretch to the row). */
function contentBottom(column: Element): number {
  const block = column.firstElementChild || column
  let bottom = -Infinity
  for (const child of Array.from(block.children)) {
    const rect = child.getBoundingClientRect()
    if (rect.height > 0) bottom = Math.max(bottom, rect.bottom)
  }
  return bottom === -Infinity ? column.getBoundingClientRect().top : bottom
}

/**
 * The pixels this frame should add so its column ends with the tallest column
 * of its row, or 0 when it is not in a row, is alone in it, or is already the
 * tallest. Publish what the frame adds now (`publishRowFill`) before asking.
 */
export function rowFillExtra(): number {
  const frame = frameElement()
  if (!frame) return 0
  const column = frame.closest(COLUMN_SELECTOR)
  const row = column?.parentElement
  if (!column || !row) return 0
  // Only the last filling frame of a column fills, so two never add up
  const fillers = column.querySelectorAll(`iframe[${FILL_ATTRIBUTE}]`)
  if (fillers.length && fillers[fillers.length - 1] !== frame) return 0

  const top = column.getBoundingClientRect().top
  let tallest = -Infinity
  for (const peer of Array.from(row.children)) {
    if (peer === column || !peer.matches(COLUMN_SELECTOR)) continue
    // Columns wrapped below (narrow screens) are not beside this one
    if (Math.abs(peer.getBoundingClientRect().top - top) > 2) continue
    tallest = Math.max(tallest, contentBottom(peer) - addedPixels(peer))
  }
  if (tallest === -Infinity) return 0
  const own = contentBottom(column) - addedPixels(column)
  const extra = Math.floor(tallest - own)
  return extra > 2 ? extra : 0
}

/** Mark this frame as filling and publish the pixels it adds. */
export function publishRowFill(extra: number): void {
  frameElement()?.setAttribute(FILL_ATTRIBUTE, String(Math.max(0, Math.round(extra))))
}

/**
 * Call `onChange` whenever the row this frame sits in may have changed size:
 * any component in the row resizes, or elements are added or removed.
 * Returns a function that stops watching.
 */
/** How long the row has to keep its size before a table fills it again. */
const ROW_SETTLE_MS = 150

export function watchRow(onChange: () => void): () => void {
  const frame = frameElement()
  const row = frame?.closest(COLUMN_SELECTOR)?.parentElement
  if (!frame || !row) return () => {}
  const parentWindow = frame.ownerDocument.defaultView as (Window & typeof globalThis) | null
  if (!parentWindow?.ResizeObserver || !parentWindow.MutationObserver) return () => {}

  // Once the row has kept its size for a moment. Views beside this one pass
  // through other heights while they load (a table laying out its rows is
  // briefly much taller); followed at once, the table grew to each of them and
  // back, and the views below moved with it.
  let timer: ReturnType<typeof setTimeout> | null = null
  const schedule = () => {
    if (timer !== null) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      onChange()
    }, ROW_SETTLE_MS)
  }
  const resizeObserver = new parentWindow.ResizeObserver(schedule)
  const observeAll = () => {
    resizeObserver.disconnect()
    resizeObserver.observe(row)
    row.querySelectorAll('[data-testid="stElementContainer"], .element-container').forEach((element) =>
      resizeObserver.observe(element)
    )
  }
  observeAll()
  const mutationObserver = new parentWindow.MutationObserver(() => {
    observeAll()
    schedule()
  })
  mutationObserver.observe(row, { childList: true, subtree: true })
  return () => {
    if (timer !== null) clearTimeout(timer)
    resizeObserver.disconnect()
    mutationObserver.disconnect()
  }
}
