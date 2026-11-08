/**
 * The image download tool of a plot's toolbar, in the format the view's
 * `imageFormat` argument names (see imageExport.ts).
 */

import type Plotly from 'plotly.js-dist-min'
import { plotly } from '@/plotly/current'
import { RASTER_SCALE, downloadTitle, type ImageFormat } from './imageExport'
import { ICONS, type PlotTool } from './plotTools'

export interface PlotlyDownloadOptions {
  /** Element id of the plot */
  plotId: string
  /** The format, read when the tool is clicked */
  format: () => ImageFormat
  /** File name without extension, read when the tool is clicked */
  filename: () => string
  /** Size of SVG downloads (raster downloads take the plot's size on screen) */
  width?: number
  height?: number
}

/**
 * The download tool (Plotly's own `toImage` button is removed). SVG keeps the
 * fixed size the components have always used; PNG, JPEG and WebP take the
 * plot's current size at RASTER_SCALE.
 */
export function downloadTool(options: PlotlyDownloadOptions): PlotTool {
  const format = options.format()
  return {
    id: 'download',
    group: 'export',
    icon: ICONS.download,
    label: downloadTitle(format),
    short: format.toUpperCase(),
    run: () => {
      const plotElement = document.getElementById(options.plotId)
      if (!plotElement) return
      const current = options.format()
      const raster = current !== 'svg'
      plotly().downloadImage(plotElement as Plotly.PlotlyHTMLElement, {
        filename: options.filename(),
        format: current,
        width: raster ? null : (options.width ?? 1200),
        height: raster ? null : (options.height ?? 400),
        ...(raster ? { scale: RASTER_SCALE } : {}),
      } as Plotly.DownloadImgopts)
    },
  }
}
