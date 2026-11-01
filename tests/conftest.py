"""Pytest configuration and shared fixtures for openms-insight tests."""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest


class MockSessionState(dict):
    """Mock Streamlit session_state that behaves like a dict."""

    pass


@pytest.fixture
def mock_streamlit():
    """
    Mock Streamlit's session_state for testing components.

    This fixture patches st.session_state to allow testing components
    without running a full Streamlit server.
    """
    mock_session_state = MockSessionState()

    with patch("streamlit.session_state", mock_session_state):
        yield mock_session_state


@pytest.fixture
def temp_cache_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for cache storage."""
    tmpdir = tempfile.mkdtemp(prefix="openms_insight_test_")
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_table_data() -> pl.LazyFrame:
    """Create sample data for Table component."""
    return pl.LazyFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "scan_id": [100, 100, 200, 200, 300],
            "mass": [500.5, 600.6, 700.7, 800.8, 900.9],
            "name": ["peak_a", "peak_b", "peak_c", "peak_d", "peak_e"],
        }
    )


@pytest.fixture
def sample_lineplot_data() -> pl.LazyFrame:
    """Create sample data for LinePlot component."""
    return pl.LazyFrame(
        {
            "mass": [100.0, 200.0, 300.0, 400.0, 500.0],
            "intensity": [1000.0, 2000.0, 1500.0, 3000.0, 500.0],
            "scan_id": [1, 1, 1, 2, 2],
            "peak_id": [10, 20, 30, 40, 50],
            "annotation": ["b2", "", "y3", "", "b4"],
        }
    )


@pytest.fixture
def sample_heatmap_data() -> pl.LazyFrame:
    """Create sample data for Heatmap component."""
    import random

    random.seed(42)

    n_points = 1000
    return pl.LazyFrame(
        {
            "retention_time": [random.uniform(0, 100) for _ in range(n_points)],
            "mz": [random.uniform(100, 2000) for _ in range(n_points)],
            "intensity": [random.uniform(100, 10000) for _ in range(n_points)],
            "scan_id": [random.randint(1, 10) for _ in range(n_points)],
        }
    )


@pytest.fixture
def sample_sequence_data() -> pl.LazyFrame:
    """Create sample data for SequenceView component."""
    return pl.LazyFrame(
        {
            "scan_id": [1, 2, 3],
            "sequence": ["PEPTIDER", "ACDEFGHK", "MNPQRST"],
            "precursor_charge": [2, 3, 1],
        }
    )


@pytest.fixture
def sample_peaks_data() -> pl.LazyFrame:
    """Create sample peaks data for SequenceView component."""
    return pl.LazyFrame(
        {
            "scan_id": [1, 1, 1, 2, 2, 3],
            "peak_id": [101, 102, 103, 201, 202, 301],
            "mass": [200.5, 300.6, 400.7, 250.3, 350.4, 150.2],
            "intensity": [1000.0, 2000.0, 1500.0, 3000.0, 2500.0, 500.0],
        }
    )


@pytest.fixture
def sample_volcanoplot_data() -> pl.LazyFrame:
    """Create sample data for VolcanoPlot component."""
    import random

    random.seed(42)

    n_proteins = 100
    return pl.LazyFrame(
        {
            "protein_id": [f"PROT{i:04d}" for i in range(n_proteins)],
            "protein_name": [f"Protein_{i}" for i in range(n_proteins)],
            "log2FC": [random.uniform(-4, 4) for _ in range(n_proteins)],
            "pvalue": [random.uniform(0.0001, 1) for _ in range(n_proteins)],
            "comparison_id": [
                random.choice(["A_vs_B", "C_vs_D"]) for _ in range(n_proteins)
            ],
        }
    )


@pytest.fixture
def sample_categorical_heatmap_data() -> pl.LazyFrame:
    """Create sample data for categorical Heatmap component."""
    import random

    random.seed(42)

    n_points = 500
    categories = ["Control", "Treatment_A", "Treatment_B"]
    return pl.LazyFrame(
        {
            "retention_time": [random.uniform(0, 100) for _ in range(n_points)],
            "mz": [random.uniform(100, 2000) for _ in range(n_points)],
            "intensity": [random.uniform(100, 10000) for _ in range(n_points)],
            "sample_group": [random.choice(categories) for _ in range(n_points)],
            "scan_id": [random.randint(1, 10) for _ in range(n_points)],
        }
    )


@pytest.fixture
def pagination_test_data() -> pl.LazyFrame:
    """
    Create 500-row synthetic dataset for pagination and filtering tests.

    Schema:
        - id: Row identifier (0-499)
        - value: String values (item_0, item_1, ...)
        - score: Float values (0.0, 1.5, 3.0, ...)
        - category: Categorical column (A/B/C/D/E cycling)
        - description: Text column for regex testing
        - priority: Numeric column with few unique values (1-5, becomes categorical)
    """
    return pl.LazyFrame(
        {
            "id": list(range(500)),
            "value": [f"item_{i}" for i in range(500)],
            "score": [i * 1.5 for i in range(500)],
            "category": ["A", "B", "C", "D", "E"] * 100,
            "description": [
                f"Description for row {i} with {'even' if i % 2 == 0 else 'odd'} index"
                for i in range(500)
            ],
            "priority": [i % 5 + 1 for i in range(500)],
        }
    )


@pytest.fixture
def sample_quantification_data() -> pl.LazyFrame:
    """Wide-format quantification matrix for the analysis pipeline tests.

    Deliberately imperfect: ``f4`` carries missing values, so imputation and
    the missing-ratio filters have something to act on, and ``f3`` is constant
    in every group, which exercises the degenerate-variance paths. The other
    four features are complete, which leaves PCAPlot enough rows after its
    ``drop_nulls()``.
    """
    return pl.LazyFrame(
        {
            "feature": ["f1", "f2", "f3", "f4", "f5"],
            "s1": [1.0, 5.0, 2.0, None, 8.0],
            "s2": [1.2, 5.1, 2.0, 3.0, 8.2],
            "s3": [1.1, 5.3, 2.0, 3.2, 7.9],
            "s4": [3.0, 5.2, 2.0, None, 1.0],
            "s5": [3.1, 4.9, 2.0, 3.1, 1.1],
            "s6": [2.9, 5.0, 2.0, 3.3, 1.2],
        }
    )


@pytest.fixture
def sample_quantification_metadata() -> pl.DataFrame:
    """Two balanced groups, for the welch / paired / limma_like paths."""
    return pl.DataFrame(
        {
            "sample_id": ["s1", "s2", "s3", "s4", "s5", "s6"],
            "group": ["A", "A", "A", "B", "B", "B"],
        }
    )


@pytest.fixture
def sample_quantification_metadata_3group() -> pl.DataFrame:
    """Three balanced groups, for the ANOVA and limma_like F-test paths."""
    return pl.DataFrame(
        {
            "sample_id": ["s1", "s2", "s3", "s4", "s5", "s6"],
            "group": ["A", "A", "B", "B", "C", "C"],
        }
    )


@pytest.fixture
def assert_analysis_contract():
    """Shape assertions shared by the analysis pipeline tests.

    Checks only what the modules document about themselves: the result stays
    lazy, no ``_``-prefixed working column leaks into it, and the caller's own
    columns survive. Nothing here asserts a statistical value.
    """

    def _assert(result, source, *, required=(), rows=None, max_rows=None):
        assert isinstance(result, pl.LazyFrame), (
            f"expected a LazyFrame, got {type(result).__name__}"
        )
        out = result.collect()
        src = source.collect() if isinstance(source, pl.LazyFrame) else source

        leaked = [c for c in out.columns if c.startswith("_")]
        assert not leaked, f"temporary working columns leaked into output: {leaked}"

        dropped = [c for c in src.columns if c not in out.columns]
        assert not dropped, f"caller columns missing from output: {dropped}"

        for column in required:
            assert column in out.columns, f"documented output column {column!r} missing"

        if rows is not None:
            assert out.height == rows, f"expected {rows} rows, got {out.height}"
        if max_rows is not None:
            assert out.height <= max_rows, f"row count grew to {out.height}"
        return out

    return _assert


@pytest.fixture
def unusable_metadata() -> pl.DataFrame:
    """Metadata carrying no usable group labels.

    ``analysis.filter`` treats null, ``""`` and ``"NA"`` as unusable and
    documents that such metadata turns every filter into a pass-through.
    """
    return pl.DataFrame(
        {
            "sample_id": ["s1", "s2", "s3", "s4", "s5", "s6"],
            "group": ["NA", "NA", "NA", "NA", "NA", "NA"],
        }
    )


@pytest.fixture
def sample_quantification_data_complete() -> pl.LazyFrame:
    """The expression matrix with no missing values.

    ClusteredHeatmap clusters via scipy's linkage, which requires a complete
    matrix; components under test here should not be exercising the missing
    value path.
    """
    return pl.LazyFrame(
        {
            "feature": ["f1", "f2", "f3", "f4", "f5"],
            "s1": [1.0, 5.0, 2.0, 3.4, 8.0],
            "s2": [1.2, 5.1, 2.0, 3.0, 8.2],
            "s3": [1.1, 5.3, 2.0, 3.2, 7.9],
            "s4": [3.0, 5.2, 2.0, 3.5, 1.0],
            "s5": [3.1, 4.9, 2.0, 3.1, 1.1],
            "s6": [2.9, 5.0, 2.0, 3.3, 1.2],
        }
    )


@pytest.fixture
def sample_series_data() -> pl.LazyFrame:
    """Create sample data for SeriesPlot (two density curves)."""
    return pl.LazyFrame(
        {
            "Score": [0.1, 0.5, 0.9, 0.1, 0.5, 0.9],
            "Density": [0.2, 1.0, 0.4, 0.8, 0.3, 0.05],
            "kind": ["target"] * 3 + ["decoy"] * 3,
        }
    )


@pytest.fixture
def sample_plot3d_data() -> pl.LazyFrame:
    """Create sample data for Plot3D: one row per mass, peaks as list columns."""
    return pl.LazyFrame(
        {
            "scan_idx": [0, 0, 0, 1],
            "mass_idx": [-1, 0, 0, 0],
            "kind": ["Signal", "Signal", "Noise", "Signal"],
            "mass": [[1000.0, 1001.0], [1000.0], [1000.5, 1002.0], [2000.0]],
            "charge": [[5.0, 6.0], [5.0], [5.0, 7.0], [10.0]],
            "intensity": [[10.0, 20.0], [10.0], [1.0, 2.0], [100.0]],
        }
    )


@pytest.fixture
def sample_deconvolved_spectra() -> pl.LazyFrame:
    """Create sample data for DeconvolvedSpectrum: one row per scan."""
    return pl.LazyFrame(
        {
            "scan_idx": [0, 1],
            "masses": [[1000.0, 2000.123456], [1500.0]],
            "intensities": [[10.0, 20.0], [5.0]],
            "peak_mz": [[201.0, 251.0, 401.0], [301.0]],
            "peak_intensity": [[1.0, 2.0, 3.0], [4.0]],
            "signal_peaks": [
                [[[0.0, 201.0, 1.0, 5.0]], [[2.0, 401.0, 3.0, 5.0]]],
                [[[0.0, 301.0, 4.0, 5.0]]],
            ],
        }
    )


@pytest.fixture
def sample_protein_sequence_data() -> pl.LazyFrame:
    """Create sample data for ProteinSequenceView: one row per identification."""
    return pl.LazyFrame(
        {
            "hit_index": [0, 1],
            "sequence": [list("PEPTIDE"), list("ACDK")],
            "theoretical_mass": [799.36, 435.2],
            "coverage": [[0.0] * 7, [1.0, 1.0, 0.5, 0.0]],
            "maxCoverage": [0.0, 2.0],
            "fragment_masses_b": [[[98.06]] * 7, [[72.04]] * 4],
            "fragment_masses_y": [[[148.06]] * 7, [[147.11]] * 4],
            "start_position": [0, 1],
            "end_position": [6, -1],
            "observed_mass": [float("nan"), 435.21],
            "masses": [[98.06, 148.06], [72.04]],
            "precursor_mass": [799.4, 435.2],
        }
    )
