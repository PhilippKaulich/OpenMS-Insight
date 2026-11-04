from collections import defaultdict

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import fisher_exact

try:
    import mygene
    import plotly.express as px
except ImportError as exc:
    raise ImportError(
        "GO enrichment requires the optional 'analysis' extra:\n"
        "    pip install openms-insight[analysis]"
    ) from exc

GO_CATEGORIES = ("BP", "CC", "MF")
GO_CATEGORY_NAMES = {
    "BP": "Biological process",
    "CC": "Cellular component",
    "MF": "Molecular function",
}


def get_clean_uniprot(name):
    """Cleans FASTA-style UniProt headers to extract the core accession ID.

    Args:
        name: Raw identifier, e.g. "sp|Q99287|SEY1_YEAST" or a bare
            accession with no "|" separators.

    Returns:
        The accession segment (e.g. "Q99287") if the FASTA-style "|"
        format is present, otherwise `name` unchanged (stringified).
    """
    parts = str(name).split("|")
    return parts[1] if len(parts) >= 2 else parts[0]


def extract_go_terms(go_data, go_type):
    """Parses nested dictionary schema from MyGene.info API response.

    Args:
        go_data: The "go" field of a single MyGene.info query result, as
            returned by `mygene.MyGeneInfo().querymany(..., fields="go")`.
            Expected to be a dict keyed by GO category, or falsy/malformed
            if the gene has no GO annotations.
        go_type: Which GO category to extract - "BP" (Biological Process),
            "CC" (Cellular Component), or "MF" (Molecular Function).

    Returns:
        List of unique GO term names for `go_type`, or an empty list if
        `go_data` isn't a dict or has no entry for `go_type`.
    """
    if not isinstance(go_data, dict) or go_type not in go_data:
        return []
    terms = go_data[go_type]
    if isinstance(terms, dict):
        terms = [terms]
    return list({t.get("term") for t in terms if "term" in t})


def go_term_table(res_go, fg_set, bg_set, go_type, adjust=True):
    """Fisher's exact test of every GO term of one category, without a plot.

    Args:
        res_go: DataFrame with a "query" column (protein ID) and a
            "{go_type}_terms" column (list of GO term names per protein), as
            returned by `fetch_go_annotations`.
        fg_set: Protein IDs of the foreground (the selected proteins).
        bg_set: Protein IDs of the background (all proteins the foreground
            was chosen from, the foreground included).
        go_type: "BP", "CC" or "MF".
        adjust: Add a Benjamini-Hochberg adjusted p-value ("p_adj").

    Returns:
        DataFrame with "GO_Term", "Count" (foreground proteins with the term),
        "Background" (background proteins with it), "GeneRatio", "BgRatio",
        "FoldEnrichment", "p_value", "-log10(p)", ("p_adj"), "Proteins" (the
        foreground proteins with the term, ";"-separated), sorted by p-value.
        Empty when no foreground protein has a term of the category.
    """
    columns = [
        "GO_Term",
        "Count",
        "Background",
        "GeneRatio",
        "BgRatio",
        "FoldEnrichment",
        "p_value",
        "-log10(p)",
        "Proteins",
    ]
    if adjust:
        columns.insert(columns.index("Proteins"), "p_adj")
    go2fg = defaultdict(set)
    go2bg = defaultdict(set)
    fg_set = set(map(str, fg_set))
    bg_set = set(map(str, bg_set)) | fg_set

    for _, row in res_go.iterrows():
        uid = str(row["query"])
        if uid not in bg_set:
            continue
        for term in row[f"{go_type}_terms"]:
            go2bg[term].add(uid)
            if uid in fg_set:
                go2fg[term].add(uid)

    records = []
    n_fg = len(fg_set)
    n_bg = len(bg_set)
    for term, fg_genes in go2fg.items():
        a = len(fg_genes)
        if a == 0:
            continue
        b = n_fg - a
        c = len(go2bg[term]) - a
        d = n_bg - (a + b + c)
        _, p = fisher_exact([[a, b], [c, d]], alternative="greater")
        records.append(
            {
                "GO_Term": term,
                "Count": a,
                "Background": len(go2bg[term]),
                "GeneRatio": f"{a}/{n_fg}",
                "BgRatio": f"{len(go2bg[term])}/{n_bg}",
                "FoldEnrichment": (a / n_fg) / (len(go2bg[term]) / n_bg),
                "p_value": p,
                "Proteins": ";".join(sorted(fg_genes)),
            }
        )
    if not records:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(records)
    df["-log10(p)"] = -np.log10(df["p_value"].clip(lower=1e-300))
    if adjust:
        df["p_adj"] = benjamini_hochberg(df["p_value"].to_numpy())
    return df.sort_values(["p_value", "GO_Term"]).reset_index(drop=True)[columns]


def benjamini_hochberg(pvalues):
    """Benjamini-Hochberg adjusted p-values, in the order given."""
    p = np.asarray(pvalues, dtype=float)
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted = np.empty(n)
    adjusted[order] = np.clip(ranked, 0, 1)
    return adjusted


def fetch_go_annotations(accessions, mygene_client=None):
    """GO terms of UniProt accessions, from MyGene.info (a network call).

    Args:
        accessions: Protein IDs, FASTA-style ("sp|P12345|NAME") or bare.
        mygene_client: A `mygene.MyGeneInfo` (default: a new one).

    Returns:
        DataFrame with "query" (the clean accession) and "BP_terms",
        "CC_terms", "MF_terms" (lists of term names), one row per accession
        that MyGene.info found; accessions it has no GO terms for get empty
        lists.
    """
    clean = sorted({get_clean_uniprot(a) for a in accessions if a})
    columns = ["query"] + [f"{t}_terms" for t in GO_CATEGORIES]
    if not clean:
        return pd.DataFrame(columns=columns)
    client = mygene_client or mygene.MyGeneInfo()
    res_list = client.querymany(
        clean, scopes="uniprot", fields="go", as_dataframe=False, verbose=False
    )
    res_go = pd.DataFrame(res_list)
    if res_go.empty or "query" not in res_go.columns:
        return pd.DataFrame(columns=columns)
    if "notfound" in res_go.columns:
        res_go = res_go[res_go["notfound"].ne(True)]
    if "go" not in res_go.columns:
        res_go["go"] = None
    for go_type in GO_CATEGORIES:
        res_go[f"{go_type}_terms"] = res_go["go"].apply(
            lambda x, go_type=go_type: extract_go_terms(x, go_type)
        )
    # One row per accession (an accession can map to several genes)
    merged = (
        res_go[columns]
        .groupby("query", as_index=False)
        .agg(lambda lists: sorted({t for terms in lists for t in terms}))
    )
    merged["query"] = merged["query"].astype(str)
    return merged.reset_index(drop=True)


def go_enrichment(annotations, foreground, background, categories=GO_CATEGORIES):
    """GO term enrichment of a selected set of proteins.

    Unlike `calculate_go_enrichment`, the foreground is given directly (e.g.
    the proteins a user selected in a plot or table) and the annotations come
    from the caller, who can cache them.

    Args:
        annotations: DataFrame from `fetch_go_annotations` covering at least
            the background.
        foreground: Protein IDs of the selection (FASTA-style or bare).
        background: Protein IDs the selection was made from.
        categories: GO categories to test.

    Returns:
        Dict with "fg_count" and "bg_count" (proteins with any GO annotation
        in either set), "fg_total"/"bg_total" (all proteins given) and
        "categories" (category -> DataFrame of `go_term_table`).
    """
    fg = {get_clean_uniprot(a) for a in foreground if a}
    bg = {get_clean_uniprot(a) for a in background if a} | fg
    annotated = set(annotations["query"].astype(str)) if len(annotations) else set()
    has_terms = set()
    for _, row in annotations.iterrows():
        if any(len(row[f"{t}_terms"]) for t in categories):
            has_terms.add(str(row["query"]))
    fg_annotated = fg & annotated & has_terms
    bg_annotated = bg & annotated & has_terms
    return {
        "fg_total": len(fg),
        "bg_total": len(bg),
        "fg_count": len(fg_annotated),
        "bg_count": len(bg_annotated),
        "categories": {
            t: go_term_table(annotations, fg_annotated, bg_annotated, t)
            for t in categories
        },
    }


def run_go_category(res_go, fg_set, bg_set, go_type):
    """Runs hypergeometric (Fisher's exact) enrichment for one GO category.

    For each GO term annotated in the background set, tests whether it is
    over-represented in the foreground (significant) set relative to the
    background, via a one-sided Fisher's exact test on the term's 2x2
    contingency table.

    Args:
        res_go: DataFrame of MyGene.info results with a "query" column
            (protein ID) and a "{go_type}_terms" column (list of GO term
            names per protein), as produced by `extract_go_terms`.
        fg_set: Set of protein IDs considered "foreground" (e.g. proteins
            passing significance/fold-change cutoffs).
        bg_set: Set of protein IDs considered "background" (typically all
            annotated proteins in the input data).
        go_type: Which GO category to test - "BP", "CC", or "MF".

    Returns:
        Tuple of `(fig, df)`: a Plotly horizontal bar chart of the top 20
        terms by p-value, and the underlying DataFrame with columns
        "GO_Term", "Count", "GeneRatio", "p_value", "-log10(p)". Returns
        `(None, None)` if no foreground-annotated GO terms were found.
    """
    go2fg = defaultdict(set)
    go2bg = defaultdict(set)

    for _, row in res_go.iterrows():
        uid = str(row["query"])
        for term in row[f"{go_type}_terms"]:
            go2bg[term].add(uid)
            if uid in fg_set:
                go2fg[term].add(uid)

    records = []
    N_fg = len(fg_set)
    N_bg = len(bg_set)

    for term, fg_genes in go2fg.items():
        a = len(fg_genes)
        if a == 0:
            continue
        b = N_fg - a
        c = len(go2bg[term]) - a
        d = N_bg - (a + b + c)

        # Hypergeometric test via Fisher's Exact Test
        _, p = fisher_exact([[a, b], [c, d]], alternative="greater")
        records.append(
            {
                "GO_Term": term,
                "Count": a,
                "GeneRatio": f"{a}/{N_fg}",
                "p_value": p,
            }
        )

    df = pd.DataFrame(records)
    if df.empty:
        return None, None

    df["-log10(p)"] = -np.log10(df["p_value"].replace(0, 1e-10))
    df = df.sort_values("p_value").head(20)

    # Generate dynamic Plotly bar figure
    fig = px.bar(
        df,
        x="-log10(p)",
        y="GO_Term",
        orientation="h",
        title=f"GO Enrichment: {go_type}",
        color="-log10(p)",
        color_continuous_scale="Viridis",
    )
    fig.update_layout(
        yaxis={"autorange": "reversed"},
        height=500,
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
    )
    return fig, df


def calculate_go_enrichment(
    final_report: pl.DataFrame,
    id_col: str,
    target_p_col: str,
    p_cutoff: float = 0.05,
    fc_cutoff: float = 1.0,
):
    """Runs the full GO enrichment pipeline: filter, annotate, test.

    Unlike the other `analysis/` modules, this makes a live network call to
    the MyGene.info API and builds Plotly figures directly, so it takes an
    eager `pl.DataFrame` (not a `LazyFrame`) and returns a status string
    instead of raising, so callers can distinguish "not enough data" from
    a hard error without a try/except.

    Args:
        final_report: Statistics table (eager DataFrame) with an ID column
            and columns for adjusted p-value and log2 fold change.
        id_col: Column in `final_report` with protein identifiers, in
            FASTA-style ("sp|ACCESSION|NAME") or bare accession form - see
            `get_clean_uniprot`.
        target_p_col: Column in `final_report` holding the p-value (or
            adjusted p-value) used for the significance cutoff.
        p_cutoff: Maximum p-value for a protein to count as "foreground"/
            significant (default: 0.05).
        fc_cutoff: Minimum absolute log2 fold change for a protein to count
            as "foreground"/significant (default: 1.0).

    Returns:
        Tuple of `(status, payload)`:
            - `("empty_data", None)` if no rows have non-null p-value/log2FC.
            - `("insufficient_proteins", fg_count)` if fewer than 3 proteins
              meet the significance cutoffs (`fg_count` is an int).
            - `("success", result_dict)` otherwise, where `result_dict` has
              keys "bg_count" (int), "fg_count" (int), and "categories"
              (dict keyed by "BP"/"CC"/"MF", each value a dict with "fig"
              and "df" as returned by `run_go_category`).
    """
    # 1. Filter non-null entries via Polars
    analysis_ready = final_report.filter(
        pl.col(target_p_col).is_not_null() & pl.col("log2FC").is_not_null()
    )

    if analysis_ready.is_empty():
        return "empty_data", None

    # 2. Extract clean UniProt accessions using Polars element mapping
    analysis_ready = analysis_ready.with_columns(
        pl.col(id_col)
        .map_elements(get_clean_uniprot, return_dtype=pl.String)
        .alias("UniProt")
    )

    bg_ids = (
        analysis_ready.select("UniProt").drop_nulls().unique().to_series().to_list()
    )
    fg_ids = (
        analysis_ready.filter(
            (pl.col(target_p_col) < p_cutoff) & (pl.col("log2FC").abs() >= fc_cutoff)
        )
        .select("UniProt")
        .drop_nulls()
        .unique()
        .to_series()
        .to_list()
    )

    if len(fg_ids) < 3:
        return "insufficient_proteins", len(fg_ids)

    # 3. Fetch data from MyGene.info
    mg = mygene.MyGeneInfo()
    res_list = mg.querymany(bg_ids, scopes="uniprot", fields="go", as_dataframe=False)
    res_go = pd.DataFrame(res_list)

    if "notfound" in res_go.columns:
        res_go = res_go[res_go["notfound"].ne(True)]

    # MyGene.info may return zero hits with a "go" field at all (e.g. for
    # organisms/genes with sparse GO annotation coverage, such as many
    # bacterial species). Treat that the same as "no GO data for anyone"
    # instead of crashing, so callers still get a clean "no terms found"
    # result rather than an unhandled KeyError.
    if "go" not in res_go.columns:
        res_go["go"] = None

    # 4. Map GO annotations
    for go_type in ["BP", "CC", "MF"]:
        res_go[f"{go_type}_terms"] = res_go["go"].apply(
            lambda x, go_type=go_type: extract_go_terms(x, go_type)
        )

    annotated_ids = set(res_go["query"].astype(str))
    fg_set = annotated_ids.intersection(fg_ids)
    bg_set = annotated_ids

    # 5. Run statistical tests across all categories
    results = {}
    for go_type in ["BP", "CC", "MF"]:
        fig, df_go = run_go_category(res_go, fg_set, bg_set, go_type)
        results[go_type] = {"fig": fig, "df": df_go}

    return "success", {
        "bg_count": len(bg_ids),
        "fg_count": len(fg_ids),
        "categories": results,
    }
