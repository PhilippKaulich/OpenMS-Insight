# OpenMS-Insight

Interactive visualization components for mass spectrometry data in Streamlit, plus a
small set of helpers for differential expression analysis. This file fixes the
vocabulary; it is a glossary, not a design document.

## Language

### Data

**Quantification matrix**:
A wide table holding one row per feature and one column per sample, carrying the
measured abundance of each feature in each sample.
_Avoid_: expression matrix, intensity table, wide data

**Feature**:
The row identity of a quantification matrix — the analyte being quantified across
samples, such as a protein or peptide. Distinct from an OpenMS
featureXML feature, which is a 2D isotopic peak cluster in a single run; when both
senses appear together, name the file format explicitly.
_Avoid_: analyte, entity, row

**Sample**:
One measured run, identified by a sample id that appears both as a column of the
quantification matrix and as a row of the sample metadata.
_Avoid_: replicate, run, experiment

**Sample metadata**:
A table mapping each sample id to the biological group it belongs to.
_Avoid_: design table, annotation, phenotype data

**Group**:
The biological condition a sample belongs to, and the unit that differential
expression compares.
_Avoid_: condition, class, cohort, label

**Working column**:
A column an analysis helper materializes part-way through a computation and removes
before returning. Named with a leading underscore, and never part of a helper's
output.
_Avoid_: temp column, intermediate, scratch column

### Code surfaces

**Core component**:
A visualization the library offers on its public surface, pairing a Python class
with a Vue view and sharing selection state with its siblings. A plain install of
the package must be enough to use one.
_Avoid_: widget, plot, chart, view

**Analysis helper**:
A transformation over a quantification matrix — filtering, imputation,
normalization, statistical testing, enrichment. It has no Vue counterpart, holds no
selection state, and is not part of the component architecture.
_Avoid_: utility, processor, pipeline step
