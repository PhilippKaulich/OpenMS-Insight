"""Compression utilities for large 2D datasets (heatmaps).

This module provides functions for multi-resolution downsampling of 2D scatter
data, enabling efficient visualization of datasets with millions of points.

Supports both streaming (lazy) and eager downsampling approaches.
"""

import importlib.util
import math

import numpy as np
import polars as pl

# scipy.stats is imported where it is used: importing it takes about half a
# second (longer on a cold disk), which every app paid on its first page load
# even when no heatmap was downsampled.
HAS_SCIPY = importlib.util.find_spec("scipy") is not None


def compute_optimal_bins(
    target_points: int,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
) -> tuple[int, int]:
    """
    Compute optimal x_bins, y_bins for even spatial distribution.

    The bin grid matches the data's aspect ratio so bins are approximately
    square in data space. Total bins ≈ target_points for 1 point per bin.

    Solves the system:
        x_bins × y_bins = target_points
        x_bins / y_bins = aspect_ratio

    Solution:
        y_bins = sqrt(target_points / aspect_ratio)
        x_bins = sqrt(target_points × aspect_ratio)

    Args:
        target_points: Target number of bins (and thus max points with 1 per bin)
        x_range: (x_min, x_max) data range
        y_range: (y_min, y_max) data range

    Returns:
        (x_bins, y_bins) tuple

    Examples:
        >>> compute_optimal_bins(10000, (0, 1000), (0, 100))  # 10:1 aspect
        (316, 31)
        >>> compute_optimal_bins(10000, (0, 100), (0, 100))   # 1:1 aspect
        (100, 100)
    """
    x_span = x_range[1] - x_range[0]
    y_span = y_range[1] - y_range[0]

    # Handle edge cases
    if y_span < 1e-10:
        y_span = x_span if x_span > 1e-10 else 1.0
    if x_span < 1e-10:
        x_span = y_span

    aspect_ratio = x_span / y_span

    # Clamp to reasonable bounds (avoid extreme rectangles)
    aspect_ratio = max(0.05, min(20.0, aspect_ratio))

    y_bins = max(1, int(math.sqrt(target_points / aspect_ratio)))
    x_bins = max(1, int(math.sqrt(target_points * aspect_ratio)))

    return x_bins, y_bins


def compute_compression_levels(min_size: int, total: int) -> list[int]:
    """
    Compute logarithmically-spaced compression level target sizes.

    Given a minimum target size and total data size, computes intermediate
    compression levels at powers of 10.

    Args:
        min_size: Minimum/smallest compression level size (e.g., 20000)
        total: Total number of data points

    Returns:
        List of target sizes, smallest first. Always returns at least one level.
        For small datasets (total <= min_size), returns [total] to preserve all data.

    Examples:
        >>> compute_compression_levels(20000, 1_000_000)
        [20000, 200000]
        >>> compute_compression_levels(20000, 50_000)
        [20000]
        >>> compute_compression_levels(20000, 15_000)
        [15000]
    """
    if total <= min_size:
        # Still return at least one level with all data
        return [total]

    # Compute powers of 10 between min and total
    min_power = int(np.log10(min_size))
    max_power = int(np.log10(total))

    if min_power >= max_power:
        # Data is between min_size and 10x min_size - one downsampled level
        return [min_size]

    # Generate levels at each power of 10, scaled by the fractional part
    scale_factor = int(10 ** (np.log10(min_size) % 1))
    levels = (
        np.logspace(min_power, max_power, max_power - min_power + 1, dtype="int")
        * scale_factor
    )

    # Filter out levels >= total (don't include full resolution for large datasets)
    levels = levels[levels < total].tolist()

    # Ensure at least one level exists
    if not levels:
        levels = [min_size]

    return levels


def downsample_2d(
    data: pl.LazyFrame | pl.DataFrame,
    max_points: int = 20000,
    x_column: str = "x",
    y_column: str = "y",
    intensity_column: str = "intensity",
    x_bins: int = 400,
    y_bins: int = 50,
) -> pl.LazyFrame:
    """
    Downsample 2D scatter data while preserving high-intensity points.

    Uses 2D binning to spatially partition data, then keeps the top N
    highest-intensity points per bin. This preserves visually important
    features (peaks) while reducing total point count.

    Args:
        data: Input data as Polars LazyFrame or DataFrame
        max_points: Maximum number of points to keep
        x_column: Name of x-axis column
        y_column: Name of y-axis column
        intensity_column: Name of intensity/value column for ranking
        x_bins: Number of bins along x-axis
        y_bins: Number of bins along y-axis

    Returns:
        Downsampled data as Polars LazyFrame

    Raises:
        ImportError: If scipy is not installed
        ValueError: If x_bins * y_bins > max_points
    """
    if not HAS_SCIPY:
        raise ImportError(
            "scipy is required for downsample_2d. Install with: pip install scipy"
        )

    if (x_bins * y_bins) > max_points:
        raise ValueError(
            f"Number of bins ({x_bins * y_bins}) exceeds max_points ({max_points}). "
            "Reduce x_bins or y_bins."
        )

    # Ensure we're working with a LazyFrame
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    # Sort by intensity (descending) to prioritize high-intensity points
    sorted_data = (
        data.sort([x_column, intensity_column], descending=[False, True])
        .with_columns([pl.int_range(pl.len()).over(x_column).alias("_rank")])
        .sort(["_rank", intensity_column], descending=[False, True])
    )

    # Collect for scipy binning (requires numpy arrays)
    collected = sorted_data.collect()

    total_count = len(collected)
    if total_count <= max_points:
        # No downsampling needed
        return collected.drop("_rank").lazy()

    # Extract arrays for scipy
    x_array = collected[x_column].to_numpy()
    y_array = collected[y_column].to_numpy()
    intensity_array = collected[intensity_column].to_numpy()

    from scipy.stats import binned_statistic_2d

    # Compute 2D bins
    count, _, _, mapping = binned_statistic_2d(
        x_array,
        y_array,
        intensity_array,
        "count",
        bins=[x_bins, y_bins],
        expand_binnumbers=True,
    )

    # Add bin indices to dataframe
    binned_data = collected.lazy().with_columns(
        [
            pl.Series("_x_bin", mapping[0] - 1),  # scipy uses 1-based indexing
            pl.Series("_y_bin", mapping[1] - 1),
        ]
    )

    # Compute max peaks per bin to stay under limit
    counted_peaks = 0
    max_peaks_per_bin = -1
    new_count = 0

    while (counted_peaks + new_count) < max_points:
        max_peaks_per_bin += 1
        counted_peaks += new_count
        new_count = np.sum(count.flatten() >= (max_peaks_per_bin + 1))

        if counted_peaks >= total_count:
            break

    # Keep top N peaks per bin
    result = (
        binned_data.group_by(["_x_bin", "_y_bin"])
        .head(max_peaks_per_bin)
        .sort(intensity_column)
        .drop(["_rank", "_x_bin", "_y_bin"])
    )

    return result


def downsample_2d_simple(
    data: pl.LazyFrame | pl.DataFrame,
    max_points: int = 20000,
    intensity_column: str = "intensity",
    descending: bool = True,
) -> pl.LazyFrame:
    """
    Simple downsampling by keeping top-priority points.

    A simpler alternative to downsample_2d that doesn't require scipy.
    Less spatially aware but still preserves important peaks.

    Args:
        data: Input data as Polars LazyFrame or DataFrame
        max_points: Maximum number of points to keep
        intensity_column: Name of intensity column for ranking
        descending: If True (default), keep highest values. If False, keep lowest.

    Returns:
        Downsampled data as Polars LazyFrame
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    return data.sort(intensity_column, descending=descending).head(max_points)


def downsample_2d_streaming(
    data: pl.LazyFrame | pl.DataFrame,
    max_points: int = 20000,
    x_column: str = "x",
    y_column: str = "y",
    intensity_column: str = "intensity",
    x_bins: int = 400,
    y_bins: int = 50,
    x_range: tuple | None = None,
    y_range: tuple | None = None,
    descending: bool = True,
) -> pl.LazyFrame:
    """
    Streaming 2D downsampling using pure Polars operations.

    Uses Polars' lazy evaluation to downsample data without full materialization.
    Creates spatial bins using integer division and keeps top-N highest-intensity
    points per bin. Stays fully lazy - no .collect() is called.

    Args:
        data: Input data as Polars LazyFrame or DataFrame
        max_points: Maximum number of points to keep
        x_column: Name of x-axis column
        y_column: Name of y-axis column
        intensity_column: Name of intensity/value column for ranking
        x_bins: Number of bins along x-axis
        y_bins: Number of bins along y-axis
        x_range: Optional (min, max) tuple for x-axis. If None, computed from data.
        y_range: Optional (min, max) tuple for y-axis. If None, computed from data.
        descending: If True (default), keep highest intensity per bin.
            If False, keep lowest intensity per bin.

    Returns:
        Downsampled data as Polars LazyFrame (fully lazy, no collection)
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    # Calculate points per bin
    total_bins = x_bins * y_bins
    points_per_bin = max(1, max_points // total_bins)

    # Build binning expression using provided or computed ranges
    if x_range is not None and y_range is not None:
        x_min, x_max = x_range
        y_min, y_max = y_range

        # Use provided ranges for bin calculation
        x_bin_expr = (
            ((pl.col(x_column) - x_min) / (x_max - x_min + 1e-10) * x_bins)
            .cast(pl.Int32)
            .clip(0, x_bins - 1)
            .alias("_x_bin")
        )
        y_bin_expr = (
            ((pl.col(y_column) - y_min) / (y_max - y_min + 1e-10) * y_bins)
            .cast(pl.Int32)
            .clip(0, y_bins - 1)
            .alias("_y_bin")
        )

        result = (
            data.with_columns([x_bin_expr, y_bin_expr])
            .sort(intensity_column, descending=descending)
            .group_by(["_x_bin", "_y_bin"])
            .head(points_per_bin)
            .drop(["_x_bin", "_y_bin"])
        )
    else:
        # Need to compute ranges - still lazy using over() window
        # First pass: add normalized bin columns using min/max over entire frame
        result = (
            data.with_columns(
                [
                    # Compute bin indices using window functions for min/max
                    (
                        (pl.col(x_column) - pl.col(x_column).min())
                        / (pl.col(x_column).max() - pl.col(x_column).min() + 1e-10)
                        * x_bins
                    )
                    .cast(pl.Int32)
                    .clip(0, x_bins - 1)
                    .alias("_x_bin"),
                    (
                        (pl.col(y_column) - pl.col(y_column).min())
                        / (pl.col(y_column).max() - pl.col(y_column).min() + 1e-10)
                        * y_bins
                    )
                    .cast(pl.Int32)
                    .clip(0, y_bins - 1)
                    .alias("_y_bin"),
                ]
            )
            .sort(intensity_column, descending=descending)
            .group_by(["_x_bin", "_y_bin"])
            .head(points_per_bin)
            .drop(["_x_bin", "_y_bin"])
        )

    return result


def get_data_range(
    data: pl.LazyFrame | pl.DataFrame,
    x_column: str,
    y_column: str,
) -> tuple:
    """
    Get the min/max ranges for x and y columns.

    This requires a collect() operation but only fetches 4 scalar values.

    Args:
        data: Input data
        x_column: X-axis column name
        y_column: Y-axis column name

    Returns:
        Tuple of ((x_min, x_max), (y_min, y_max))
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    stats = data.select(
        [
            pl.col(x_column).min().alias("x_min"),
            pl.col(x_column).max().alias("x_max"),
            pl.col(y_column).min().alias("y_min"),
            pl.col(y_column).max().alias("y_max"),
        ]
    ).collect()

    return (
        (stats["x_min"][0], stats["x_max"][0]),
        (stats["y_min"][0], stats["y_max"][0]),
    )
