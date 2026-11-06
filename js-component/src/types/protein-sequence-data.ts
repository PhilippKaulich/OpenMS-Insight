// Data types of the ProteinSequenceView

export type SequenceData = {
  sequence: string[]
  start_position?: number
  end_position?: number
  coverage: number[]
  maxCoverage: number
  theoretical_mass: number
  observed_mass?: number
  modifications? : ModificationData[]
  fixed_modifications: string[]
  fragment_masses_a: number[][]
  fragment_masses_b: number[][]
  fragment_masses_c: number[][]
  fragment_masses_x: number[][]
  fragment_masses_y: number[][]
  fragment_masses_z: number[][]
  annotated_fragments?: AnnotatedFragment[] | null
  annotation_summary?: AnnotationSummary | null
  // The entry was edited in the view (see editIdentifier): its modifications
  // are the user's and are not part of the fragment masses
  edited?: boolean | null
}

// What an edit of an identification writes to editIdentifier. 'edit' starts
// editing the search result, 'reset' goes back to it, 'update' carries the
// edited sequence and modifications (positions in `sequence`, start == end;
// -1 the N-terminus, the sequence length the C-terminus).
export type IdentificationEdit = {
  action: 'edit' | 'update' | 'reset'
  nonce: number
  sequence?: string
  start_position?: number
  end_position?: number
  modifications?: ModificationData[]
}

// A fragment isotope envelope annotated on the raw spectrum by an external tool.
// first/last: 0-based residues of the identified sequence; start/end: the same residues
// in the coordinates of `sequence` (inclusive).
export type AnnotatedFragment = {
  name: string
  ion_type: string
  kind: 'N' | 'C' | 'I'
  length: number
  first: number
  last: number
  start: number
  end: number
  charge: number
  mono_mass: number
  observed_mass: number
  mz: number
  ppm_error: number
  matched_peaks: number
  predicted_peaks: number
  cosine: number
  intensity: number
}

// Entry-level annotation summary; null where the annotating tool gave no value
export type AnnotationSummary = {
  score: number | null
  raw_score: number | null
  matched_fragments: number | null
  fragment_hypotheses: number | null
  covered_bonds: number | null
  coverage: number | null
  calibration_ppm: number | null
  internal_score: number | null
  internal_matched: number | null
  internal_hypotheses: number | null
  authentic_cleavages: number | null
  coverage_with_internal: number | null
}

export type ModificationData = {
  start : number
  end : number
  mass_diff : number
  labels : string
}

// Bounds (positions in `sequence`) of a fragment ion selected in the sequence
// view: N-terminal ions end at `end`, C-terminal ions start at `start`,
// internal ions are cleaved at both
export type FragmentSelection = {
  name: string
  kind: 'N' | 'C' | 'I'
  start: number
  end: number
}

export type FragmentSettings = {
  tolerance : number
  // 'ppm' (default) or 'Da'
  tolerance_unit? : string | null
  // Ion series: a b c x y z and the variants a• x• y-1 z• (also a+1, x+1, z+1)
  ion_types? : string[] | null
  // Fragmentation method choosing the ion series when ion_types is not given:
  // 'CID/HCD' ('CID', 'HCD'), 'ETD/ECD' ('ETD', 'ECD'), 'EThcD' or 'UVPD'
  fragmentation? : string | null
}

export type SequenceDataDictionary = Record<number, SequenceData>

// The spectrum the sequence is matched against: its deconvolved masses and,
// for a fragmentation spectrum, the precursor mass (0 when there is none)
export type MatchedSpectrum = {
  masses: number[]
  precursorMass?: number | null
  // Fragmentation method the spectrum was acquired with (see FragmentSettings)
  fragmentation?: string | null
}

// Sequence tag marked on the sequence (0-based residues, inclusive)
export type SequenceTag = {
  startPos: number
  endPos: number
}
