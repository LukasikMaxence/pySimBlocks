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

from pySimBlocks.core.config import PlotConfig


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

    # Simulink-like readability: split automatically when too many curves.
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
        requested_signals.update(plot["signals"])

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

        flat_series = [
            (sig, label, values)
            for sig, sig_series in series_by_signal
            for label, values in sig_series
        ]
        mode = _resolve_plot_mode(plot, total_series=len(flat_series), signal_count=len(signals))

        if mode == "overlay":
            fig, ax = plt.subplots()
            for _, label, values in flat_series:
                ax.step(time, values, where="post", label=label)
            _style_axes(ax, title, show_legend=True)
            fig.tight_layout()
            continue

        if mode == "split_signals":
            fig, axes = plt.subplots(len(series_by_signal), 1, sharex=True, squeeze=False)
            axes_1d = axes.flatten()
            for i, (sig, sig_series) in enumerate(series_by_signal):
                ax = axes_1d[i]
                for label, values in sig_series:
                    ax.step(time, values, where="post", label=label)
                panel_title = f"{title} - {sig}" if title else sig
                _style_axes(ax, panel_title, show_legend=True)
            fig.tight_layout()
            continue

        # split_components
        fig, axes = plt.subplots(len(flat_series), 1, sharex=True, squeeze=False)
        axes_1d = axes.flatten()
        for i, (_, label, values) in enumerate(flat_series):
            ax = axes_1d[i]
            ax.step(time, values, where="post", label=label)
            panel_title = f"{title} - {label}" if title else label
            _style_axes(ax, panel_title, show_legend=False)
        fig.tight_layout()

    if show:
        plt.show(block=block)
