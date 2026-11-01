"""Tests for the spectrum and sequence components and the Table options they need.

Covers SeriesPlot, Plot3D, DeconvolvedSpectrum, ProteinSequenceView, the
Table options toggle_filters / range_filters / on_select and float_precision.
"""

import json
import math
from pathlib import Path

import polars as pl
import pytest

from openms_insight import (
    DeconvolvedSpectrum,
    Plot3D,
    ProteinSequenceView,
    SeriesPlot,
    Table,
)


@pytest.fixture
def protein_table_data() -> pl.LazyFrame:
    """Identifications, two per scan, the best one flagged."""
    return pl.LazyFrame(
        {
            "index": [0, 1, 2, 3],
            "scan_idx": [10, 10, 20, 20],
            "is_best": [True, False, False, True],
            "Score": [9.0, 5.0, 3.0, 8.0],
        }
    )


@pytest.fixture
def tag_table_data() -> pl.LazyFrame:
    """Sequence tags with their residue ranges."""
    return pl.LazyFrame(
        {
            "tag_idx": [0, 1, 2],
            "scan_idx": [10, 10, 10],
            "StartPos": [0, 5, 8],
            "EndPos": [4, 9, 12],
        }
    )


class TestTableOptions:
    """toggle_filters, range_filters and on_select."""

    def test_defaults_leave_args_and_config_unchanged(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data
    ):
        table = Table(
            cache_id="plain",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
        )
        args = table._get_component_args()
        for key in ("toggleFilters", "onSelect", "toggle_filters", "range_filters"):
            assert key not in args
        config = table._get_cache_config()
        for key in ("toggle_filters", "range_filters", "on_select"):
            assert key not in config

    def test_toggle_filter_args_and_filtering(
        self, mock_streamlit, temp_cache_dir: Path, protein_table_data
    ):
        table = Table(
            cache_id="proteins",
            data=protein_table_data,
            index_field="index",
            interactivity={"protein": "index"},
            toggle_filters=[
                {
                    "label": "Best per spectrum",
                    "column": "is_best",
                    "group_column": "scan_idx",
                }
            ],
            on_select={"tag": None},
            cache_path=str(temp_cache_dir),
        )
        args = table._get_component_args()
        assert args["toggleFilters"] == [
            {
                "label": "Best per spectrum",
                "column": "is_best",
                "default": True,
                "group_column": "scan_idx",
            }
        ]
        assert args["onSelect"] == {"tag": None}
        assert "toggle_filters" not in args and "on_select" not in args

        # Default on: only the best rows
        rows = table._prepare_vue_data({})["tableData"]
        assert sorted(rows["index"]) == [0, 3]
        # Switched off through the pagination state: every row
        state = {"proteins_page": {"page": 1, "toggles": {"is_best": False}}}
        rows = table._prepare_vue_data(state)["tableData"]
        assert sorted(rows["index"]) == [0, 1, 2, 3]

    def test_toggle_filter_needs_column(self, mock_streamlit, temp_cache_dir: Path):
        with pytest.raises(ValueError, match="column"):
            Table(
                cache_id="bad",
                data=pl.LazyFrame({"a": [1]}),
                toggle_filters=[{"label": "x"}],
                cache_path=str(temp_cache_dir),
            )

    def test_toggle_options_survive_reconstruction(
        self, mock_streamlit, temp_cache_dir: Path, protein_table_data
    ):
        kwargs = {
            "toggle_filters": [{"label": "Best", "column": "is_best"}],
            "range_filters": {"aa": ["Score", "Score"]},
            "on_select": {"tag": None},
        }
        Table(
            cache_id="rebuild",
            data=protein_table_data,
            cache_path=str(temp_cache_dir),
            **kwargs,
        )
        restored = Table(cache_id="rebuild", cache_path=str(temp_cache_dir))
        args = restored._get_component_args()
        assert args["toggleFilters"][0]["column"] == "is_best"
        assert args["onSelect"] == {"tag": None}
        assert "aa" in restored.get_state_dependencies()

    def test_range_filter(self, mock_streamlit, temp_cache_dir: Path, tag_table_data):
        table = Table(
            cache_id="tags",
            data=tag_table_data,
            index_field="tag_idx",
            filters={"scan": "scan_idx"},
            range_filters={"aa": ["StartPos", "EndPos"]},
            cache_path=str(temp_cache_dir),
        )
        assert "aa" in table.get_state_dependencies()
        rows = table._prepare_vue_data({"scan": 10})["tableData"]
        assert list(rows["tag_idx"]) == [0, 1, 2]
        rows = table._prepare_vue_data({"scan": 10, "aa": 6})["tableData"]
        assert list(rows["tag_idx"]) == [1]
        rows = table._prepare_vue_data({"scan": 10, "aa": 9.0})["tableData"]
        assert list(rows["tag_idx"]) == [1, 2]

        # The bridge drops a selection the range filter hides
        lf = table._preprocessed_data["data"]
        kept = table._apply_validation_filters(lf, {"aa": 2}).collect()
        assert kept["tag_idx"].to_list() == [0]

        exported = table.export_data({"scan": 10, "aa": 12})
        assert exported["tag_idx"].to_list() == [2]


class TestFloatPrecision:
    def test_default_downcasts(self, mock_streamlit, temp_cache_dir: Path):
        table = Table(
            cache_id="f32",
            data=pl.LazyFrame({"mass": [12345.6789012]}),
            cache_path=str(temp_cache_dir),
        )
        schema = table._preprocessed_data["data"].collect_schema()
        assert schema["mass"] == pl.Float32

    def test_float64_keeps_precision(self, mock_streamlit, temp_cache_dir: Path):
        table = Table(
            cache_id="f64",
            data=pl.LazyFrame({"mass": [12345.6789012]}),
            cache_path=str(temp_cache_dir),
            float_precision="float64",
        )
        df = table._preprocessed_data["data"].collect()
        assert df.schema["mass"] == pl.Float64
        assert df["mass"][0] == pytest.approx(12345.6789012, abs=1e-9)

    def test_default_keeps_config_hash(self, mock_streamlit, temp_cache_dir: Path):
        data = pl.LazyFrame({"mass": [1.0]})

        def table(subdir, **kwargs):
            return Table(
                cache_id="h",
                data=data,
                cache_path=str(temp_cache_dir / subdir),
                **kwargs,
            )

        a = table("a")
        b = table("b", float_precision="float32")
        c = table("c", float_precision="float64")
        assert a._compute_config_hash() == b._compute_config_hash()
        assert a._compute_config_hash() != c._compute_config_hash()

    def test_invalid_precision(self, mock_streamlit, temp_cache_dir: Path):
        with pytest.raises(ValueError, match="float_precision"):
            Table(
                cache_id="bad",
                data=pl.LazyFrame({"a": [1.0]}),
                cache_path=str(temp_cache_dir),
                float_precision="float16",
            )


class TestSeriesPlot:
    def test_args_and_data(self, mock_streamlit, temp_cache_dir, sample_series_data):
        plot = SeriesPlot(
            cache_id="fdr",
            data=sample_series_data,
            x_column="Score",
            y_column="Density",
            series_column="kind",
            series_names={"target": "Target scores", "decoy": "Decoy scores"},
            series_colors={"target": "green", "decoy": "red"},
            title="FDR Plot",
            cache_path=str(temp_cache_dir),
        )
        args = plot._get_component_args()
        assert args["componentType"] == "PlotlySeries"
        # Pairs keep the legend order through JSON
        assert args["seriesNames"] == [
            ["target", "Target scores"],
            ["decoy", "Decoy scores"],
        ]
        data = plot._prepare_vue_data({})
        assert len(data["plotData"]) == 6


class TestPlot3D:
    def _plot(self, data, cache_dir):
        return Plot3D(
            cache_id="signals",
            data=data,
            filters={"scan": "scan_idx", "mass": "mass_idx"},
            filter_defaults={"mass": -1},
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            series_column="kind",
            title="",
            selection_titles={"mass": "Mass signals", "scan": "Precursor signals"},
            cache_path=str(cache_dir),
        )

    def test_list_columns_are_spread(
        self, mock_streamlit, temp_cache_dir, sample_plot3d_data
    ):
        plot = self._plot(sample_plot3d_data, temp_cache_dir)
        df = plot._prepare_vue_data({"scan": 0, "mass": 0})["plotData"]
        assert len(df) == 3
        assert sorted(df["mass"]) == [1000.0, 1000.5, 1002.0]
        assert df["intensity"].dtype == "float64"

    def test_default_rows_without_mass(
        self, mock_streamlit, temp_cache_dir, sample_plot3d_data
    ):
        plot = self._plot(sample_plot3d_data, temp_cache_dir)
        df = plot._prepare_vue_data({"scan": 0})["plotData"]
        assert sorted(df["mass"]) == [1000.0, 1001.0]

    def test_no_scan_no_points(
        self, mock_streamlit, temp_cache_dir, sample_plot3d_data
    ):
        plot = self._plot(sample_plot3d_data, temp_cache_dir)
        df = plot._prepare_vue_data({})["plotData"]
        assert len(df) == 0

    def test_args(self, mock_streamlit, temp_cache_dir, sample_plot3d_data):
        args = self._plot(sample_plot3d_data, temp_cache_dir)._get_component_args()
        assert args["componentType"] == "Plotly3D"
        assert args["selectionTitles"] == [
            ["mass", "Mass signals"],
            ["scan", "Precursor signals"],
        ]

    def test_invalid_mode(self, mock_streamlit, temp_cache_dir, sample_plot3d_data):
        with pytest.raises(ValueError, match="mode"):
            Plot3D(
                cache_id="bad",
                data=sample_plot3d_data,
                x_column="mass",
                y_column="charge",
                z_column="intensity",
                mode="bars",
                cache_path=str(temp_cache_dir),
            )


class TestDeconvolvedSpectrum:
    def test_one_spectrum_per_scan(
        self, mock_streamlit, temp_cache_dir, sample_deconvolved_spectra
    ):
        spectrum = DeconvolvedSpectrum(
            cache_id="anno",
            data=sample_deconvolved_spectra,
            filters={"scan": "scan_idx"},
            mass_identifier="mass",
            view="annotated",
            float_precision="float64",
            cache_path=str(temp_cache_dir),
        )
        # Selecting a mass must not invalidate the cached spectrum
        assert spectrum.get_state_dependencies() == ["scan"]
        df = spectrum._prepare_vue_data({"scan": 0, "mass": 1})["plotData"]
        assert len(df) == 1
        assert list(df["masses"][0]) == [1000.0, 2000.123456]
        assert len(spectrum._prepare_vue_data({})["plotData"]) == 0

        args = spectrum._get_component_args()
        assert args["title"] == "Annotated Spectrum"
        assert args["massIdentifier"] == "mass"
        assert args["ladder"] is None

    def test_ladder(self, mock_streamlit, temp_cache_dir, sample_deconvolved_spectra):
        spectrum = DeconvolvedSpectrum(
            cache_id="ladder",
            data=sample_deconvolved_spectra,
            filters={"scan": "scan_idx"},
            view="ladder",
            cache_path=str(temp_cache_dir),
        )
        spectrum.set_ladder([1000, 1057.02], "G", selected_index=0, key=7)
        assert spectrum._get_component_args()["ladder"] == {
            "masses": [1000.0, 1057.02],
            "sequence": "G",
            "selectedIndex": 0,
            "key": 7,
        }
        spectrum.set_ladder(None)
        assert spectrum._get_component_args()["ladder"] is None

    def test_deconvolved_view_needs_no_peaks(self, mock_streamlit, temp_cache_dir):
        data = pl.LazyFrame(
            {"scan_idx": [0], "masses": [[1.0]], "intensities": [[2.0]]}
        )
        DeconvolvedSpectrum(
            cache_id="deconv",
            data=data,
            filters={"scan": "scan_idx"},
            cache_path=str(temp_cache_dir),
        )
        with pytest.raises(ValueError, match="not found"):
            DeconvolvedSpectrum(
                cache_id="anno_missing",
                data=data,
                filters={"scan": "scan_idx"},
                view="annotated",
                cache_path=str(temp_cache_dir),
            )

    def test_invalid_view(self, mock_streamlit, temp_cache_dir):
        with pytest.raises(ValueError, match="view"):
            DeconvolvedSpectrum(
                cache_id="bad",
                data=pl.LazyFrame({"masses": [[1.0]], "intensities": [[1.0]]}),
                view="raw",
                cache_path=str(temp_cache_dir),
            )


class TestProteinSequenceView:
    def test_selected_entry(
        self, mock_streamlit, temp_cache_dir, sample_protein_sequence_data
    ):
        view = ProteinSequenceView(
            cache_id="seq",
            data=sample_protein_sequence_data,
            filters={"protein": "hit_index"},
            mass_identifier="mass",
            aa_identifier="aa",
            cache_path=str(temp_cache_dir),
        )
        assert view.get_state_dependencies() == ["protein"]

        data = view._prepare_vue_data({"protein": 1})
        assert data["sequenceData"]["sequence"] == list("ACDK")
        assert data["sequenceData"]["end_position"] == -1
        assert data["spectrumData"] == {"masses": [72.04], "precursorMass": 435.2}
        # Spectrum columns are not part of the sequence entry
        assert "masses" not in data["sequenceData"]
        # The payload is valid JSON (NaN replaced)
        json.dumps(data, allow_nan=False)

        nan_row = view._prepare_vue_data({"protein": 0})["sequenceData"]
        assert nan_row["observed_mass"] is None

        empty = view._prepare_vue_data({})
        assert empty["sequenceData"] is None and empty["spectrumData"] is None
        assert empty["_hash"] != data["_hash"]

    def test_fixed_sequence(self, mock_streamlit, temp_cache_dir):
        spectra = pl.LazyFrame(
            {
                "scan_idx": [0, 1],
                "masses": [[1.0, 2.0], [3.0]],
                "precursor_mass": [500.0, 0.0],
            }
        )
        sequence = {
            "sequence": list("PEP"),
            "theoretical_mass": 311.15,
            "fragment_masses_b": [[98.06], [227.1], [float("nan")]],
        }
        view = ProteinSequenceView(
            cache_id="seq_fixed",
            data=spectra,
            filters={"scan": "scan_idx"},
            sequence=sequence,
            sequence_identifier="sequence",
            cache_path=str(temp_cache_dir),
        )
        data = view._prepare_vue_data({"scan": 1})
        assert data["sequenceData"]["sequence"] == list("PEP")
        assert data["sequenceData"]["fragment_masses_b"][2] == [None]
        assert data["spectrumData"]["masses"] == [3.0]

        # The sequence is part of the configuration: a new one rebuilds the cache
        other = ProteinSequenceView(
            cache_id="seq_fixed",
            data=spectra,
            filters={"scan": "scan_idx"},
            sequence={"sequence": list("AAA")},
            cache_path=str(temp_cache_dir),
        )
        assert other._prepare_vue_data({"scan": 1})["sequenceData"]["sequence"] == [
            "A",
            "A",
            "A",
        ]
        restored = ProteinSequenceView(
            cache_id="seq_fixed", cache_path=str(temp_cache_dir)
        )
        assert restored._prepare_vue_data({"scan": 0})["sequenceData"]["sequence"] == [
            "A",
            "A",
            "A",
        ]

    def test_args_and_tag(
        self, mock_streamlit, temp_cache_dir, sample_protein_sequence_data
    ):
        view = ProteinSequenceView(
            cache_id="seq_args",
            data=sample_protein_sequence_data,
            filters={"protein": "hit_index"},
            aa_identifier="aa",
            settings={"tolerance": 10, "ion_types": ["b", "y"]},
            cache_path=str(temp_cache_dir),
        )
        args = view._get_component_args()
        assert args["componentType"] == "ProteinSequenceView"
        assert args["sequenceIdentifier"] is None
        assert args["settings"] == {"tolerance": 10, "ion_types": ["b", "y"]}
        assert args["tag"] is None
        assert args["accentColor"] is None
        assert args["fragmentIdentifier"] is None
        view.set_tag(2, 5)
        assert view._get_component_args()["tag"] == {"startPos": 2, "endPos": 5}
        view.set_tag(None)
        assert view._get_component_args()["tag"] is None

    def test_accent_color(
        self, mock_streamlit, temp_cache_dir, sample_protein_sequence_data
    ):
        ProteinSequenceView(
            cache_id="seq_accent",
            data=sample_protein_sequence_data,
            filters={"protein": "hit_index"},
            accent_color="#336699",
            cache_path=str(temp_cache_dir),
        )
        restored = ProteinSequenceView(
            cache_id="seq_accent", cache_path=str(temp_cache_dir)
        )
        assert restored._get_component_args()["accentColor"] == "#336699"

    def test_entry_mass_labels(
        self, mock_streamlit, temp_cache_dir, sample_protein_sequence_data
    ):
        default = ProteinSequenceView(
            cache_id="seq_labels_default",
            data=sample_protein_sequence_data,
            filters={"protein": "hit_index"},
            cache_path=str(temp_cache_dir),
        )._get_component_args()
        assert default["entryTitle"] == "Identification"
        assert default["observedMassLabel"] == "Observed mass"
        ProteinSequenceView(
            cache_id="seq_labels",
            data=sample_protein_sequence_data,
            filters={"protein": "hit_index"},
            entry_title="Peptide",
            observed_mass_label="Observed peptide mass",
            cache_path=str(temp_cache_dir),
        )
        restored = ProteinSequenceView(
            cache_id="seq_labels", cache_path=str(temp_cache_dir)
        )._get_component_args()
        assert restored["entryTitle"] == "Peptide"
        assert restored["observedMassLabel"] == "Observed peptide mass"

    def test_requires_sequence(self, mock_streamlit, temp_cache_dir):
        with pytest.raises(ValueError, match="sequence"):
            ProteinSequenceView(
                cache_id="noseq",
                data=pl.LazyFrame({"masses": [[1.0]], "precursor_mass": [1.0]}),
                cache_path=str(temp_cache_dir),
            )

    def test_masses_keep_full_precision(self, mock_streamlit, temp_cache_dir):
        data = pl.LazyFrame(
            {
                "hit_index": [0],
                "sequence": [["A"]],
                "masses": [[12345.678901]],
                "precursor_mass": [12345.678901],
            }
        )
        view = ProteinSequenceView(
            cache_id="seq_precision",
            data=data,
            filters={"protein": "hit_index"},
            cache_path=str(temp_cache_dir),
        )
        masses = view._prepare_vue_data({"protein": 0})["spectrumData"]["masses"]
        assert math.isclose(masses[0], 12345.678901, abs_tol=1e-9)


def test_table_navigation_uses_render_state_manager():
    """Navigation state goes to the manager the table is rendered with, and
    only for the duration of that render."""
    from openms_insight.core.state import (
        _render_state_manager,
        get_default_state_manager,
        get_render_state_manager,
    )

    own = object()
    assert get_render_state_manager() is get_default_state_manager()
    token = _render_state_manager.set(own)
    try:
        assert get_render_state_manager() is own
    finally:
        _render_state_manager.reset(token)
    assert get_render_state_manager() is get_default_state_manager()


def test_table_default_row_minus_one_selects_nothing(
    mock_streamlit, temp_cache_dir: Path, sample_table_data
):
    """default_row=-1 means no automatic selection, also when filters change."""
    from openms_insight import Table

    kwargs = {
        "data": sample_table_data,
        "cache_path": str(temp_cache_dir),
        "filters": {"spectrum": "scan_id"},
        "interactivity": {"peak": "id"},
        "index_field": "id",
    }
    none = Table(cache_id="none", default_row=-1, **kwargs)
    assert none._prepare_vue_data({"spectrum": 200})["_auto_selection"] == {}
    first = Table(cache_id="first", **kwargs)
    assert first._prepare_vue_data({"spectrum": 200})["_auto_selection"] == {"peak": 3}


def test_table_reclick_and_default_row_options(
    mock_streamlit, temp_cache_dir: Path, sample_table_data
):
    """reclick and default_row_selects reach Vue and survive cache
    reconstruction, and tables without them keep their configuration (and
    cache) unchanged."""
    from openms_insight import Table

    kwargs = {
        "data": sample_table_data,
        "cache_path": str(temp_cache_dir),
        "interactivity": {"peak": "id"},
        "index_field": "id",
    }
    plain = Table(cache_id="plain", **kwargs)
    assert "reclick" not in plain._get_component_args()
    assert "highlightDefaultRow" not in plain._get_component_args()
    assert "reclick" not in plain._get_cache_config()
    assert "default_row_selects" not in plain._get_cache_config()

    table = Table(
        cache_id="reclick", reclick="unhighlight", default_row_selects=False, **kwargs
    )
    assert table._get_component_args()["reclick"] == "unhighlight"
    restored = Table(cache_id="reclick", cache_path=str(temp_cache_dir))
    args = restored._get_component_args()
    assert args["reclick"] == "unhighlight"
    assert args["highlightDefaultRow"] is True
    # Only highlighted: nothing is selected for the default row
    assert restored.get_initial_selection({}) is None
    assert restored._prepare_vue_data({})["_auto_selection"] == {}

    with pytest.raises(ValueError, match="reclick"):
        Table(cache_id="bad", reclick="toggle", **kwargs)


def test_deselected_row_is_not_selected_again_until_filters_change(
    mock_streamlit, temp_cache_dir: Path
):
    """The default row fills an empty selection, except one the user cleared:
    that stays empty until the table is filtered to something else."""
    from unittest.mock import patch

    import polars as pl

    from openms_insight import StateManager, Table
    from openms_insight.rendering.bridge import _apply_auto_selection

    data = pl.LazyFrame({"id": [0, 1, 2], "scan": [1, 1, 2]})
    kwargs = {
        "data": data,
        "cache_path": str(temp_cache_dir),
        "index_field": "id",
        "filters": {"scan": "scan"},
        "interactivity": {"row": "id"},
    }
    plain = Table(cache_id="plain_rows", **kwargs)
    table = Table(cache_id="rows", reclick="deselect", **kwargs)
    assert plain.auto_selection_scope({"scan": 1}) is None

    with patch("openms_insight.rendering.bridge.st.session_state", mock_streamlit):
        state = StateManager(session_key="reclick_scope")
        state.set_selection("scan", 1)
        assert _apply_auto_selection(table, "t", {"row": 0}, state)
        assert state.get_selection("row") == 0

        state.set_selection("row", None)  # the user re-clicked the row
        assert not _apply_auto_selection(table, "t", {"row": 0}, state)
        assert state.get_selection("row") is None

        state.set_selection("scan", 2)
        assert _apply_auto_selection(table, "t", {"row": 2}, state)
        assert state.get_selection("row") == 2

        # Without reclick="deselect" an empty selection is always filled
        state.set_selection("row", None)
        assert _apply_auto_selection(plain, "p", {"row": 2}, state)
        state.set_selection("row", None)
        assert _apply_auto_selection(plain, "p", {"row": 2}, state)


def test_unpaginated_table_sends_every_row(mock_streamlit, temp_cache_dir):
    """Without pagination every row is sent unsorted, in their order in the
    data (Tabulator's own sorts start from it), while the default row is the
    first of the sorted rows."""
    from openms_insight import Table

    n = 250
    data = pl.LazyFrame(
        {"id": list(range(n)), "group": [i % 2 for i in range(n)], "score": [1] * n}
    )
    table = Table(
        cache_id="all_rows",
        data=data,
        cache_path=str(temp_cache_dir),
        index_field="id",
        filters={"group": "group"},
        interactivity={"row": "id"},
        initial_sort=[{"column": "id", "dir": "desc"}],
        pagination=False,
    )
    result = table._prepare_vue_data({"group": 1})
    assert list(result["tableData"]["id"]) == list(range(1, n, 2))
    assert result["_auto_selection"] == {"row": n - 1}
    # The initial selection is the first sorted row, not the first sent one
    assert table.get_initial_selection({"group": 1}) == {"row": n - 1}


def test_toggle_filter_colour_reaches_vue(mock_streamlit, temp_cache_dir):
    from openms_insight import Table

    data = pl.LazyFrame({"id": [0, 1], "best": [True, False]})
    table = Table(
        cache_id="toggle_colour",
        data=data,
        cache_path=str(temp_cache_dir),
        index_field="id",
        toggle_filters=[{"label": "Best", "column": "best", "color": "#6200EE"}],
    )
    assert table._get_component_args()["toggleFilters"][0]["color"] == "#6200EE"


def test_series_plot_font(mock_streamlit, temp_cache_dir: Path, sample_series_data):
    """A font of the plot's own reaches Vue (the theme's font otherwise)."""
    from openms_insight import SeriesPlot

    kwargs = {
        "data": sample_series_data,
        "x_column": "Score",
        "y_column": "Density",
        "cache_path": str(temp_cache_dir),
    }
    assert "font" not in SeriesPlot(cache_id="themed", **kwargs)._get_component_args()
    plot = SeriesPlot(
        cache_id="arial", font={"family": "Arial", "color": "black"}, **kwargs
    )
    assert plot._get_component_args()["font"] == {"family": "Arial", "color": "black"}


def test_scroll_position_reaches_vue_and_cache(mock_streamlit, temp_cache_dir):
    from openms_insight import Table

    data = pl.LazyFrame({"id": [0, 1]})
    table = Table(
        cache_id="scroll_top",
        data=data,
        cache_path=str(temp_cache_dir),
        index_field="id",
        scroll_position="top",
    )
    assert table._get_component_args()["scrollPosition"] == "top"
    cached = Table(cache_id="scroll_top", cache_path=str(temp_cache_dir))
    assert cached._get_component_args()["scrollPosition"] == "top"
    default = Table(
        cache_id="scroll_default",
        data=data,
        cache_path=str(temp_cache_dir),
        index_field="id",
    )
    assert "scrollPosition" not in default._get_component_args()
    with pytest.raises(ValueError):
        Table(
            cache_id="bad",
            data=data,
            cache_path=str(temp_cache_dir),
            scroll_position="up",
        )


def test_pandas_hash_of_rows_holding_arrays():
    """Rows holding nested arrays hash by content, not by their text form.

    The text form was slow (seconds for a spectrum's peaks) and summarises the
    middle of a long array as '...', so a change there went unnoticed: the
    changed row below sits in that middle. No wall-clock assertion, which
    fails on a busy CI runner.
    """
    import numpy as np
    import pandas as pd

    from openms_insight.preprocessing.filtering import compute_pandas_dataframe_hash

    peaks = np.array([np.arange(4.0) + i for i in range(50000)], dtype=object)
    df = pd.DataFrame({"id": [0], "peaks": [peaks]})
    first = compute_pandas_dataframe_hash(df)
    changed = peaks.copy()
    changed[100] = changed[100] + 1
    assert (
        compute_pandas_dataframe_hash(pd.DataFrame({"id": [0], "peaks": [changed]}))
        != first
    )
    same = np.array([np.arange(4.0) + i for i in range(50000)], dtype=object)
    assert (
        compute_pandas_dataframe_hash(pd.DataFrame({"id": [0], "peaks": [same]}))
        == first
    )


def test_column_menu_can_be_hidden(mock_streamlit, temp_cache_dir):
    from openms_insight import Table

    data = pl.LazyFrame({"id": [0, 1]})
    table = Table(
        cache_id="no_menu",
        data=data,
        cache_path=str(temp_cache_dir),
        index_field="id",
        column_menu=False,
        reset_sort=True,
        reset_sort_on=["protein"],
    )
    assert table._get_component_args()["columnMenu"] is False
    assert table._get_component_args()["resetSort"] is True
    cached = Table(cache_id="no_menu", cache_path=str(temp_cache_dir))
    assert cached._get_component_args()["columnMenu"] is False
    assert cached._get_component_args()["resetSort"] is True
    assert cached._get_component_args()["resetSortOn"] == ["protein"]
    shown = Table(
        cache_id="menu", data=data, cache_path=str(temp_cache_dir), index_field="id"
    )
    assert "columnMenu" not in shown._get_component_args()
    assert "resetSort" not in shown._get_component_args()


class TestProteinStructureView:
    def _view(self, data, cache_dir, **kwargs):
        from openms_insight import ProteinStructureView

        return ProteinStructureView(
            cache_id="structure_view",
            data=data,
            filters={"protein": "hit_index"},
            aa_identifier="aa",
            cache_path=str(cache_dir),
            **kwargs,
        )

    def test_entry_and_structure(
        self, mock_streamlit, temp_cache_dir, sample_protein_sequence_data
    ):
        view = self._view(sample_protein_sequence_data, temp_cache_dir)
        args = view._get_component_args()
        assert args["componentType"] == "ProteinStructureView"
        assert args["aaIdentifier"] == "aa"
        assert args["viewerHeight"] == 480
        assert args["emptyMessage"] == "Select an entry to show its structure."

        data = view._prepare_vue_data({"protein": 1})
        assert data["sequenceData"]["sequence"] == list("ACDK")
        assert data["spectrumData"]["masses"] == [72.04]
        assert data["structure"] is None

        empty = view._prepare_vue_data({"protein": 1})["_hash"]
        view.set_structure({"status": "ok", "format": "pdb", "data": "ATOM  1"})
        data = view._prepare_vue_data({"protein": 1})
        assert data["structure"]["data"] == "ATOM  1"
        assert data["_hash"] != empty
        view.set_structure({"status": "ok", "format": "pdb", "data": "ATOM  2"})
        assert view._prepare_vue_data({"protein": 1})["_hash"] != data["_hash"]

    def test_new_structure_is_not_served_stale(
        self, mock_streamlit, temp_cache_dir, sample_protein_sequence_data
    ):
        # An upload changes the structure while the selection stays the same
        from unittest.mock import patch

        from openms_insight.rendering.bridge import (
            _payload_cache_key,
            _prepare_vue_data_cached,
        )

        view = self._view(sample_protein_sequence_data, temp_cache_dir)
        state_keys = set(view.get_state_dependencies())

        def render():
            key = _payload_cache_key(view, {"protein": 1}, state_keys)
            with patch(
                "openms_insight.rendering.bridge.st.session_state", mock_streamlit
            ):
                data, _ = _prepare_vue_data_cached(
                    view, "structure_view", key, {"protein": 1}
                )
            return data["structure"]

        view.set_structure({"status": "ok", "format": "pdb", "data": "ATOM  1"})
        assert render()["data"] == "ATOM  1"
        view.set_structure({"status": "ok", "format": "pdb", "data": "ATOM  2"})
        assert render()["data"] == "ATOM  2"
        view.set_structure(None)
        assert render() is None

    def test_structure_actions(
        self, mock_streamlit, temp_cache_dir, sample_protein_sequence_data
    ):
        view = self._view(sample_protein_sequence_data, temp_cache_dir)
        assert view._get_component_args()["structureUploads"] is False
        event = {
            "type": "structure",
            "op": "upload",
            "accession": "P60844",
            "name": "x.pdb",
            "data": "ATOM",
            "nonce": "1",
        }
        assert view._handle_event(event) is False

        received = []
        view.on_structure_action(lambda action: received.append(action) or True)
        assert view._get_component_args()["structureUploads"] is True
        assert view._handle_event({"type": "other", "nonce": "2"}) is False
        assert view._handle_event(event) is True
        assert received == [
            {"op": "upload", "accession": "P60844", "name": "x.pdb", "data": "ATOM"}
        ]

    def test_structure_is_validated(
        self, mock_streamlit, temp_cache_dir, sample_protein_sequence_data
    ):
        view = self._view(sample_protein_sequence_data, temp_cache_dir)
        with pytest.raises(ValueError, match="status"):
            view.set_structure({"status": "found"})
        with pytest.raises(ValueError, match="format"):
            view.set_structure({"status": "ok", "format": "mol2", "data": ""})
        view.set_structure({"status": "missing", "message": "No structure"})

    def test_options_survive_the_cache(
        self, mock_streamlit, temp_cache_dir, sample_protein_sequence_data
    ):
        from openms_insight import ProteinStructureView

        self._view(
            sample_protein_sequence_data,
            temp_cache_dir,
            empty_message="Pick a protein.",
            viewer_height=300,
            fragment_identifier="fragment",
        )
        restored = ProteinStructureView(
            cache_id="structure_view", cache_path=str(temp_cache_dir)
        )
        args = restored._get_component_args()
        assert args["emptyMessage"] == "Pick a protein."
        assert args["viewerHeight"] == 300
        assert args["fragmentIdentifier"] == "fragment"
