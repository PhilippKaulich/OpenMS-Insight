"""Shared component cases for the cross-component contract tests.

Not a test module — ``python_files = ["test_*.py"]`` keeps pytest from
collecting it. It exists so the contract tests parametrize over one list
instead of two that can silently drift apart.

Each case is ``(component, data fixture, literal kwargs, fixture kwargs)``.
The fourth element covers components needing a frame that cannot be written
as a literal here: PCAPlot and ClusteredHeatmap both take sample metadata.
Because ``BaseComponent.__init__`` preprocesses, listing a component here is
what puts its preprocessing path — scikit-learn for PCAPlot, SciPy linkage
for ClusteredHeatmap — under CI on every supported Python.
"""

from openms_insight import (
    ClusteredHeatmap,
    DeconvolvedSpectrum,
    Heatmap,
    LinePlot,
    PCAPlot,
    Plot3D,
    ProteinSequenceView,
    SeriesPlot,
    Table,
    VolcanoPlot,
)

COMPONENT_CASES = [
    (Table, "sample_table_data", {}, {}),
    (
        LinePlot,
        "sample_lineplot_data",
        {"x_column": "mass", "y_column": "intensity"},
        {},
    ),
    (
        Heatmap,
        "sample_heatmap_data",
        {
            "x_column": "retention_time",
            "y_column": "mz",
            "intensity_column": "intensity",
        },
        {},
    ),
    (
        VolcanoPlot,
        "sample_volcanoplot_data",
        {"log2fc_column": "log2FC", "pvalue_column": "pvalue"},
        {},
    ),
    (
        PCAPlot,
        "sample_quantification_data",
        {},
        {"metadata": "sample_quantification_metadata"},
    ),
    (
        ClusteredHeatmap,
        "sample_quantification_data_complete",
        {"id_col": "feature"},
        {"metadata": "sample_quantification_metadata"},
    ),
    (
        SeriesPlot,
        "sample_series_data",
        {"x_column": "Score", "y_column": "Density", "series_column": "kind"},
        {},
    ),
    (
        Plot3D,
        "sample_plot3d_data",
        {
            "x_column": "mass",
            "y_column": "charge",
            "z_column": "intensity",
            "series_column": "kind",
            "filters": {"scan": "scan_idx", "mass": "mass_idx"},
            "filter_defaults": {"mass": -1},
        },
        {},
    ),
    (
        DeconvolvedSpectrum,
        "sample_deconvolved_spectra",
        {"filters": {"scan": "scan_idx"}, "view": "annotated"},
        {},
    ),
    (
        ProteinSequenceView,
        "sample_protein_sequence_data",
        {"filters": {"protein": "hit_index"}},
        {},
    ),
]

COMPONENT_IDS = [case[0].__name__ for case in COMPONENT_CASES]
COMPONENT_ARGNAMES = "ComponentClass,data_fixture,extra_kwargs,fixture_kwargs"


def build_kwargs(request, extra_kwargs, fixture_kwargs):
    """Merge literal kwargs with kwargs resolved from fixture names."""
    kwargs = dict(extra_kwargs)
    kwargs.update(
        {name: request.getfixturevalue(f) for name, f in fixture_kwargs.items()}
    )
    return kwargs
