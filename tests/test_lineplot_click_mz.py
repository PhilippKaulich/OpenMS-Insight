"""A LinePlot click can hand the m/z to the page through `interactivity`."""

import polars as pl

from openms_insight import LinePlot


def test_x_column_and_an_id_reach_the_browser(mock_streamlit, temp_cache_dir):
    data = pl.LazyFrame(
        {
            "peak_id": [1, 2, 3],
            "mz": [341.3387, 501.0625, 913.7987],
            "intensity": [10.0, 20.0, 30.0],
        }
    )
    plot = LinePlot(
        cache_id="click_mz",
        data=data,
        x_column="mz",
        y_column="intensity",
        interactivity={"peak": "peak_id", "xic_mz": "mz"},
        cache_path=str(temp_cache_dir),
    )
    assert plot.get_interactivity_mapping() == {"peak": "peak_id", "xic_mz": "mz"}
    frame = plot._prepare_vue_data({})["plotData"]
    if isinstance(frame, pl.LazyFrame):
        frame = frame.collect()
    assert {"peak_id", "mz"} <= set(frame.columns)
