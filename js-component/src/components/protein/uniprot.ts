/**
 * A protein sequence from UniProt by accession, for the Change sequence dialog.
 *
 * The browser asks the UniProt REST API (https://rest.uniprot.org) for the
 * entry as FASTA; isoforms (P0ACF0-2) and FASTA identifiers
 * (sp|P0ACF0|DBHA_ECOLI) are accepted as well.
 */

export const UNIPROT_REST_URL = 'https://rest.uniprot.org'

// https://www.uniprot.org/help/accession_numbers
const ACCESSION = /^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-\d+)?$/

export interface UniProtEntry {
  /** Accession as asked for, with its isoform suffix if any */
  accession: string
  /** Entry name, e.g. DBHA_ECOLI */
  entryName: string
  /** Recommended protein name */
  proteinName: string
  organism: string
  sequence: string
  /** The entry on uniprot.org */
  url: string
}

export class UniProtError extends Error {}

/** The accession in an input (accession, isoform or FASTA identifier), or null. */
export function parseAccession(input: string): string | null {
  const text = input.trim()
  if (!text) return null
  const parts = text.split('|')
  const candidates = parts.length >= 3 && ['sp', 'tr'].includes(parts[0].toLowerCase()) ? [parts[1]] : parts
  for (const candidate of candidates) {
    const word = candidate.trim().split(/\s+/)[0]?.toUpperCase() ?? ''
    if (ACCESSION.test(word)) return word
  }
  return null
}

/** Entry of a UniProt FASTA record. */
export function parseFasta(text: string, accession: string): UniProtEntry {
  const lines = text.trim().split(/\r?\n/)
  const header = lines[0] ?? ''
  if (!header.startsWith('>')) throw new UniProtError(`UniProt sent no sequence for ${accession}`)
  const sequence = lines.slice(1).join('').replace(/\s+/g, '')
  if (!sequence) throw new UniProtError(`UniProt sent no sequence for ${accession}`)
  // >sp|P0ACF0|DBHA_ECOLI DNA-binding protein HU-alpha OS=Escherichia coli (strain K12) OX=83333 GN=hupA PE=1 SV=2
  const match = /^>\w+\|[^|]+\|(\S+)\s+(.*?)(?:\s+OS=(.*?))?(?:\s+OX=.*)?$/.exec(header)
  return {
    accession,
    entryName: match?.[1] ?? accession,
    proteinName: match?.[2] ?? header.slice(1),
    organism: match?.[3] ?? '',
    sequence,
    url: `https://www.uniprot.org/uniprotkb/${accession}/entry`,
  }
}

/** Fetches the entry of an accession; throws UniProtError with a message for the dialog. */
export async function fetchUniProtEntry(
  input: string,
  fetchFn: typeof fetch = fetch,
  baseUrl: string = UNIPROT_REST_URL,
): Promise<UniProtEntry> {
  const accession = parseAccession(input)
  if (accession === null) {
    throw new UniProtError(`'${input.trim()}' is not a UniProt accession (e.g. P0ACF0 or P0ACF0-2)`)
  }
  let response: Response
  try {
    response = await fetchFn(`${baseUrl}/uniprotkb/${accession}.fasta`)
  } catch {
    throw new UniProtError('UniProt could not be reached')
  }
  if (response.status === 400 || response.status === 404) {
    throw new UniProtError(`UniProt has no entry ${accession}`)
  }
  if (!response.ok) throw new UniProtError(`UniProt answered ${response.status}`)
  const text = await response.text()
  if (!text.trim()) throw new UniProtError(`UniProt has no entry ${accession}`)
  return parseFasta(text, accession)
}
