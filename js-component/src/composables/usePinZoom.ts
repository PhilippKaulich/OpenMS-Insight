/**
 * The "Pin zoom" button in the plot toolbar of the spectrum views.
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
import { ICONS, type PlotTool } from '@/utils/plotTools'

/** Class on the plot element while the zoom is pinned. */
const PINNED_CLASS = 'zoom-pinned'

export function usePinZoom(initial: () => boolean) {
  const pinned = ref(initial())
  let plotElement: HTMLElement | null = null

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

  /** The pin of the plot toolbar, in the View group. */
  function tools(): PlotTool[] {
    return [
      {
        id: 'pin-zoom',
        group: 'view',
        icon: ICONS.pin,
        label: 'Pin zoom',
        help: 'keep the zoom when other data is plotted',
        active: pinned.value,
        run: toggle,
      },
    ]
  }

  return reactive({ pinned, toggle, bind, tools })
}
