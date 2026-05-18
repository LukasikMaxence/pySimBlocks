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

from pySimBlocks.project.plot_series_helpers import SeriesStyle, plot_step_series_styled


def plot_step_series(
    ax,
    time: np.ndarray,
    values: np.ndarray,
    label: str,
    style: SeriesStyle | None = None,
) -> None:
    """Draw one step series on ``ax`` using optional line/marker/color style."""
    plot_step_series_styled(ax, time, values, label, style)
