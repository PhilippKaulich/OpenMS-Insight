"""
Streamlit Vue Components - Interactive visualization components for Streamlit.

This package provides reusable, interactive Streamlit components backed by Vue.js
visualizations with cross-component selection state management.
"""

from .components.clustered_heatmap import ClusteredHeatmap
from .components.deconvolved_spectrum import DeconvolvedSpectrum
from .components.heatmap import Heatmap
from .components.lineplot import LinePlot
from .components.mirrorplot import MirrorPlot
from .components.pca import PCAPlot
from .components.plot3d import Plot3D
from .components.protein_sequence_view import ProteinSequenceView
from .components.protein_structure_view import ProteinStructureView
from .components.sequenceview import SequenceView, SequenceViewResult
from .components.series_plot import SeriesPlot
from .components.table import Table
from .components.volcanoplot import VolcanoPlot
from .core.base import BaseComponent
from .core.cache import CacheMissError
from .core.registry import get_component_class, register_component
from .core.state import StateManager
from .rendering.bridge import (
    clear_component_annotations,
    defer_reruns,
    get_component_annotations,
)

__version__ = "0.4.0.dev0"

__all__ = [
    # Core
    "BaseComponent",
    "StateManager",
    "register_component",
    "get_component_class",
    "CacheMissError",
    # Components
    "Table",
    "LinePlot",
    "Heatmap",
    "ClusteredHeatmap",
    "VolcanoPlot",
    "SequenceView",
    "SequenceViewResult",
    "MirrorPlot",
    "PCAPlot",
    "SeriesPlot",
    "Plot3D",
    "DeconvolvedSpectrum",
    "ProteinSequenceView",
    "ProteinStructureView",
    # Utilities
    "get_component_annotations",
    "clear_component_annotations",
    "defer_reruns",
]
