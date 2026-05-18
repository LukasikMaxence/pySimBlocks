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

from pySimBlocks.gui.dialogs.plot_series_style_dialog import (
    DEFAULT_SERIES_STYLE,
    SeriesStyle,
    normalize_plot_marker,
)


def plot_step_series(
    ax,
    time: np.ndarray,
    values: np.ndarray,
    label: str,
    style: SeriesStyle | None = None,
) -> None:
    """Draw one step series on ``ax`` using optional line/marker/color style."""
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
