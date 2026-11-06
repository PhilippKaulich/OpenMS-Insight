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
