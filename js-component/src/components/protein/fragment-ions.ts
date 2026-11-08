// Fragment ion series and fragmentation methods shared by the sequence and
// structure views.
//
// The theoretical masses of the six base series arrive per position as
// `fragment_masses_<a|b|c|x|y|z>` (neutral, monoisotopic; z is the
// even-electron z = y - NH3, as in OpenMS). The radical and hydrogen-shifted
// series that ETD/ECD and UVPD produce are offsets of a base series.

export type BaseIon = 'a' | 'b' | 'c' | 'x' | 'y' | 'z'

export type IonSeries = {
  // Name shown in the menu, the fragment table and the residue tooltip
  name: string
  base: BaseIon
  // Added to the base series' neutral mass
  offset: number
}

// Mass of a hydrogen atom
export const H_ATOM = 1.00782503207

export const BASE_IONS: BaseIon[] = ['a', 'b', 'c', 'x', 'y', 'z']

export const ION_VARIANTS: IonSeries[] = [
  { name: 'a•', base: 'a', offset: H_ATOM },
  { name: 'x•', base: 'x', offset: H_ATOM },
  { name: 'y-1', base: 'y', offset: -H_ATOM },
  { name: 'z•', base: 'z', offset: H_ATOM },
]

// Accepted spellings of the variant names in `settings.ion_types`
const VARIANT_ALIASES: Record<string, string> = {
  'a+1': 'a•', 'a.': 'a•',
  'x+1': 'x•', 'x.': 'x•',
  'y−1': 'y-1',
  'z+1': 'z•', 'z.': 'z•', 'z-dot': 'z•', zp1: 'z•',
}

export function canonicalIonName(name: string): string {
  return VARIANT_ALIASES[name] ?? name
}

export function ionSeries(name: string): IonSeries | undefined {
  const canonical = canonicalIonName(name)
  if ((BASE_IONS as string[]).includes(canonical)) {
    return { name: canonical, base: canonical as BaseIon, offset: 0 }
  }
  return ION_VARIANTS.find((variant) => variant.name === canonical)
}

export function isPrefixIon(base: string): boolean {
  return base === 'a' || base === 'b' || base === 'c'
}

export function isSuffixIon(base: string): boolean {
  return base === 'x' || base === 'y' || base === 'z'
}

// Ion series per fragmentation method, as in ProSight Lite
export const FRAGMENTATION_METHODS: { name: string; ions: string[] }[] = [
  { name: 'CID / HCD', ions: ['b', 'y'] },
  { name: 'ETD / ECD', ions: ['c', 'z•'] },
  { name: 'EThcD', ions: ['b', 'c', 'y', 'z•'] },
  { name: 'UVPD', ions: ['a', 'a•', 'b', 'c', 'x', 'x•', 'y', 'y-1', 'z'] },
]

export const CUSTOM_METHOD = 'Custom'

export function methodIons(method: string | undefined | null): string[] | undefined {
  if (!method) return undefined
  const key = method.replace(/\s+/g, '').toLowerCase()
  const found = FRAGMENTATION_METHODS.find((m) => {
    const names = m.name.replace(/\s+/g, '').toLowerCase()
    return names === key || names.split('/').includes(key)
  })
  return found?.ions
}

// The method whose ion series are exactly the selected ones, else 'Custom'
export function methodForIons(selected: string[]): string {
  const set = new Set(selected.map(canonicalIonName))
  const found = FRAGMENTATION_METHODS.find(
    (m) => m.ions.length === set.size && m.ions.every((ion) => set.has(ion))
  )
  return found?.name ?? CUSTOM_METHOD
}

export type ToleranceUnit = 'ppm' | 'Da'

export function toleranceUnit(unit: string | undefined | null): ToleranceUnit {
  return unit !== undefined && unit !== null && unit.toLowerCase() === 'da' ? 'Da' : 'ppm'
}

// Absolute tolerance (Da) around a mass
export function toleranceDa(mass: number, tolerance: number, unit: ToleranceUnit): number {
  return unit === 'Da' ? tolerance : (Math.abs(mass) * tolerance) / 1e6
}

// The ion series to match for the view's settings: `ion_types` when given,
// else the fragmentation method's, else b and y
export function settingsIons(
  settings: { ion_types?: string[] | null; fragmentation?: string | null } | null | undefined
): IonSeries[] {
  const names = settings?.ion_types ?? methodIons(settings?.fragmentation) ?? ['b', 'y']
  const series: IonSeries[] = []
  names.forEach((name) => {
    const s = ionSeries(name)
    if (s !== undefined && !series.some((known) => known.name === s.name)) series.push(s)
  })
  return series
}

// Spacing of adjacent isotope peaks of a protein-sized mass (averagine).
// Deconvolution can place a monoisotopic mass whole isotopes off; such a mass
// is read as the theoretical one plus k times this spacing.
export const ISOTOPE_SPACING = 1.00235

// Isotope offsets to try for at most `maxErrors` isotope errors, smallest
// first: 0, +1, -1, +2, -2, ...
export function isotopeOffsets(maxErrors: number): number[] {
  const n = Math.max(0, Math.floor(maxErrors || 0))
  const offsets = [0]
  for (let k = 1; k <= n; ++k) offsets.push(k, -k)
  return offsets
}

// The isotope offset k at which `observed` matches `theoretical` + k ×
// ISOTOPE_SPACING within the tolerance, trying `offsets` in order; undefined
// when none does
export function matchIsotopeOffset(
  observed: number,
  theoretical: number,
  offsets: number[],
  tolerance: number,
  unit: ToleranceUnit
): number | undefined {
  for (const k of offsets) {
    const shifted = theoretical + k * ISOTOPE_SPACING
    if (Math.abs(observed - shifted) <= toleranceDa(shifted, tolerance, unit)) return k
  }
  return undefined
}

// "+1", "−2" or "0" for an isotope offset
export function formatIsotopeOffset(k: number): string {
  if (k > 0) return `+${k}`
  if (k < 0) return `−${-k}`
  return '0'
}

// Whether the selected series come from electron-based or photo fragmentation
// (ETD/ECD, EThcD, UVPD): c or z ions, or a radical / hydrogen-shifted series.
// A hydrogen moving between the fragments (proton loss/addition) happens
// there; with collisional b/y (and a/x) ions alone it does not.
export function hydrogenShiftExpected(series: IonSeries[]): boolean {
  return series.some((s) => s.base === 'c' || s.base === 'z' || s.offset !== 0)
}
