"""Bridge between Python components and Vue frontend."""

import contextlib
import contextvars
import hashlib
import json
import logging
import os
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pandas as pd
import polars as pl
import streamlit as st

# Configure debug logging for hash tracking
_DEBUG_HASH_TRACKING = os.environ.get("SVC_DEBUG_HASH", "").lower() == "true"
# Debug logging for page navigation / state sync issues
_DEBUG_STATE_SYNC = os.environ.get("SVC_DEBUG_STATE", "").lower() == "true"
_logger = logging.getLogger(__name__)

# Numeric data types for type conversion during selection validation
NUMERIC_DTYPES = (
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
)


def _make_hashable(value: Any) -> Any:
    """
    Convert a value to a hashable form for use in cache keys.

    Handles dicts and lists by converting to JSON strings.

    Args:
        value: Any value from state

    Returns:
        A hashable version of the value
    """
    if isinstance(value, dict):
        # Convert dict to sorted JSON string for consistent hashing
        return json.dumps(value, sort_keys=True)
    if isinstance(value, list):
        return json.dumps(value)
    return value


if TYPE_CHECKING:
    from ..core.base import BaseComponent
    from ..core.state import StateManager


# Cache the Vue component function
_vue_component_func = None

# Session state key for Vue's echoed hash (what Vue currently has)
# Used for bidirectional hash confirmation - we only send data when
# Vue's echoed hash doesn't match the current data hash
_VUE_ECHOED_HASH_KEY = "_svc_vue_echoed_hashes"

# Session state key for the data hash last sent to each component. Data the
# component already has is not sent again (see _render_component).
_SENT_HASH_KEY = "_svc_sent_hashes"
# The hashes recorded in _SENT_HASH_KEY during the current script run: (run, {key:
# hash before the run})
_RUN_SENT_KEY = "_svc_run_sent_hashes"
# Per component: the last data request from Vue that was acted on
_HANDLED_REQUESTS_KEY = "_svc_handled_data_requests"
# Per component: the scope (see Table.auto_selection_scope) its first row was
# last selected in, or selected by the user in
_AUTO_SELECTION_SCOPE_KEY = "_svc_auto_selection_scopes"
# Per component rendered inside defer_reruns(): its StateManager's session key
# and the last value from Vue that was applied (see defer_reruns)
_DEFERRED_COMPONENTS_KEY = "_svc_deferred_components"

# Session state key for per-component data cache
# Each component stores exactly one entry (current filter state)
_COMPONENT_DATA_CACHE_KEY = "_svc_component_data_cache"

# Session state key for component annotations (from Vue)
# Stores annotation dataframes returned by components like SequenceView
_COMPONENT_ANNOTATIONS_KEY = "_svc_component_annotations"

# Session state key for batch resend flag
# When any component requests data (e.g., after page navigation), we clear
# ALL hashes on the next render so all components get data in one rerun
_BATCH_RESEND_KEY = "_svc_batch_resend"


# Payload entries that ask Vue to act (not part of the data hash): a payload that
# carries one is always sent
_NAVIGATION_KEYS = ("_navigate_to_page", "_target_row_index")

# Key under which a component's cache build is folded into its payload cache key.
# Leading underscores keep it clear of state identifiers, which the key also holds.
_CACHE_GENERATION_KEY = "__cache_generation__"

# Session key: per component key, the nonce of the last view action applied
_HANDLED_EVENTS_KEY = "_svc_handled_events"

# Key under which data a component is given per render is folded in (see
# BaseComponent._get_render_key).
_RENDER_KEY = "__render_key__"


def _payload_cache_key(
    component: "BaseComponent",
    state: dict[str, Any],
    state_keys: set[str],
) -> tuple[tuple[str, Any], ...]:
    """
    Build the key that decides whether a cached payload is still valid.

    The payload cache lives in session state and is keyed by component id, which is
    derived from cache_id. Filter state alone therefore cannot tell a rebuilt cache
    from the one already served: rerunning a workflow rewrites the cache on disk
    under the same cache_id, and the browser would keep being sent the old payload
    until the session ended. Folding in the cache's build generation makes a
    rebuild a cache miss.

    Args:
        component: The component being rendered
        state: Current selection state
        state_keys: State identifiers that affect this component's data

    Returns:
        Hashable, order-independent key of filter state plus cache generation.
    """
    return tuple(
        sorted(
            [(k, _make_hashable(state.get(k))) for k in state_keys]
            + [(_CACHE_GENERATION_KEY, getattr(component, "_cache_generation", ""))]
            + [(_RENDER_KEY, component._get_render_key())]
        )
    )


def _get_component_cache() -> dict[str, Any]:
    """Get per-component data cache from session state."""
    if _COMPONENT_DATA_CACHE_KEY not in st.session_state:
        st.session_state[_COMPONENT_DATA_CACHE_KEY] = {}
    return st.session_state[_COMPONENT_DATA_CACHE_KEY]


def clear_component_cache() -> None:
    """
    Clear all per-component cached data.

    Call this when loading a new file to ensure fresh data is sent to Vue.
    """
    if _COMPONENT_DATA_CACHE_KEY in st.session_state:
        st.session_state[_COMPONENT_DATA_CACHE_KEY].clear()


def _store_component_annotations(
    component_key: str, annotations: dict[str, Any]
) -> None:
    """
    Store annotations returned by a Vue component.

    Args:
        component_key: Unique key for the component
        annotations: Dict with annotation arrays (e.g., peak_id, highlight_color, annotation)
    """
    if _COMPONENT_ANNOTATIONS_KEY not in st.session_state:
        st.session_state[_COMPONENT_ANNOTATIONS_KEY] = {}
    st.session_state[_COMPONENT_ANNOTATIONS_KEY][component_key] = annotations


def get_component_annotations(component_key: str | None) -> pl.DataFrame | None:
    """
    Get annotations stored by a Vue component.

    Args:
        component_key: Unique key for the component

    Returns:
        Polars DataFrame with annotations, or None if not available
    """
    if component_key is None:
        return None

    if _COMPONENT_ANNOTATIONS_KEY not in st.session_state:
        return None

    annotations = st.session_state[_COMPONENT_ANNOTATIONS_KEY].get(component_key)
    if annotations is None:
        return None

    # Convert to DataFrame
    try:
        # annotations should be a dict with arrays: {peak_id: [...], highlight_color: [...], annotation: [...]}
        return pl.DataFrame(annotations)
    except Exception:
        return None


def clear_component_annotations() -> None:
    """Clear all component annotations."""
    if _COMPONENT_ANNOTATIONS_KEY in st.session_state:
        st.session_state[_COMPONENT_ANNOTATIONS_KEY].clear()


# Attributes under which components store per-render annotations. LinePlot keeps a
# single set; MirrorPlot keeps one per side. Both must be visible here, or the cached
# payload path silently drops annotations for the components it misses.
_DYNAMIC_ANNOTATION_ATTRS = (
    "_dynamic_annotations",
    "_top_dynamic_annotations",
    "_bottom_dynamic_annotations",
)


def _get_dynamic_annotations(
    component: "BaseComponent",
) -> list[tuple[str, dict[Any, Any]]] | None:
    """
    Collect a component's dynamic annotation dicts, whichever shape it uses.

    Args:
        component: The component to inspect

    Returns:
        List of (attribute name, annotations) pairs, or None if there are none.
        The attribute name is carried so the hash can tell the sides apart --
        moving a label from the top spectrum to the bottom must invalidate the cache.
    """
    present = [
        (attr, annotations)
        for attr, annotations in (
            (attr, getattr(component, attr, None)) for attr in _DYNAMIC_ANNOTATION_ATTRS
        )
        # Annotations are always dicts. Requiring that (rather than "not None") keeps
        # test doubles, whose auto-created attributes are truthy, from being mistaken
        # for real annotations.
        if isinstance(annotations, dict)
    ]
    return present or None


def _compute_annotation_hash(component: "BaseComponent") -> str | None:
    """
    Compute hash of component's dynamic annotations, if any.

    Args:
        component: The component to check for annotations

    Returns:
        Short hash string if annotations exist, None otherwise
    """
    annotation_sets = _get_dynamic_annotations(component)
    if annotation_sets is None:
        return None
    # Hash each set's sorted keys alongside the attribute it came from, so the same
    # labels on a different side produce a different hash.
    keys = [(attr, sorted(annotations.keys())) for attr, annotations in annotation_sets]
    return hashlib.md5(str(keys).encode()).hexdigest()[:8]


def _get_cached_vue_data(
    component_id: str,
    filter_state_hashable: tuple[tuple[str, Any], ...],
) -> tuple[dict[str, Any], str, str | None] | None:
    """
    Get cached Vue data for component if filter state matches.

    Each component has exactly one cached entry. If filter state changed,
    returns None (cache miss).

    Args:
        component_id: Unique identifier for this component
        filter_state_hashable: Current filter state (for cache validation)

    Returns:
        Tuple of (vue_data, data_hash, annotation_hash) if cache hit, None otherwise
    """
    cache = _get_component_cache()
    if component_id in cache:
        entry = cache[component_id]
        # Support both old (3-tuple) and new (4-tuple) format
        if len(entry) == 4:
            cached_state, vue_data, data_hash, ann_hash = entry
        else:
            cached_state, vue_data, data_hash = entry
            ann_hash = None
        if cached_state == filter_state_hashable:
            return (vue_data, data_hash, ann_hash)
    return None


def _set_cached_vue_data(
    component_id: str,
    filter_state_hashable: tuple[tuple[str, Any], ...],
    vue_data: dict[str, Any],
    data_hash: str,
    ann_hash: str | None = None,
) -> None:
    """
    Cache Vue data for component, replacing any previous entry.

    Each component stores exactly one entry, so memory = O(num_components).

    Args:
        component_id: Unique identifier for this component
        filter_state_hashable: Current filter state
        vue_data: Data to cache
        data_hash: Hash of the data
        ann_hash: Hash of dynamic annotations (if any)
    """
    cache = _get_component_cache()
    cache[component_id] = (filter_state_hashable, vue_data, data_hash, ann_hash)


def _prepare_vue_data_cached(
    component: "BaseComponent",
    component_id: str,
    filter_state_hashable: tuple[tuple[str, Any], ...],
    state_dict: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """
    Prepare Vue data with per-component caching.

    Each component caches exactly one entry (its current filter state).
    When filter state changes, old entry is replaced - memory stays bounded.

    For components with dynamic annotations (e.g., LinePlot linked to SequenceView):
    - Cache stores BASE data (without annotation columns)
    - Annotations are re-applied fresh each render (cheap operation)
    - Final hash reflects current annotation state

    Args:
        component: The component to prepare data for
        component_id: Unique identifier for this component
        filter_state_hashable: Hashable version of filter state (for cache key)
        state_dict: Original state dict with actual values

    Returns:
        Tuple of (vue_data dict, data_hash string)
    """
    # Check if component has dynamic annotations (e.g., LinePlot linked to
    # SequenceView, or MirrorPlot with per-side annotations)
    has_dynamic_annotations = _get_dynamic_annotations(component) is not None

    # Try cache first (works for ALL components now)
    cached = _get_cached_vue_data(component_id, filter_state_hashable)

    if _DEBUG_HASH_TRACKING:
        cache_hit = cached is not None
        _logger.warning(f"[CacheDebug] {component._cache_id}: cache_hit={cache_hit}")

    if cached is not None:
        cached_data, cached_hash, _ = cached  # Ignore cached annotation hash here

        if has_dynamic_annotations:
            # Cache hit but need to re-apply annotations (they may have changed)
            # Use component method to apply fresh annotations to cached base data
            if hasattr(component, "_apply_fresh_annotations"):
                # Shallow copy to avoid mutating cache
                vue_data = component._apply_fresh_annotations(dict(cached_data))
                # Hash final data (includes new annotations)
                data_hash = _hash_data(vue_data)
                return vue_data, data_hash
            else:
                # Fallback: recompute if component doesn't support fresh annotations
                vue_data = component._prepare_vue_data(state_dict)
                data_hash = _hash_data(vue_data)
                return vue_data, data_hash
        else:
            # No dynamic annotations - ensure _plotConfig is present
            # When annotations are cleared, Vue needs _plotConfig with null columns
            # to stop showing stale annotations (Vue merge only updates keys present)
            if hasattr(component, "_build_plot_config"):
                vue_data = dict(cached_data)
                vue_data["_plotConfig"] = component._build_plot_config(
                    getattr(component, "_highlight_column", None),
                    getattr(component, "_annotation_column", None),
                )
                return vue_data, cached_hash
            return cached_data, cached_hash

    # Cache miss - compute data
    vue_data = component._prepare_vue_data(state_dict)

    # Compute annotation hash for cache storage
    ann_hash = _compute_annotation_hash(component)

    if has_dynamic_annotations:
        # Store BASE data (without dynamic annotation columns) in cache
        if hasattr(component, "_strip_dynamic_columns"):
            base_data = component._strip_dynamic_columns(vue_data)
        else:
            # Fallback: store without _plotConfig (may have stale column refs)
            base_data = {k: v for k, v in vue_data.items() if k != "_plotConfig"}
        base_hash = _hash_data(base_data)
        _set_cached_vue_data(
            component_id, filter_state_hashable, base_data, base_hash, ann_hash
        )

        # Return full data with annotations
        data_hash = _hash_data(vue_data)
        return vue_data, data_hash
    else:
        # Store complete data in cache
        data_hash = _hash_data(vue_data)
        _set_cached_vue_data(
            component_id, filter_state_hashable, vue_data, data_hash, ann_hash
        )
        return vue_data, data_hash


def get_vue_component_function():
    """
    Get the Streamlit component function for the Vue frontend.

    Returns:
        The declared Streamlit component function
    """
    global _vue_component_func

    if _vue_component_func is None:
        import streamlit.components.v1 as st_components

        # Check for development mode
        dev_mode = os.environ.get("SVC_DEV_MODE", "false").lower() == "true"

        if dev_mode:
            # Development mode: connect to Vite dev server
            dev_url = os.environ.get("SVC_DEV_URL", "http://localhost:5173")
            _vue_component_func = st_components.declare_component(
                "streamlit_vue_component",
                url=dev_url,
            )
        else:
            # Production mode: use built component
            parent_dir = os.path.dirname(os.path.abspath(__file__))
            build_dir = os.path.join(parent_dir, "..", "js-component", "dist")

            if not os.path.exists(build_dir):
                raise RuntimeError(
                    f"Vue component build not found at {build_dir}. "
                    "Please build the Vue component or set SVC_DEV_MODE=true "
                    "for development."
                )

            _vue_component_func = st_components.declare_component(
                "streamlit_vue_component",
                path=build_dir,
            )

    return _vue_component_func


def _get_validation_filter_groups(
    component: "BaseComponent",
) -> list[tuple[dict[str, str], dict[str, Any]]]:
    """Filter groups to validate interactivity selections against.

    A group is one independently filtered view of the component's data. Most
    components have exactly one; a MirrorPlot has one per side. Components that
    predate the hook fall back to their flat filters.
    """
    getter = getattr(component, "get_validation_filter_groups", None)
    if callable(getter):
        groups: list[tuple[dict[str, str], dict[str, Any]]] = getter()
        if groups:
            return groups

    return [
        (
            getattr(component, "_filters", None) or {},
            getattr(component, "_filter_defaults", None) or {},
        )
    ]


def _apply_auto_selection(
    component: "BaseComponent",
    component_id: str,
    selection: dict[str, Any],
    state_manager: "StateManager",
) -> bool:
    """
    Set each identifier of a component's default selection that has no value.

    A component that lets the user clear its selection reports the scope its
    rows were selected in (its filter values); it is not selected again in the
    scope the user cleared it in, only once the scope changes.

    Returns whether the state changed.
    """
    if not selection:
        return False
    scope_of = getattr(component, "auto_selection_scope", None)
    scope = scope_of(state_manager.get_state_for_vue()) if scope_of else None
    if scope is not None:
        scopes = st.session_state.setdefault(_AUTO_SELECTION_SCOPE_KEY, {})
        selected = any(
            state_manager.get_selection(identifier) is not None
            for identifier in selection
        )
        if selected or scopes.get(component_id) == scope:
            scopes[component_id] = scope
            return False
        scopes[component_id] = scope

    state_changed = False
    for identifier, value in selection.items():
        if state_manager.get_selection(identifier) is None:
            state_manager.set_selection(identifier, value)
            state_changed = True
    return state_changed


def _prefetch(
    component: "BaseComponent",
    component_id: str,
    state_manager: "StateManager",
    state: dict[str, Any],
) -> tuple[dict[str, Any], str, bool] | None:
    """
    Data for the current state when no payload is cached for it, inside
    defer_reruns() only (else None).

    Rendered one after another, a component that sees a selection made earlier in
    the same run has no payload cached for it. Outside defer_reruns() it reruns
    the script at once and sends the data then. Inside, the rerun only comes at
    the end, so the data is computed now and sent in this run.

    Returns (payload, hash, whether the state changed), or None when the data
    cannot be sent yet: a filter has no value, or preparing the data changed the
    state it depends on (e.g. table navigation).
    """
    if _deferred_rerun.get() is None:
        return None
    filters = getattr(component, "_filters", None) or {}
    filter_defaults = getattr(component, "_filter_defaults", None) or {}
    if any(
        state.get(identifier) is None and identifier not in filter_defaults
        for identifier in filters
    ):
        return None

    state_keys = set(component.get_state_dependencies())
    cache_key = _payload_cache_key(component, state, state_keys)
    vue_data, data_hash = _prepare_vue_data_cached(
        component, component_id, cache_key, {k: state.get(k) for k in state_keys}
    )
    after = state_manager.get_state_for_vue()
    if _payload_cache_key(component, after, state_keys) != cache_key:
        return None

    state_changed = _apply_auto_selection(
        component, component_id, vue_data.pop("_auto_selection", {}), state_manager
    )

    payload: dict[str, Any] = {}
    for data_key, value in vue_data.items():
        if data_key == "_hash":
            continue
        if isinstance(value, pl.LazyFrame):
            payload[data_key] = value.collect().to_pandas()
        elif isinstance(value, pl.DataFrame):
            payload[data_key] = value.to_pandas()
        else:
            payload[data_key] = value
    return payload, data_hash, state_changed


def _validate_interactivity_selections(
    component: "BaseComponent",
    state_manager: "StateManager",
    state: dict[str, Any],
) -> bool:
    """
    Validate that interactivity selections still exist in filtered data.

    When an external filter changes, the currently selected value may no longer
    exist in the filtered dataset. This function checks each interactivity
    selection and clears it if invalid.

    Args:
        component: The component to validate selections for
        state_manager: StateManager to clear invalid selections
        state: Current state dict (already has filter values)

    Returns:
        True if any selection was cleared (state changed), False otherwise
    """
    interactivity = getattr(component, "_interactivity", None)
    if not interactivity:
        return False

    filter_groups = _get_validation_filter_groups(component)

    # Get the preprocessed data
    preprocessed = getattr(component, "_preprocessed_data", None)
    if preprocessed is not None:
        data = preprocessed.get("data")
    else:
        data = None
    if data is None:
        data = getattr(component, "_raw_data", None)
    if data is None:
        # Component doesn't have data we can validate against
        return False

    # Ensure LazyFrame
    if isinstance(data, pl.DataFrame):
        data = data.lazy()

    # Apply filters to get the filtered dataset.
    #
    # Each group is one view of the data, and a selection is valid if it survives in
    # ANY of them. Components with a single set of filters have exactly one group, so
    # this reduces to the plain conjunction it always was. A MirrorPlot has one group
    # per side: ANDing the two together would ask for rows where scan_id equals both
    # the top and the bottom scan at once, which is never satisfiable, so every
    # selection would be judged missing and cleared the moment it was made.
    group_predicates: list[pl.Expr] = []
    for filters, filter_defaults in filter_groups:
        if not filters:
            # An unfiltered view shows every row, so the union admits everything and
            # there is nothing any other group could rule out.
            group_predicates = []
            break

        predicate = None
        for identifier, column in filters.items():
            selected_value = state.get(identifier)
            if selected_value is None and identifier in filter_defaults:
                selected_value = filter_defaults[identifier]

            if selected_value is None:
                # Awaiting filter - no data to validate against
                return False

            # Convert float to int for integer columns (type mismatch handling)
            if isinstance(selected_value, float) and selected_value.is_integer():
                selected_value = int(selected_value)

            term = pl.col(column) == selected_value
            predicate = term if predicate is None else (predicate & term)

        if predicate is not None:
            group_predicates.append(predicate)

    if group_predicates:
        combined = group_predicates[0]
        for predicate in group_predicates[1:]:
            combined = combined | predicate
        data = data.filter(combined)

    # Restrictions that are not plain equality filters (e.g. a Table's range
    # filters) hide rows just the same, so a selection outside them is invalid too.
    # Looked up on the class, so test doubles' auto-created attributes are ignored.
    extra_filters = getattr(type(component), "_apply_validation_filters", None)
    if callable(extra_filters):
        data = extra_filters(component, data, state)

    # Collect all checks to validate
    state_changed = False
    schema = data.collect_schema()
    checks_to_validate: list[tuple[str, str, Any]] = []

    for identifier, column in interactivity.items():
        selected_value = state.get(identifier)
        if selected_value is None:
            continue  # No selection to validate

        if column not in schema.names():
            continue  # Column doesn't exist

        # Type conversion for numeric columns
        col_dtype = schema[column]
        if col_dtype in NUMERIC_DTYPES:
            if isinstance(selected_value, float) and selected_value.is_integer():
                selected_value = int(selected_value)

        checks_to_validate.append((identifier, column, selected_value))

    # Early return if nothing to validate
    if not checks_to_validate:
        return False

    # Build single query with all existence checks
    #
    # An empty frame clears every selection, and that is deliberate: it means the
    # component displays no rows at all, so nothing in it can still be selected. See
    # TestTableSelectionClearingOnInvalidFilter in tests/integration/test_tabulator.py.
    existence_exprs = [
        (pl.col(column) == value).any().alias(identifier)
        for identifier, column, value in checks_to_validate
    ]

    # Execute ONE query instead of N
    results = data.select(existence_exprs).collect().row(0, named=True)

    # Process results and clear invalid selections
    for identifier, _column, value in checks_to_validate:
        if not results[identifier]:
            state_manager.set_selection(identifier, None)
            state_changed = True
            if _DEBUG_STATE_SYNC:
                _logger.warning(
                    f"[Bridge:{component._cache_id}] Cleared invalid selection: "
                    f"{identifier}={value} not in filtered data"
                )

    return state_changed


# Set inside defer_reruns(): components record there that they need a rerun
# instead of rerunning the script themselves
_deferred_rerun: contextvars.ContextVar[list[bool] | None] = contextvars.ContextVar(
    "openms_insight_deferred_rerun", default=None
)


def _sent_this_run() -> dict[str, Any]:
    """The sent hashes recorded during this script run, with their earlier values."""
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    ctx = get_script_run_ctx()
    # A new set per run (ScriptRunContext.reset), so it identifies the run
    run = getattr(ctx, "widget_ids_this_run", None)
    entry = st.session_state.get(_RUN_SENT_KEY)
    if entry is None or entry[0] is not run:
        entry = (run, {})
        st.session_state[_RUN_SENT_KEY] = entry
    return entry[1]


def _record_sent(key: str, data_hash: str) -> None:
    sent = st.session_state[_SENT_HASH_KEY]
    _sent_this_run().setdefault(key, sent.get(key))
    sent[key] = data_hash


def _rerun() -> None:
    """
    Rerun the script, forgetting the data sent in this run.

    Starting a run drops the messages of the previous one that have not reached
    the browser yet, so the data sent in this run may never arrive. The next
    run sends it again; a view that got it already does not parse it twice.
    """
    sent = st.session_state.get(_SENT_HASH_KEY, {})
    for key, before in _sent_this_run().items():
        if before is None:
            sent.pop(key, None)
        else:
            sent[key] = before
    _sent_this_run().clear()
    st.rerun()


def _apply_new_vue_values() -> None:
    """
    Apply the values Vue sent since the last run, for the components rendered
    inside defer_reruns(), before any of them renders.

    Streamlit returns a component's last value on every run, so only a value
    that differs from the one applied last is new. Applying it again in Phase 3
    of the component's render then changes nothing.
    """
    from ..core.state import StateManager

    deferred = st.session_state.get(_DEFERRED_COMPONENTS_KEY, {})
    for key, (session_key, applied) in list(deferred.items()):
        value = st.session_state.get(key) if key in st.session_state else None
        if not isinstance(value, dict) or value == applied:
            continue
        deferred[key] = (session_key, value)
        if session_key in st.session_state:
            StateManager(session_key).update_from_vue(dict(value))


@contextlib.contextmanager
def defer_reruns() -> Iterator[None]:
    """
    Render several components with at most one rerun, after the last of them.

    A component whose selection or data changed reruns the script so that every
    component gets the new state. Rendered one after another, each component
    that only now sees a new selection (e.g. the views of a table that was just
    clicked) reruns the script again, so one click can cost one rerun per
    component. Inside this block they all render first, with the state updated
    in place, and the script reruns once at the end if any of them asked for it.

    A click in one of them is applied before any of them renders, so the
    components rendered before the clicked one see it too, and the click costs
    no rerun at all unless preparing the data changes the state again.

    Example:
        with defer_reruns():
            table(key="table", state_manager=state_manager)
            plot(key="plot", state_manager=state_manager)
    """
    _apply_new_vue_values()
    pending = [False]
    token = _deferred_rerun.set(pending)
    try:
        yield
    finally:
        _deferred_rerun.reset(token)
    if pending[0]:
        _rerun()


def render_component(
    component: "BaseComponent",
    state_manager: "StateManager",
    key: str | None = None,
    height: int | None = None,
) -> Any:
    """Render a component in Streamlit (see _render_component)."""
    from ..core.state import _render_state_manager

    # Components that write state while preparing data (Table navigation) write
    # it to the manager they are rendered with
    token = _render_state_manager.set(state_manager)
    try:
        return _render_component(component, state_manager, key=key, height=height)
    finally:
        _render_state_manager.reset(token)


def _render_component(
    component: "BaseComponent",
    state_manager: "StateManager",
    key: str | None = None,
    height: int | None = None,
) -> Any:
    """
    Render a component in Streamlit.

    This function uses a two-phase approach to handle state synchronization:

    Phase 1: Call vue_func with CACHED data to get Vue's request
    Phase 2: Apply Vue's request, then prepare UPDATED data for next render

    This order is critical because Vue's request (e.g., page change, sort) is only
    available after calling vue_func(). By calling it first with cached data, we:
    1. Get Vue's request immediately
    2. Apply it to state BEFORE preparing data
    3. Prepare correct data for the next render
    4. Rerun to send the correct data

    Args:
        component: The component to render
        state_manager: StateManager for cross-component state
        key: Optional unique key for the Streamlit component
        height: Optional height in pixels

    Returns:
        The value returned by the Vue component
    """
    # === PHASE 0: Generate key and get component info ===
    if key is None:
        interactivity_str = json.dumps(component._interactivity or {}, sort_keys=True)
        key = f"svc_{component._cache_id}_{hashlib.md5(interactivity_str.encode()).hexdigest()[:8]}"

    component_type = component._get_vue_component_name()
    component_id = f"{component_type}:{key}"
    component_args = component._get_component_args()
    if height is not None:
        component_args["height"] = height

    # Batch resend: if any component requested data in previous run, clear ALL hashes
    if st.session_state.get(_BATCH_RESEND_KEY):
        st.session_state[_VUE_ECHOED_HASH_KEY] = {}
        st.session_state[_SENT_HASH_KEY] = {}
        _sent_this_run().clear()
        st.session_state.pop(_BATCH_RESEND_KEY, None)

    # Initialize hash cache in session state if needed
    if _VUE_ECHOED_HASH_KEY not in st.session_state:
        st.session_state[_VUE_ECHOED_HASH_KEY] = {}
    if _SENT_HASH_KEY not in st.session_state:
        st.session_state[_SENT_HASH_KEY] = {}

    # === PHASE 1: Get CACHED data from previous render ===
    cache = _get_component_cache()
    cached_entry = cache.get(component_id)

    # Get current state for initial render (may be stale until we apply Vue's request)
    initial_state = state_manager.get_state_for_vue()

    # Pre-compute initial selections BEFORE Vue renders (for first render only)
    initial_selection_changed = False
    if hasattr(component, "get_initial_selection"):
        initial_selection = component.get_initial_selection(initial_state)
        if _apply_auto_selection(
            component, component_id, initial_selection or {}, state_manager
        ):
            new_state = state_manager.get_state_for_vue()
            initial_selection_changed = new_state != initial_state
            initial_state = new_state

    # Compute current filter state for cache validity check
    # This tells us what state the component SHOULD have data for
    state_keys = set(component.get_state_dependencies())
    current_filter_state = _payload_cache_key(component, initial_state, state_keys)

    # Check if cached data is VALID for current state
    # KEY FIX: Only send data when cache matches current state
    # - Before: Always sent cached data, even if stale (page 38 when Vue wants page 1)
    # - Now: Only send if cache matches current state AND annotation state matches
    cache_valid = False
    # Components rendered before this one have not seen the initial selection.
    # Without defer_reruns() the cache miss below reruns anyway; with it, a
    # prefetched payload would not, so the selection asks for the rerun itself.
    prefetch_changed_state = (
        initial_selection_changed and _deferred_rerun.get() is not None
    )
    current_ann_hash = _compute_annotation_hash(component)

    if cached_entry is not None:
        # Support both old (3-tuple) and new (4-tuple) cache format
        if len(cached_entry) == 4:
            cached_state, cached_data, cached_hash, cached_ann_hash = cached_entry
        else:
            cached_state, cached_data, cached_hash = cached_entry
            cached_ann_hash = None

        # Cache valid only if BOTH filter state AND annotation state match
        filter_state_matches = cached_state == current_filter_state
        ann_state_matches = cached_ann_hash == current_ann_hash
        cache_valid = filter_state_matches and ann_state_matches

        if _DEBUG_STATE_SYNC:
            _logger.warning(
                f"[Bridge:{component._cache_id}] Phase1: cache_valid={cache_valid}, "
                f"filter_match={filter_state_matches}, ann_match={ann_state_matches}, "
                f"cached_ann={cached_ann_hash}, current_ann={current_ann_hash}"
            )

    # Build payload - only send data if cache is valid for current state
    if (
        cache_valid
        and st.session_state[_SENT_HASH_KEY].get(key) == cached_hash
        and not any(k in cached_data for k in _NAVIGATION_KEYS)
    ):
        # Vue already has this data (it was sent in an earlier run): send the
        # state and the component arguments only. Resending the data on every
        # rerun made each view parse and redraw it again, once per rerun. A
        # component that lost its data (e.g. remounted) asks for it with
        # _requestData, which clears the sent hashes.
        data_payload = {
            "selection_store": initial_state,
            "hash": cached_hash,
            "dataChanged": False,
            "awaitingFilter": False,
            **(
                {"_plotConfig": cached_data["_plotConfig"]}
                if "_plotConfig" in cached_data
                else {}
            ),
        }
    elif cache_valid:
        # Cache HIT - send cached data (it's correct for current state)
        data_payload = {
            **cached_data,
            "selection_store": initial_state,
            "hash": cached_hash,
            "dataChanged": True,
            "awaitingFilter": False,
        }
        if _DEBUG_STATE_SYNC:
            # Log pagination state for debugging
            pagination_key = next((k for k in state_keys if "page" in k.lower()), None)
            if pagination_key:
                _logger.warning(
                    f"[Bridge:{component._cache_id}] Phase1: Cache HIT, "
                    f"sending data with hash={cached_hash[:8]}, "
                    f"pagination={initial_state.get(pagination_key)}"
                )
    elif (
        prefetched := _prefetch(component, component_id, state_manager, initial_state)
    ) is not None:
        # Inside defer_reruns(): the data for the current state, computed now
        # and sent in this run rather than after the rerun
        prefetched_data, prefetched_hash, auto_selected = prefetched
        prefetch_changed_state = prefetch_changed_state or auto_selected
        initial_state = state_manager.get_state_for_vue()
        data_payload = {
            **prefetched_data,
            "selection_store": initial_state,
            "hash": prefetched_hash,
            "dataChanged": True,
            "awaitingFilter": False,
        }
        cache_valid = True
    else:
        # Cache MISS (no cache, or state mismatch) - don't send stale data
        # Vue will show loading or use its local cache
        data_payload = {
            "selection_store": initial_state,
            "hash": "",
            "dataChanged": False,
            "awaitingFilter": False,
        }
        if _DEBUG_STATE_SYNC:
            _logger.warning(
                f"[Bridge:{component._cache_id}] Phase1: Cache MISS, "
                f"not sending data (cached_entry={cached_entry is not None})"
            )

    if data_payload["dataChanged"]:
        _record_sent(key, data_payload["hash"])

    # Component layout: [[{componentArgs: {...}}]]
    components = [[{"componentArgs": component_args}]]

    # === PHASE 2: Call vue_func to get Vue's request ===
    vue_func = get_vue_component_function()

    kwargs = {
        "components": components,
        "key": key,
        **data_payload,
    }
    if height is not None:
        kwargs["height"] = height

    if _DEBUG_STATE_SYNC:
        _logger.warning(
            f"[Bridge:{component._cache_id}] Phase2: Calling vue_func to get request"
        )

    result = vue_func(**kwargs)

    # === PHASE 3: Apply Vue's request FIRST ===
    state_changed = prefetch_changed_state
    if result is not None:
        # Debug logging: what we received from Vue
        if _DEBUG_STATE_SYNC:
            vue_counter = result.get("counter")
            vue_keys = [k for k in result.keys() if not k.startswith("_")]
            _logger.warning(
                f"[Bridge:{component._cache_id}] Phase3: Received counter={vue_counter}, "
                f"keys={vue_keys}, _requestData={result.get('_requestData', False)}"
            )

        # Store Vue's echoed hash
        vue_hash = result.get("_vueDataHash")
        if vue_hash is not None:
            st.session_state[_VUE_ECHOED_HASH_KEY][key] = vue_hash

        # Apply Vue's state update FIRST - this is the key fix!
        # (or: a selection made in Phase 1 still needs its rerun)
        if state_manager.update_from_vue(dict(result)):
            state_changed = True
        if _deferred_rerun.get() is not None:
            st.session_state.setdefault(_DEFERRED_COMPONENTS_KEY, {})[key] = (
                state_manager._session_key,
                result,
            )

        # An action the view sent (e.g. a file the user chose). Streamlit returns
        # the last value on every run, so each one (by its nonce) is applied once.
        event = result.get("_event")
        if isinstance(event, dict) and event.get("nonce") is not None:
            handled_events = st.session_state.setdefault(_HANDLED_EVENTS_KEY, {})
            if handled_events.get(key) != event["nonce"]:
                handled_events[key] = event["nonce"]
                if component._handle_event(event):
                    state_changed = True

        # Check if Vue is requesting data resend
        # The data is only sent with the next render, which this run has passed:
        # rerun, or a view that missed its data keeps waiting for it. Streamlit
        # returns the last value Vue sent on every run, so each request (Vue
        # numbers them) is acted on once; else every run would rerun again.
        request = result.get("_requestData", False)
        handled = st.session_state.setdefault(_HANDLED_REQUESTS_KEY, {})
        if request is True:
            st.session_state[_BATCH_RESEND_KEY] = True
        elif request and handled.get(key) != request:
            handled[key] = request
            st.session_state[_BATCH_RESEND_KEY] = True
            state_changed = True

    # === PHASE 4: Get UPDATED state and prepare data ===
    # Now state reflects Vue's request (e.g., new page number after click)
    state = state_manager.get_state_for_vue()

    # Check if component has required filters without values
    filters = getattr(component, "_filters", None) or {}
    filter_defaults = getattr(component, "_filter_defaults", None) or {}

    awaiting_filter = False
    for identifier in filters.keys():
        if state.get(identifier) is None and identifier not in filter_defaults:
            awaiting_filter = True
            break

    # === Validate interactivity selections BEFORE preparing data ===
    # When filter changes, the current selection may no longer exist
    # in the filtered data. Clear it so auto-selection can kick in.
    if not awaiting_filter:
        if _validate_interactivity_selections(component, state_manager, state):
            state_changed = True
            # Refresh state after clearing invalid selections
            state = state_manager.get_state_for_vue()

    if not awaiting_filter:
        # Extract state keys that affect this component's data
        state_keys = set(component.get_state_dependencies())
        relevant_state = {k: state.get(k) for k in state_keys}

        # Build hashable version for cache key
        filter_state_hashable = _payload_cache_key(component, state, state_keys)

        if _DEBUG_HASH_TRACKING:
            _logger.warning(
                f"[CacheKey] {component._cache_id}: state_keys={list(state_keys)}"
            )
            for k in state_keys:
                if "page" in k.lower():
                    _logger.warning(
                        f"[CacheKey] {component._cache_id}: {k}={state.get(k)}"
                    )

        # Prepare data with UPDATED state (includes Vue's request)
        # This may also call set_selection() to override (e.g., sort resets page)
        vue_data, data_hash = _prepare_vue_data_cached(
            component, component_id, filter_state_hashable, relevant_state
        )

        # Apply auto-selection from first row (for tables with interactivity)
        # This ensures downstream components receive data when a filter changes
        if _apply_auto_selection(
            component, component_id, vue_data.pop("_auto_selection", {}), state_manager
        ):
            state_changed = True

        # Check if Python overrode state during _prepare_vue_data
        # (e.g., table.py sets page to last page after sort)
        final_state = state_manager.get_state_for_vue()
        if final_state != state:
            state_changed = True
            if _DEBUG_STATE_SYNC:
                _logger.warning(
                    f"[Bridge:{component._cache_id}] Phase4: Python overrode state"
                )
    else:
        vue_data = {}
        data_hash = "awaiting_filter"
        filter_state_hashable = ()

    _logger.info(
        f"[bridge] Phase4: {component._cache_id} prepared data, hash={data_hash[:8] if data_hash else 'None'}"
    )

    # === PHASE 5: Cache data for next render ===
    if vue_data:
        # Convert for caching (Arrow serialization requires pandas)
        converted_data = {}
        for data_key, value in vue_data.items():
            if data_key == "_hash":
                continue
            if isinstance(value, pl.LazyFrame):
                converted_data[data_key] = value.collect().to_pandas()
            elif isinstance(value, pl.DataFrame):
                converted_data[data_key] = value.to_pandas()
            else:
                converted_data[data_key] = value

        # Store in cache for next render (include annotation hash for validity check)
        cache[component_id] = (
            filter_state_hashable,
            converted_data,
            data_hash,
            current_ann_hash,
        )

        # If cache was invalid at Phase 1, we didn't send data to Vue (dataChanged=False).
        # Trigger a rerun so the newly cached data gets sent on the next render.
        # This handles cross-component filter changes where the affected component
        # needs to receive updated data (e.g., new total_rows/total_pages).
        if not cache_valid:
            state_changed = True
            if _DEBUG_STATE_SYNC:
                _logger.warning(
                    f"[Bridge:{component._cache_id}] Phase5: Cache was invalid, "
                    f"triggering rerun to send newly cached data"
                )

        if _DEBUG_STATE_SYNC:
            # Log what we're caching for debugging
            pagination_key = next(
                (k for k, v in filter_state_hashable if "page" in k.lower()), None
            )
            if pagination_key:
                pagination_val = next(
                    (v for k, v in filter_state_hashable if k == pagination_key), None
                )
                _logger.warning(
                    f"[Bridge:{component._cache_id}] Phase5: Cached data with hash={data_hash[:8]}, "
                    f"filter_state includes {pagination_key}={pagination_val}"
                )

    # Handle annotations from Vue (e.g., from SequenceView)
    if result is not None:
        annotations = result.get("_annotations")
        annotations_changed = False

        if annotations is not None:
            peak_ids = annotations.get("peak_id", [])
            new_hash = hash(tuple(peak_ids)) if peak_ids else 0

            ann_hash_key = f"_svc_ann_hash_{key}"
            old_hash = st.session_state.get(ann_hash_key)

            if old_hash != new_hash:
                annotations_changed = True
                st.session_state[ann_hash_key] = new_hash

            _store_component_annotations(key, annotations)
        else:
            ann_hash_key = f"_svc_ann_hash_{key}"
            if st.session_state.get(ann_hash_key) is not None:
                annotations_changed = True
                st.session_state[ann_hash_key] = None
            _store_component_annotations(key, None)

        if annotations_changed:
            state_changed = True

    # === PHASE 6: Rerun if state changed ===
    # This will send the UPDATED data (now in cache) to Vue
    if state_changed:
        if _DEBUG_STATE_SYNC:
            _logger.warning(
                f"[Bridge:{component._cache_id}] Phase6: RERUN triggered, "
                f"next render will have cache HIT"
            )
        pending = _deferred_rerun.get()
        if pending is not None:
            pending[0] = True
        else:
            _rerun()
    elif _DEBUG_STATE_SYNC:
        _logger.warning(
            f"[Bridge:{component._cache_id}] Phase6: No rerun needed, state_changed=False"
        )

    return result


def _hash_data(data: dict[str, Any]) -> str:
    """
    Compute hash of data payload for change detection.

    Uses efficient hashing based on shape and samples for DataFrames,
    avoiding full data serialization.

    Args:
        data: The data dict to hash

    Returns:
        SHA256 hash string
    """
    from ..preprocessing.filtering import (
        compute_dataframe_hash,
        compute_pandas_dataframe_hash,
    )

    hash_parts = []
    for key, value in sorted(data.items()):
        # Skip internal metadata but NOT dynamic annotation columns or pagination
        if (
            key.startswith("_")
            and not key.startswith("_dynamic")
            and not key.startswith("_pagination")
        ):
            continue
        if isinstance(value, pd.DataFrame):
            # Hash pandas directly. Converting to polars first crashes the interpreter
            # when two renders overlap -- see compute_pandas_dataframe_hash.
            hash_parts.append(f"{key}:{compute_pandas_dataframe_hash(value)}")
        elif isinstance(value, pl.DataFrame):
            hash_parts.append(f"{key}:{compute_dataframe_hash(value)}")
        elif isinstance(value, (list, dict)):
            # For small data, use string repr
            hash_parts.append(f"{key}:{hash(str(value)[:1000])}")
        else:
            hash_parts.append(f"{key}:{hash(str(value))}")

    return hashlib.sha256("|".join(hash_parts).encode()).hexdigest()
