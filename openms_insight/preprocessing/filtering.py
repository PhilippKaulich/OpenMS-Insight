"""Data filtering utilities for selection-based filtering."""

import hashlib
import threading
from typing import Any

import numpy as np
import pandas as pd
import polars as pl


def optimize_for_transfer(
    df: pl.DataFrame, downcast_floats: bool = True
) -> pl.DataFrame:
    """
    Optimize DataFrame types for efficient Arrow transfer to frontend.

    This function downcasts numeric types to reduce Arrow payload size and
    avoid BigInt overhead in JavaScript:
    - Int64 → Int32 (if values fit): Avoids BigInt conversion in JS
    - Float64 → Float32: Sufficient precision for visualization

    Args:
        df: Polars DataFrame to optimize
        downcast_floats: Cast Float64 to Float32 (default True). False keeps
            full precision and only narrows integers.

    Returns:
        DataFrame with optimized types
    """
    if len(df) == 0:
        return df

    casts = []

    for col in df.columns:
        dtype = df[col].dtype

        # Downcast Int64 to Int32 to avoid BigInt in JavaScript
        # JS safe integer is 2^53, but Int32 range is simpler and sufficient for most data
        if dtype == pl.Int64:
            # Get min/max in a single pass
            stats = df.select(
                [
                    pl.col(col).min().alias("min"),
                    pl.col(col).max().alias("max"),
                ]
            ).row(0)
            col_min, col_max = stats

            if col_min is not None and col_max is not None:
                # Int32 range: -2,147,483,648 to 2,147,483,647
                if col_min >= -2147483648 and col_max <= 2147483647:
                    casts.append(pl.col(col).cast(pl.Int32))

        # Downcast Float64 to Float32 (sufficient for display)
        # Float32 has ~7 significant digits - enough for visualization
        elif dtype == pl.Float64 and downcast_floats:
            casts.append(pl.col(col).cast(pl.Float32))

    if casts:
        df = df.with_columns(casts)

    return df


def optimize_for_transfer_lazy(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Optimize LazyFrame types for efficient Arrow transfer (streaming-safe).

    Unlike optimize_for_transfer(), this only applies optimizations that don't
    require knowing the data values, preserving the ability to stream via sink_parquet().

    Currently applies:
    - Float64 → Float32: Always safe, no bounds check needed

    Int64 → Int32 is NOT applied here because it requires bounds checking.
    Use optimize_for_transfer() on collected DataFrames for full optimization.

    Args:
        lf: Polars LazyFrame to optimize

    Returns:
        LazyFrame with Float64 columns cast to Float32
    """
    schema = lf.collect_schema()
    casts = []

    for col, dtype in zip(schema.names(), schema.dtypes(), strict=True):
        # Only Float64 → Float32 is safe without bounds checking
        if dtype == pl.Float64:
            casts.append(pl.col(col).cast(pl.Float32))

    if casts:
        lf = lf.with_columns(casts)

    return lf


def _make_cache_key(
    filters: dict[str, str],
    state: dict[str, Any],
    filter_defaults: dict[str, Any] | None = None,
) -> tuple[tuple[str, Any], ...]:
    """
    Create a hashable cache key from filters and state.

    Only includes state values for identifiers that are in filters,
    so cache is invalidated only when relevant selections change.

    Args:
        filters: Mapping of identifier names to column names
        state: Current selection state
        filter_defaults: Optional default values for filters when state is None

    Returns:
        Tuple of (identifier, value) pairs for use as cache key
    """
    relevant_state = []
    for identifier in sorted(filters.keys()):
        value = state.get(identifier)
        # Apply default if value is None and default exists
        if value is None and filter_defaults and identifier in filter_defaults:
            value = filter_defaults[identifier]
        relevant_state.append((identifier, value))
    return tuple(relevant_state)


def compute_dataframe_hash(df: pl.DataFrame) -> str:
    """
    Compute an efficient hash for a DataFrame without pickling.

    Uses shape, column names, and sampled values to create a fast hash
    that detects data changes without materializing extra copies.

    Args:
        df: Polars DataFrame to hash

    Returns:
        SHA256 hash string
    """
    # Build hash from metadata and sampled content
    hash_parts = [
        str(df.shape),  # (rows, cols)
        str(df.columns),  # Column names
    ]

    # For small DataFrames, hash first/last values of each column
    # For large DataFrames, this is still O(1) memory
    if len(df) > 0:
        # Sample first and last row for change detection
        first_row = df.head(1).to_dicts()[0] if len(df) > 0 else {}
        last_row = df.tail(1).to_dicts()[0] if len(df) > 0 else {}
        hash_parts.append(str(first_row))
        hash_parts.append(str(last_row))

        # Add sum of numeric columns for content verification
        for col in df.columns:
            dtype = df[col].dtype
            if dtype in (
                pl.Int8,
                pl.Int16,
                pl.Int32,
                pl.Int64,
                pl.UInt8,
                pl.UInt16,
                pl.UInt32,
                pl.UInt64,
                pl.Float32,
                pl.Float64,
            ):
                try:
                    col_sum = df[col].sum()
                    hash_parts.append(f"{col}:{col_sum}")
                except Exception:
                    pass
            elif dtype == pl.Boolean:
                # Count True values for boolean columns (important for annotations)
                try:
                    true_count = df[col].sum()  # True=1, False=0
                    hash_parts.append(f"{col}_bool:{true_count}")
                except Exception:
                    pass
            elif dtype == pl.Utf8 and col.startswith("_dynamic"):
                # Hash content of dynamic string columns (annotations)
                try:
                    # Use hash of all non-empty values for annotation text
                    non_empty = df[col].filter(pl.col(col) != "").to_list()
                    if non_empty:
                        hash_parts.append(f"{col}_str:{hash(tuple(non_empty))}")
                except Exception:
                    pass

    hash_input = "|".join(hash_parts).encode()
    return hashlib.sha256(hash_input).hexdigest()


def _row_digest(row: dict) -> str:
    """Digest of one row whose cells may hold (nested) arrays.

    ``str()`` of an object array of arrays formats every element and took
    seconds for a row holding the peaks of a spectrum; the bytes are hashed
    instead.
    """
    digest = hashlib.sha256()

    def add(value: Any) -> None:
        if isinstance(value, np.ndarray) and value.dtype != object:
            digest.update(f"{value.dtype}{value.shape}".encode())
            digest.update(np.ascontiguousarray(value).tobytes())
        elif isinstance(value, (np.ndarray, list, tuple)):
            digest.update(f"[{len(value)}".encode())
            for item in value:
                add(item)
            digest.update(b"]")
        else:
            digest.update(repr(value).encode())
            digest.update(b",")

    for key, value in row.items():
        digest.update(f"{key}=".encode())
        add(value)
    return digest.hexdigest()


def compute_pandas_dataframe_hash(df: pd.DataFrame) -> str:
    """
    Compute an efficient hash for a pandas DataFrame, without converting it.

    Mirrors :func:`compute_dataframe_hash` -- shape, column names, first and last row,
    per-column sums -- but reads them straight off pandas.

    Converting to polars first is what this exists to avoid: ``pl.from_pandas()``
    parallelises Series construction across polars' own thread pool, and two Streamlit
    script threads hashing at the same moment crash the interpreter with an access
    violation inside ``numpy_to_pyseries``. Nothing about hashing needs the conversion.

    The two functions need not agree on the hash of equivalent data, and do not: a
    payload key keeps its type across renders, so hashes are only ever compared
    like-for-like.

    Args:
        df: pandas DataFrame to hash

    Returns:
        SHA256 hash string
    """
    hash_parts = [
        str(df.shape),
        str(list(df.columns)),
    ]

    if len(df) > 0:
        hash_parts.append(_row_digest(df.head(1).to_dict("records")[0]))
        hash_parts.append(_row_digest(df.tail(1).to_dict("records")[0]))

        for col in df.columns:
            series = df[col]
            if pd.api.types.is_bool_dtype(series):
                # Count True values for boolean columns (important for annotations)
                try:
                    hash_parts.append(f"{col}_bool:{int(series.sum())}")
                except Exception:
                    pass
            elif pd.api.types.is_numeric_dtype(series):
                try:
                    hash_parts.append(f"{col}:{series.sum()}")
                except Exception:
                    pass
            elif str(col).startswith("_dynamic"):
                # Hash content of dynamic string columns (annotations)
                try:
                    non_empty = [v for v in series.tolist() if v != ""]
                    if non_empty:
                        hash_parts.append(f"{col}_str:{hash(tuple(non_empty))}")
                except Exception:
                    pass

    hash_input = "|".join(hash_parts).encode()
    return hashlib.sha256(hash_input).hexdigest()


# Serializes pl.from_pandas across threads. See compute_pandas_dataframe_hash for why:
# concurrent conversions corrupt memory. Where a polars frame is genuinely needed the
# conversion cannot be dropped, so it is made non-concurrent instead. The critical
# section is short next to the render it belongs to.
_from_pandas_lock = threading.Lock()


def from_pandas_safe(df: pd.DataFrame) -> pl.DataFrame:
    """Convert pandas to polars without racing another thread doing the same.

    Args:
        df: pandas DataFrame to convert

    Returns:
        The equivalent polars DataFrame.
    """
    with _from_pandas_lock:
        return pl.from_pandas(df)


def _filter_and_collect(
    data: pl.LazyFrame,
    filters_tuple: tuple[tuple[str, str], ...],
    state_tuple: tuple[tuple[str, Any], ...],
    columns_tuple: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    Filter data and collect.

    This function executes the filter query. Caching is handled at a higher
    level (per-component in bridge.py) to ensure memory = O(num_components).

    Returns pandas DataFrame for efficient Arrow serialization to frontend.

    Args:
        data: LazyFrame to filter
        filters_tuple: Tuple of (identifier, column) pairs from filters dict
        state_tuple: Tuple of (identifier, value) pairs for current selection state
            (already has defaults applied from _make_cache_key)
        columns_tuple: Optional tuple of column names to select (projection)

    Returns:
        Tuple of (pandas DataFrame, hash string)
    """
    filters = dict(filters_tuple)
    state = dict(state_tuple)  # Already has defaults applied

    # Apply column projection FIRST (before filters) for efficiency
    # This ensures we only read needed columns from disk
    if columns_tuple:
        data = data.select(list(columns_tuple))

    # Apply filters
    # If ANY filter has no selection (and no default), return empty DataFrame
    # This prevents loading millions of rows when no spectrum is selected
    for identifier, column in filters.items():
        selected_value = state.get(identifier)
        if selected_value is None:
            # No selection for this filter - return empty DataFrame
            # Collect with limit 0 to get schema without data
            df_polars = data.head(0).collect()
            data_hash = compute_dataframe_hash(df_polars)
            df_pandas = df_polars.to_pandas()
            return (df_pandas, data_hash)

        # Convert float to int for integer columns to handle JSON number parsing
        # (JavaScript numbers come back as floats, but Polars Int64 needs int comparison)
        if isinstance(selected_value, float) and selected_value.is_integer():
            selected_value = int(selected_value)
        data = data.filter(pl.col(column) == selected_value)

    # Collect to Polars DataFrame
    # Note: Type optimization (Int64→Int32, Float64→Float32) is applied at cache
    # creation time in base.py._save_to_cache(), so data is already optimized
    df_polars = data.collect()

    # Compute hash efficiently (no pickle)
    data_hash = compute_dataframe_hash(df_polars)

    # Convert to pandas for Arrow serialization (zero-copy when possible)
    df_pandas = df_polars.to_pandas()

    return (df_pandas, data_hash)


def filter_and_collect_cached(
    data: pl.LazyFrame | pl.DataFrame,
    filters: dict[str, str],
    state: dict[str, Any],
    columns: list[str] | None = None,
    filter_defaults: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    Filter data based on selection state and collect, with caching.

    This is the recommended function for components that need filtered data.
    Results are cached based on filter state, so interactions that don't
    change the filter values (e.g., clicking within already-filtered data)
    will return cached results instantly.

    Returns pandas DataFrame for efficient Arrow serialization to the frontend.
    The hash is computed efficiently without pickling the data.

    Args:
        data: The data to filter (LazyFrame or DataFrame)
        filters: Mapping of identifier names to column names for filtering
        state: Current selection state with identifier values
        columns: Optional list of column names to select (projection pushdown)
        filter_defaults: Optional default values for filters when state is None.
            When a filter's state value is None, the default is used instead.
            Example: {"identification": -1} means None → -1 for identification filter.

    Returns:
        Tuple of (pandas DataFrame, hash string) with filters and projection applied
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    # Convert to tuples for consistent processing
    filters_tuple = tuple(sorted(filters.items()))
    # Pass filter_defaults to _make_cache_key so defaults are applied to state
    state_tuple = _make_cache_key(filters, state, filter_defaults)
    columns_tuple = tuple(columns) if columns else None

    return _filter_and_collect(
        data,
        filters_tuple,
        state_tuple,
        columns_tuple,
    )


def filter_by_selection(
    data: pl.LazyFrame | pl.DataFrame,
    interactivity: dict[str, str],
    state: dict[str, Any],
) -> pl.LazyFrame:
    """
    Filter data based on selection state and interactivity mapping.

    For each identifier in the interactivity mapping, if there's a
    corresponding selection in state, filter the data to rows where
    the mapped column equals the selected value.

    Args:
        data: The data to filter (LazyFrame or DataFrame)
        interactivity: Mapping of identifier names to column names
        state: Current selection state with identifier values

    Returns:
        Filtered LazyFrame
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    for identifier, column in interactivity.items():
        selected_value = state.get(identifier)
        if selected_value is not None:
            data = data.filter(pl.col(column) == selected_value)

    return data


def filter_by_index(
    data: pl.LazyFrame | pl.DataFrame,
    index_column: str,
    index_value: Any,
) -> pl.LazyFrame:
    """
    Filter data to a single row by index value.

    Args:
        data: The data to filter
        index_column: Name of the index column
        index_value: The index value to filter to

    Returns:
        Filtered LazyFrame (typically 1 row)
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    return data.filter(pl.col(index_column) == index_value)


def filter_by_range(
    data: pl.LazyFrame | pl.DataFrame,
    x_column: str,
    y_column: str,
    x_range: tuple,
    y_range: tuple,
) -> pl.LazyFrame:
    """
    Filter data within x/y range bounds.

    Args:
        data: The data to filter
        x_column: Name of the x-axis column
        y_column: Name of the y-axis column
        x_range: Tuple of (min, max) for x-axis
        y_range: Tuple of (min, max) for y-axis

    Returns:
        Filtered LazyFrame
    """
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    return data.filter(
        (pl.col(x_column) >= x_range[0])
        & (pl.col(x_column) <= x_range[1])
        & (pl.col(y_column) >= y_range[0])
        & (pl.col(y_column) <= y_range[1])
    )


def slice_by_row_index(
    data: pl.LazyFrame | pl.DataFrame,
    row_index: int | None,
) -> pl.DataFrame:
    """
    Slice data to a single row by row position.

    Args:
        data: The data to slice
        row_index: The row index (position) to extract

    Returns:
        DataFrame with single row, or empty DataFrame if index is None
    """
    if row_index is None:
        # Return empty DataFrame with same schema
        if isinstance(data, pl.LazyFrame):
            return data.head(0).collect()
        return data.head(0)

    # For LazyFrames, add slice to query plan before collecting
    # This allows Polars to optimize and avoid materializing all rows
    if isinstance(data, pl.LazyFrame):
        # Note: We can't check bounds without collecting, so we slice optimistically
        # and return empty if result is empty
        return data.slice(row_index, 1).collect()

    # For DataFrames, check bounds first
    if row_index < 0 or row_index >= len(data):
        return data.head(0)

    return data.slice(row_index, 1)
