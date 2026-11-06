/**
 * Fragment ions matched by a ProteinSequenceView, marked on a spectrum.
 *
 * The sequence view writes its matched ions to a selection identifier
 * (FragmentMatches); a spectrum view reads them and works out which of its
 * masses and raw peaks they explain.
 */
import type { FragmentMatches, MatchedFragmentIon } from '@/types/component'

export type FragmentKind = 'N' | 'C' | 'I'

/** m/z distance between neighbouring isotopes at charge 1 (C13 - C12). */
const ISOTOPE_SPACING = 1.00235
const PROTON = 1.007276

/** A label drawn on the spectrum: an ion (or ions) at one peak. */
export interface FragmentLabel {
  x: number
  y: number
  text: string
  kind: FragmentKind
}

/** What the fragment ions mark on one spectrum. */
export interface FragmentMarks {
  /** Kind of the ion explaining each mass (by mass index), or undefined */
  massKinds: (FragmentKind | undefined)[]
  /** Kind of the ion explaining each raw peak (by peak index), or undefined */
  peakKinds: (FragmentKind | undefined)[]
  /** Hover text per mass and per raw peak */
  massHover: (string | undefined)[]
  peakHover: (string | undefined)[]
  /** One label per marked mass */
  massLabels: FragmentLabel[]
  /** One label per ion and charge on the raw peaks */
  peakLabels: FragmentLabel[]
}

/** Tolerance in Da at a mass or m/z. */
export function toleranceDa(value: number, tolerance: number, unit: string): number {
  return unit === 'Da' ? tolerance : (Math.abs(value) * tolerance) / 1e6
}

/** Index of the value in `values` (ascending) nearest to `target`, or -1. */
export function nearestIndex(values: number[], target: number): number {
  const n = values.length
  if (n === 0) return -1
  let lo = 0
  let hi = n - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (values[mid] < target) lo = mid + 1
    else hi = mid
  }
  if (lo > 0 && Math.abs(values[lo - 1] - target) <= Math.abs(values[lo] - target)) return lo - 1
  return lo
}

/** Whether `matches` were made on the spectrum whose key is `key`. Unknown on
 * either side counts as the same spectrum. */
export function matchesSpectrum(matches: FragmentMatches | null | undefined, key: unknown): boolean {
  if (!matches || !Array.isArray(matches.fragments)) return false
  if (matches.spectrum === null || matches.spectrum === undefined) return true
  if (key === null || key === undefined) return true
  return String(matches.spectrum) === String(key)
}

/** Sorted copy of `values` with the original indices. */
function sortedWithIndex(values: number[]): { sorted: number[]; index: number[] } {
  const index = values.map((_, i) => i)
  let ascending = true
  for (let i = 1; i < values.length; i++) {
    if (values[i] < values[i - 1]) {
      ascending = false
      break
    }
  }
  if (!ascending) index.sort((a, b) => values[a] - values[b])
  return { sorted: index.map((i) => values[i]), index }
}

/** Order of precedence when ions of different kinds explain one peak. */
const KIND_ORDER: FragmentKind[] = ['N', 'C', 'I']
function preferredKind(a: FragmentKind | undefined, b: FragmentKind): FragmentKind {
  if (a === undefined) return b
  return KIND_ORDER.indexOf(a) <= KIND_ORDER.indexOf(b) ? a : b
}

function charged(name: string, charge: number | undefined): string {
  return charge ? `${name} (${charge}+)` : name
}

/**
 * Masses and raw peaks of a spectrum explained by the matched fragment ions.
 *
 * A fragment with a mass index marks that mass and its signal peaks (the raw
 * peaks assigned to it). An annotated fragment (with charge and m/z) also
 * marks the raw peaks of its isotope envelope: from the peak nearest its m/z,
 * the neighbouring isotopes of its charge as long as each is found within the
 * tolerance.
 */
export function fragmentMarks(
  matches: FragmentMatches,
  masses: number[],
  massIntensities: number[],
  peakMzs: number[],
  peakIntensities: number[],
  signals: number[][][],
): FragmentMarks {
  const massKinds: (FragmentKind | undefined)[] = new Array(masses.length).fill(undefined)
  const peakKinds: (FragmentKind | undefined)[] = new Array(peakMzs.length).fill(undefined)
  const massNames: string[][] = masses.map(() => [])
  const peakNames: string[][] = peakMzs.map(() => [])
  const tolerance = Number(matches.tolerance?.value) || 10
  const unit = matches.tolerance?.unit === 'Da' ? 'Da' : 'ppm'
  const peaks = sortedWithIndex(peakMzs)
  // Raw peak index by m/z, for the signal peaks (whose m/z equal the raw peaks')
  const peakByMz = new Map<number, number>()
  peakMzs.forEach((mz, i) => peakByMz.set(mz, i))

  // Labels on the raw peaks: one per ion name and charge, at its most intense peak
  const peakGroups = new Map<string, { kind: FragmentKind; best: number; text: string }>()
  const markPeak = (peak: number, ion: MatchedFragmentIon, charge: number | undefined) => {
    if (peak < 0 || peak >= peakMzs.length) return
    peakKinds[peak] = preferredKind(peakKinds[peak], ion.kind)
    const text = charged(ion.name, charge)
    if (!peakNames[peak].includes(text)) peakNames[peak].push(text)
    const key = `${ion.name}|${charge ?? ''}`
    const group = peakGroups.get(key)
    if (!group) {
      peakGroups.set(key, { kind: ion.kind, best: peak, text })
    } else if ((peakIntensities[peak] ?? 0) > (peakIntensities[group.best] ?? 0)) {
      group.best = peak
    }
  }

  for (const ion of matches.fragments) {
    const massIndex = ion.massIndex
    if (typeof massIndex === 'number' && massIndex >= 0 && massIndex < masses.length) {
      massKinds[massIndex] = preferredKind(massKinds[massIndex], ion.kind)
      if (!massNames[massIndex].includes(ion.name)) massNames[massIndex].push(ion.name)
      const group = signals[massIndex]
      if (Array.isArray(group)) {
        for (const signal of group) {
          if (!Array.isArray(signal) || signal.length < 4) continue
          // Annotated fragments name one charge: its envelope is found below
          if (ion.charge && signal[3] !== ion.charge) continue
          markPeak(peakByMz.get(signal[1]) ?? -1, ion, ion.charge ?? signal[3])
        }
      }
    }
    // The isotope envelope of an annotated fragment on the raw peaks
    if (ion.charge && ion.mz && peaks.sorted.length > 0) {
      const step = ISOTOPE_SPACING / ion.charge
      const tol = toleranceDa(ion.mz, tolerance, unit)
      const found = (mz: number): number => {
        const at = nearestIndex(peaks.sorted, mz)
        return at >= 0 && Math.abs(peaks.sorted[at] - mz) <= tol ? peaks.index[at] : -1
      }
      // The apex, else the isotope the observed mass puts nearest the m/z
      let start = ion.mz
      if (found(start) < 0 && ion.mass) {
        const mono = ion.mass / ion.charge + PROTON
        start = mono + Math.round((ion.mz - mono) / step) * step
      }
      if (found(start) >= 0) {
        for (const direction of [1, -1]) {
          for (let k = direction === 1 ? 0 : 1; k < 60; k++) {
            const peak = found(start + direction * k * step)
            if (peak < 0) break
            markPeak(peak, ion, ion.charge)
          }
        }
      }
    }
  }

  const massLabels: FragmentLabel[] = []
  massKinds.forEach((kind, i) => {
    if (kind === undefined) return
    massLabels.push({ x: masses[i], y: massIntensities[i] ?? 0, text: massNames[i].join(', '), kind })
  })
  const peakLabels: FragmentLabel[] = []
  peakGroups.forEach(({ kind, best, text }) => {
    peakLabels.push({ x: peakMzs[best], y: peakIntensities[best] ?? 0, text, kind })
  })
  return {
    massKinds,
    peakKinds,
    massHover: massNames.map((names) => (names.length ? names.join(', ') : undefined)),
    peakHover: peakNames.map((names) => (names.length ? names.join(', ') : undefined)),
    massLabels,
    peakLabels,
  }
}

/**
 * Labels that fit: the most intense first, each kept unless a kept label lies
 * within `minSpacingPx` pixels of it, and only those inside `xRange`.
 */
export function visibleLabels(
  labels: FragmentLabel[],
  xRange: number[],
  pixelsPerX: number,
  minSpacingPx: number,
): FragmentLabel[] {
  const inRange = labels.filter((label) => label.x >= xRange[0] && label.x <= xRange[1])
  inRange.sort((a, b) => b.y - a.y)
  const kept: FragmentLabel[] = []
  for (const label of inRange) {
    const px = label.x * pixelsPerX
    if (kept.some((other) => Math.abs(other.x * pixelsPerX - px) < minSpacingPx)) continue
    kept.push(label)
  }
  return kept
}
