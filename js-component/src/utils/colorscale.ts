/**
 * Colorscales a user can change in the plot (ColorbarLegend.vue).
 *
 * A plot starts on its configured scale: a Plotly name such as "Portland" or
 * a list of [fraction, color] stops. The editor turns it into a ColorbarSpec
 * of one, two or three colors, which `specToScale` turns back into stops for
 * Plotly and for the small colorbar below the plot.
 */

export type ColorStops = Array<[number, string]>

export interface ColorbarSpec {
  /** 1: from the background to the color; 2: low to high; 3: low, middle, high. */
  mode: 1 | 2 | 3
  /** Up to three colors as #rrggbb, in the order low, (middle,) high. */
  colors: string[]
  /** Position of the middle color (mode 3), 0..1. */
  mid: number
}

/** The stops of Plotly's named colorscales (as plotly.js defines them). */
const NAMED: Record<string, ColorStops> = {
  Portland: [
    [0, 'rgb(12,51,131)'],
    [0.25, 'rgb(10,136,186)'],
    [0.5, 'rgb(242,211,56)'],
    [0.75, 'rgb(242,143,56)'],
    [1, 'rgb(217,30,30)'],
  ],
  Viridis: [
    [0, '#440154'],
    [0.06274509803921569, '#48186a'],
    [0.12549019607843137, '#472d7b'],
    [0.18823529411764706, '#424086'],
    [0.25098039215686274, '#3b528b'],
    [0.3137254901960784, '#33638d'],
    [0.3764705882352941, '#2c728e'],
    [0.4392156862745098, '#26828e'],
    [0.5019607843137255, '#21918c'],
    [0.5647058823529412, '#1fa088'],
    [0.6274509803921569, '#28ae80'],
    [0.6901960784313725, '#3fbc73'],
    [0.7529411764705882, '#5ec962'],
    [0.8156862745098039, '#84d44b'],
    [0.8784313725490196, '#addc30'],
    [0.9411764705882353, '#d8e219'],
    [1, '#fde725'],
  ],
  Cividis: [
    [0, 'rgb(0,32,76)'],
    [0.25, 'rgb(64,77,107)'],
    [0.5, 'rgb(124,123,120)'],
    [0.75, 'rgb(188,175,111)'],
    [1, 'rgb(255,233,69)'],
  ],
  RdBu: [
    [0, 'rgb(5,10,172)'],
    [0.35, 'rgb(106,137,247)'],
    [0.5, 'rgb(190,190,190)'],
    [0.6, 'rgb(220,170,132)'],
    [0.7, 'rgb(230,145,90)'],
    [1, 'rgb(178,10,28)'],
  ],
  Bluered: [
    [0, 'rgb(0,0,255)'],
    [1, 'rgb(255,0,0)'],
  ],
  Blues: [
    [0, 'rgb(5,10,172)'],
    [0.35, 'rgb(40,60,190)'],
    [0.5, 'rgb(70,100,245)'],
    [0.6, 'rgb(90,120,245)'],
    [0.7, 'rgb(106,137,247)'],
    [1, 'rgb(220,220,220)'],
  ],
  Reds: [
    [0, 'rgb(220,220,220)'],
    [0.2, 'rgb(245,195,157)'],
    [0.4, 'rgb(245,160,105)'],
    [1, 'rgb(178,10,28)'],
  ],
  Greens: [
    [0, 'rgb(0,68,27)'],
    [0.125, 'rgb(0,109,44)'],
    [0.25, 'rgb(35,139,69)'],
    [0.375, 'rgb(65,171,93)'],
    [0.5, 'rgb(116,196,118)'],
    [0.625, 'rgb(161,217,155)'],
    [0.75, 'rgb(199,233,192)'],
    [0.875, 'rgb(229,245,224)'],
    [1, 'rgb(247,252,245)'],
  ],
  Greys: [
    [0, 'rgb(0,0,0)'],
    [1, 'rgb(255,255,255)'],
  ],
  YlGnBu: [
    [0, 'rgb(8,29,88)'],
    [0.125, 'rgb(37,52,148)'],
    [0.25, 'rgb(34,94,168)'],
    [0.375, 'rgb(29,145,192)'],
    [0.5, 'rgb(65,182,196)'],
    [0.625, 'rgb(127,205,187)'],
    [0.75, 'rgb(199,233,180)'],
    [0.875, 'rgb(237,248,217)'],
    [1, 'rgb(255,255,217)'],
  ],
  YlOrRd: [
    [0, 'rgb(128,0,38)'],
    [0.125, 'rgb(189,0,38)'],
    [0.25, 'rgb(227,26,28)'],
    [0.375, 'rgb(252,78,42)'],
    [0.5, 'rgb(253,141,60)'],
    [0.625, 'rgb(254,178,76)'],
    [0.75, 'rgb(254,217,118)'],
    [0.875, 'rgb(255,237,160)'],
    [1, 'rgb(255,255,204)'],
  ],
  Hot: [
    [0, 'rgb(0,0,0)'],
    [0.3, 'rgb(230,0,0)'],
    [0.6, 'rgb(255,210,0)'],
    [1, 'rgb(255,255,255)'],
  ],
  Jet: [
    [0, 'rgb(0,0,131)'],
    [0.125, 'rgb(0,60,170)'],
    [0.375, 'rgb(5,255,255)'],
    [0.625, 'rgb(255,255,0)'],
    [0.875, 'rgb(250,0,0)'],
    [1, 'rgb(128,0,0)'],
  ],
  Picnic: [
    [0, 'rgb(0,0,255)'],
    [0.1, 'rgb(51,153,255)'],
    [0.2, 'rgb(102,204,255)'],
    [0.3, 'rgb(153,204,255)'],
    [0.4, 'rgb(204,204,255)'],
    [0.5, 'rgb(255,255,255)'],
    [0.6, 'rgb(255,204,255)'],
    [0.7, 'rgb(255,153,255)'],
    [0.8, 'rgb(255,102,204)'],
    [0.9, 'rgb(255,102,102)'],
    [1, 'rgb(255,0,0)'],
  ],
  Electric: [
    [0, 'rgb(0,0,0)'],
    [0.15, 'rgb(30,0,100)'],
    [0.4, 'rgb(120,0,100)'],
    [0.6, 'rgb(160,90,0)'],
    [0.8, 'rgb(230,200,0)'],
    [1, 'rgb(255,250,220)'],
  ],
  Blackbody: [
    [0, 'rgb(0,0,0)'],
    [0.2, 'rgb(230,0,0)'],
    [0.4, 'rgb(230,210,0)'],
    [0.7, 'rgb(255,255,255)'],
    [1, 'rgb(160,200,255)'],
  ],
  Earth: [
    [0, 'rgb(0,0,130)'],
    [0.1, 'rgb(0,180,180)'],
    [0.2, 'rgb(40,210,40)'],
    [0.4, 'rgb(230,230,50)'],
    [0.6, 'rgb(120,70,20)'],
    [1, 'rgb(255,255,255)'],
  ],
  Rainbow: [
    [0, 'rgb(150,0,90)'],
    [0.125, 'rgb(0,0,200)'],
    [0.25, 'rgb(0,25,255)'],
    [0.375, 'rgb(0,152,255)'],
    [0.5, 'rgb(44,255,150)'],
    [0.625, 'rgb(151,255,0)'],
    [0.75, 'rgb(255,234,0)'],
    [0.875, 'rgb(255,111,0)'],
    [1, 'rgb(255,0,0)'],
  ],
}

/** Ready-made colors per number of colors, offered in the editor. */
export const PRESETS: Record<1 | 2 | 3, string[][]> = {
  1: [['#2a78d6'], ['#eb6834'], ['#1baf7a'], ['#6250d6'], ['#e34948']],
  2: [
    ['#2a78d6', '#e34948'],
    ['#3b4cc0', '#eda100'],
    ['#1baf7a', '#6250d6'],
    ['#0f6e56', '#d85a30'],
    ['#6250d6', '#eb6834'],
  ],
  3: [
    ['#2a78d6', '#f0efec', '#e34948'],
    ['#440154', '#21918c', '#fde725'],
    ['#1baf7a', '#eda100', '#e34948'],
    ['#0c3c70', '#9fe1cb', '#fac775'],
    ['#0c3383', '#f2d338', '#d91e1e'],
  ],
}

function parseColor(color: string): [number, number, number] {
  const c = color.trim()
  if (c.startsWith('#')) {
    const hex = c.length === 4 ? c.slice(1).split('').map((d) => d + d).join('') : c.slice(1, 7)
    return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number]
  }
  const m = c.match(/rgba?\(([^)]+)\)/)
  if (m) {
    const [r, g, b] = m[1].split(',').map((v) => parseFloat(v))
    return [r, g, b]
  }
  return [128, 128, 128]
}

export function toHex(color: string): string {
  return (
    '#' +
    parseColor(color)
      .map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0'))
      .join('')
  )
}

/** The color `t` of the way from `a` to `b`. */
export function mix(a: string, b: string, t: number): string {
  const A = parseColor(a)
  const B = parseColor(b)
  return toHex(`rgb(${A.map((v, i) => v + (B[i] - v) * t).join(',')})`)
}

/** Stops of a configured colorscale: a Plotly name or a stop list. */
export function scaleStops(scale: string | ColorStops | undefined, reverse = false): ColorStops {
  let stops: ColorStops
  if (Array.isArray(scale) && scale.length >= 2) stops = scale.map(([p, c]) => [Number(p), c])
  else stops = NAMED[typeof scale === 'string' ? scale : 'Portland'] ?? NAMED.Viridis
  return reverse ? stops.map(([p, c]) => [1 - p, c] as [number, string]).reverse() : stops
}

/** Color at fraction `t` of a stop list. */
export function colorAt(stops: ColorStops, t: number): string {
  const x = Math.max(0, Math.min(1, t))
  for (let i = 1; i < stops.length; i++) {
    if (x <= stops[i][0]) {
      const [p0, c0] = stops[i - 1]
      const [p1, c1] = stops[i]
      return mix(c0, c1, p1 > p0 ? (x - p0) / (p1 - p0) : 0)
    }
  }
  return toHex(stops[stops.length - 1][1])
}

/** The spec the editor starts from: the scale's first, middle and last color. */
export function specFromStops(stops: ColorStops): ColorbarSpec {
  const low = toHex(stops[0][1])
  const high = toHex(stops[stops.length - 1][1])
  if (stops.length <= 2) return { mode: 2, colors: [low, high, mix(low, high, 0.5)], mid: 0.5 }
  return { mode: 3, colors: [low, colorAt(stops, 0.5), high], mid: 0.5 }
}

/** Stops of a spec; `background` is where a one-color scale starts. */
export function specToStops(spec: ColorbarSpec, background = '#ffffff'): ColorStops {
  const [a, b, c] = spec.colors
  if (spec.mode === 1) return [[0, mix(background, a, 0.15)], [1, a]]
  if (spec.mode === 2) return [[0, a], [1, b]]
  const mid = Math.max(0.05, Math.min(0.95, spec.mid))
  return [[0, a], [mid, b], [1, c]]
}

/** CSS gradient of a stop list, left (low) to right (high). */
export function cssGradient(stops: ColorStops): string {
  return `linear-gradient(90deg, ${stops.map(([p, c]) => `${c} ${Math.round(p * 100)}%`).join(', ')})`
}

/** The spec with `mode` colors, keeping as much of the previous look as it can. */
export function withMode(spec: ColorbarSpec, mode: 1 | 2 | 3, neutral: string): ColorbarSpec {
  const [a, b, c] = spec.colors
  const high = spec.mode === 3 ? c : spec.mode === 2 ? b : a
  const low = spec.mode === 1 ? '#2a78d6' : a
  if (mode === 1) return { mode, colors: [high, b, c], mid: spec.mid }
  if (mode === 2) return { mode, colors: spec.mode === 1 ? ['#2a78d6', '#e34948', neutral] : [low, high, b], mid: spec.mid }
  return { mode, colors: [spec.mode === 1 ? '#2a78d6' : low, neutral, spec.mode === 1 ? a : high], mid: 0.5 }
}
