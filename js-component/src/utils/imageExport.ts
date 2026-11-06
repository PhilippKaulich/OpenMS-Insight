/**
 * Image downloads of every component: one format for all of them.
 *
 * Python sends the format as the `imageFormat` component argument
 * (`openms_insight.set_image_format()` or a component's `image_format`).
 * SVG stays the default. Raster formats are drawn at RASTER_SCALE times the
 * size the view has on screen, so they stay sharp when zoomed or printed.
 *
 * No Plotly here: the frame of every view loads this module. The mode bar
 * button of the Plotly views is in plotlyDownload.ts.
 */

export type ImageFormat = 'svg' | 'png' | 'jpeg' | 'webp'

export const IMAGE_FORMATS: readonly ImageFormat[] = ['svg', 'png', 'jpeg', 'webp']

/** Pixel ratio of PNG, JPEG and WebP downloads. */
export const RASTER_SCALE = 2

const MIME: Record<ImageFormat, string> = {
  svg: 'image/svg+xml',
  png: 'image/png',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
}

const EXTENSION: Record<ImageFormat, string> = { svg: 'svg', png: 'png', jpeg: 'jpeg', webp: 'webp' }

const LABEL: Record<ImageFormat, string> = { svg: 'SVG', png: 'PNG', jpeg: 'JPEG', webp: 'WebP' }

/** The format a component argument asks for; anything unknown means SVG. */
export function imageFormatOf(value: unknown): ImageFormat {
  return IMAGE_FORMATS.includes(value as ImageFormat) ? (value as ImageFormat) : 'svg'
}

/** Tooltip of a download button, e.g. "Download as PNG". */
export function downloadTitle(format: ImageFormat): string {
  return `Download as ${LABEL[format]}`
}

/** `name` with the extension of `format` (a name ending in .svg loses it). */
export function imageFileName(name: string, format: ImageFormat): string {
  const base = name.replace(/\.(svg|png|jpe?g|webp)$/i, '')
  return `${base}.${EXTENSION[format]}`
}

/** Save a data URL or blob URL under `filename`. */
export function saveImage(url: string, filename: string): void {
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
}

/**
 * Encode a canvas in a raster format. A browser that cannot write WebP
 * (Safari) returns PNG instead; the returned format says which one it is.
 */
export function encodeCanvas(
  canvas: HTMLCanvasElement,
  format: Exclude<ImageFormat, 'svg'>,
): { url: string; format: ImageFormat } {
  const url = canvas.toDataURL(MIME[format], 0.95)
  if (url.startsWith(`data:${MIME[format]}`)) return { url, format }
  return { url: canvas.toDataURL('image/png'), format: 'png' }
}

/**
 * Re-encode a raster image (a PNG data URL) in `format`, on a white
 * background for JPEG, which has no transparency.
 */
export async function convertRaster(
  pngUrl: string,
  format: Exclude<ImageFormat, 'svg'>,
): Promise<{ url: string; format: ImageFormat }> {
  if (format === 'png') return { url: pngUrl, format }
  const image = new Image()
  image.src = pngUrl
  await image.decode()
  const canvas = document.createElement('canvas')
  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight
  const context = canvas.getContext('2d')
  if (!context) return { url: pngUrl, format: 'png' }
  if (format === 'jpeg') {
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)
  }
  context.drawImage(image, 0, 0)
  return encodeCanvas(canvas, format)
}
