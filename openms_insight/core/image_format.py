"""The format of the image downloads of every component.

Every component with an image download -- the Plotly plots, the 3D plot, the
sequence views and the structure view -- saves in one format: SVG by default,
or PNG, JPEG or WebP. An app picks it once with :func:`set_image_format`
(e.g. from a settings widget on every page run); a component's
``image_format`` argument overrides it for that component.

The format only changes what the download button does. It is a render-time
argument kept on the component and resolved when the component is drawn,
never part of its cache configuration, so changing it never rebuilds a cache.

Inside a Streamlit session the package default is kept per session (in
``st.session_state``), so two users of one app can pick different formats;
outside a session (scripts, tests) it is process wide.
"""

from typing import Any

IMAGE_FORMATS = ("svg", "png", "jpeg", "webp")
DEFAULT_IMAGE_FORMAT = "svg"

_SESSION_KEY = "_openms_insight_image_format"
_process_default = DEFAULT_IMAGE_FORMAT


def validate_image_format(image_format: Any, allow_none: bool = False) -> str | None:
    """
    Check an image format and return it in lower case.

    Args:
        image_format: One of 'svg', 'png', 'jpeg', 'webp' (any case).
        allow_none: Accept None (a component without an override).

    Raises:
        ValueError: For anything else.
    """
    if image_format is None and allow_none:
        return None
    if isinstance(image_format, str) and image_format.lower() in IMAGE_FORMATS:
        return image_format.lower()
    raise ValueError(
        f"image_format must be one of {', '.join(IMAGE_FORMATS)}, got {image_format!r}"
    )


def _session_state() -> Any:
    """st.session_state while a Streamlit script runs, else None."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True) is None:
            return None
        import streamlit as st

        return st.session_state
    except Exception:
        return None


def set_image_format(image_format: str) -> None:
    """
    Set the format of the image downloads of every component.

    Components without their own ``image_format`` use it the next time they
    are drawn. Call it before drawing them, e.g. on every page run with the
    value of a settings widget.

    Args:
        image_format: 'svg' (the default), 'png', 'jpeg' or 'webp'. PNG, JPEG
            and WebP are drawn at twice the size of the view on screen.

    Raises:
        ValueError: For any other value.
    """
    global _process_default
    validated = str(validate_image_format(image_format))
    session = _session_state()
    if session is not None:
        session[_SESSION_KEY] = validated
    else:
        _process_default = validated


def get_image_format() -> str:
    """The format set with :func:`set_image_format` ('svg' if none was set)."""
    session = _session_state()
    if session is not None and _SESSION_KEY in session:
        return str(session[_SESSION_KEY])
    return _process_default


def image_format_args(image_format: str | None) -> dict[str, str]:
    """
    Component args for the view.

    Args:
        image_format: The component's own format, or None for the package
            default at the time of the call (render time).

    Returns:
        ``{"imageFormat": <format>}``.
    """
    return {"imageFormat": image_format or get_image_format()}
