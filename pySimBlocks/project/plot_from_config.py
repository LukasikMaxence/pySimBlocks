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

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import gridspec

from pySimBlocks.core.config import PlotConfig
from pySimBlocks.project.plot_series_helpers import (
    effective_style_for_component,
    flatten_series,
    is_manual_layout_plot,
    plot_step_series_styled,
    resolve_series_style,
    selection_from_panel_dict,
)


def _stack_logged_signal(logs: dict, sig: str) -> np.ndarray:
    """Stack a logged signal over time into a (T, m, n) array."""
    samples = logs[sig]
    if not isinstance(samples, list) or len(samples) == 0:
        raise ValueError(f"Signal '{sig}' has no samples in logs.")

    first = None
    for s in samples:
        if s is not None:
            first = np.asarray(s)
            break

    if first is None:
        raise ValueError(f"Signal '{sig}' is always None; cannot plot.")

    if first.ndim != 2:
        raise ValueError(f"Signal '{sig}' must be 2D. Got ndim={first.ndim} with shape {first.shape}.")

    shape0 = first.shape

    stacked = []
    for k, s in enumerate(samples):
        if s is None:
            raise ValueError(f"Signal '{sig}' contains None at index {k}; cannot plot.")
        a = np.asarray(s)
        if a.ndim != 2:
            raise ValueError(
                f"Signal '{sig}' sample {k} must be 2D. Got ndim={a.ndim} with shape {a.shape}."
            )
        if a.shape != shape0:
            raise ValueError(
                f"Signal '{sig}' shape changed over time: expected {shape0}, got {a.shape} at sample {k}."
            )
        stacked.append(a)

    data = np.stack(stacked, axis=0)
    return data


def _series_from_signal(logs: dict, sig: str) -> list[tuple[str, np.ndarray]]:
    """Return flat (label, values) series for one signal."""
    data = _stack_logged_signal(logs, sig)
    m, n = data.shape[1], data.shape[2]

    if (m, n) == (1, 1):
        return [(sig, data[:, 0, 0])]

    if n == 1:
        return [(f"{sig}[{i}]", data[:, i, 0]) for i in range(m)]

    return [(f"{sig}[{r},{c}]", data[:, r, c]) for r in range(m) for c in range(n)]


def _resolve_plot_mode(plot: dict, total_series: int, signal_count: int) -> str:
    """Resolve plot mode with safe defaults."""
    mode = str(plot.get("mode", "auto")).strip().lower()
    if mode in {"overlay", "split_signals", "split_components"}:
        return mode
    if mode != "auto":
        return "overlay"

    # split automatically when too many curves.
    if total_series > 6:
        return "split_components"
    if signal_count > 2:
        return "split_signals"
    return "overlay"


def _style_axes(ax: plt.Axes, title: str, show_legend: bool) -> None:
    """Apply consistent axis style."""
    ax.set_xlabel("Time [s]")
    ax.grid(True)
    if title:
        ax.set_title(title)
    if show_legend and ax.lines:
        ax.legend()


def _series_from_manual_panel(
    logs: dict,
    selection: dict[str, set[str]],
    time: np.ndarray,
) -> list[tuple[str, np.ndarray]]:
    """Build (label, values) series for one manual panel selection."""
    T = len(time)
    series: list[tuple[str, np.ndarray]] = []
    for sig in sorted(selection.keys()):
        data = _stack_logged_signal(logs, sig)
        if data.shape[0] != T:
            raise ValueError(
                f"Time length mismatch for '{sig}': time has {T} samples but signal has {data.shape[0]}."
            )
        m, n = data.shape[1], data.shape[2]
        if (m, n) == (1, 1):
            candidates = [(sig, data[:, 0, 0])]
        elif n == 1:
            candidates = [(f"{sig}[{i}]", data[:, i, 0]) for i in range(m)]
        else:
            candidates = [
                (f"{sig}[{r},{c}]", data[:, r, c]) for r in range(m) for c in range(n)
            ]
        selected_labels = selection[sig]
        for label, values in candidates:
            if label in selected_labels:
                series.append((label, values))
    return series


def _plot_manual_layout_figure(logs: dict, time: np.ndarray, plot: dict) -> None:
    """Render one figure for a ``layout: manual`` plot descriptor."""
    panels_raw = plot.get("panels")
    if not isinstance(panels_raw, list) or not panels_raw:
        return
    panel_blocks: list[tuple[str, list[tuple[str, np.ndarray]], dict]] = []
    for i, panel in enumerate(panels_raw):
        if not isinstance(panel, dict):
            continue
        ptitle = str(panel.get("title", f"Plot {i + 1}"))
        sel = selection_from_panel_dict(panel)
        if not sel:
            panel_blocks.append((ptitle, [], panel))
            continue
        try:
            ser = _series_from_manual_panel(logs, sel, time)
        except Exception:
            ser = []
        panel_blocks.append((ptitle, ser, panel))
    if not panel_blocks:
        return
    n_plots = len(panel_blocks)
    fig = plt.figure()
    if n_plots == 1:
        ptitle, series, panel = panel_blocks[0]
        ax = fig.add_subplot(111)
        if series:
            for label, values in series:
                st = effective_style_for_component(plot, panel, label)
                plot_step_series_styled(ax, time, values, label, st)
        else:
            ax.text(
                0.5,
                0.5,
                "No signals selected.",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )
        _style_axes(ax, str(plot.get("title", "")) or ptitle, True)
        fig.tight_layout()
        return
    n_rows = (n_plots + 1) // 2
    gs = gridspec.GridSpec(n_rows, 2, figure=fig)
    fig_title = str(plot.get("title", "") or "")
    for i, (ptitle, series, panel) in enumerate(panel_blocks):
        if i == n_plots - 1 and n_plots % 2 == 1:
            ax = fig.add_subplot(gs[i // 2, :])
        else:
            ax = fig.add_subplot(gs[i // 2, i % 2])
        if series:
            for label, values in series:
                st = effective_style_for_component(plot, panel, label)
                plot_step_series_styled(ax, time, values, label, st)
        else:
            ax.text(
                0.5,
                0.5,
                "No signals selected.",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )
        stitle = f"{fig_title} — {ptitle}" if fig_title else ptitle
        _style_axes(ax, stitle, True)
    fig.tight_layout()


def plot_from_config(
    logs: dict,
    plot_cfg: PlotConfig | None,
    show: bool = True,
    block: bool = True,
) -> None:
    """Plot logged simulation signals according to a :class:`PlotConfig`.

    Each signal component is plotted as a separate step curve. Labels follow
    the convention: scalar signals use ``sig``; column vector elements use
    ``sig[i]``; matrix elements use ``sig[r,c]``.

    Args:
        logs: Dictionary of logged signals as returned by
            :meth:`~Simulator.run`. Must contain a ``'time'`` key.
        plot_cfg: Plot configuration. If None, the function returns immediately
            without producing any figures.
        show: If True, call ``plt.show()`` after creating all figures.
        block: Passed to ``plt.show()``; controls whether the call blocks.

    Raises:
        KeyError: If any signal requested by ``plot_cfg`` was not logged, or
            if ``'time'`` is missing from ``logs``.
        ValueError: If any logged signal is not a list of 2D arrays with a
            consistent shape.
    """
    if plot_cfg is None:
        return

    requested_signals = set()
    for plot in plot_cfg.plots:
        if is_manual_layout_plot(plot):
            for panel in plot.get("panels") or []:
                if not isinstance(panel, dict):
                    continue
                sel = panel.get("selection")
                if isinstance(sel, dict):
                    requested_signals.update(str(k) for k in sel.keys())
            continue
        requested_signals.update(plot.get("signals") or [])

    available_signals = set(logs.keys())
    available_signals.discard("time")

    missing = sorted(requested_signals - available_signals)
    if missing:
        raise KeyError(
            "The following signals are requested for plotting but were not logged:\n"
            + "\n".join(f"  - {sig}" for sig in missing)
            + "\n\nAvailable logged signals:\n"
            + "\n".join(f"  - {sig}" for sig in sorted(available_signals))
        )

    if "time" not in logs:
        raise KeyError("Logs must contain a 'time' entry.")

    time = np.asarray(logs["time"]).flatten()
    T = len(time)
    if T == 0:
        return

    for plot in plot_cfg.plots:
        if is_manual_layout_plot(plot):
            _plot_manual_layout_figure(logs, time, plot)
            continue
        title = plot.get("title", "")
        signals = plot["signals"]
        series_by_signal: list[tuple[str, list[tuple[str, np.ndarray]]]] = []

        for sig in signals:
            data = _stack_logged_signal(logs, sig)
            if data.shape[0] != T:
                raise ValueError(
                    f"Time length mismatch for '{sig}': time has {T} samples but signal has {data.shape[0]}."
                )
            series_by_signal.append((sig, _series_from_signal(logs, sig)))

        flat_series = flatten_series(series_by_signal)
        mode = _resolve_plot_mode(plot, total_series=len(flat_series), signal_count=len(signals))
        session_styles: dict = {}

        if mode == "overlay":
            fig, ax = plt.subplots()
            for _, label, values in flat_series:
                style = resolve_series_style(label, session_styles, plot)
                plot_step_series_styled(ax, time, values, label, style)
            _style_axes(ax, title, show_legend=True)
            fig.tight_layout()
            continue

        if mode == "split_signals":
            fig, axes = plt.subplots(len(series_by_signal), 1, sharex=True, squeeze=False)
            axes_1d = axes.flatten()
            for i, (sig, sig_series) in enumerate(series_by_signal):
                ax = axes_1d[i]
                for label, values in sig_series:
                    style = resolve_series_style(label, session_styles, plot)
                    plot_step_series_styled(ax, time, values, label, style)
                panel_title = f"{title} - {sig}" if title else sig
                _style_axes(ax, panel_title, show_legend=True)
            fig.tight_layout()
            continue

        # split_components
        fig, axes = plt.subplots(len(flat_series), 1, sharex=True, squeeze=False)
        axes_1d = axes.flatten()
        for i, (_, label, values) in enumerate(flat_series):
            ax = axes_1d[i]
            style = resolve_series_style(label, session_styles, plot)
            plot_step_series_styled(ax, time, values, label, style)
            panel_title = f"{title} - {label}" if title else label
            _style_axes(ax, panel_title, show_legend=False)
        fig.tight_layout()

    if show:
        plt.show(block=block)
