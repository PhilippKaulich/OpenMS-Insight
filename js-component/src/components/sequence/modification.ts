/**
 * Modification definitions and extra fragment types for SequenceView.
 */

export type KnownModification =
  | 'Methyl'
  | 'Acetyl'
  | 'Phospho'
  | 'Oxidation'
  | 'Deamidated'
  | 'Amidated'

export const modificationMassMap: Record<KnownModification, number> = {
  Acetyl: 42.010565,
  Methyl: 14.01565,
  Phospho: 79.966331,
  Oxidation: 15.994915,
  Deamidated: 0.984016,
  Amidated: -0.984016,
}

export const potentialModificationMap: Record<string, KnownModification[]> = {
  'N-term': ['Acetyl', 'Methyl', 'Phospho'],
  'C-term': ['Amidated'],
  C: ['Acetyl', 'Methyl', 'Phospho'],
  E: ['Methyl', 'Phospho'],
  D: ['Methyl', 'Phospho'],
  H: ['Methyl', 'Phospho'],
  I: ['Methyl'],
  K: ['Methyl', 'Phospho'],
  L: ['Methyl'],
  M: ['Oxidation'],
  N: ['Methyl'],
  Q: ['Deamidated', 'Methyl'],
  R: ['Methyl', 'Phospho'],
  S: ['Acetyl', 'Methyl', 'Phospho'],
  T: ['Acetyl', 'Methyl', 'Phospho'],
  Y: ['Phospho'],
}

/** A modification of an app-provided library (e.g. pyOpenMS ModificationsDB). */
export interface LibraryModification {
  id: string
  mass: number
  site?: string | null
}

/**
 * Library ids suggested in a site's menu before anything is typed: common
 * biological modifications and sample-preparation artefacts. Ids missing
 * from the library are left out.
 */
export const defaultSuggestedModifications: Record<string, string[]> = {
  'N-term': [
    'Acetyl (Protein N-term)',
    'Acetyl (N-term)',
    'Formyl (Protein N-term)',
    'Methyl (Protein N-term)',
    'Carbamyl (N-term)',
    'Gln->pyro-Glu (N-term Q)',
    'Glu->pyro-Glu (N-term E)',
  ],
  'C-term': ['Amidated (Protein C-term)', 'Amidated (C-term)', 'Methyl (C-term)'],
  C: [
    'Carbamidomethyl (C)',
    'Oxidation (C)',
    'Dioxidation (C)',
    'Trioxidation (C)',
    'Nitrosyl (C)',
    'Cysteinyl (C)',
  ],
  D: ['Methyl (D)'],
  E: ['Methyl (E)', 'Carboxy (E)'],
  H: ['Phospho (H)', 'Methyl (H)', 'Oxidation (H)'],
  K: [
    'Acetyl (K)',
    'Methyl (K)',
    'Dimethyl (K)',
    'Trimethyl (K)',
    'GG (K)',
    'Succinyl (K)',
    'Formyl (K)',
    'Carbamyl (K)',
  ],
  M: ['Oxidation (M)', 'Dioxidation (M)'],
  N: ['Deamidated (N)', 'HexNAc (N)', 'Hex (N)'],
  P: ['Oxidation (P)'],
  Q: ['Deamidated (Q)', 'Methyl (Q)'],
  R: ['Methyl (R)', 'Dimethyl (R)', 'Deamidated (R)'],
  S: ['Phospho (S)', 'Acetyl (S)', 'HexNAc (S)'],
  T: ['Phospho (T)', 'Acetyl (T)', 'HexNAc (T)'],
  W: ['Oxidation (W)', 'Dioxidation (W)'],
  Y: ['Phospho (Y)', 'Nitro (Y)', 'Sulfo (Y)'],
}

/** The built-in modifications as a library, one entry per site, for
 * matching a mass shift to names when the app gives no library. */
export function builtInLibrary(): LibraryModification[] {
  const entries: LibraryModification[] = []
  for (const [site, names] of Object.entries(potentialModificationMap)) {
    for (const name of names) {
      entries.push({ id: `${name} (${site})`, mass: modificationMassMap[name], site })
    }
  }
  return entries
}

/** One entry of a residue's modification menu. */
export interface ModificationOption {
  title: string
  value: string
  mass: number | null
}

/**
 * The modification menu of a residue (one-letter code) or terminus
 * ('N-term' / 'C-term'): None, Custom, then the library's modifications at
 * that site, or the built-in ones without a library.
 */
export function modificationOptions(
  site: string,
  library?: LibraryModification[] | null
): ModificationOption[] {
  const options: ModificationOption[] = [
    { title: 'None', value: 'None', mass: null },
    { title: 'Custom', value: 'Custom', mass: null },
  ]
  if (library && library.length > 0) {
    for (const m of library) {
      if (m.site === site) {
        const mass = m.mass.toLocaleString('en-US', {
          signDisplay: 'always',
          maximumFractionDigits: 4,
        })
        options.push({ title: `${m.id}  ${mass} Da`, value: m.id, mass: m.mass })
      }
    }
    return options
  }
  for (const name of potentialModificationMap[site] ?? []) {
    options.push({ title: name, value: name, mass: modificationMassMap[name] })
  }
  return options
}

/**
 * The suggested entries of a site's menu, in the order of `suggested`
 * (default: `defaultSuggestedModifications`).
 */
export function suggestedOptions(
  site: string,
  options: ModificationOption[],
  suggested?: Record<string, string[]> | null
): ModificationOption[] {
  const ids = (suggested ?? defaultSuggestedModifications)[site] ?? []
  const byValue = new Map(options.map((o) => [o.value, o]))
  return ids.flatMap((id) => byValue.get(id) ?? [])
}

/** Entries whose title contains every word of `query` (case-insensitive);
 * a number also matches the mass shift written to fewer decimals. */
export function searchOptions(options: ModificationOption[], query: string): ModificationOption[] {
  const words = query.toLowerCase().split(/\s+/).filter((w) => w.length > 0)
  if (words.length === 0) return []
  return options.filter((o) => {
    if (o.mass === null) return false
    const title = o.title.toLowerCase()
    return words.every((w) => title.includes(w) || String(o.mass).includes(w.replace(/^\+/, '')))
  })
}

export type ExtraFragmentType = 'water loss' | 'ammonium loss' | 'proton loss/addition'

export const extraFragmentTypeObject: Record<
  ExtraFragmentType | 'default',
  { typeName: string; typeMass: number }[]
> = {
  default: [{ typeName: '', typeMass: 0 }],
  'water loss': [{ typeName: '-H2O', typeMass: -18.0105646863 }],
  'ammonium loss': [{ typeName: '-NH3', typeMass: -17.0265491015 }],
  'proton loss/addition': [
    { typeName: '-H', typeMass: -1.0078250319 },
    { typeName: '+H', typeMass: 1.0078250319 },
  ],
}
