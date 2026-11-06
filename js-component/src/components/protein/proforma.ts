/**
 * ProForma 2.0 notation of the sequence a sequence view shows.
 *
 * Fixed modifications become global ones (`<[Carbamidomethyl]@C>`),
 * modifications on one residue a tag after it (`K[+42.0106]`), those spread
 * over a range an ambiguous range (`(PEP)[+15.9949]`), terminal ones
 * `[x]-SEQ` / `SEQ-[x]`. A modification that overlaps another range is given
 * as an unlocalized one (`[+x]?SEQ`).
 */

export interface ProFormaFixed {
  /** Name, e.g. 'Carbamidomethyl' */
  name: string
  /** A residue letter, 'N-term' or 'C-term' */
  site: string
}

export interface ProFormaModification {
  /** 0-based positions in the full sequence; -1 is the N-terminus and
   * sequence.length the C-terminus */
  start: number
  end: number
  mass: number
  /** Written instead of the mass when given */
  name?: string
}

export interface ProFormaInput {
  /** One-letter residues of the full sequence */
  sequence: string[]
  /** Inclusive bounds of the proteoform within the sequence */
  start: number
  end: number
  fixed?: ProFormaFixed[]
  modifications?: ProFormaModification[]
}

export function formatMass(mass: number): string {
  const text = mass.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
  return mass >= 0 ? `+${text}` : text
}

function tag(mod: ProFormaModification): string {
  return `[${mod.name ?? formatMass(mod.mass)}]`
}

/** A fixed modification id such as 'Carbamidomethyl (C)' or
 * 'Acetyl (Protein N-term)' as a name and site. */
export function fixedFromId(id: string): ProFormaFixed {
  const match = /^(.*) \(([^()]*)\)$/.exec(id)
  if (!match) return { name: id, site: '' }
  const [, name, where] = match
  if (where.includes('N-term')) return { name, site: 'N-term' }
  if (where.includes('C-term')) return { name, site: 'C-term' }
  return { name, site: where }
}

export function toProForma(input: ProFormaInput): string {
  const { sequence } = input
  const first = Math.max(0, input.start)
  const last = Math.min(sequence.length - 1, input.end)
  if (sequence.length === 0 || last < first) return ''

  // Global fixed modifications, sites of one name together
  const sites = new Map<string, string[]>()
  for (const f of input.fixed ?? []) {
    if (!f.name || !f.site) continue
    const list = sites.get(f.name) ?? []
    if (!list.includes(f.site)) list.push(f.site)
    sites.set(f.name, list)
  }
  let prefix = ''
  for (const [name, where] of sites) prefix += `<[${name}]@${where.join(',')}>`

  const nTerm: string[] = []
  const cTerm: string[] = []
  const onResidue = new Map<number, string[]>()
  const ranges: ProFormaModification[] = []
  const unlocalized: string[] = []
  for (const mod of input.modifications ?? []) {
    if (!mod.mass && !mod.name) continue
    if (mod.end < 0 || mod.start === -1) {
      nTerm.push(tag(mod))
    } else if (mod.start >= sequence.length) {
      cTerm.push(tag(mod))
    } else if (mod.start === mod.end) {
      if (mod.start < first || mod.start > last) continue
      const list = onResidue.get(mod.start) ?? []
      list.push(tag(mod))
      onResidue.set(mod.start, list)
    } else {
      const start = Math.max(first, mod.start)
      const end = Math.min(last, mod.end)
      if (end < start) continue
      ranges.push({ ...mod, start, end })
    }
  }
  // Ranges that do not overlap an earlier one, or contain a tagged residue
  ranges.sort((a, b) => a.start - b.start || a.end - b.end)
  const placed: ProFormaModification[] = []
  for (const r of ranges) {
    const prev = placed[placed.length - 1]
    let clash = prev !== undefined && r.start <= prev.end
    for (let i = r.start; i < r.end && !clash; i++) clash = onResidue.has(i)
    if (clash) unlocalized.push(tag(r))
    else placed.push(r)
  }
  const rangeStart = new Map(placed.map((r) => [r.start, r]))

  let body = ''
  let open: ProFormaModification | undefined
  for (let i = first; i <= last; i++) {
    if (!open && rangeStart.has(i)) {
      open = rangeStart.get(i)
      body += '('
    }
    body += sequence[i]
    if (open && i === open.end) {
      body += `)${tag(open)}`
      open = undefined
    }
    body += (onResidue.get(i) ?? []).join('')
  }

  return (
    prefix +
    unlocalized.map((t) => `${t}?`).join('') +
    (nTerm.length ? `${nTerm.join('')}-` : '') +
    body +
    (cTerm.length ? `-${cTerm.join('')}` : '')
  )
}

/** A modification read from ProForma: a mass shift, or a name to look up. */
export interface ParsedModification {
  /** 0-based residue; -1 is the N-terminus and sequence.length the C-terminus */
  index: number
  mass?: number
  name?: string
}

export interface ParsedProForma {
  /** One-letter residues */
  sequence: string
  /** Global fixed modifications by name and site */
  fixed: ProFormaFixed[]
  modifications: ParsedModification[]
}

export class ProFormaError extends Error {}

const RESIDUES = /^[ACDEFGHIKLMNOPQRSTUVWY]$/

/** The content of one `[...]` tag as a mass or a name. Unimod/PSI-MOD name
 * prefixes (`U:`, `M:`) and `Obs:` are dropped; accessions, formulas and
 * glycans are refused, since they need a database lookup. */
function readTag(text: string): { mass?: number; name?: string } {
  // Alternatives (`[Phospho|+79.966]`): the first name and the first mass
  const read: { mass?: number; name?: string } = {}
  for (const part of text.split('|')) {
    const tag = part.trim().replace(/^(U|M|Obs):/i, '')
    if (/^[+-]\d+(\.\d+)?$/.test(tag)) read.mass ??= parseFloat(tag)
    else if (/^(UNIMOD|MOD|RESID|XLMOD|GNO|Formula|Glycan|INFO|#)/i.test(tag)) continue
    else if (tag.length > 0) read.name ??= tag
  }
  if (read.mass === undefined && read.name === undefined) {
    throw new ProFormaError(`Cannot read the modification [${text}]: give a name or a mass such as [+79.9663]`)
  }
  return read
}

/** Reads a ProForma 2.0 proteoform: global fixed modifications
 * (`<[Carbamidomethyl]@C>`), terminal (`[Acetyl]-SEQ`, `SEQ-[Amidated]`) and
 * residue modifications (`K[Acetyl]`, `S[+79.9663]`). Ambiguous ranges,
 * unlocalized and labile modifications, cross-links and chimeras are refused
 * with a message, since a sequence view places a modification on one residue. */
export function parseProForma(input: string): ParsedProForma {
  let text = input.replace(/\s+/g, '')
  if (text.includes('+') && /\/|\+[A-Z]/.test(text)) {
    throw new ProFormaError('Only one proteoform at a time: chimeric spectra are not supported')
  }
  const fixed: ProFormaFixed[] = []
  const globalPattern = /^<\[([^\]]+)\]@([^>]+)>/
  for (let m = globalPattern.exec(text); m; m = globalPattern.exec(text)) {
    const tag = readTag(m[1])
    if (!tag.name) throw new ProFormaError(`Give a fixed modification by name, not mass: <[${m[1]}]@${m[2]}>`)
    for (const site of m[2].split(',')) fixed.push({ name: tag.name, site: site.trim() })
    text = text.slice(m[0].length)
  }
  if (text.startsWith('<')) throw new ProFormaError('Only global modifications of the form <[Name]@C> are supported')
  if (/^\[[^\]]*\]\??\^?\d*\?/.test(text) || /\]\?/.test(text)) {
    throw new ProFormaError('Unlocalized modifications ([x]?) are not supported: place each on a residue')
  }
  if (text.includes('{')) throw new ProFormaError('Labile modifications ({x}) are not supported')
  if (text.includes('(')) throw new ProFormaError('Ambiguous ranges ((ABC)[x]) are not supported: place the modification on one residue')

  const modifications: { index: number; tag: string }[] = []
  const nTerm = /^((?:\[[^\]]+\])+)-/.exec(text)
  if (nTerm) {
    for (const t of nTerm[1].match(/\[[^\]]+\]/g) ?? []) modifications.push({ index: -1, tag: t.slice(1, -1) })
    text = text.slice(nTerm[0].length)
  }
  let cTags: string[] = []
  const cTerm = /-((?:\[[^\]]+\])+)$/.exec(text)
  if (cTerm) {
    cTags = (cTerm[1].match(/\[[^\]]+\]/g) ?? []).map((t) => t.slice(1, -1))
    text = text.slice(0, cTerm.index)
  }

  let sequence = ''
  for (let i = 0; i < text.length; ) {
    const c = text[i].toUpperCase()
    if (text[i] === '[') {
      const end = text.indexOf(']', i)
      if (end < 0) throw new ProFormaError('A modification is missing its closing ]')
      if (sequence.length === 0) throw new ProFormaError('A modification before the first residue needs a dash: [Acetyl]-SEQ')
      modifications.push({ index: sequence.length - 1, tag: text.slice(i + 1, end) })
      i = end + 1
    } else if (RESIDUES.test(c)) {
      sequence += c
      i += 1
    } else {
      throw new ProFormaError(`Unexpected "${text[i]}" at position ${i + 1}`)
    }
  }
  if (sequence.length === 0) throw new ProFormaError('No residues')
  for (const t of cTags) modifications.push({ index: sequence.length, tag: t })

  return {
    sequence,
    fixed,
    modifications: modifications.map((m) => ({ index: m.index, ...readTag(m.tag) })),
  }
}

/** The library id of modification `name` at a site: `Name (K)`, or for a
 * terminus `Name (N-term)`, `Name (Protein N-term)` or `Name (N-term Q)`
 * (`residue`: the terminal residue). Case-insensitive. */
export function findLibraryId(
  name: string,
  site: string,
  ids: string[],
  residue?: string
): string | undefined {
  const lower = new Map(ids.map((id) => [id.toLowerCase(), id]))
  const candidates =
    site === 'N-term' || site === 'C-term'
      ? [`${name} (${site})`, `${name} (Protein ${site})`, `${name} (${site} ${residue ?? ''})`]
      : [`${name} (${site})`]
  for (const c of candidates) {
    const id = lower.get(c.toLowerCase())
    if (id) return id
  }
  // A name that is already a full id
  return lower.get(name.toLowerCase())
}
