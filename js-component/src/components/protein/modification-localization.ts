// Where on the sequence the matched fragments allow a modification to sit, and
// which modifications its mass shift could be.
//
// A modification set on residue p shifts every N-terminal fragment that
// contains p and every C-terminal fragment that contains p. A fragment that
// matches the spectrum only with the shift places the modification inside it;
// one that matches only without the shift places it outside. The residues
// left between the two bounds are where the fragments put the modification:
// one residue localizes it, several leave it ambiguous.

import { isPrefixIon, toleranceDa, type IonSeries, type ToleranceUnit } from './fragment-ions'
import type { LibraryModification } from '@/components/sequence/modification'

export type LocalizationInput = {
  sequence: string[]
  // First and last residue of the matched sequence (0-based, inclusive)
  start: number
  end: number
  // Theoretical neutral masses per base ion series, per fragment length - 1
  fragmentMasses: (base: string) => number[][]
  series: IonSeries[]
  // Mass offsets of the neutral losses matched besides the plain fragment
  extraMasses: number[]
  observedMasses: number[]
  tolerance: number
  unit: ToleranceUnit
  // Modification masses by residue index (-1: N-terminus, sequence.length:
  // C-terminus)
  modifications: Record<number, number>
  library?: LibraryModification[] | null
  // Mass whose tolerance decides which library entries the shift could be
  // (the precursor or proteoform mass), at most 0.01 Da; 0 compares at 0.01 Da
  referenceMass?: number
}

export type ModificationAlternative = {
  id: string
  // Residues (0-based) of the window where this entry can sit
  positions: number[]
}

export type ModificationLocalization = {
  index: number
  mass: number
  // Residues the fragments allow (inclusive); lo > hi when they disagree
  lo: number
  hi: number
  // Fragments supporting each bound (0: no fragment limits it)
  evidence: number
  // Residues in the window where the modification can sit: library entries
  // of this mass at their sites, every residue for a mass not in the library
  candidates: number[]
  // Library entries of this mass (within tolerance) that fit in the window
  alternatives: ModificationAlternative[]
  ambiguous: boolean
  // The fragments place the modification away from the residue it is set on
  misplaced: boolean
  conflict: boolean
}

function sortedCopy(values: number[]): number[] {
  return Array.from(values).sort((a, b) => a - b)
}

/** Whether a mass in `sorted` lies within `tol` of `mass`. */
export function hasMatch(sorted: number[], mass: number, tol: number): boolean {
  let lo = 0
  let hi = sorted.length
  const target = mass - tol
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (sorted[mid] < target) lo = mid + 1
    else hi = mid
  }
  return lo < sorted.length && sorted[lo] <= mass + tol
}

/** Library entries whose mass is within `tol` of `mass`. */
export function libraryMatches(
  mass: number,
  tol: number,
  library: LibraryModification[] | null | undefined
): LibraryModification[] {
  if (!library) return []
  return library.filter((m) => Math.abs(m.mass - mass) <= tol)
}

// Residues of start..end where a library entry with this site can sit
function sitePositions(site: string | null | undefined, sequence: string[], lo: number, hi: number, start: number, end: number): number[] {
  if (!site) return []
  if (site === 'N-term' || site.startsWith('N-term')) {
    // "N-term Q": the terminus, if that residue is first
    const residue = site.split(/\s+/)[1]
    return lo <= start && start <= hi && (!residue || sequence[start] === residue) ? [start] : []
  }
  if (site === 'C-term' || site.startsWith('C-term')) {
    const residue = site.split(/\s+/)[1]
    return lo <= end && end <= hi && (!residue || sequence[end] === residue) ? [end] : []
  }
  const positions: number[] = []
  for (let i = Math.max(lo, start); i <= Math.min(hi, end); i++) {
    if (sequence[i] === site) positions.push(i)
  }
  return positions
}

/**
 * Localize each modification set on a residue between start and end (the
 * termini are localized by definition).
 */
export function localizeModifications(input: LocalizationInput): ModificationLocalization[] {
  const { start, end, sequence } = input
  const observed = sortedCopy(input.observedMasses)
  const entries = Object.entries(input.modifications)
    .map(([key, mass]) => ({ index: Number(key), mass }))
    .filter((m) => m.mass && !Number.isNaN(m.mass))
  const results: ModificationLocalization[] = []
  if (observed.length === 0) return results
  const extras = input.extraMasses.length > 0 ? input.extraMasses : [0]
  // At most 0.01 Da: at a proteoform's mass a ppm tolerance would let
  // unrelated entries (e.g. +16.031 for +15.995) through
  const refTol =
    input.referenceMass && input.referenceMass > 0
      ? Math.min(Math.max(toleranceDa(input.referenceMass, input.tolerance, input.unit), 0.001), 0.01)
      : 0.01

  for (const mod of entries) {
    if (mod.index < start || mod.index > end) continue
    let lo = start
    let hi = end
    let evidence = 0
    const others = entries.filter((o) => o.index !== mod.index)
    for (const series of input.series) {
      const prefix = isPrefixIon(series.base)
      const masses = input.fragmentMasses(series.base)
      for (let t = 0; t < masses.length; t++) {
        // N-terminal: residues start..start+t; C-terminal: end-t..end
        const boundary = prefix ? start + t : end - t
        if (boundary < start || boundary > end) continue
        let shift = 0
        for (const o of others) {
          if (prefix ? o.index <= boundary : o.index >= boundary) shift += o.mass
        }
        for (const theoretical of masses[t]) {
          for (const extra of extras) {
            const without = theoretical + series.offset + extra + shift
            const withMod = without + mod.mass
            const matchWithout = hasMatch(observed, without, toleranceDa(without, input.tolerance, input.unit))
            const matchWith = hasMatch(observed, withMod, toleranceDa(withMod, input.tolerance, input.unit))
            if (matchWith === matchWithout) continue
            evidence++
            if (prefix) {
              // Inside residues start..boundary, or after them
              if (matchWith) hi = Math.min(hi, boundary)
              else lo = Math.max(lo, boundary + 1)
            } else {
              if (matchWith) lo = Math.max(lo, boundary)
              else hi = Math.min(hi, boundary - 1)
            }
          }
        }
      }
    }
    const conflict = lo > hi
    const matches = libraryMatches(mod.mass, refTol, input.library)
    const alternatives: ModificationAlternative[] = []
    let candidates: number[] = []
    if (!conflict && matches.length > 0) {
      const seen = new Set<number>()
      for (const m of matches) {
        const positions = sitePositions(m.site, sequence, lo, hi, start, end)
        if (positions.length === 0) continue
        alternatives.push({ id: m.id, positions })
        positions.forEach((p) => seen.add(p))
      }
      candidates = [...seen].sort((a, b) => a - b)
    }
    if (!conflict && candidates.length === 0) {
      // A mass the library has no entry for at these residues: any of them
      for (let i = lo; i <= hi; i++) candidates.push(i)
    }
    results.push({
      index: mod.index,
      mass: mod.mass,
      lo,
      hi,
      evidence,
      candidates,
      alternatives,
      ambiguous: !conflict && (candidates.length > 1 || alternatives.length > 1),
      misplaced: !conflict && (mod.index < lo || mod.index > hi),
      conflict,
    })
  }
  return results
}

/** Residue label as in the view: letter and 1-based position. */
export function residueLabel(sequence: string[], index: number): string {
  if (index < 0) return 'N-term'
  if (index >= sequence.length) return 'C-term'
  return `${sequence[index]}${index + 1}`
}

/** One line describing a localization, for tooltips and the list of
 * applied modifications; '' for a localized modification. */
export function describeLocalization(loc: ModificationLocalization, sequence: string[]): string {
  if (loc.conflict) return 'fragments disagree on its position'
  const parts: string[] = []
  if (loc.evidence === 0) parts.push('no matched fragment localizes it')
  const names = [...new Set(loc.alternatives.map((a) => a.id))]
  if (loc.evidence > 0 && loc.candidates.length > 1) {
    const shown = loc.candidates.slice(0, 6).map((i) => residueLabel(sequence, i))
    const more = loc.candidates.length > 6 ? ` and ${loc.candidates.length - 6} more` : ''
    parts.push(`could be on ${shown.join(', ')}${more}`)
  } else if (loc.misplaced && loc.candidates.length === 1) {
    parts.push(`fragments place it on ${residueLabel(sequence, loc.candidates[0])}`)
  } else if (loc.misplaced) {
    parts.push(`fragments place it on ${residueLabel(sequence, loc.lo)}–${residueLabel(sequence, loc.hi)}`)
  }
  if (names.length > 1) {
    parts.push(`mass fits ${names.slice(0, 4).join(', ')}${names.length > 4 ? ` and ${names.length - 4} more` : ''}`)
  }
  return parts.join('; ')
}
