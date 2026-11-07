/**
 * The "Pin zoom" button in Plotly's mode bar of the spectrum views.
 *
 * Unpinned (the default), a view shows each new spectrum at its full extent.
 * Pinned, the zoomed x range stays when other data is plotted, so the same
 * region can be compared across spectra. A double-click still resets the
 * zoom. While pinned the button is highlighted.
 *
 * The component's `keep_zoom` argument sets the initial state; a change of
 * that argument from Python sets it again.
 */

import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import type Plotly from 'plotly.js-dist-min'

/** Mode bar title of the button; also selects it for the active style. */
const PIN_TITLE = 'Pin zoom: keep the zoom when other data is plotted'
/** Class on the plot element while the zoom is pinned. */
const PINNED_CLASS = 'zoom-pinned'

// A push pin (Material Design "pin")
const PIN_PATH = 'M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z'

let styleInstalled = false

/** The highlighted button while the zoom is pinned (once per page). */
function installStyle(): void {
  if (styleInstalled || typeof document === 'undefined') return
  styleInstalled = true
  const style = document.createElement('style')
  style.textContent =
    `.${PINNED_CLASS} .modebar-btn[data-title="${PIN_TITLE}"] path` +
    ' { fill: #ff4b4b !important; }' +
    `.${PINNED_CLASS} .modebar-btn[data-title="${PIN_TITLE}"]` +
    ' { opacity: 1 !important; }'
  document.head.appendChild(style)
}

export function usePinZoom(initial: () => boolean) {
  const pinned = ref(initial())
  let plotElement: HTMLElement | null = null
  installStyle()

  function markPinned(): void {
    plotElement?.classList.toggle(PINNED_CLASS, pinned.value)
  }

  const stopInitial = watch(initial, (value) => {
    pinned.value = value
  })
  watch(pinned, markPinned)
  onBeforeUnmount(stopInitial)

  function toggle(): void {
    pinned.value = !pinned.value
  }

  /** Remember the plot element (after each newPlot) so it carries the state. */
  function bind(element: HTMLElement | null): void {
    plotElement = element
    markPinned()
  }

  function modeBarButtons(): Plotly.ModeBarButton[] {
    return [
      {
        name: 'pinZoom',
        title: PIN_TITLE,
        icon: { width: 24, height: 24, path: PIN_PATH },
        click: () => toggle(),
      },
    ] as unknown as Plotly.ModeBarButton[]
  }

  return reactive({ pinned, toggle, bind, modeBarButtons })
}
