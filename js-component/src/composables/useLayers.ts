/**
 * Layers of a plot the user can show or hide from the toolbar: the groups of
 * a PCA, the series of a series plot, the categories of a heatmap, ...
 *
 * The component lists its layers (key, name, color) and asks `visible(key)`
 * while it builds its traces. One layer always stays shown, so the plot is
 * never empty. The choice lasts while the component is on the page.
 */
import { reactive } from 'vue'
import { ICONS, type PlotTool } from '@/utils/plotTools'

export interface Layer {
  key: string
  label: string
  color?: string
}

export function useLayers() {
  const state = reactive({ hidden: [] as string[] })

  function visible(key: string): boolean {
    return !state.hidden.includes(key)
  }

  function toggle(key: string, all: Layer[]): void {
    if (visible(key)) {
      const shown = all.filter((layer) => visible(layer.key))
      if (shown.length <= 1) return
      state.hidden = [...state.hidden, key]
    } else {
      state.hidden = state.hidden.filter((k) => k !== key)
    }
  }

  /** The toolbar's "Layers" button; none for fewer than two layers. */
  function tool(layers: Layer[], label = 'Layers'): PlotTool[] {
    if (layers.length < 2) return []
    const shown = layers.filter((layer) => visible(layer.key)).length
    const hiddenCount = layers.length - shown
    return [
      {
        id: 'layers',
        group: 'show',
        icon: ICONS.layers,
        label,
        short: hiddenCount ? `${label} ${shown}/${layers.length}` : label,
        help: 'show or hide parts of the plot',
        menu: [
          {
            kind: 'toggles',
            label: 'Show',
            items: layers.map((layer) => ({
              value: layer.key,
              label: layer.label,
              color: layer.color,
              active: visible(layer.key),
              disabled: visible(layer.key) && shown <= 1,
            })),
            toggle: (key: string) => toggle(key, layers),
          },
        ],
        run: () => {},
      },
    ]
  }

  return { state, visible, toggle, tool }
}
