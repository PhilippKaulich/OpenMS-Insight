/**
 * The image download button of the Plotly mode bar, in the format the view's
 * `imageFormat` argument names (see imageExport.ts).
 */

import Plotly from 'plotly.js-dist-min'
import { RASTER_SCALE, downloadTitle, type ImageFormat } from './imageExport'

/** Icon of the download button of the spectrum views (LinePlot, DeconvolvedSpectrum). */
export const SPECTRUM_DOWNLOAD_ICON: Plotly.Icon = {
  width: 1792,
  height: 1792,
  path: 'M1152 1376v-160q0-14-9-23t-23-9h-96v-512q0-14-9-23t-23-9h-320q-14 0-23 9t-9 23v160q0 14 9 23t23 9h96v320h-96q-14 0-23 9t-9 23v160q0 14 9 23t23 9h320q14 0 23-9t9-23zm-128-896v-160q0-14-9-23t-23-9h-192q-14 0-23 9t-9 23v160q0 14 9 23t23 9h192q14 0 23-9t9-23zm640 416q0 209-103 385.5t-279.5 279.5-385.5 103-385.5-103-279.5-279.5-103-385.5 103-385.5 279.5-279.5 385.5-103 385.5 103 279.5 279.5 103 385.5z',
}

export interface PlotlyDownloadOptions {
  /** The format, read when the button is clicked */
  format: () => ImageFormat
  /** File name without extension, read when the button is clicked */
  filename: () => string
  /** Size of SVG downloads (raster downloads take the plot's size on screen) */
  width?: number
  height?: number
  icon?: Plotly.Icon
}

/**
 * The download button of a Plotly mode bar (Plotly's own `toImage` button is
 * removed). SVG keeps the fixed size the components have always used;
 * PNG, JPEG and WebP take the plot's current size at RASTER_SCALE.
 */
export function plotlyDownloadButton(options: PlotlyDownloadOptions): Plotly.ModeBarButton {
  const format = options.format()
  return {
    title: downloadTitle(format),
    name: 'toImageSvg',
    icon: options.icon ?? Plotly.Icons.camera,
    click: (plotElement: Plotly.PlotlyHTMLElement) => {
      const current = options.format()
      const raster = current !== 'svg'
      Plotly.downloadImage(plotElement, {
        filename: options.filename(),
        format: current,
        width: raster ? null : (options.width ?? 1200),
        height: raster ? null : (options.height ?? 400),
        ...(raster ? { scale: RASTER_SCALE } : {}),
      } as Plotly.DownloadImgopts)
    },
  }
}
