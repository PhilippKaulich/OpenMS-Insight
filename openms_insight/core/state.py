"""State management for cross-component selection synchronization."""

import contextvars
import logging
import os
from typing import Any, Optional

import numpy as np

# Debug logging for state sync issues
_DEBUG_STATE_SYNC = os.environ.get("SVC_DEBUG_STATE", "").lower() == "true"
_logger = logging.getLogger(__name__)

# Module-level default state manager
_default_state_manager: Optional["StateManager"] = None


def get_default_state_manager() -> "StateManager":
    """
    Get or create the default shared StateManager.

    Returns:
        The default StateManager instance
    """
    global _default_state_manager
    if _default_state_manager is None:
        _default_state_manager = StateManager()
    return _default_state_manager


# The StateManager of the component being rendered (set by render_component).
# A context variable, not an attribute of the component, so a component object
# shared between sessions cannot write into another session's state.
_render_state_manager: contextvars.ContextVar[Optional["StateManager"]] = (
    contextvars.ContextVar("openms_insight_render_state_manager", default=None)
)


def get_render_state_manager() -> "StateManager":
    """StateManager of the render in progress, else the default one."""
    return _render_state_manager.get() or get_default_state_manager()


def reset_default_state_manager() -> None:
    """Reset the default state manager (useful for testing)."""
    global _default_state_manager
    _default_state_manager = None


class StateManager:
    """
    Manages selection state across components with conflict resolution.

    Features:
        - Counter-based conflict resolution to handle concurrent updates
        - Session ID for multi-tab/session safety
        - Streamlit session_state integration
        - Support for arbitrary selection identifiers

    The StateManager maintains a dict of selections keyed by identifier names.
    When a component updates a selection, all components sharing that identifier
    will see the new value on the next render.
    """

    def __init__(self, session_key: str = "svc_state"):
        """
        Initialize the StateManager.

        Args:
            session_key: Key to use in Streamlit session_state for storing
                state. Use different keys for independent component groups.
        """
        self._session_key = session_key
        self._ensure_session_state()

    def _is_pagination_identifier(self, identifier: str) -> bool:
        """Check if identifier is for pagination state (ends with '_page')."""
        return identifier.endswith("_page")

    def _ensure_session_state(self) -> None:
        """Ensure session state is initialized."""
        import streamlit as st

        if self._session_key not in st.session_state:
            st.session_state[self._session_key] = {
                "selection_counter": 0,
                "pagination_counter": 0,
                "id": float(np.random.random()),
                "selections": {},
            }
        # Migration: add new counter keys if missing (backwards compat)
        state = st.session_state[self._session_key]
        if "selection_counter" not in state:
            # Migrate from legacy single counter
            legacy_counter = state.get("counter", 0)
            state["selection_counter"] = legacy_counter
            state["pagination_counter"] = legacy_counter

    @property
    def _state(self) -> dict[str, Any]:
        """Get the internal state dict from session_state."""
        import streamlit as st

        self._ensure_session_state()
        return st.session_state[self._session_key]

    @property
    def session_id(self) -> float:
        """Get the unique session ID."""
        return self._state["id"]

    @property
    def selection_counter(self) -> int:
        """Get the current selection counter."""
        return self._state["selection_counter"]

    @property
    def pagination_counter(self) -> int:
        """Get the current pagination counter."""
        return self._state["pagination_counter"]

    @property
    def counter(self) -> int:
        """Get the current state counter (backwards compatibility)."""
        return max(self._state["selection_counter"], self._state["pagination_counter"])

    def get_selection(self, identifier: str) -> Any:
        """
        Get current selection value for an identifier.

        Args:
            identifier: The selection identifier name

        Returns:
            The current selection value, or None if not set
        """
        return self._state["selections"].get(identifier)

    def set_selection(self, identifier: str, value: Any) -> bool:
        """
        Set selection value for an identifier.

        Args:
            identifier: The selection identifier name
            value: The value to set

        Returns:
            True if the value changed, False otherwise
        """
        current = self._state["selections"].get(identifier)
        if current == value:
            return False

        self._state["selections"][identifier] = value
        if self._is_pagination_identifier(identifier):
            self._state["pagination_counter"] += 1
        else:
            self._state["selection_counter"] += 1
        return True

    def clear_selection(self, identifier: str) -> bool:
        """
        Clear selection for an identifier.

        Args:
            identifier: The selection identifier name

        Returns:
            True if a selection was cleared, False if it wasn't set
        """
        if identifier in self._state["selections"]:
            del self._state["selections"][identifier]
            if self._is_pagination_identifier(identifier):
                self._state["pagination_counter"] += 1
            else:
                self._state["selection_counter"] += 1
            return True
        return False

    def get_all_selections(self) -> dict[str, Any]:
        """
        Get all current selections.

        Returns:
            Dict mapping identifiers to their selected values
        """
        return self._state["selections"].copy()

    def get_state_for_vue(self) -> dict[str, Any]:
        """
        Get state dict formatted for sending to Vue component.

        Returns:
            Dict with counters, id, and all selections as top-level keys
        """
        state = {
            "selection_counter": self._state["selection_counter"],
            "pagination_counter": self._state["pagination_counter"],
            # Backwards compatibility: include legacy counter as max of both
            "counter": max(
                self._state["selection_counter"], self._state["pagination_counter"]
            ),
            "id": self._state["id"],
        }
        state.update(self._state["selections"])
        return state

    def update_from_vue(self, vue_state: dict[str, Any]) -> bool:
        """
        Update state from Vue component return value.

        Uses counter-based conflict resolution with separate counters for
        selection and pagination state. This prevents rapid pagination clicks
        from causing legitimate selection updates to be rejected.

        Args:
            vue_state: State dict returned by Vue component

        Returns:
            True if state was modified, False otherwise
        """
        if vue_state is None:
            return False

        # Verify same session (prevents cross-tab interference)
        if vue_state.get("id") != self._state["id"]:
            if _DEBUG_STATE_SYNC:
                _logger.warning(
                    f"[StateManager] Session mismatch: vue_id={vue_state.get('id')}, "
                    f"python_id={self._state['id']}"
                )
            return False

        # Extract metadata - support both new separate counters and legacy single counter
        vue_selection_counter = vue_state.pop("selection_counter", None)
        vue_pagination_counter = vue_state.pop("pagination_counter", None)
        vue_legacy_counter = vue_state.pop("counter", 0)
        vue_state.pop("id", None)

        # Backwards compat: if Vue doesn't send separate counters, use legacy
        if vue_selection_counter is None:
            vue_selection_counter = vue_legacy_counter
        if vue_pagination_counter is None:
            vue_pagination_counter = vue_legacy_counter

        old_selection_counter = self._state["selection_counter"]
        old_pagination_counter = self._state["pagination_counter"]

        # Debug: log pagination state updates
        if _DEBUG_STATE_SYNC:
            pagination_keys = [
                k
                for k in vue_state.keys()
                if "page" in k.lower() and not k.startswith("_")
            ]
            for pk in pagination_keys:
                old_val = self._state["selections"].get(pk)
                new_val = vue_state.get(pk)
                _logger.warning(
                    f"[StateManager] Pagination update: key={pk}, "
                    f"old={old_val}, new={new_val}, "
                    f"vue_pagination_counter={vue_pagination_counter}, "
                    f"python_pagination_counter={old_pagination_counter}"
                )

        # Filter out internal keys (starting with _)
        vue_state = {k: v for k, v in vue_state.items() if not k.startswith("_")}

        modified = False
        selection_modified = False
        pagination_modified = False

        # Always accept previously undefined keys (but skip None/undefined values)
        for key, value in vue_state.items():
            if key not in self._state["selections"]:
                # Only add if value is not None (undefined in Vue = no selection)
                if value is not None:
                    self._state["selections"][key] = value
                    modified = True
                    if self._is_pagination_identifier(key):
                        pagination_modified = True
                    else:
                        selection_modified = True
                    if _DEBUG_STATE_SYNC:
                        _logger.warning(
                            f"[StateManager] NEW KEY: {key}={value} "
                            f"(is_pagination={self._is_pagination_identifier(key)})"
                        )

        # For existing keys, check appropriate counter for conflict resolution
        for key, value in vue_state.items():
            if key in self._state["selections"]:
                old_val = self._state["selections"][key]
                if old_val != value:
                    # Use appropriate counter based on key type
                    is_pagination = self._is_pagination_identifier(key)
                    if is_pagination:
                        vue_counter = vue_pagination_counter
                        python_counter = old_pagination_counter
                    else:
                        vue_counter = vue_selection_counter
                        python_counter = old_selection_counter

                    # Only accept update if Vue has newer state for this type
                    if vue_counter >= python_counter:
                        self._state["selections"][key] = value
                        modified = True
                        if is_pagination:
                            pagination_modified = True
                        else:
                            selection_modified = True
                        if _DEBUG_STATE_SYNC:
                            _logger.warning(
                                f"[StateManager] UPDATE: {key}: {old_val} → {value} "
                                f"(vue_counter={vue_counter} >= python_counter={python_counter}, "
                                f"is_pagination={is_pagination})"
                            )

        # Update appropriate counter(s) if modified
        if selection_modified:
            self._state["selection_counter"] = max(
                self._state["selection_counter"] + 1, vue_selection_counter + 1
            )
        if pagination_modified:
            self._state["pagination_counter"] = max(
                self._state["pagination_counter"] + 1, vue_pagination_counter + 1
            )

        if _DEBUG_STATE_SYNC:
            _logger.warning(
                f"[StateManager] modified={modified}, "
                f"selection_counter: {old_selection_counter} → {self._state['selection_counter']}, "
                f"pagination_counter: {old_pagination_counter} → {self._state['pagination_counter']}"
            )

        return modified

    def clear(self) -> None:
        """Clear all selections and reset counters."""
        self._state["selections"] = {}
        self._state["selection_counter"] = 0
        self._state["pagination_counter"] = 0

    def __repr__(self) -> str:
        return (
            f"StateManager(session_key='{self._session_key}', "
            f"counter={self.counter}, "
            f"selections={self.get_all_selections()})"
        )
