"""Contract tests for MirrorPlot."""

import pandas as pd
import pytest

from openms_insight import MirrorPlot


class TestMirrorPlotContract:
    def test_cache_config_roundtrip(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """_get_cache_config / _restore_cache_config preserves every field."""
        original = MirrorPlot(
            cache_id="test_roundtrip",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            filters_top={"spectrum_top": "scan_id"},
            filter_defaults_top={"spectrum_top": 1},
            filters_bottom={"spectrum_bottom": "scan_id"},
            filter_defaults_bottom={"spectrum_bottom": 2},
            interactivity={"selected_peak": "peak_id"},
            x_column="mass",
            y_column="intensity",
            highlight_column="annotation",
            annotation_column="annotation",
            title="Compare",
            title_top="PSM A",
            title_bottom="PSM B",
            x_label="m/z",
            y_label="Intensity",
            styling={"unhighlightedColor": "#1f77b4"},
            config={"displayModeBar": True},
        )
        config = original._get_cache_config()

        # Every constructor field that affects rendering must round-trip
        assert config["filters_top"] == {"spectrum_top": "scan_id"}
        assert config["filters_bottom"] == {"spectrum_bottom": "scan_id"}
        assert config["filter_defaults_top"] == {"spectrum_top": 1}
        assert config["filter_defaults_bottom"] == {"spectrum_bottom": 2}
        assert config["x_column"] == "mass"
        assert config["y_column"] == "intensity"
        assert config["highlight_column"] == "annotation"
        assert config["annotation_column"] == "annotation"
        assert config["title"] == "Compare"
        assert config["title_top"] == "PSM A"
        assert config["title_bottom"] == "PSM B"
        assert config["x_label"] == "m/z"
        assert config["y_label"] == "Intensity"
        assert config["styling"] == {"unhighlightedColor": "#1f77b4"}
        assert config["plot_config"] == {"displayModeBar": True}

        # Restore on a fresh instance
        restored = MirrorPlot(
            cache_id="test_roundtrip_target",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            filters_top={"spectrum_top": "scan_id"},
            filters_bottom={"spectrum_bottom": "scan_id"},
            x_column="mass",
            y_column="intensity",
        )
        restored._restore_cache_config(config)

        assert restored._filters_top == {"spectrum_top": "scan_id"}
        assert restored._filters_bottom == {"spectrum_bottom": "scan_id"}
        assert restored._filter_defaults_top == {"spectrum_top": 1}
        assert restored._filter_defaults_bottom == {"spectrum_bottom": 2}
        assert restored._title_top == "PSM A"
        assert restored._title_bottom == "PSM B"
        assert restored._top_dynamic_annotations is None
        assert restored._bottom_dynamic_annotations is None
        assert restored._top_dynamic_title is None
        assert restored._bottom_dynamic_title is None
        assert restored._x_column == "mass"
        assert restored._y_column == "intensity"
        assert restored._highlight_column == "annotation"
        assert restored._annotation_column == "annotation"
        assert restored._title == "Compare"
        assert restored._x_label == "m/z"
        assert restored._y_label == "Intensity"
        assert restored._styling == {"unhighlightedColor": "#1f77b4"}
        assert restored._plot_config == {"displayModeBar": True}


class TestMirrorPlotPrepareVueData:
    def _make(self, temp_cache_dir, data, **overrides):
        defaults = {
            "cache_id": "test_prepare",
            "data": data,
            "cache_path": str(temp_cache_dir),
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "interactivity": {"selected_peak": "peak_id"},
            "x_column": "mass",
            "y_column": "intensity",
        }
        defaults.update(overrides)
        return MirrorPlot(**defaults)

    def test_returns_dict_with_hash(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        assert isinstance(result, dict)
        assert "_hash" in result
        assert isinstance(result["_hash"], str)

    def test_returns_both_dataframes(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        assert "plotDataTop" in result
        assert "plotDataBottom" in result
        assert isinstance(result["plotDataTop"], pd.DataFrame)
        assert isinstance(result["plotDataBottom"], pd.DataFrame)

    def test_filters_independently(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """Top selection (scan 1) and bottom selection (scan 2) produce disjoint rows."""
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        df_top = result["plotDataTop"]
        df_bot = result["plotDataBottom"]
        # sample_lineplot_data has scan_id [1,1,1,2,2]: scan 1 has 3 rows, scan 2 has 2
        assert len(df_top) == 3
        assert len(df_bot) == 2
        assert set(df_top["scan_id"]) == {1}
        assert set(df_bot["scan_id"]) == {2}

    def test_keeps_y_positive_on_bottom(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """Vue does the y-flip; Python emits positive intensities for both halves."""
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        assert (result["plotDataTop"]["intensity"] >= 0).all()
        assert (result["plotDataBottom"]["intensity"] >= 0).all()

    def test_get_data_key_returns_plotDataTop(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        assert comp._get_data_key() == "plotDataTop"

    def test_state_dependencies_includes_both_sides(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        deps = comp.get_state_dependencies()
        assert "spectrum_top" in deps
        assert "spectrum_bottom" in deps

    def test_state_dependencies_excludes_interactivity(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        assert "selected_peak" not in comp.get_state_dependencies()

    def test_build_plot_config_accepts_two_args(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """Bridge calls _build_plot_config with 2 args; both halves get the same columns."""
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._build_plot_config("highlight_col_name", "annotation_col_name")
        assert result["topHighlightColumn"] == "highlight_col_name"
        assert result["bottomHighlightColumn"] == "highlight_col_name"
        assert result["topAnnotationColumn"] == "annotation_col_name"
        assert result["bottomAnnotationColumn"] == "annotation_col_name"


class TestMirrorPlotComponentArgs:
    def _make(self, temp_cache_dir, data, **overrides):
        defaults = {
            "cache_id": "test_args",
            "data": data,
            "cache_path": str(temp_cache_dir),
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "interactivity": {"selected_peak": "peak_id"},
            "x_column": "mass",
            "y_column": "intensity",
        }
        defaults.update(overrides)
        return MirrorPlot(**defaults)

    def test_includes_componentType(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        args = comp._get_component_args()
        assert args["componentType"] == "PlotlyMirrorPlot"

    def test_carries_per_side_titles_and_columns(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(
            temp_cache_dir,
            sample_lineplot_data,
            title="Compare",
            title_top="A",
            title_bottom="B",
            x_label="m/z",
            y_label="Intensity",
        )
        args = comp._get_component_args()
        assert args["title"] == "Compare"
        assert args["titleTop"] == "A"
        assert args["titleBottom"] == "B"
        assert args["xLabel"] == "m/z"
        assert args["yLabel"] == "Intensity"
        assert args["xColumn"] == "mass"
        assert args["yColumn"] == "intensity"
        assert args["interactivity"] == {"selected_peak": "peak_id"}

    def test_styling_merged_with_defaults(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(
            temp_cache_dir,
            sample_lineplot_data,
            styling={"unhighlightedColor": "#1f77b4"},
        )
        args = comp._get_component_args()
        # Override applied
        assert args["styling"]["unhighlightedColor"] == "#1f77b4"
        # Defaults preserved for unspecified keys
        assert "highlightColor" in args["styling"]
        assert "selectedColor" in args["styling"]

    def test_svg_filename_reaches_vue_and_survives_cache(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """svg_filename reaches Vue, also when loaded from the cache, and a plot
        without it keeps its old cache config (no hash change)."""
        plain = self._make(temp_cache_dir, sample_lineplot_data, cache_id="plain")
        assert "svgFilename" not in plain._get_component_args()
        assert "svg_filename" not in plain._get_cache_config()

        self._make(
            temp_cache_dir,
            sample_lineplot_data,
            cache_id="named",
            svg_filename="psm_scan_42",
        )
        loaded = MirrorPlot(cache_id="named", cache_path=str(temp_cache_dir))
        assert loaded._get_component_args()["svgFilename"] == "psm_scan_42"


class TestMirrorPlotMeasure:
    def _make(self, temp_cache_dir, data, **overrides):
        defaults = {
            "cache_id": "test_measure",
            "data": data,
            "cache_path": str(temp_cache_dir),
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "interactivity": {"selected_peak": "peak_id"},
            "x_column": "mass",
            "y_column": "intensity",
        }
        defaults.update(overrides)
        return MirrorPlot(**defaults)

    def test_on_by_default_and_never_in_the_cache_config(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """measure is on by default, and no measure option reaches the cache."""
        plain = self._make(temp_cache_dir, sample_lineplot_data, cache_id="plain")
        args = plain._get_component_args()
        assert args["measure"] is True
        assert args["measureTolerance"] == 0.02
        assert "measureResidues" not in args
        config = plain._get_cache_config()
        assert not any(key.startswith("measure") for key in config)

        off = self._make(
            temp_cache_dir,
            sample_lineplot_data,
            cache_id="off",
            measure=False,
            measure_tolerance=0.05,
            measure_residues={"M(Oxidation)": 147.0354},
        )
        args = off._get_component_args()
        assert args["measure"] is False
        assert "measureTolerance" not in args
        assert "measureResidues" not in args
        assert off._compute_config_hash() == plain._compute_config_hash()

    def test_measure_args_reach_vue(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data, measure=True)
        args = comp._get_component_args()
        assert args["measure"] is True
        assert args["measureTolerance"] == 0.02
        assert "measureResidues" not in args

        comp = self._make(
            temp_cache_dir,
            sample_lineplot_data,
            cache_id="measure_custom",
            measure=True,
            measure_tolerance=0.005,
            measure_residues={"M(Oxidation)": 147.0354},
        )
        args = comp._get_component_args()
        assert args["measureTolerance"] == 0.005
        assert args["measureResidues"] == {"M(Oxidation)": 147.0354}

    def test_measure_options_apply_when_loading_a_cache(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """Loading by cache_id takes the measure options passed now, not the
        ones the cache was built with: they are not stored in it."""
        self._make(
            temp_cache_dir,
            sample_lineplot_data,
            cache_id="measured",
            measure_tolerance=0.01,
            measure_residues={"C(Carbamidomethyl)": 160.03065},
        )
        loaded = MirrorPlot(cache_id="measured", cache_path=str(temp_cache_dir))
        args = loaded._get_component_args()
        assert args["measure"] is True
        assert args["measureTolerance"] == 0.02
        assert "measureResidues" not in args

        loaded = MirrorPlot(
            cache_id="measured",
            cache_path=str(temp_cache_dir),
            measure_residues={"C(Carbamidomethyl)": 160.03065},
        )
        assert loaded._get_component_args()["measureResidues"] == {
            "C(Carbamidomethyl)": 160.03065
        }

    def test_measure_can_be_switched_off_when_loading_a_cache(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        self._make(temp_cache_dir, sample_lineplot_data, cache_id="plain_cache")
        loaded = MirrorPlot(
            cache_id="plain_cache", cache_path=str(temp_cache_dir), measure=False
        )
        assert loaded._get_component_args()["measure"] is False

    def test_measure_plot_from_data_path_reuses_its_cache(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data, tmp_path
    ):
        """A data_path plot (built in a subprocess) with measure options finds
        its cache again on the next construction instead of rebuilding it, also
        when the options change."""
        parquet = tmp_path / "peaks.parquet"
        sample_lineplot_data.collect().write_parquet(parquet)
        options = {
            "data_path": str(parquet),
            "cache_id": "measured_path",
            "measure": True,
            "measure_residues": {"M(Oxidation)": 147.0354},
        }
        first = self._make(temp_cache_dir, None, **options)
        manifest = first._get_manifest_path()
        before = manifest.stat().st_mtime_ns

        second = self._make(temp_cache_dir, None, **options)
        assert manifest.stat().st_mtime_ns == before
        args = second._get_component_args()
        assert args["measure"] is True
        assert args["measureResidues"] == {"M(Oxidation)": 147.0354}

        third = self._make(temp_cache_dir, None, **{**options, "measure": False})
        assert manifest.stat().st_mtime_ns == before
        assert third._get_component_args()["measure"] is False

    @pytest.mark.parametrize(
        "overrides",
        [
            {"measure_tolerance": -0.1},
            {"measure_tolerance": float("nan")},
            {"measure_tolerance": "0.02"},
            {"measure_residues": [("X", 100.0)]},
            {"measure_residues": {"": 100.0}},
            {"measure_residues": {"X": 0}},
            {"measure_residues": {"X": "heavy"}},
            {"measure": "yes"},
            {"measure": 1},
            {"measure": None},
        ],
    )
    def test_invalid_measure_options_raise(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data, overrides
    ):
        with pytest.raises(ValueError, match="measure"):
            self._make(temp_cache_dir, sample_lineplot_data, **overrides)


class TestMirrorPlotDynamicAnnotations:
    def _make(self, temp_cache_dir, data, **overrides):
        defaults = {
            "cache_id": "test_dyn",
            "data": data,
            "cache_path": str(temp_cache_dir),
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "interactivity": {"selected_peak": "peak_id"},
            "x_column": "mass",
            "y_column": "intensity",
        }
        defaults.update(overrides)
        return MirrorPlot(**defaults)

    def test_set_top_only_affects_top(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_top_dynamic_annotations(
            {10: {"highlight": True, "annotation": "b1"}},
            title="Top!",
        )
        assert comp._top_dynamic_annotations == {
            10: {"highlight": True, "annotation": "b1"}
        }
        assert comp._top_dynamic_title == "Top!"
        assert comp._bottom_dynamic_annotations is None
        assert comp._bottom_dynamic_title is None

    def test_set_bottom_only_affects_bottom(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}, title="Bot"
        )
        assert comp._bottom_dynamic_annotations == {
            40: {"highlight": True, "annotation": "y3"}
        }
        assert comp._bottom_dynamic_title == "Bot"
        assert comp._top_dynamic_annotations is None

    def test_clear_top_only(self, mock_streamlit, temp_cache_dir, sample_lineplot_data):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}
        )
        comp.clear_dynamic_annotations(side="top")
        assert comp._top_dynamic_annotations is None
        assert comp._top_dynamic_title is None
        # Bottom untouched
        assert comp._bottom_dynamic_annotations == {
            40: {"highlight": True, "annotation": "y3"}
        }

    def test_clear_bottom_only(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}
        )
        comp.clear_dynamic_annotations(side="bottom")
        assert comp._bottom_dynamic_annotations is None
        assert comp._bottom_dynamic_title is None
        # Top untouched
        assert comp._top_dynamic_annotations == {
            10: {"highlight": True, "annotation": "b1"}
        }

    def test_clear_both(self, mock_streamlit, temp_cache_dir, sample_lineplot_data):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}
        )
        comp.clear_dynamic_annotations()  # side=None default
        assert comp._top_dynamic_annotations is None
        assert comp._bottom_dynamic_annotations is None
        assert comp._top_dynamic_title is None
        assert comp._bottom_dynamic_title is None

    def test_setters_return_self_for_chaining(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        assert comp.set_top_dynamic_annotations({}) is comp
        assert comp.set_bottom_dynamic_annotations({}) is comp
        assert comp.clear_dynamic_annotations() is comp


class TestMirrorPlotBridgeIntegration:
    def _make(self, temp_cache_dir, data, **overrides):
        defaults = {
            "cache_id": "test_bridge",
            "data": data,
            "cache_path": str(temp_cache_dir),
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "interactivity": {"selected_peak": "peak_id"},
            "x_column": "mass",
            "y_column": "intensity",
        }
        defaults.update(overrides)
        return MirrorPlot(**defaults)

    def test_strip_drops_dynamic_columns_from_both(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        # Build vue_data containing dynamic cols on both sides
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}
        )
        vue_data = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        assert "_dynamic_highlight" in vue_data["plotDataTop"].columns
        assert "_dynamic_highlight" in vue_data["plotDataBottom"].columns

        stripped = comp._strip_dynamic_columns(vue_data)
        assert "_dynamic_highlight" not in stripped["plotDataTop"].columns
        assert "_dynamic_annotation" not in stripped["plotDataTop"].columns
        assert "_dynamic_highlight" not in stripped["plotDataBottom"].columns
        assert "_dynamic_annotation" not in stripped["plotDataBottom"].columns
        # _plotConfig also removed (may reference dynamic column names)
        assert "_plotConfig" not in stripped

    def test_apply_fresh_annotations_top_only(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        # Build cached vue_data with no annotations
        cached = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        cached_clean = comp._strip_dynamic_columns(cached)

        # Set top annotations only
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        refreshed = comp._apply_fresh_annotations(cached_clean)

        assert "_dynamic_highlight" in refreshed["plotDataTop"].columns
        # Bottom must NOT have dynamic columns since no bottom annotations set
        assert "_dynamic_highlight" not in refreshed["plotDataBottom"].columns
        # _plotConfig rebuilt
        assert "_plotConfig" in refreshed
