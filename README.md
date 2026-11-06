# OpenMS-Insight

[![PyPI version](https://badge.fury.io/py/openms-insight.svg)](https://badge.fury.io/py/openms-insight)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/t0mdavid-m/OpenMS-Insight/actions/workflows/tests.yml/badge.svg)](https://github.com/t0mdavid-m/OpenMS-Insight/actions/workflows/tests.yml)

Interactive visualization components for mass spectrometry data in Streamlit, backed by Vue.js.

## Features

- **Cross-component selection linking** via shared identifiers
- **Memory-efficient preprocessing** via subprocess isolation
- **Automatic disk caching** with config-based invalidation
- **Cache reconstruction** - components can be restored from cache without re-specifying configuration
- **Table component** (Tabulator.js) with server-side pagination, filtering, sorting, go-to, CSV export
- **Line plot component** (Plotly.js) with highlighting, annotations, zoom
- **Mirror plot component** for paired-spectrum comparison with independent per-side filtering and shared click selection
- **Heatmap component** (Plotly scattergl) with multi-resolution downsampling for millions of points
- **Clustered heatmap component** (Plotly) for feature-by-sample matrices, with row/column dendrograms and a group annotation bar
- **Volcano plot component** for differential expression visualization with significance thresholds
- **PCA component** for sample-level dimensionality reduction with per-group coloring and confidence ellipses
- **Sequence view component** for peptide visualization with fragment ion matching and auto-zoom
- **Deconvolved spectrum component** for charge-state deconvolution results: deconvolved masses, their annotated raw peaks per charge state, and sequence tag ladders
- **Series plot component** for continuous curves (score densities, calibration curves, chromatogram overlays)
- **3D plot component** drawing points as stems (e.g. isotope peaks across charge states) or as traces (e.g. the mass traces of a feature)
- **Protein sequence view component** with matched fragment ions, tag coverage, truncations, modifications and internal fragments, linked to a fragment table
- **Protein structure view component** (3Dmol.js) colouring a PDB or mmCIF structure by the fragment evidence of a sequence entry, with in-view upload and removal of structure files
- **Batched reruns** (`defer_reruns()`) so a click across many linked components costs one script rerun
- **Differential expression analysis** (`openms_insight.analysis`) - filtering, imputation, normalization, statistical testing and GO enrichment over Polars LazyFrames

## Installation

```bash
pip install openms-insight
```

GO enrichment ([`openms_insight.analysis.enrichment`](#go-enrichment)) needs two
additional packages:

```bash
pip install "openms-insight[analysis]"
```

Everything else - every component, and the rest of `openms_insight.analysis` -
works with the base install.

## Quick Start

```python
import streamlit as st
from openms_insight import Table, LinePlot, Heatmap, VolcanoPlot, StateManager

# Create state manager for cross-component linking
state_manager = StateManager()

# Create a table - clicking a row sets the 'item' selection
table = Table(
    cache_id="items_table",
    data_path="items.parquet",
    interactivity={"item": "item_id"},
    column_definitions=[
        {"field": "item_id", "title": "ID", "sorter": "number"},
        {"field": "name", "title": "Name"},
    ],
)
table(state_manager=state_manager)

# Create a linked plot - filters by the selected 'item'
plot = LinePlot(
    cache_id="values_plot",
    data_path="values.parquet",
    filters={"item": "item_id"},
    x_column="x",
    y_column="y",
)
plot(state_manager=state_manager)
```

## Cross-Component Linking

Components communicate through **identifiers** using three mechanisms:

- **`filters`**: INPUT - filter this component's data by the selection
- **`filter_defaults`**: INPUT - default value when selection is None
- **`interactivity`**: OUTPUT - set a selection when user clicks

```python
# Master table: no filters, sets 'spectrum' on click
master = Table(
    cache_id="spectra",
    data_path="spectra.parquet",
    interactivity={"spectrum": "scan_id"},  # Click -> sets spectrum=scan_id
)

# Detail table: filters by 'spectrum', sets 'peak' on click
detail = Table(
    cache_id="peaks",
    data_path="peaks.parquet",
    filters={"spectrum": "scan_id"},  # Filters where scan_id = selected spectrum
    interactivity={"peak": "peak_id"},  # Click -> sets peak=peak_id
)

# Plot: filters by 'spectrum', highlights selected 'peak'
plot = LinePlot(
    cache_id="plot",
    data_path="peaks.parquet",
    filters={"spectrum": "scan_id"},
    interactivity={"peak": "peak_id"},
    x_column="mass",
    y_column="intensity",
)

# Table with filter defaults - shows unannotated data when no identification selected
annotations = Table(
    cache_id="annotations",
    data_path="annotations.parquet",
    filters={"identification": "id_idx"},
    filter_defaults={"identification": -1},  # Use -1 when identification is None
)
```

---

## Components

### Table

Interactive table using Tabulator.js with filtering dialogs, sorting, pagination, and CSV export.

```python
Table(
    cache_id="spectra_table",
    data_path="spectra.parquet",
    interactivity={"spectrum": "scan_id"},
    column_definitions=[
        {"field": "scan_id", "title": "Scan", "sorter": "number"},
        {
            "field": "rt",
            "title": "RT (min)",
            "sorter": "number",
            "hozAlign": "right",
            "formatter": "money",
            "formatterParams": {"precision": 2, "symbol": ""},
        },
        {"field": "precursor_mz", "title": "m/z", "sorter": "number"},
    ],
    index_field="scan_id",
    go_to_fields=["scan_id"],
    initial_sort=[{"column": "scan_id", "dir": "asc"}],
    default_row=0,
    pagination=True,
    page_size=100,
)
```

**Key parameters:**
- `column_definitions`: List of Tabulator column configs (field, title, sorter, formatter, etc.)
- `index_field`: Column used as unique row identifier (default: 'id')
- `go_to_fields`: Columns available in "Go to" navigation
- `initial_sort`: Default sort configuration
- `pagination`: Enable server-side pagination (default: True). Only the current page of data is sent to the browser, dramatically reducing memory usage for large datasets.
- `page_size`: Rows per page (default: 100)
- `hidden_columns`: Columns that start hidden. The viewer can show them, or hide any other column, from the column menu in the table toolbar. Their choice is kept in their browser, per table.
- `search`: A search box in the toolbar. `True` searches the text columns, a list of column names searches those (they need not be shown). Rows must contain every word, in any of the columns; case is ignored and words are matched literally. `search_placeholder` sets its placeholder.
- `numeric_filters`: Numeric columns offered in the filter dialog as a one-sided threshold, with one-click suggested values and an optional default.
- `keyboard_navigation`: Step through the rows with the keyboard once a row is clicked or the table is tabbed to (default: True). Up and Down select the previous and next row, Page Up and Page Down move by the rows in view, Home and End go to the first and last row, across pages. The row reached is highlighted at once and selected, as if clicked, once no key has been pressed for 200 ms, so holding a key down reruns the app once rather than for every row. Keys typed in the search box or a dialog are left alone. `False` turns it off; it does not affect the cache.

**Filters.** The filter button opens a dialog with a filter per column: values to
keep, a text pattern, or for numbers "at least", "at most" or a range. Every
filter, and the search, runs in Python over the whole table. The filters in force
show as chips under the toolbar, each removable, with "Clear all"; they are kept
when the table is drawn again.

```python
Table(
    cache_id="proteins",
    data=proteins,
    search=True,  # or ["accession", "gene", "description"]
    search_placeholder="Accession, gene or protein name",
    numeric_filters={
        "q_value": {
            "op": "<=",
            "suggestions": [{"value": 0.01, "label": "1 % (run)"}, 0.001],
        },
        "peptides": {"op": ">=", "suggestions": [2, 3], "default": 2},
    },
)
```

**Custom formatters:**
In addition to Tabulator's built-in formatters, these custom formatters are available:
- `scientific`: Exponential notation (e.g., "1.23e-05") - use `formatterParams: {precision: 3}`
- `signed`: Explicit +/- prefix (e.g., "+1.234") - use `formatterParams: {precision: 3, showPositive: true}`
- `badge`: Colored pill/badge for categorical values - use `formatterParams: {colorMap: {"Up": "#FF0000"}, defaultColor: "#888"}`

```python
column_definitions = [
    {
        "field": "pvalue",
        "title": "P-value",
        "formatter": "scientific",
        "formatterParams": {"precision": 2},
    },
    {
        "field": "log2fc",
        "title": "Log2 FC",
        "formatter": "signed",
        "formatterParams": {"precision": 3},
    },
    {
        "field": "regulation",
        "title": "Status",
        "formatter": "badge",
        "formatterParams": {
            "colorMap": {"Up": "#d62728", "Down": "#1f77b4", "NS": "#888888"}
        },
    },
]
```

**CSV export.** The table's download button exports every row that passes the
current filters, in the current sort order, with every column of the data, not
only the page on screen and the columns in `column_definitions`. Displayed
columns come first. The same export is available in Python:

```python
table.export_data()  # whole table, initial sort
table.export_data(state)  # as rendered for this selection state
```

### LinePlot

Stick-style line plot using Plotly.js for mass spectra visualization.

```python
LinePlot(
    cache_id="spectrum_plot",
    data_path="peaks.parquet",
    filters={"spectrum": "scan_id"},
    interactivity={"peak": "peak_id"},
    x_column="mass",
    y_column="intensity",
    highlight_column="is_annotated",
    annotation_column="ion_label",
    title="MS/MS Spectrum",
    x_label="m/z",
    y_label="Intensity",
    styling={
        "highlightColor": "#E4572E",
        "selectedColor": "#F3A712",
        "unhighlightedColor": "lightblue",
    },
)
```

**Key parameters:**
- `x_column`, `y_column`: Column names for x/y values
- `highlight_column`: Boolean/int column indicating which points to highlight
- `annotation_column`: Text column for labels on highlighted points
- `styling`: Color configuration dict

### MirrorPlot

Two stick-style spectra rendered against a shared x-axis with the bottom half flipped, used for comparing paired spectra (experimental vs. theoretical, sample vs. reference, MS1 vs. MS2 fragments). Each half is filtered independently, while clicks on either half feed into one shared selection.

```python
from openms_insight import MirrorPlot

mirror = MirrorPlot(
    cache_id="mirror",
    data_path="peaks.parquet",
    filters_top={"spectrum_a": "scan_id"},  # top half follows spectrum_a
    filters_bottom={"spectrum_b": "scan_id"},  # bottom half follows spectrum_b
    interactivity={"selected_peak": "peak_id"},  # click in either half -> shared
    x_column="mass",
    y_column="intensity",  # positive for both halves
    highlight_column="is_annotated",
    annotation_column="ion_label",
    title_top="Experimental",
    title_bottom="Reference",
    x_label="m/z",
    y_label="Intensity",
)
mirror(state_manager=state_manager, height=600)
```

**Key parameters:**
- `filters_top` / `filters_bottom`: Per-side filter mappings (independent selections drive each half)
- `filter_defaults_top` / `filter_defaults_bottom`: Per-side default values when the corresponding selection is `None`
- `interactivity`: Shared across both halves — a click in either half writes the same identifier
- `x_column`, `y_column`: Shared schema. Provide y values as positive numbers; the bottom half is flipped at render time
- `highlight_column`, `annotation_column`: Shared schema for highlights and label text
- `title_top`, `title_bottom`: In-figure labels for each half (rendered inside the plot, not above it)
- `styling`: Color dict with `highlightColor`, `selectedColor`, `unhighlightedColor` (same defaults as LinePlot)
- `svg_filename`: File name for the modebar's "Download as SVG" button (default: `title`, then `mirror_plot`)
- `measure`, `measure_tolerance`, `measure_residues`: The measure tool, on by default (see [Measuring](#measuring-measure))

**Behavior:**
- The y-axis auto-rescales to the maximum visible peak when zooming, and overlapping annotation labels are re-evaluated at the new pixel/data ratio so previously hidden labels reappear when there is room (matches LinePlot's zoom behavior)
- Tick labels show absolute intensity on both sides — the bottom half is flipped only for layout, not for the displayed values
- Marker traces are kept in addition to stick shapes so Plotly fires `plotly_click` events; the click handler picks the side via `curveNumber` and routes the row's interactivity column value to the shared selection
- In measure mode the two peaks of a measurement must be in the same half; a click in the other half starts a new measurement there
- `set_top_dynamic_annotations(...)` / `set_bottom_dynamic_annotations(...)` allow another component (e.g. a `SequenceView`) to push fragment-ion annotations into one half without invalidating the cache

### Heatmap

2D scatter heatmap using Plotly scattergl with multi-resolution downsampling for large datasets (millions of points).

```python
Heatmap(
    cache_id="peaks_heatmap",
    data_path="all_peaks.parquet",
    x_column="retention_time",
    y_column="mass",
    intensity_column="intensity",
    interactivity={"spectrum": "scan_id", "peak": "peak_id"},
    min_points=30000,
    x_bins=400,
    y_bins=50,
    title="Peak Map",
    x_label="Retention Time (min)",
    y_label="m/z",
    colorscale="Portland",
)
```

**Key parameters:**
- `x_column`, `y_column`, `intensity_column`: Column names for axes and color
- `min_points`: Target size for downsampling (default: 20000)
- `x_bins`, `y_bins`: Grid resolution for spatial binning
- `colorscale`: Plotly colorscale name (default: 'Portland')
- `reversescale`: Invert colorscale direction (default: False)
- `log_scale`: Use log10 color mapping (default: True). Set to False for linear.
- `low_values_on_top`: Prioritize low values during downsampling and display them on top (default: False). Use for scores where lower = better (e.g., e-values, PEP, q-values).
- `intensity_label`: Custom colorbar label (default: 'Intensity')
- `hover_column`: Column whose text is shown when hovering a point, above its intensity
- `on_select`: Selections a click sets besides `interactivity`, as Table's `on_select` (None clears one)
- `highlight`: Mapping of identifier names to column names. The points whose column value is the identifier's selected value are ringed, whichever component selected it (looked up in the full data, so a point the current level dropped is still marked)

**Marking a selection made elsewhere:**
```python
Heatmap(
    cache_id="identifications",
    data=hits,  # one row per identified spectrum
    x_column="rt",
    y_column="mass",
    intensity_column="score",
    log_scale=False,
    intensity_label="Score",
    hover_column="name",
    interactivity={"hit": "hit_id"},  # a click selects the hit ...
    highlight={"hit": "hit_id"},  # ... and the selected hit is ringed,
)  # also when a table selected it
```

**Linear scale example:**
```python
Heatmap(
    cache_id="psm_scores",
    data_path="psm_data.parquet",
    x_column="rt",
    y_column="mz",
    intensity_column="score",
    log_scale=False,  # Linear color mapping
    intensity_label="Score",  # Custom colorbar label
    colorscale="Blues",
)
```

**Low values on top (PSM scores):**
For identification results where lower scores indicate better matches (e.g., e-values, PEP, q-values), use `low_values_on_top=True` to preserve low-scoring points during downsampling and display them on top of high-scoring points:

```python
Heatmap(
    cache_id="psm_evalue",
    data_path="psm_data.parquet",
    x_column="rt",
    y_column="mz",
    intensity_column="e_value",
    log_scale=True,  # Log scale for e-values
    low_values_on_top=True,  # Keep/show low e-values (best hits)
    reversescale=True,  # Bright color = low value = best
    intensity_label="E-value",
    colorscale="Portland",
)
```

**Categorical mode:**
Use `category_column` for discrete coloring by category instead of continuous intensity colorscale:

```python
Heatmap(
    cache_id="samples_heatmap",
    data_path="samples.parquet",
    x_column="retention_time",
    y_column="mass",
    intensity_column="intensity",
    category_column="sample_group",  # Color by category instead of intensity
    category_colors={  # Optional custom colors
        "Control": "#1f77b4",
        "Treatment_A": "#ff7f0e",
        "Treatment_B": "#2ca02c",
    },
)
```

**Boxes (e.g. LC-MS features):**
`set_boxes()` draws rectangles over the points. Boxes are given per render, so
call it before each render; only boxes in the visible range are sent. With
`selection=`, clicking a point inside a box sets that identifier to the box's
id, and the selected box is drawn with a thicker outline.

```python
heatmap.set_boxes(
    features_df,
    x_range=("rt_start", "rt_end"),
    y_range=("mz_start", "mz_end"),
    id_column="feature_id",
    selection="feature",
    label="Features",
)
heatmap(key="peak_map", state_manager=state_manager)
```

### ClusteredHeatmap

Grid heatmap for categorical axes (e.g. proteins against samples), with optional
hierarchical clustering and dendrograms on either axis.

Use this rather than `Heatmap` when both axes are labels rather than numbers.
`Heatmap` is a scattergl point cloud built for continuous axes (RT vs m/z) and
millions of points; `ClusteredHeatmap` renders an actual grid and ships the whole
matrix in one payload, so it expects tens to low-thousands of cells and has no
pagination, filtering or zoom machinery.

```python
from openms_insight import ClusteredHeatmap

ClusteredHeatmap(
    cache_id="protein_heatmap",
    data_path="quantification.parquet",  # wide: id_col + one column per sample
    id_col="ProteinName",
    metadata=metadata_df,  # columns: sample_id, group
    row_cluster=True,
    col_cluster=True,
    linkage_method="average",
    linkage_metric="euclidean",
    title="Protein Abundance",
    colorscale="RdBu",
    reversescale=True,
    group_colors={"Control": "#1f77b4", "Treatment": "#d62728"},
)(state_manager=state_manager, height=600)
```

**Key parameters:**
- `id_col`: Column naming each row (e.g. protein name). Every other column is treated as a sample column
- `metadata`: Optional `sample_id` -> `group` table. When given, a group color bar is drawn above the heatmap
- `row_cluster` / `col_cluster`: Cluster that axis and draw its dendrogram (left for rows, top for columns). Skipped automatically when the axis has fewer than 2 entries
- `linkage_method` / `linkage_metric`: Passed through to `scipy.cluster.hierarchy.linkage`
- `colorscale`, `reversescale`, `intensity_label`: Cell color mapping and colorbar label
- `group_colors`: Map group value -> color for the annotation bar. Groups without an explicit color get one from a default palette

**No `filters` or `interactivity`.** Unlike the other components, `ClusteredHeatmap`
does not participate in cross-component linking: the clustered layout depends on the
full matrix, so there is nothing sensible to filter. Both arguments are accepted (they are
part of the shared signature) but have no effect on what is rendered.

**The matrix must be complete when clustering.** Hierarchical clustering cannot
compute distances across missing values, so the component raises a `ValueError`
naming the number of affected rows. Impute first (see
[Differential Expression Analysis](#differential-expression-analysis)), or pass
`row_cluster=False, col_cluster=False` to render an incomplete matrix as-is.

**Mouse-wheel zoom is disabled** here. The layout anchors the heatmap, both
dendrograms and the group bar to manually positioned axes, which `scrollZoom`
re-ranges inconsistently. Use the mode bar's box zoom instead.

### VolcanoPlot

Interactive volcano plot for differential expression analysis with significance thresholds.

```python
from openms_insight import VolcanoPlot

VolcanoPlot(
    cache_id="de_volcano",
    data_path="differential_expression.parquet",
    log2fc_column="log2FC",
    pvalue_column="pvalue",
    label_column="protein_name",  # Optional: labels for significant points
    filters={"comparison": "comparison_id"},
    interactivity={"protein": "protein_id"},
    title="Differential Expression",
    x_label="Log2 Fold Change",
    y_label="-log10(p-value)",
    up_color="#d62728",  # Color for up-regulated
    down_color="#1f77b4",  # Color for down-regulated
    ns_color="#888888",  # Color for not significant
)(
    state_manager=state_manager,
    fc_threshold=1.0,  # Fold change threshold (render-time)
    p_threshold=0.05,  # P-value threshold (render-time)
    max_labels=20,  # Max labels to show
)
```

**Key parameters:**
- `log2fc_column`: Column with log2 fold change values
- `pvalue_column`: Column with p-values (automatically converted to -log10)
- `label_column`: Optional column for point labels
- `up_color`, `down_color`, `ns_color`: Colors for significance categories
- `fc_threshold`, `p_threshold`: Significance thresholds (passed at render time, not cached)
- `max_labels`: Maximum number of labels to display on significant points

**Render-time thresholds:** The `fc_threshold` and `p_threshold` are passed via `__call__()`, not `__init__()`. This allows instant threshold adjustment without cache invalidation.

### PCAPlot

Sample-level PCA scatter plot, computed directly from a wide quantification matrix.

```python
from openms_insight import PCAPlot

PCAPlot(
    cache_id="protein_pca",
    data_path="quantification.parquet",  # wide: id_col + one column per sample
    metadata=metadata_df,  # columns: sample_id, group
    n_components=4,  # compute 4 PCs, display any pair of them
    standardize=True,  # z-score each feature before fitting
    interactivity={"sample": "sample_id"},
    title="Sample PCA",
    group_colors={"Control": "#1f77b4", "Treatment": "#d62728"},
    show_ellipses=True,
)(
    state_manager=state_manager,
    pc_x=1,  # x-axis component, 1-indexed (render-time)
    pc_y=2,  # y-axis component, 1-indexed (render-time)
)
```

**Key parameters:**
- `metadata`: `sample_id` -> `group` table. Required whenever `data` or `data_path` is given
- `n_components`: How many principal components to compute. Set above 2 to browse further component pairs without recomputing
- `standardize`: Z-score each feature across samples before fitting (default `True`; recommended when features are on different scales)
- `show_ellipses`: Draw a 95% confidence ellipse per group. Only drawn for groups with at least 3 samples
- `group_colors`: Map group value -> color. Each group is its own trace, so the legend is clickable
- `pc_x`, `pc_y`: Which components to plot (passed at render time, not cached)

`filters` and `interactivity` map to columns of the *computed* score table -
`sample_id`, `group`, and `PC1`..`PCn` - not to columns of the input matrix.

**Render-time component selection:** like `VolcanoPlot`'s thresholds, `pc_x` and
`pc_y` are passed via `__call__()`. Switching from PC1/PC2 to PC1/PC3 re-renders
immediately; PCA itself is only recomputed when the data, metadata or
`n_components` change.

Axis labels default to `PC{n} (xx.x%)` from each component's explained variance
ratio.

### SequenceView

Peptide sequence visualization with fragment ion matching. Supports both dynamic (filtered by selection) and static sequences.

```python
# Dynamic: sequence from DataFrame filtered by selection
SequenceView(
    cache_id="peptide_view",
    sequence_data_path="sequences.parquet",  # columns: scan_id, sequence, precursor_charge
    peaks_data_path="peaks.parquet",  # columns: scan_id, peak_id, mass, intensity
    filters={"spectrum": "scan_id"},
    interactivity={"peak": "peak_id"},
    deconvolved=False,  # peaks are m/z values, consider charge states
    title="Fragment Coverage",
)

# Static: single sequence with optional peaks
SequenceView(
    cache_id="static_peptide",
    sequence_data=("PEPTIDEK", 2),  # (sequence, charge) tuple
    peaks_data=peaks_df,  # Optional: LazyFrame with mass, intensity columns
    deconvolved=True,  # peaks are neutral masses
)

# Simplest: just a sequence string
SequenceView(
    cache_id="simple_seq",
    sequence_data="PEPTIDEK",  # charge defaults to 1
)
```

**Key parameters:**
- `sequence_data`: LazyFrame, (sequence, charge) tuple, or sequence string
- `sequence_data_path`: Path to parquet with sequence data
- `peaks_data` / `peaks_data_path`: Optional peak data for fragment matching
- `deconvolved`: If False (default), peaks are m/z and matching considers charge states
- `annotation_config`: Dict with ion_types, tolerance, neutral_losses settings

**Features:**
- Automatic fragment ion matching (a/b/c/x/y/z ions)
- Configurable mass tolerance (ppm or Da)
- Neutral loss support (-H2O, -NH3)
- Auto-zoom for short sequences (≤20 amino acids)
- Fragment coverage statistics
- Click-to-select peaks with cross-component linking
- Fragment ion export for every sequence, not just the selected one

**Fragment ion export.** `export_fragment_ions()` runs the view's matching (its
`annotation_config` and `deconvolved` setting) over every cached sequence,
against the peaks that share its filter columns, and returns one row per matched
ion: the sequence's filter columns, `sequence`, `precursor_charge`, `ion`,
`ion_type`, `ion_number`, `charge`, `theoretical_mz`, `observed_mz`,
`intensity`, `mass_error_da`, `mass_error_ppm` and `peak_id`.

```python
fragments = sequence_view.export_fragment_ions()  # matched ions only
fragments = sequence_view.export_fragment_ions(include_unmatched=True)
fragments.write_csv("fragment_ions.tsv", separator="\t")
```

### DeconvolvedSpectrum

Spectrum plot for charge-state deconvolution results. Each row of data is one spectrum, with list columns: the deconvolved masses and their intensities, the raw peaks, and for each mass the raw peaks assigned to it.

```python
from openms_insight import DeconvolvedSpectrum

spectrum = DeconvolvedSpectrum(
    cache_id="deconv_spectrum",
    data=spectra,  # one row per scan, list columns
    filters={"spectrum": "scan_idx"},
    mass_identifier="mass",  # index into the selected spectrum's mass list
    view="deconvolved",  # or "annotated", "ladder"
)
spectrum(key="spectrum", state_manager=state_manager)
```

**Views:**
- `deconvolved`: the masses as sticks. Clicking one selects it.
- `annotated`: the raw peaks, with the signal peaks of the selected mass highlighted and each charge state labelled `z=N`.
- `ladder`: the masses with a sequence tag drawn as a ladder, set per render with `set_ladder(masses, sequence)`. Clicking a ladder mass shows its raw peaks.

### SeriesPlot

Line and marker plot with one trace per series, for continuous curves where the x values are sampled points rather than peaks (for stick spectra use `LinePlot`).

```python
from openms_insight import SeriesPlot

SeriesPlot(
    cache_id="score_density",
    data=densities,  # columns: x, y, kind
    x_column="x",
    y_column="y",
    series_column="kind",
    series_names={"target": "Target scores", "decoy": "Decoy scores"},
    series_colors={"target": "green", "decoy": "red"},
    x_label="Score",
    y_label="Density",
)(key="density", state_manager=state_manager)
```

### Plot3D

Interactive 3D plot. `mode="stems"` draws every point as a vertical line from the floor (e.g. x = mass, y = charge, z = intensity); `mode="lines"` joins the points sharing a `trace_column` value (e.g. x = m/z, y = retention time, z = intensity). Data is tidy, or holds equal-length list columns with all points of one entity per row, which are spread into points after filtering.

```python
from openms_insight import Plot3D

Plot3D(
    cache_id="mass_signals",
    data=peaks,  # columns: scan, mass_idx, kind, mass, charge, intensity
    filters={"spectrum": "scan", "mass": "mass_idx"},
    x_column="mass",
    y_column="charge",
    z_column="intensity",
    series_column="kind",
    series_colors={"Signal": "#3366CC", "Noise": "#DC3912"},
)(key="signals", state_manager=state_manager)
```

### ProteinSequenceView

Sequence view of a protein or peptide with its fragment and tag evidence: matched fragment ions (a/b/c/x/y/z), tag coverage, the selected tag, truncations, localized and ambiguous modifications and, with externally annotated fragments, internal fragments. A table below the grid lists the matched fragments. Residues, fragment rows and the masses of the spectrum are linked.

```python
from openms_insight import ProteinSequenceView

ProteinSequenceView(
    cache_id="sequence_view",
    data=identifications,  # one row per sequence entry with its spectrum
    filters={"protein": "hit_index"},
    mass_column="masses",
    mass_identifier="mass",
    aa_identifier="aa",
    fragment_identifier="fragment",  # selected fragment row, shared with other views
)(key="sequence", state_manager=state_manager)
```

The expected columns are listed in `ProteinSequenceView.SEQUENCE_COLUMNS` and the class docstring. Pass `sequence=` (a dict with those columns) for one fixed sequence. `entry_title` and `observed_mass_label` name the entry in the header.

### ProteinStructureView

3D structure of a protein (PDB or mmCIF, drawn with 3Dmol.js), coloured by the fragment evidence of a sequence entry. It takes the same data as `ProteinSequenceView`, aligns the sequence to the structure's chains, and shares residue and fragment selection with a sequence view. Residues outside the entry's start..end positions are not shown.

```python
from openms_insight import ProteinStructureView

view = ProteinStructureView(
    cache_id="structure_view",
    data=identifications,
    filters={"protein": "hit_index"},
    aa_identifier="aa",
    fragment_identifier="fragment",
)
view.set_structure(
    {
        "status": "ok",
        "format": "pdb",
        "data": pdb_text,
        "accession": "P60844",
        "label": "AlphaFold DB model",
    }
)
view.on_structure_action(handle_upload_or_remove)  # optional: upload/remove buttons
view(key="structure", state_manager=state_manager)
```

The structure is given per render with `set_structure()`, since where it comes from is up to the app. With `on_structure_action(handler)`, the view offers buttons to upload a structure file and to remove an uploaded one. The handler receives `{"op": "upload", "accession", "name", "data"}` or `{"op": "remove", "accession"}` and returns True to rerun.

---

## Shared Component Arguments

All components accept these common arguments:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `cache_id` | `str` | **Required** | Unique identifier for disk cache |
| `data_path` | `str` | `None` | Path to parquet file (preferred for memory efficiency) |
| `data` | `pl.LazyFrame` | `None` | Polars LazyFrame (alternative to data_path) |
| `filters` | `Dict[str, str]` | `None` | Map identifier -> column for filtering |
| `filter_defaults` | `Dict[str, Any]` | `None` | Default values when selection is None |
| `interactivity` | `Dict[str, str]` | `None` | Map identifier -> column for click actions |
| `cache_path` | `str` | `"."` | Base directory for cache storage |
| `regenerate_cache` | `bool` | `False` | Force cache regeneration |
| `height` | `int` | `400` | Component height in pixels (render-time parameter) |

### Selecting several entries (`multi_select`)

`Table`, `VolcanoPlot`, `Heatmap` and `ClusteredHeatmap` take
`multi_select={identifier: column}`. The user then picks several rows or points at
once, and the identifier holds the sorted distinct values of `column` over them
(None when nothing is picked). Components with the same identifier show and change
the same set, so any page can read it with `state_manager.get_selection(identifier)`.

A multi-selection is a selection level like any other. In `filters` it keeps the rows
whose column is in the set, so `Table(..., filters={"proteins": "accession"})` lists the
picked proteins, and the same works for masses, scans or any other column.

| Component | How the user selects |
|-----------|----------------------|
| `Table` | A check mark button in the toolbar shows a check box per row (hidden until then); Shift-click ticks a range; the header box ticks every row passing the filters (on a paginated table, in Python over all pages). Selected rows are marked by a bar on the left whether or not the boxes are shown |
| `VolcanoPlot` | Box or lasso select in Plotly's mode bar (Shift adds). With `selection_presets=True`, buttons above the plot select **All changed**, **Up** or **Down** at the plot's cut-offs; `preset_labels={"up": ..., "down": ..., "changed": ..., "clear": ...}` renames them |
| `Heatmap` | Box or lasso select in Plotly's mode bar (Shift adds); the region is resolved in Python on the full data, not the downsampled level shown; every point of the picked entries is marked |
| `ClusteredHeatmap` | Box or lasso select over rows (the column must be `id_col`); selected rows are outlined |

Each plot's mode bar gets a **Clear selection** button (the eraser).

```python
volcano = VolcanoPlot(
    ...,
    label_column="name",
    multi_select={"proteins": "accession"},
    selection_presets=True,
    preset_labels={"up": "Higher in treated", "down": "Lower in treated"},
)
table = Table(..., multi_select={"proteins": "accession"})
picked_only = Table(..., filters={"proteins": "accession"})  # the picked rows
picked = state_manager.get_selection("proteins")  # e.g. ["P0A6Y8", "P0A7V0"] or None
```

### Measuring (`measure`)

Every 2D plot has a **Measure** button (a ruler) in its Plotly mode bar: `LinePlot`,
`MirrorPlot`, `SeriesPlot`, `DeconvolvedSpectrum`, `Heatmap`, `VolcanoPlot` and
`PCAPlot`. It is on by default; `measure=False` removes it. Pressing it switches
clicks from selecting to measuring: click a point, then a second one. While measuring
the ruler is highlighted and a short note sits over the plot's top-left corner; the
plot keeps its height.

| Component | What a measurement shows |
|-----------|--------------------------|
| `LinePlot` | A bracket above the two peaks labelled with the x difference: `Δm/z 128.059` when the x-axis label is m/z, otherwise `Δ<x label>`. On an m/z axis the difference is matched to residue masses at 1+ and 2+ (`≈ Q/K`, `≈ G (2+)`) |
| `MirrorPlot` | As `LinePlot` on an m/z axis; both peaks must be in the same half |
| `DeconvolvedSpectrum` | Between masses: `Δmass 128.095 ≈ K`, matched as a neutral mass (1+ only). Between raw peaks (`'annotated'`, a ladder drill-down): `Δm/z`, matched at 1+ and 2+ |
| `SeriesPlot` | A bracket labelled with the x difference only (`ΔRT 12.400`) |
| `Heatmap`, `VolcanoPlot`, `PCAPlot` | A line between the two points labelled with the x and y differences, from the first point to the second (`Δlog2 Fold Change +2.150`, `Δ-log10(p-value) −1.300`), using the axis labels |

Residues are the 20 standard amino acids, monoisotopic, I and L shown as `I/L`,
closest first. `measure_tolerance` (default `0.02` Da per point; a difference
matches within twice that, since both points carry the error) and
`measure_residues` (extra named masses, e.g. `{"M(Oxidation)": 147.0354}`) tune
the matching on `LinePlot`, `MirrorPlot` and `DeconvolvedSpectrum`.

Several measurements can stay on a plot. Esc cancels a half-finished one,
clicking a label removes that measurement and the **Clear measurements** button (×)
next to the ruler removes all. They are
plain Plotly shapes and annotations, so the SVG download includes them. They are
cleared when other data is plotted (a `Heatmap` keeps them while zooming). With
measure mode off, clicks select as they always did.

The measure options are render-time settings: they are not part of the cache
configuration, so switching the tool on or off never rebuilds a cache.
`ClusteredHeatmap` (a categorical matrix: there is no distance between two
samples' columns) and `Plot3D` (a click in 3D does not pick comparable points)
have no measure tool.

## Memory-Efficient Preprocessing

When working with large datasets (especially heatmaps with millions of points), use `data_path` instead of `data` to enable subprocess preprocessing:

```python
# Subprocess preprocessing (recommended for large datasets)
# Memory is fully released after cache creation
heatmap = Heatmap(
    data_path="large_peaks.parquet",  # triggers subprocess
    cache_id="peaks_heatmap",
    ...
)

# In-process preprocessing (for smaller datasets or debugging)
# Memory may be retained by allocator after preprocessing
heatmap = Heatmap(
    data=pl.scan_parquet("large_peaks.parquet"),  # runs in main process
    cache_id="peaks_heatmap",
    ...
)
```

**Why this matters:** Memory allocators like mimalloc (used by Polars) retain freed memory for performance. For large datasets, this can cause memory usage to stay high even after preprocessing completes. Running preprocessing in a subprocess guarantees all memory is returned to the OS when the subprocess exits.

## Caching

A `cache_id` identifies one **(data, config)** pair. Constructing a component whose cache already exists with the same configuration reuses it and skips preprocessing entirely — which is what makes it safe to build components at the top of a Streamlit script, where the whole script reruns on every interaction:

```python
# Runs preprocessing once. Every rerun after that loads the cache.
table = Table(
    cache_id="spectra",
    data=pl.scan_parquet("spectra.parquet"),
    cache_path="./cache",
    index_field="scan_id",
)
```

**Changing the data does not invalidate the cache.** The configuration is hashed, but the data behind a LazyFrame cannot be without collecting it — which is the expense the cache exists to avoid. Give new data a new `cache_id`, or force a rebuild:

```python
table = Table(
    cache_id="spectra",
    data=pl.scan_parquet("todays_spectra.parquet"),
    cache_path="./cache",
    index_field="scan_id",
    regenerate_cache=True,  # rebuild even though the config is unchanged
)
```

Render-only settings such as `title` and `colorscale` currently take part in the cache key, so changing one rebuilds the cache rather than being ignored. That is wasteful but safe.

## Cache Reconstruction

Components can be reconstructed from cache using only `cache_id` and `cache_path`. All configuration is restored from the cached manifest:

```python
# First run: create component with data and config
table = Table(
    cache_id="my_table",
    data_path="data.parquet",
    filters={"spectrum": "scan_id"},
    column_definitions=[...],
    cache_path="./cache",
)

# Subsequent runs: reconstruct from cache only
table = Table(
    cache_id="my_table",
    cache_path="./cache",
)
# All config (filters, column_definitions, etc.) restored from cache
```

## Rendering

All components are callable. Pass a `StateManager` to enable cross-component linking:

```python
from openms_insight import StateManager

state_manager = StateManager()

table(state_manager=state_manager, height=300)
plot(state_manager=state_manager, height=400)
```

## Differential Expression Analysis

`openms_insight.analysis` is the pipeline that feeds `VolcanoPlot`, `PCAPlot` and
`ClusteredHeatmap`: filtering, imputation, normalization, statistical testing and
GO enrichment.

It sits outside the component architecture and is deliberately not re-exported from
the package root, so import the modules directly. Note that `analysis.filter`
shadows the builtin `filter` if you import it under its bare name - the example
below aliases it:

```python
import polars as pl

from openms_insight.analysis import filter as feature_filter
from openms_insight.analysis import imputation, normalization, statistics
```

Every function takes a **wide-format** `pl.LazyFrame` (one row per feature, one
column per sample) plus a **sample metadata** `pl.DataFrame` with `sample_id` and
`group` columns, and returns a `LazyFrame`. Nothing is collected until you ask for
it.

```python
data = pl.scan_parquet("quantification.parquet")  # ProteinName, S1 .. S6
metadata = pl.DataFrame(
    {
        "sample_id": ["S1", "S2", "S3", "S4", "S5", "S6"],
        "group": ["Control"] * 3 + ["Treatment"] * 3,
    }
)

data = feature_filter.filter_low_abundance(data, metadata, threshold_percentile=10.0)
data = feature_filter.filter_low_repeatability(data, metadata, max_missing_ratio=0.5)
data = imputation.impute_mar(data, metadata, strategy="median")
data = normalization.transform_data(data, metadata, "log2")
data = normalization.normalize_samples(data, metadata, "median", id_col="ProteinName")
data = normalization.scale_data(data, metadata, "auto_scaling")

results = statistics.calculate_statistical_tests(data, metadata, method="limma_like")
results = statistics.adjust_fdr_lazy(results, strategy="BH")

report = results.collect()  # adds log2FC, stat, p-value, p-adj
```

### Filtering

| Function | Keeps a row when |
|----------|------------------|
| `filter_low_abundance` | at least one group's median clears that group's `threshold_percentile` cutoff |
| `filter_low_repeatability` | at least one group has no more than `max_missing_ratio` of its samples missing |
| `filter_low_variance` | at least one group's variance clears that group's `threshold_percentile` cutoff |

All three apply their cutoff **per group** and keep the row if any single group
passes, so a feature that varies only within one condition is not discarded for
having low variance overall. Zeros count as missing. A metadata table with no
usable groups leaves the data unchanged rather than filtering everything away.

### Imputation

- `impute_mar(data, metadata, strategy="median")` - missing at random: fill from the feature's own mean or median **within the same group**
- `impute_smallest_value(data, metadata, scope="row")` - missing not at random: fill with the smallest observed value, per feature (`"row"`) or across the whole matrix (`"global"`), on the assumption that missing MS values fall below the detection limit

Both treat explicit nulls and zeros as missing.

### Normalization

| Function | Operates on | Strategies |
|----------|-------------|------------|
| `transform_data` | each value | `"log2"`, `"log10"` (both add 1 first, so zeros do not become `-inf`), `"square_root"`, `"cube_root"` |
| `normalize_samples` | whole samples (columns) | `"sum"`, `"median"`, `"pqn"`, `"reference_feature"`, `"quantile"` |
| `scale_data` | each feature (row) | `"mean_centering"`, `"auto_scaling"` (Z-score), `"pareto_scaling"`, `"range_scaling"` |

All three accept `"None"` and return the input unchanged, which makes them easy to
wire straight to a Streamlit selectbox. `"reference_feature"` additionally needs
`reference_feature=` naming a row in `id_col`.

### Statistical testing

`calculate_statistical_tests(data, metadata, method=...)` adds `log2FC`, `stat` and
`p-value`:

| Method | Test | Groups |
|--------|------|--------|
| `"limma_like"` (default) | Empirical Bayes variance-moderated t-test / F-test | 2 / 3+ |
| `"welch"` | Welch's t-test (unequal variances) | exactly 2 |
| `"paired"` | Paired t-test | exactly 2, equal size |
| `"anova"` | One-way ANOVA F-test | 3+ |

`limma_like` shrinks each feature's variance towards a common prior, which is what
makes small-n experiments usable. Everything is expressed as lazy Polars operations
and only drops into SciPy for the final p-value.

`adjust_fdr_lazy(results, strategy=...)` then adds `p-adj`, using `"BH"`
(Benjamini-Hochberg, the default), `"Bonferroni"`, or `"None"` to copy `p-value`
through unchanged.

The result feeds `VolcanoPlot` directly:

```python
VolcanoPlot(
    cache_id="de_volcano",
    data=results,
    log2fc_column="log2FC",
    pvalue_column="p-adj",
    label_column="ProteinName",
)(state_manager=state_manager, fc_threshold=1.0, p_threshold=0.05)
```

### GO enrichment

`calculate_go_enrichment` annotates UniProt accessions via
[MyGene.info](https://mygene.info) and runs Fisher's exact test per GO term, for
each of the BP, CC and MF categories.

It is the odd one out in this module: it makes a live network call, takes an
**eager** `pl.DataFrame`, and returns a `(status, payload)` tuple instead of raising,
so callers can tell "not enough significant proteins" apart from a hard failure.

```python
from openms_insight.analysis.enrichment import calculate_go_enrichment

status, payload = calculate_go_enrichment(
    report,  # eager DataFrame with an ID column, log2FC, and a p-value column
    id_col="ProteinName",
    target_p_col="p-adj",
    p_cutoff=0.05,
    fc_cutoff=1.0,
)

if status == "success":
    for category, result in payload["categories"].items():
        st.plotly_chart(result["fig"])  # "BP" | "CC" | "MF"
```

`status` is `"success"`, `"insufficient_proteins"` (fewer than 3 proteins pass the
cutoffs) or `"empty_data"`.

For a set the user picked (see `multi_select`), `go_enrichment` takes the
foreground and background directly, and the annotations from
`fetch_go_annotations`, so an app can cache them per protein:

```python
from openms_insight.analysis.enrichment import fetch_go_annotations, go_enrichment

annotations = fetch_go_annotations(background)  # query, BP_terms, CC_terms, MF_terms
result = go_enrichment(annotations, foreground=picked, background=background)
result["categories"]["BP"]  # GO_Term, Count, Background, GeneRatio, BgRatio,
# FoldEnrichment, p_value, -log10(p), p_adj, Proteins
```

When the user tests many selections of the same proteins (a lasso on a plot,
check boxes in a table), build the term index once and test each selection from
it. The index is a Polars frame (accession, category, term) that an app can
store, for example as parquet next to its results, so a selection only counts its
proteins and runs the tests:

```python
from openms_insight.analysis.enrichment import go_enrichment_from_index, go_term_index

index = go_term_index(annotations, background)  # once, e.g. after the workflow
result = go_enrichment_from_index(index, foreground=picked, background=background)
```

`go_enrichment` returns the same result; it builds the index itself.

These functions need the `analysis` extra:

```bash
pip install "openms-insight[analysis]"
```

---

## Development

For a comprehensive guide to the internal architecture, conventions, and pitfalls, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Building the Vue Component

```bash
cd js-component
npm install
npm run build
```

### Development Mode (Hot Reload)

```bash
# Terminal 1: Vue dev server
cd js-component
npm run dev

# Terminal 2: Streamlit with dev mode
SVC_DEV_MODE=true SVC_DEV_URL=http://localhost:5173 streamlit run app.py
```

### Debug Mode

Enable hash tracking logs to debug data synchronization issues:

```bash
SVC_DEBUG_HASH=true streamlit run app.py
```

### Running Tests

```bash
# Python tests
pip install -e ".[dev]"
pytest tests/ -v

# TypeScript type checking
cd js-component
npm run type-check
```

### Linting and Formatting

```bash
# Python
ruff check .
ruff format .

# JavaScript/TypeScript
cd js-component
npm run lint
npm run format
```
