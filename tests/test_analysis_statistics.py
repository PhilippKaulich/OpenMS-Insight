"""Shape and contract tests for openms_insight.analysis.statistics.

These assert what the module documents about itself — output schema, laziness,
row preservation, the absence of temporary working columns, the argument
validation it promises, and the bounds any p-value must satisfy. They
deliberately assert no statistical *values*: matching an external reference
would require the implementation to share that reference's variance and
degrees-of-freedom conventions, and a mismatch there says nothing useful.
"""

import polars as pl
import pytest

from openms_insight.analysis.statistics import (
    adjust_fdr_lazy,
    calculate_statistical_tests,
)

TWO_GROUP_METHODS = ["limma_like", "welch", "paired"]
THREE_GROUP_METHODS = ["limma_like", "anova"]
DOCUMENTED_COLUMNS = ("log2FC", "stat", "p-value")


def _within_unit_interval(series: pl.Series) -> bool:
    """True when every non-missing value lies in [0, 1].

    Missing and NaN entries are excluded rather than asserted against: a
    feature with no variance across its replicates legitimately yields NaN.
    """
    finite = series.drop_nulls().drop_nans()
    return bool(((finite >= 0.0) & (finite <= 1.0)).all())


@pytest.mark.parametrize("method", TWO_GROUP_METHODS)
def test_two_group_methods_satisfy_output_contract(
    sample_quantification_data,
    sample_quantification_metadata,
    assert_analysis_contract,
    method,
):
    result = calculate_statistical_tests(
        sample_quantification_data, sample_quantification_metadata, method=method
    )
    out = assert_analysis_contract(
        result, sample_quantification_data, required=DOCUMENTED_COLUMNS, rows=5
    )
    assert _within_unit_interval(out["p-value"]), (
        f"{method} produced p-values outside [0, 1]"
    )


@pytest.mark.parametrize("method", THREE_GROUP_METHODS)
def test_three_group_methods_satisfy_output_contract(
    sample_quantification_data,
    sample_quantification_metadata_3group,
    assert_analysis_contract,
    method,
):
    result = calculate_statistical_tests(
        sample_quantification_data, sample_quantification_metadata_3group, method=method
    )
    out = assert_analysis_contract(
        result, sample_quantification_data, required=DOCUMENTED_COLUMNS, rows=5
    )
    assert _within_unit_interval(out["p-value"]), (
        f"{method} produced p-values outside [0, 1]"
    )


@pytest.mark.parametrize("method", ["welch", "paired"])
def test_two_group_methods_reject_three_groups(
    sample_quantification_data, sample_quantification_metadata_3group, method
):
    with pytest.raises(ValueError, match="exactly 2 groups"):
        calculate_statistical_tests(
            sample_quantification_data,
            sample_quantification_metadata_3group,
            method=method,
        )


def test_anova_rejects_two_groups(
    sample_quantification_data, sample_quantification_metadata
):
    with pytest.raises(ValueError, match="3\\+ groups"):
        calculate_statistical_tests(
            sample_quantification_data, sample_quantification_metadata, method="anova"
        )


def test_paired_rejects_unequal_group_sizes(sample_quantification_data):
    lopsided = pl.DataFrame(
        {
            "sample_id": ["s1", "s2", "s3", "s4", "s5"],
            "group": ["A", "A", "A", "B", "B"],
        }
    )
    with pytest.raises(ValueError, match="equal sample sizes"):
        calculate_statistical_tests(
            sample_quantification_data, lopsided, method="paired"
        )


def test_unknown_method_is_rejected(
    sample_quantification_data, sample_quantification_metadata
):
    with pytest.raises(ValueError, match="Unknown method strategy"):
        calculate_statistical_tests(
            sample_quantification_data,
            sample_quantification_metadata,
            method="not_a_method",
        )


@pytest.mark.parametrize("strategy", ["None", "Bonferroni", "BH"])
def test_fdr_adjustment_satisfies_output_contract(
    sample_quantification_data,
    sample_quantification_metadata,
    assert_analysis_contract,
    strategy,
):
    tested = calculate_statistical_tests(
        sample_quantification_data, sample_quantification_metadata, method="welch"
    )
    result = adjust_fdr_lazy(tested, strategy=strategy)
    out = assert_analysis_contract(
        result, sample_quantification_data, required=("p-adj",), rows=5
    )

    assert _within_unit_interval(out["p-adj"]), (
        f"{strategy} produced adjusted p-values outside [0, 1]"
    )
    comparable = out.drop_nulls(["p-value", "p-adj"])
    assert (comparable["p-adj"] >= comparable["p-value"]).all(), (
        f"{strategy} produced an adjusted p-value below the raw p-value"
    )


def test_unknown_fdr_strategy_is_rejected(
    sample_quantification_data, sample_quantification_metadata
):
    tested = calculate_statistical_tests(
        sample_quantification_data, sample_quantification_metadata, method="welch"
    )
    with pytest.raises(ValueError, match="Unknown FDR strategy"):
        adjust_fdr_lazy(tested, strategy="not_a_strategy")


def test_import_leaves_scipy_stats_unloaded():
    """Importing the analysis modules must not load scipy.stats (about 0.6 s):
    an app imports them with its pages, before any test is computed."""
    import subprocess
    import sys

    code = (
        "import sys, openms_insight.analysis.statistics\n"
        "try:\n"
        "    import openms_insight.analysis.enrichment\n"
        "except ImportError:\n"  # without the optional 'analysis' extra
        "    pass\n"
        "print('scipy.stats' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"
