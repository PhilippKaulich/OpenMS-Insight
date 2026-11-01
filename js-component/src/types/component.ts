/**
 * Type definitions for component configuration and data structures.
 */

import type { ColumnDefinition, Options as TabulatorOptions } from 'tabulator-tables'

/**
 * Base component arguments shared by all components.
 */
export interface BaseComponentArgs {
  componentType: string
}

/**
 * Interactivity mapping: identifier name -> column name
 */
export type InteractivityMapping = Record<string, string>

/**
 * Pagination state for server-side pagination.
 * Stored in StateManager via paginationIdentifier.
 */
export interface PaginationState {
  page: number
  page_size: number
  total_rows: number
  total_pages: number
  sort_column?: string
  sort_dir?: 'asc' | 'desc'
  toggles?: Record<string, boolean>
}

/**
 * Column metadata for server-side filter dialogs.
 * Precomputed during preprocessing to avoid client-side data scanning.
 */
export interface ColumnMetadata {
  type: 'categorical' | 'numeric' | 'text'
  /** Unique values for categorical columns (max 100 values) */
  unique_values?: (string | number | boolean)[]
  /** Min value for numeric columns */
  min?: number
  /** Max value for numeric columns */
  max?: number
}

/**
 * Table component arguments.
 */
export interface TableComponentArgs extends BaseComponentArgs {
  componentType: 'TabulatorTable'
  columnDefinitions: ColumnDefinition[]
  tableIndexField?: string
  tableLayoutParam?: TabulatorOptions['layout']
  title?: string
  defaultRow?: number
  initialSort?: Array<{ column: string; dir: 'asc' | 'desc' }>
  goToFields?: string[]
  interactivity?: InteractivityMapping
  height?: number
  pagination?: boolean
  pageSize?: number
  /** State key for storing pagination state (page, sort, filters) */
  paginationIdentifier?: string
  /** Column metadata for filter dialogs (precomputed unique values, min/max) */
  columnMetadata?: Record<string, ColumnMetadata>
  /** Title-row checkboxes that restrict rows to a boolean column */
  toggleFilters?: Array<{ label: string; column: string; default: boolean; group_column?: string | null }>
  /** Selections set (null clears) when a row click changes the selection */
  onSelect?: Record<string, unknown>
  /** Clicking the selected row again clears the interactivity selections */
  reclick?: 'unhighlight' | 'deselect'
  highlightDefaultRow?: boolean
  // Where a selected row is scrolled to (default 'center'); when set, a
  // clicked row that is cut off is scrolled there too
  scrollPosition?: 'top' | 'center' | 'bottom' | 'nearest'
  /** Fields hidden until the viewer turns them on in the column menu */
  hiddenColumns?: string[]
  /** New rows are sorted by initialSort again (client-side tables) */
  resetSort?: boolean
  /** Identifiers whose selection change sorts by initialSort again */
  resetSortOn?: string[]
  /** False hides the column menu */
  columnMenu?: boolean
}

/**
 * Line plot component arguments.
 */
export interface LinePlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyLineplotUnified' | 'PlotlyLineplot'
  title: string
  xLabel?: string
  yLabel?: string
  styling?: LinePlotStyling
  config?: LinePlotConfig
  interactivity?: InteractivityMapping
  xColumn?: string // Column name for x-axis values
  yColumn?: string // Column name for y-axis values
  highlightColumn?: string // Column name for highlight mask (boolean)
  annotationColumn?: string // Column name for annotation text
  height?: number // Component height in pixels
}

export interface LinePlotStyling {
  highlightColor?: string
  selectedColor?: string
  unhighlightedColor?: string
  highlightHiddenColor?: string
  annotationColors?: {
    massButton?: string
    selectedMassButton?: string
    sequenceArrow?: string
    selectedSequenceArrow?: string
    background?: string
    buttonHover?: string
  }
}

export interface LinePlotConfig {
  xPosScalingFactor?: number
  xPosScalingThreshold?: number
  enableManualZoom?: boolean
  showChargeLabels?: boolean
  minAnnotationWidth?: number
}

/**
 * Heatmap component arguments.
 */
export interface HeatmapComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyHeatmap'
  title?: string
  svgFilename?: string
  scrollZoom?: boolean
  xColumn: string
  yColumn: string
  intensityColumn: string
  xLabel?: string
  yLabel?: string
  colorscale?: string
  /** Reverse the colorscale direction (default: false) */
  reversescale?: boolean
  zoomIdentifier?: string
  interactivity?: InteractivityMapping
  height?: number
  /** Column for categorical coloring (if set, uses discrete colors instead of colorscale) */
  categoryColumn?: string
  /** Map of category values to colors (e.g., { "Control": "#FF0000", "Treatment": "#00FF00" }) */
  categoryColors?: Record<string, string>
  /** Use log10 transformation for intensity color mapping (default: true) */
  logScale?: boolean
  /** Custom label for the colorbar (default: "Intensity") */
  intensityLabel?: string
}

/**
 * PCA plot component arguments.
 */
export interface PCAPlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyPca'
  /** Column name for the x-axis principal component (e.g. "PC1") */
  xColumn: string
  /** Column name for the y-axis principal component (e.g. "PC2") */
  yColumn: string
  xLabel?: string
  yLabel?: string
  title?: string
  /** Column with the discrete group/condition label used for coloring */
  groupColumn?: string
  /** Map of group values to colors (e.g. { "Control": "#1f77b4", "Treated": "#d62728" }) */
  groupColors?: Record<string, string>
  /** Column with sample identifiers, shown in hover text */
  sampleIdColumn?: string
  /** Draw a 95% confidence ellipse per group (default: true; needs >=3 points/group) */
  showEllipses?: boolean
  interactivity?: InteractivityMapping
  height?: number
}

/**
 * PCA plot data format.
 * Each entry is a row with the PC columns, group column, sample id column,
 * and any additional columns needed for interactivity.
 */
export type PCAData = Record<string, unknown>

/**
 * SequenceView component arguments.
 */
export interface SequenceViewComponentArgs extends BaseComponentArgs {
  componentType: 'SequenceView'
  title?: string
  height?: number
  /** If true (default), observed masses are neutral masses. If false, they are m/z values. */
  deconvolved?: boolean
  /** Max charge state to consider for fragment matching when deconvolved=false. */
  precursorCharge?: number
  /** Interactivity mapping: identifier name -> column name for click handling. */
  interactivity?: InteractivityMapping
}

/**
 * VolcanoPlot component arguments.
 */
export interface VolcanoPlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyVolcano'
  /** Column name for log2 fold change (x-axis) */
  log2fcColumn: string
  /** Column name for -log10(p-value) (y-axis, pre-computed) */
  neglog10pColumn: string
  /** Column name for raw p-value (for hover display) */
  pvalueColumn: string
  /** Column name for point labels (hover and annotations) */
  labelColumn?: string
  title?: string
  xLabel?: string
  yLabel?: string
  /** Color for up-regulated points */
  upColor?: string
  /** Color for down-regulated points */
  downColor?: string
  /** Color for not significant points */
  nsColor?: string
  /** Show threshold lines on plot */
  showThresholdLines?: boolean
  /** Line style for thresholds ("dash", "solid", "dot") */
  thresholdLineStyle?: string
  /** Fold change threshold (|log2FC| >= fcThreshold is significant) */
  fcThreshold?: number
  /** P-value threshold (p < pThreshold is significant) */
  pThreshold?: number
  /** Max number of labels to show on significant points */
  maxLabels?: number
  interactivity?: InteractivityMapping
  height?: number
}

/**
 * Heatmap data format.
 * Each entry is a row with x, y, intensity, and any additional columns
 * needed for interactivity (e.g., scan_id, mass_idx).
 */
export type HeatmapData = Record<string, unknown>

/**
 * Dendrogram line-segment coordinates, in the same format
 * `scipy.cluster.hierarchy.dendrogram(..., no_plot=True)` produces:
 * each index into `icoord`/`dcoord` is one line segment of the tree, as
 * parallel x/y coordinate arrays (4 points per segment).
 */
export interface DendrogramData {
  leafOrder: number[]
  icoord: number[][]
  dcoord: number[][]
}

/**
 * ClusteredHeatmap component arguments.
 */
export interface ClusteredHeatmapComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyClusteredHeatmap'
  idCol: string
  /** Row labels (e.g. protein names), in clustered/rendered order. */
  rowLabels: string[]
  /** Column labels (e.g. sample names), in clustered/rendered order. */
  colLabels: string[]
  /** Row (left-side) dendrogram, or null if row clustering was skipped. */
  rowDendrogram: DendrogramData | null
  /** Column (top) dendrogram, or null if column clustering was skipped. */
  colDendrogram: DendrogramData | null
  /** Group label per column (same order as colLabels), or null entries if no metadata was provided. */
  colGroups: (string | null)[]
  /** Map of group value -> color, for the group annotation bar. */
  groupColors: Record<string, string>
  title?: string
  xLabel?: string
  yLabel?: string
  /** Named Plotly colorscale (e.g. "RdBu") or a custom [fraction, color] stop list. */
  colorscale?: string | Array<[number, string]>
  reversescale?: boolean
  intensityLabel?: string
  height?: number
}

/**
 * ClusteredHeatmap matrix row format.
 * Each entry has the id column plus one numeric field per sample column.
 */
export type ClusteredHeatmapData = Record<string, unknown>

/**
 * VolcanoPlot data format.
 * Each entry is a row with log2fc, neglog10p, pvalue, label, and any
 * additional columns needed for interactivity.
 */
export type VolcanoData = Record<string, unknown>

/**
 * MirrorPlot component arguments.
 */
export interface MirrorPlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyMirrorPlot'
  title?: string
  /** Label shown inside the top half of the figure. */
  titleTop?: string
  /** Label shown inside the bottom half of the figure. */
  titleBottom?: string
  xColumn: string
  yColumn: string
  highlightColumn?: string
  annotationColumn?: string
  xLabel?: string
  yLabel?: string
  interactivity?: InteractivityMapping
  styling?: MirrorPlotStyling
  config?: Record<string, unknown>
  height?: number
}

export interface MirrorPlotStyling {
  unhighlightedColor?: string
  highlightColor?: string
  selectedColor?: string
  annotationColors?: Record<string, string>
}

/**
 * Series plot component arguments.
 */
export interface SeriesPlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlySeries'
  font?: { family?: string; color?: string; size?: number }
  xColumn: string
  yColumn: string
  seriesColumn?: string | null
  /** [series value, legend name] pairs, in drawing order */
  seriesNames?: Array<[string, string]>
  seriesColors?: Record<string, string>
  mode?: 'lines' | 'markers' | 'lines+markers'
  title?: string
  xLabel?: string
  yLabel?: string
  showLegend?: boolean
  fixedYRange?: boolean
  svgFilename?: string
  interactivity?: InteractivityMapping
  height?: number
}

/**
 * 3D plot component arguments.
 */
export interface Plot3DComponentArgs extends BaseComponentArgs {
  componentType: 'Plotly3D'
  titleBold?: boolean
  border?: boolean
  exportFormat?: 'svg' | 'png'
  xColumn: string
  yColumn: string
  zColumn: string
  mode: 'stems' | 'lines'
  seriesColumn?: string | null
  /** [series value, legend name] pairs, in drawing order */
  seriesNames?: Array<[string, string]>
  seriesNameTemplate?: string | null
  seriesColors?: Record<string, string>
  color: string
  traceColumn?: string | null
  title: string
  /** [identifier, title] pairs: first identifier with a selection sets the title */
  selectionTitles?: Array<[string, string]>
  xLabel: string
  yLabel: string
  zLabel: string
  yDtick?: number | null
  cameraEye?: { x: number; y: number; z: number } | null
  showLegend?: boolean
  svgFilename?: string
  height?: number
}

/**
 * Deconvolved spectrum component arguments.
 */
export interface DeconvolvedSpectrumComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyDeconvolvedSpectrum'
  view: 'deconvolved' | 'annotated' | 'ladder'
  title: string
  /** Title while a ladder view shows the raw peaks of a mass */
  drilldownTitle?: string
  /** Selection identifier holding the index of the selected mass */
  massIdentifier?: string | null
  massColumn: string
  massIntensityColumn: string
  peakMzColumn?: string | null
  peakIntensityColumn?: string | null
  signalColumn?: string | null
  styling?: {
    highlightColor?: string
    selectedColor?: string
    unhighlightedColor?: string
    highlightHiddenColor?: string
    annotationColors?: Record<string, string>
  }
  config?: { xPosScalingFactor?: number; xPosScalingThreshold?: number }
  svgFilename?: string
  /** Sequence tag drawn in the ladder view */
  ladder?: { masses: number[]; sequence: string; selectedIndex?: number | null; key?: unknown } | null
  height?: number
}

/**
 * ProteinStructureView component arguments.
 */
export interface ProteinStructureViewComponentArgs extends BaseComponentArgs {
  componentType: 'ProteinStructureView'
  title?: string
  /** Identifier holding the selected residue (0-based position in the sequence) */
  aaIdentifier?: string | null
  /** Fragment ion types and tolerance (ppm) to match with */
  settings?: { tolerance: number; ion_types: string[] } | null
  /** Identifier holding the fragment selected in a sequence view */
  fragmentIdentifier?: string | null
  /** Shown while no entry is selected */
  emptyMessage?: string
  /** Height of the 3D viewer in pixels */
  viewerHeight?: number
  /** Upload and remove buttons (the app stores the files) */
  structureUploads?: boolean
}

/**
 * ProteinSequenceView component arguments.
 */
export interface ProteinSequenceViewComponentArgs extends BaseComponentArgs {
  componentType: 'ProteinSequenceView'
  title?: string
  /** Label of the annotation summary line */
  annotationTitle?: string
  /** Identifier holding the selected mass (index into the spectrum's masses) */
  massIdentifier?: string | null
  /** Identifier holding the selected residue (0-based position in the sequence) */
  aaIdentifier?: string | null
  /** Identifier the change-sequence dialog writes the new sequence to */
  sequenceIdentifier?: string | null
  /** Identifier the selected fragment's bounds are written to */
  fragmentIdentifier?: string | null
  /** Fragment ion types and tolerance (ppm) to start from */
  settings?: { tolerance: number; ion_types: string[] } | null
  /** Sequence tag to mark (0-based residues) */
  tag?: { startPos: number; endPos: number } | null
  svgFilename?: string
  /** Colour of the dialog buttons (default: the theme's primary colour) */
  accentColor?: string | null
  /** Heading of an entry's mass summary (default 'Identification') */
  entryTitle?: string
  /** Label of the entry's observed mass (default 'Observed mass') */
  observedMassLabel?: string
  height?: number
}

/**
 * Union type for all component arguments.
 */
export type ComponentArgs =
  | TableComponentArgs
  | LinePlotComponentArgs
  | HeatmapComponentArgs
  | ClusteredHeatmapComponentArgs
  | PCAPlotComponentArgs
  | SequenceViewComponentArgs
  | VolcanoPlotComponentArgs
  | MirrorPlotComponentArgs
  | SeriesPlotComponentArgs
  | Plot3DComponentArgs
  | DeconvolvedSpectrumComponentArgs
  | ProteinSequenceViewComponentArgs
  | ProteinStructureViewComponentArgs

/**
 * Component layout entry.
 */
export interface ComponentLayout {
  componentArgs: ComponentArgs
}

/**
 * Streamlit data structure received from Python.
 */
export interface StreamlitData {
  components?: ComponentLayout[][]
  selection_store?: Record<string, unknown>
  hash?: string
  [key: string]: unknown
}

/**
 * Table data format.
 */
export type TableData = Record<string, unknown>[]

/**
 * Plot data format for line plots.
 * x_values and y_values contain raw data points.
 * Vue component converts to stick plot format (triplets) for rendering.
 * Additional interactivity columns (e.g., interactivity_peak_id) are added dynamically.
 */
export interface PlotData {
  x_values: number[]
  y_values: number[]
  highlight_mask?: boolean[]
  annotations?: string[]
  // Allow dynamic interactivity columns like interactivity_peak_id
  [key: string]: unknown[] | undefined
}

/**
 * Plot annotation data.
 */
export interface PlotAnnotations {
  shapes: Partial<Plotly.Shape>[]
  annotations: Partial<Plotly.Annotations>[]
  traces: Plotly.Data[]
}
