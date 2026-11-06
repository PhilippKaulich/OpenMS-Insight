"""
Tests for compression.py downsampling functions.
"""

import polars as pl

from openms_insight.preprocessing.compression import (
    downsample_2d_simple,
    downsample_2d_streaming,
)


class TestDownsampleDescendingParameter:
    """Test descending parameter in downsampling functions."""

    def test_simple_descending_true_keeps_high(self):
        """descending=True keeps highest values."""
        data = pl.LazyFrame(
            {
                "x": [1, 2, 3, 4, 5],
                "intensity": [100, 500, 200, 400, 300],
            }
        )
        result = downsample_2d_simple(
            data, max_points=3, intensity_column="intensity", descending=True
        ).collect()

        intensities = result["intensity"].to_list()
        assert 500 in intensities
        assert 400 in intensities
        assert 300 in intensities

    def test_simple_descending_false_keeps_low(self):
        """descending=False keeps lowest values."""
        data = pl.LazyFrame(
            {
                "x": [1, 2, 3, 4, 5],
                "intensity": [100, 500, 200, 400, 300],
            }
        )
        result = downsample_2d_simple(
            data, max_points=3, intensity_column="intensity", descending=False
        ).collect()

        intensities = result["intensity"].to_list()
        assert 100 in intensities
        assert 200 in intensities
        assert 300 in intensities

    def test_simple_default_is_descending_true(self):
        """Default behavior (no descending arg) keeps highest values."""
        data = pl.LazyFrame(
            {
                "x": [1, 2, 3, 4, 5],
                "intensity": [100, 500, 200, 400, 300],
            }
        )
        result = downsample_2d_simple(
            data, max_points=3, intensity_column="intensity"
        ).collect()

        intensities = result["intensity"].to_list()
        # Default should keep highest
        assert 500 in intensities
        assert 400 in intensities
        assert 300 in intensities

    def test_streaming_descending_true_keeps_high(self):
        """descending=True keeps highest values in streaming mode."""
        data = pl.LazyFrame(
            {
                "x": [1.0, 2.0, 3.0, 4.0, 5.0],
                "y": [10.0, 20.0, 30.0, 40.0, 50.0],
                "intensity": [100.0, 500.0, 200.0, 400.0, 300.0],
            }
        )
        result = downsample_2d_streaming(
            data,
            max_points=3,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=5,
            y_bins=5,
            descending=True,
        ).collect()

        intensities = result["intensity"].to_list()
        # Should keep highest values
        assert 500.0 in intensities
        assert 400.0 in intensities
        assert 300.0 in intensities

    def test_streaming_descending_false_keeps_low(self):
        """descending=False keeps lowest values in streaming mode."""
        data = pl.LazyFrame(
            {
                "x": [1.0, 2.0, 3.0, 4.0, 5.0],
                "y": [10.0, 20.0, 30.0, 40.0, 50.0],
                "intensity": [100.0, 500.0, 200.0, 400.0, 300.0],
            }
        )
        result = downsample_2d_streaming(
            data,
            max_points=3,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=5,
            y_bins=5,
            descending=False,
        ).collect()

        intensities = result["intensity"].to_list()
        # Should keep lowest values
        assert 100.0 in intensities
        assert 200.0 in intensities
        assert 300.0 in intensities

    def test_streaming_default_is_descending_true(self):
        """Default behavior (no descending arg) keeps highest values in streaming."""
        data = pl.LazyFrame(
            {
                "x": [1.0, 2.0, 3.0, 4.0, 5.0],
                "y": [10.0, 20.0, 30.0, 40.0, 50.0],
                "intensity": [100.0, 500.0, 200.0, 400.0, 300.0],
            }
        )
        result = downsample_2d_streaming(
            data,
            max_points=3,
            x_column="x",
            y_column="y",
            intensity_column="intensity",
            x_bins=5,
            y_bins=5,
        ).collect()

        intensities = result["intensity"].to_list()
        # Default should keep highest
        assert 500.0 in intensities
        assert 400.0 in intensities
        assert 300.0 in intensities


def test_import_leaves_scipy_stats_unloaded():
    """Importing the package must not load scipy.stats: it takes half a second
    or more, and apps pay it on the first page load after every restart."""
    import subprocess
    import sys

    code = "import sys, openms_insight; print('scipy.stats' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"
