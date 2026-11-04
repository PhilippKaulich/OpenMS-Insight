"""Constructor validation tests for MirrorPlot."""

import polars as pl
import pytest

from openms_insight import MirrorPlot


class TestMirrorPlotValidation:
    def test_missing_filters_top_raises(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        with pytest.raises(ValueError, match="filters_top"):
            MirrorPlot(
                cache_id="test_missing_top",
                data=sample_lineplot_data,
                cache_path=str(temp_cache_dir),
                filters_bottom={"spectrum_bottom": "scan_id"},
                x_column="mass",
                y_column="intensity",
            )

    def test_missing_filters_bottom_raises(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        with pytest.raises(ValueError, match="filters_bottom"):
            MirrorPlot(
                cache_id="test_missing_bottom",
                data=sample_lineplot_data,
                cache_path=str(temp_cache_dir),
                filters_top={"spectrum_top": "scan_id"},
                x_column="mass",
                y_column="intensity",
            )

    def test_shared_identifier_filters_each_half_by_its_column(
        self, mock_streamlit, temp_cache_dir
    ):
        """Both halves may follow one selection, each through its own column
        (e.g. observed and theoretical peaks of the selected spectrum)."""
        data = pl.LazyFrame(
            {
                "observed_scan": [1, 1, None, None, 2],
                "theoretical_scan": [None, None, 1, 1, None],
                "mass": [100.0, 101.0, 100.0, 101.0, 200.0],
                "intensity": [10.0, 5.0, 9.0, 6.0, 1.0],
            }
        )
        mirror = MirrorPlot(
            cache_id="test_shared_identifier",
            data=data,
            cache_path=str(temp_cache_dir),
            filters_top={"spectrum": "observed_scan"},
            filters_bottom={"spectrum": "theoretical_scan"},
            x_column="mass",
            y_column="intensity",
        )
        vue_data = mirror._prepare_vue_data({"spectrum": 1})
        assert list(vue_data["plotDataTop"]["intensity"]) == [10.0, 5.0]
        assert list(vue_data["plotDataBottom"]["intensity"]) == [9.0, 6.0]

    def test_invalid_x_column_raises(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        with pytest.raises(ValueError, match="x_column"):
            MirrorPlot(
                cache_id="test_bad_x",
                data=sample_lineplot_data,
                cache_path=str(temp_cache_dir),
                filters_top={"spectrum_top": "scan_id"},
                filters_bottom={"spectrum_bottom": "scan_id"},
                x_column="not_a_column",
                y_column="intensity",
            )

    def test_invalid_filter_column_raises(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        with pytest.raises(ValueError, match="not.*found"):
            MirrorPlot(
                cache_id="test_bad_filter_col",
                data=sample_lineplot_data,
                cache_path=str(temp_cache_dir),
                filters_top={"spectrum_top": "missing_col"},
                filters_bottom={"spectrum_bottom": "scan_id"},
                x_column="mass",
                y_column="intensity",
            )

    def test_invalid_interactivity_column_raises(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        with pytest.raises(ValueError, match="not.*found"):
            MirrorPlot(
                cache_id="test_bad_interact_col",
                data=sample_lineplot_data,
                cache_path=str(temp_cache_dir),
                filters_top={"spectrum_top": "scan_id"},
                filters_bottom={"spectrum_bottom": "scan_id"},
                interactivity={"peak": "missing_col"},
                x_column="mass",
                y_column="intensity",
            )

    def test_state_dependencies_returns_identifier_keys(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """get_state_dependencies returns identifier names (.keys()), not column names (.values())."""
        mp = MirrorPlot.__new__(MirrorPlot)
        mp._filters_top = {"spectrum_top": "scan_id"}
        mp._filters_bottom = {"spectrum_bottom": "scan_id"}
        deps = mp.get_state_dependencies()
        assert deps == ["spectrum_top", "spectrum_bottom"]
        # Sanity check: filter columns (values) are NOT in the deps
        assert "scan_id" not in deps

    def test_reconstruct_from_cache_only(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """After full creation, instantiate with just cache_id — succeeds."""
        # First, create with full args to populate cache
        MirrorPlot(
            cache_id="test_reconstruct",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            filters_top={"spectrum_top": "scan_id"},
            filters_bottom={"spectrum_bottom": "scan_id"},
            interactivity={"selected_peak": "peak_id"},
            x_column="mass",
            y_column="intensity",
            title_top="Top",
            title_bottom="Bottom",
        )
        # Then reconstruct with only cache_id + cache_path
        restored = MirrorPlot(
            cache_id="test_reconstruct",
            cache_path=str(temp_cache_dir),
        )
        assert restored._title_top == "Top"
        assert restored._title_bottom == "Bottom"
        assert restored._filters_top == {"spectrum_top": "scan_id"}
        assert restored._filters_bottom == {"spectrum_bottom": "scan_id"}
