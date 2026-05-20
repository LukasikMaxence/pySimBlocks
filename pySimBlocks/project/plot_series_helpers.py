# ******************************************************************************
#                                  pySimBlocks
#                     Copyright (c) 2026 Université de Lille & INRIA
# ******************************************************************************
#  This program is free software: you can redistribute it and/or modify it
#  under the terms of the GNU Lesser General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful, but WITHOUT
#  ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
#  FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License
#  for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ******************************************************************************
#  Authors: see Authors.txt
# ******************************************************************************

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle

DEFAULT_SERIES_STYLE: "SeriesStyle"

_SKIP_MARKERS = frozenset({"", " ", "None", "none"})


@dataclass
class SeriesStyle:
    """Matplotlib draw style for one logged series component."""

    color: str = ""
    linestyle: str = "-"
    marker: str = ""
    display_name: str = ""


DEFAULT_SERIES_STYLE = SeriesStyle()


def normalize_marker_code(marker: object) -> str:
    """Return a stripped marker code string, or empty for no marker."""
    if marker is None:
        return ""
    text = str(marker).strip()
    if not text or text.lower() in _SKIP_MARKERS:
        return ""
    return text


def is_usable_line_marker(marker: object) -> bool:
    """True if matplotlib can draw this marker on a Line2D (step/plot)."""
    code = normalize_marker_code(marker)
    if not code:
        return False
    try:
        Line2D([0], [0], marker=code)
        return True
    except (ValueError, TypeError):
        return False


def normalize_plot_marker(marker: object) -> str:
    """Return marker code for plotting, or '' if missing or not supported on lines."""
    code = normalize_marker_code(marker)
    if not code:
        return ""
    return code if is_usable_line_marker(code) else ""


def series_style_to_dict(style: SeriesStyle) -> dict[str, str]:
    """Serialize a series style, omitting default fields."""
    data: dict[str, str] = {}
    if style.color:
        data["color"] = style.color
    if style.linestyle and style.linestyle != "-":
        data["linestyle"] = style.linestyle
    marker = normalize_plot_marker(style.marker)
    if marker:
        data["marker"] = marker
    if style.display_name.strip():
        data["display_name"] = style.display_name.strip()
    return data


def series_style_from_dict(data: dict[str, Any] | None) -> SeriesStyle:
    """Build a :class:`SeriesStyle` from a YAML/plot-config mapping."""
    if not isinstance(data, dict):
        return SeriesStyle()
    return SeriesStyle(
        color=str(data.get("color", "") or ""),
        linestyle=str(data.get("linestyle", "-") or "-"),
        marker=str(data.get("marker", "") or ""),
        display_name=str(data.get("display_name", "") or ""),
    )


def merge_series_styles(primary: SeriesStyle, fallback: SeriesStyle) -> SeriesStyle:
    """Merge two styles; non-empty fields in ``primary`` override ``fallback``."""
    return SeriesStyle(
        color=primary.color or fallback.color,
        linestyle=primary.linestyle or fallback.linestyle,
        marker=primary.marker or fallback.marker,
        display_name=primary.display_name or fallback.display_name,
    )


def resolve_series_style(
    label: str,
    session_styles: dict[str, SeriesStyle],
    plot: dict | None = None,
) -> SeriesStyle:
    """Merge plot-config styles with in-session overrides (session wins)."""
    from_plot = series_style_from_dict((plot or {}).get("series_styles", {}).get(label))
    session = session_styles.get(label)
    if session is None:
        return from_plot
    return merge_series_styles(session, from_plot)


def effective_style_for_component(
    plot: dict | None,
    panel: dict | None,
    label: str,
) -> SeriesStyle:
    """Style for one component label: panel ``series_styles`` overrides plot-level."""
    plot = plot or {}
    panel = panel or {}
    base = series_style_from_dict(plot.get("series_styles", {}).get(label))
    override = series_style_from_dict(panel.get("series_styles", {}).get(label))
    return merge_series_styles(override, base)


def filter_series_by_signal(
    series_by_signal: list[tuple[str, list[tuple[str, np.ndarray]]]],
    components: list[str] | None,
) -> list[tuple[str, list[tuple[str, np.ndarray]]]]:
    """Keep only component labels listed in ``components`` (if provided)."""
    if not components:
        return series_by_signal
    allowed = set(components)
    filtered: list[tuple[str, list[tuple[str, np.ndarray]]]] = []
    for sig, sig_series in series_by_signal:
        kept = [(label, values) for label, values in sig_series if label in allowed]
        if kept:
            filtered.append((sig, kept))
    return filtered


def flatten_series(
    series_by_signal: list[tuple[str, list[tuple[str, np.ndarray]]]],
) -> list[tuple[str, str, np.ndarray]]:
    """Flatten grouped series into (signal, label, values) tuples."""
    return [
        (sig, label, values)
        for sig, sig_series in series_by_signal
        for label, values in sig_series
    ]


def plot_step_series_styled(
    ax,
    time: np.ndarray,
    values: np.ndarray,
    label: str,
    style: SeriesStyle | None = None,
) -> None:
    """Draw one step series with optional style (shared by GUI and plot_from_config)."""
    st = style or DEFAULT_SERIES_STYLE
    legend = st.display_name.strip() if st.display_name.strip() else label
    kwargs: dict = {"where": "post", "label": legend}
    if st.color:
        kwargs["color"] = st.color
    if st.linestyle:
        kwargs["linestyle"] = st.linestyle
    marker = normalize_plot_marker(st.marker)
    if marker:
        kwargs["marker"] = marker
    ax.step(time, values, **kwargs)


MANUAL_LAYOUT_KEY = "manual"


def is_manual_layout_plot(plot: dict) -> bool:
    """Return True if ``plot`` is a saved multi-panel manual layout preset."""
    return str(plot.get("layout", "")).strip().lower() == MANUAL_LAYOUT_KEY


def panel_dict_from_selection(
    title: str,
    selection: dict[str, set[str]],
    series_styles: dict[str, SeriesStyle] | None = None,
) -> dict[str, Any]:
    """Serialize one manual panel for YAML storage."""
    out: dict[str, Any] = {
        "title": title.strip() or "Plot",
        "selection": {sig: sorted(labels) for sig, labels in selection.items()},
    }
    if not series_styles:
        return out
    serialized: dict[str, dict[str, str]] = {}
    for lbl, st in series_styles.items():
        data = series_style_to_dict(st)
        if data:
            serialized[str(lbl)] = data
    if serialized:
        out["series_styles"] = serialized
    return out


def selection_from_panel_dict(panel: dict) -> dict[str, set[str]]:
    """Restore one manual panel selection from YAML."""
    raw = panel.get("selection")
    if isinstance(raw, dict):
        return {str(sig): {str(lbl) for lbl in labels} for sig, labels in raw.items() if labels}
    signals = panel.get("signals", [])
    components = panel.get("components", [])
    if not isinstance(signals, list) or not isinstance(components, list):
        return {}
    selection: dict[str, set[str]] = {str(sig): set() for sig in signals}
    for comp in components:
        comp_s = str(comp)
        for sig in selection:
            if comp_s == sig or comp_s.startswith(f"{sig}["):
                selection[sig].add(comp_s)
                break
    return {sig: labels for sig, labels in selection.items() if labels}


def manual_layout_to_plot_dict(
    preset_title: str,
    panel_titles: list[str],
    panel_selections: list[dict[str, set[str]]],
    panel_styles: list[dict[str, SeriesStyle]],
) -> dict[str, Any] | None:
    """Build one plot preset that stores a full manual multi-panel layout.

    Each entry in ``panel_styles`` holds styles for component labels in that
    panel only (name, color, etc. may differ per panel for the same signal).
    """
    panels: list[dict[str, Any]] = []
    for i, (title, selection) in enumerate(zip(panel_titles, panel_selections)):
        if not selection:
            continue
        ps = panel_styles[i] if i < len(panel_styles) else {}
        picked: dict[str, SeriesStyle] = {}
        for labels in selection.values():
            for lbl in labels:
                sl = str(lbl)
                if sl in ps:
                    picked[sl] = ps[sl]
        panels.append(panel_dict_from_selection(title, selection, picked))
    if not panels:
        return None
    return {
        "title": preset_title.strip() or "Manual layout",
        "layout": MANUAL_LAYOUT_KEY,
        "panels": panels,
    }


def manual_state_from_layout_plot(
    plot: dict,
) -> tuple[list[dict[str, set[str]]], list[str], list[dict[str, SeriesStyle]]]:
    """Extract manual panel state from a layout preset.

    Returns one style map per panel (merged plot-level + panel-level YAML).
    """
    panels_raw = plot.get("panels", [])
    selections: list[dict[str, set[str]]] = []
    titles: list[str] = []
    per_panel_styles: list[dict[str, SeriesStyle]] = []
    if isinstance(panels_raw, list):
        for i, panel in enumerate(panels_raw):
            if not isinstance(panel, dict):
                continue
            titles.append(str(panel.get("title", f"Plot {i + 1}")))
            sel = selection_from_panel_dict(panel)
            selections.append(sel)
            merged: dict[str, SeriesStyle] = {}
            for labels in sel.values():
                for lbl in labels:
                    sl = str(lbl)
                    merged[sl] = effective_style_for_component(plot, panel, sl)
            per_panel_styles.append(merged)
    return selections, titles, per_panel_styles
