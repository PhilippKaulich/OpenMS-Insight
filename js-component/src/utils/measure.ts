/**
 * Measuring the distance between two points of a plot: residue matching of a
 * difference and the label texts. Pure functions only, so they can be checked
 * without a browser.
 */

/**
 * Monoisotopic residue masses (Da) of the 20 standard amino acids. Isoleucine
 * and leucine are isobaric and share one entry.
 */
export const STANDARD_RESIDUE_MASSES: Readonly<Record<string, number>> = {
  G: 57.02146,
  A: 71.03711,
  S: 87.03203,
  P: 97.05276,
  V: 99.06841,
  T: 101.04768,
  C: 103.00919,
  'I/L': 113.08406,
  N: 114.04293,
  D: 115.02694,
  Q: 128.05858,
  K: 128.09496,
  E: 129.04259,
  M: 131.04049,
  H: 137.05891,
  F: 147.06841,
  R: 156.10111,
  Y: 163.06333,
  W: 186.07931,
}

/** Charges at which an m/z difference is compared with the residue masses. */
export const MEASURE_CHARGES: readonly number[] = [1, 2]

/** Default per-point matching tolerance in Da. */
export const DEFAULT_MEASURE_TOLERANCE = 0.02

export interface ResidueMatch {
  name: string
  mass: number
  charge: number
  /** Absolute mass error in Da (|delta * charge - mass|). */
  error: number
}

/**
 * Residues whose mass matches `delta` (a difference, positive or negative). A
 * match at charge z means |delta| * z is within `2 * tolerance` of the residue
 * mass: each of the two points may be off by `tolerance`. Matches are ordered
 * by charge, then by mass error. `charges` [1] compares neutral masses only.
 */
export function matchResidues(
  delta: number,
  tolerance: number,
  extraResidues: Record<string, number> = {},
  charges: readonly number[] = MEASURE_CHARGES,
): ResidueMatch[] {
  const absDelta = Math.abs(delta)
  if (!Number.isFinite(absDelta) || absDelta === 0) return []
  const window = 2 * Math.max(tolerance, 0)
  const table: Record<string, number> = { ...STANDARD_RESIDUE_MASSES, ...extraResidues }
  const matches: ResidueMatch[] = []
  for (const charge of charges) {
    const neutral = absDelta * charge
    const atCharge: ResidueMatch[] = []
    for (const [name, mass] of Object.entries(table)) {
      const error = Math.abs(neutral - mass)
      if (error <= window) atCharge.push({ name, mass, charge, error })
    }
    atCharge.sort((a, b) => a.error - b.error || a.mass - b.mass)
    matches.push(...atCharge)
  }
  return matches
}

/**
 * A difference with as many decimals as it needs: three for values from 1 up,
 * three significant digits below 1, one decimal from 10000 up.
 */
export function formatDelta(value: number, signed = false): string {
  const abs = Math.abs(value)
  let text: string
  if (abs === 0) text = '0'
  else if (abs >= 10000) text = abs.toFixed(1)
  else if (abs >= 1) text = abs.toFixed(3)
  else text = abs.toPrecision(3)
  if (!signed || value === 0) return text
  return `${value < 0 ? '−' : '+'}${text}`
}

/**
 * Short name of an axis for a Δ label: the label without a trailing
 * parenthesised note ("PC1 (42.0%)" -> "PC1"), or `fallback` when empty.
 */
export function axisQuantity(label: string | undefined | null, fallback: string): string {
  const name = (label ?? '').replace(/\s+\([^()]*\)\s*$/, '').trim()
  return name || fallback
}

/** Whether an axis label names an m/z axis. */
export function isMzLabel(label: string | undefined | null): boolean {
  const text = (label ?? '').trim().toLowerCase()
  return text.includes('m/z') || text === 'mz'
}

/**
 * Label of a difference along x: "Δm/z 128.059", followed by the matches if
 * any, e.g. "Δm/z 128.059 ≈ Q/K" or "Δm/z 28.511 ≈ G (2+)".
 */
export function formatMeasureLabel(delta: number, matches: ResidueMatch[], quantity = 'm/z'): string {
  const base = `Δ${quantity} ${formatDelta(delta)}`
  if (matches.length === 0) return base
  const charges = Array.from(new Set(matches.map((m) => m.charge))).sort((a, b) => a - b)
  const parts: string[] = []
  for (const charge of charges) {
    const names = matches.filter((m) => m.charge === charge).map((m) => m.name)
    parts.push(charge === 1 ? names.join('/') : `${names.join('/')} (${charge}+)`)
  }
  return `${base} ≈ ${parts.join(', ')}`
}

/**
 * Label of a difference between two points of a scatter plot, from the first
 * point clicked to the second: "Δlog2FC +1.234<br>Δ-log10(p) −0.502".
 */
export function formatPointLabel(dx: number, dy: number, xQuantity: string, yQuantity: string): string {
  return `Δ${xQuantity} ${formatDelta(dx, true)}<br>Δ${yQuantity} ${formatDelta(dy, true)}`
}

/**
 * Cheap identity of plotted points, so a rerun that sends the same points keeps
 * the measurements taken on them while other data drops them.
 */
export function pointsKey(xs: ArrayLike<unknown> | undefined, ys?: ArrayLike<unknown>): string {
  if (!xs || xs.length === 0) return '-'
  let sum = 0
  for (let i = 0; i < xs.length; i++) {
    const x = Number(xs[i])
    const y = ys ? Number(ys[i]) : 0
    if (Number.isFinite(x)) sum += x * 7
    if (Number.isFinite(y)) sum += y
  }
  return `${xs.length}:${String(xs[0])}:${String(xs[xs.length - 1])}:${sum}`
}
