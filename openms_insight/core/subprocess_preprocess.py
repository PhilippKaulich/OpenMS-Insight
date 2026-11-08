"""Subprocess-based preprocessing to ensure memory is released after cache creation.

When preprocessing large datasets (especially heatmaps with millions of points),
memory allocators like mimalloc retain freed memory. Running preprocessing in a
subprocess ensures all memory is returned to the OS when the subprocess exits.
"""

import multiprocessing
import os
import traceback
from typing import Any


def _preprocess_worker(
    component_class: type,
    data_path: str,
    kwargs: dict[str, Any],
    error_queue: multiprocessing.Queue,
) -> None:
    """Worker function that runs in subprocess to do preprocessing."""
    try:
        # Set mimalloc to release memory aggressively (in case not inherited)
        os.environ.setdefault("MIMALLOC_PURGE_DELAY", "0")

        # Create component with data - this triggers preprocessing and cache save
        from openms_insight.core.storage import scan_parquet

        data = scan_parquet(data_path)
        component_class(data=data, **kwargs)
        # Subprocess exits here, releasing all memory
        error_queue.put(None)
    except Exception as e:
        # Send exception info back to parent process
        error_queue.put((type(e).__name__, str(e), traceback.format_exc()))


def preprocess_component(
    component_class: type,
    data_path: str,
    cache_id: str,
    cache_path: str,
    **kwargs,
) -> None:
    """
    Run component preprocessing in a subprocess to guarantee memory release.

    This is an internal function called by BaseComponent when data_path is
    provided. Users should use the component constructor directly:

        heatmap = Heatmap(
            data_path="/path/to/data.parquet",
            cache_id="my_heatmap",
            cache_path="/path/to/cache",
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
        )

    Args:
        component_class: The component class (e.g., Heatmap, Table)
        data_path: Path to the parquet file containing the data
        cache_id: Unique identifier for the cache
        cache_path: Directory for cache storage
        **kwargs: Additional arguments passed to component constructor
    """
    # Prepare kwargs for subprocess
    worker_kwargs = {
        "cache_id": cache_id,
        "cache_path": cache_path,
        **kwargs,
    }

    # Use spawn to get a fresh process (fork might copy memory)
    ctx = multiprocessing.get_context("spawn")
    error_queue = ctx.Queue()
    process = ctx.Process(
        target=_preprocess_worker,
        args=(component_class, data_path, worker_kwargs, error_queue),
    )
    process.start()
    process.join()

    # Check for errors from subprocess
    if not error_queue.empty():
        error_info = error_queue.get_nowait()
        if error_info is not None:
            exc_type, exc_msg, exc_tb = error_info
            raise RuntimeError(
                f"Subprocess preprocessing failed with {exc_type}: {exc_msg}\n"
                f"Subprocess traceback:\n{exc_tb}"
            )

    if process.exitcode != 0:
        raise RuntimeError(f"Preprocessing failed with exit code {process.exitcode}")
