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
from copy import copy
from functools import lru_cache

from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle

from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QColorDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


@dataclass
class SeriesStyle:
    """Matplotlib draw style for one logged series component."""

    color: str = ""
    linestyle: str = "-"
    marker: str = ""
    display_name: str = ""


DEFAULT_SERIES_STYLE = SeriesStyle()

_SKIP_MARKERS = frozenset({"", " ", "None", "none"})


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


def marker_display_label(marker: str) -> str:
    """Human-readable marker name for the combo box (matplotlib registry description)."""
    desc = MarkerStyle.markers.get(marker)
    if isinstance(desc, str) and desc:
        return desc
    return str(marker)


def marker_from_display_name(name: str) -> str:
    """Resolve a display name (or symbol) back to a matplotlib marker code."""
    text = name.strip()
    if not text or text.lower() == "none":
        return ""
    _, name_to_symbol = matplotlib_marker_maps()
    key = text.lower()
    if key in name_to_symbol:
        return name_to_symbol[key]
    return normalize_plot_marker(text)


@lru_cache(maxsize=1)
def matplotlib_marker_maps() -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Build combo options and a lookup from display name / symbol to marker code."""
    options: list[tuple[str, str]] = [("None", "")]
    name_to_symbol: dict[str, str] = {"none": ""}
    labels_seen: dict[str, int] = {}

    for marker in sorted(MarkerStyle.markers.keys(), key=lambda m: (len(str(m)), str(m).lower())):
        symbol = normalize_marker_code(marker)
        if not symbol or not is_usable_line_marker(symbol):
            continue
        label = marker_display_label(symbol)
        count = labels_seen.get(label, 0)
        labels_seen[label] = count + 1
        if count > 0:
            label = f"{label} ({symbol!r})"
        options.append((label, symbol))
        name_to_symbol[label.lower()] = symbol
        name_to_symbol[symbol.lower()] = symbol
        desc = MarkerStyle.markers.get(marker)
        if isinstance(desc, str) and desc:
            name_to_symbol[desc.lower()] = symbol

    return options, name_to_symbol


def matplotlib_marker_options() -> list[tuple[str, str]]:
    """Return (label, marker) pairs for line-plot markers only."""
    return matplotlib_marker_maps()[0]


LINESTYLE_OPTIONS: list[tuple[str, str]] = [
    ("Solid", "-"),
    ("Dashed", "--"),
    ("Dash-dot", "-."),
    ("Dotted", ":"),
]

COLOR_OPTIONS: list[tuple[str, str]] = [
    ("Auto", ""),
    ("Blue", "#1f77b4"),
    ("Orange", "#ff7f0e"),
    ("Green", "#2ca02c"),
    ("Red", "#d62728"),
    ("Purple", "#9467bd"),
    ("Brown", "#8c564b"),
    ("Pink", "#e377c2"),
    ("Gray", "#7f7f7f"),
    ("Olive", "#bcbd22"),
    ("Cyan", "#17becf"),
    ("Black", "#000000"),
]


class SeriesStyleDialog(QDialog):
    """Dialog to edit marker, linestyle, and color for one series."""

    def __init__(self, series_label: str, style: SeriesStyle, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Series style - {series_label}")
        self._style = copy(style)
        self._custom_color = style.color if style.color and not self._is_preset_color(style.color) else ""

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"<b>Signal</b> (logged): <code>{series_label}</code>"))
        layout.addWidget(QLabel("<b>Legend name</b> (empty = default label in plot)"))
        self.display_name_edit = QLineEdit()
        self.display_name_edit.setText(style.display_name)
        self.display_name_edit.setPlaceholderText(series_label)
        self.display_name_edit.setToolTip(
            "Name shown in the legend and on curves. Leave empty to use the logged signal label."
        )
        layout.addWidget(self.display_name_edit)

        layout.addWidget(QLabel("<b>Marker</b> (None = no markers on the step curve)"))
        self.marker_combo = QComboBox()
        self.marker_combo.setEditable(True)
        self.marker_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.marker_combo.setMaxVisibleItems(20)
        for label, value in matplotlib_marker_options():
            self.marker_combo.addItem(label, value)
        completer = QCompleter([self.marker_combo.itemText(i) for i in range(self.marker_combo.count())])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.marker_combo.setCompleter(completer)
        self._set_marker_combo(self._style.marker)
        layout.addWidget(self.marker_combo)

        layout.addWidget(QLabel("<b>Line style</b>"))
        self.linestyle_combo = QComboBox()
        for label, value in LINESTYLE_OPTIONS:
            self.linestyle_combo.addItem(label, value)
        self._set_combo_by_data(self.linestyle_combo, self._style.linestyle)
        layout.addWidget(self.linestyle_combo)

        layout.addWidget(QLabel("<b>Color</b>"))
        color_row = QHBoxLayout()
        self.color_combo = QComboBox()
        for label, value in COLOR_OPTIONS:
            self.color_combo.addItem(label, value)
        if self._style.color and self._is_preset_color(self._style.color):
            self._set_combo_by_data(self.color_combo, self._style.color)
        else:
            self.color_combo.setCurrentIndex(0)
        self.color_combo.currentIndexChanged.connect(self._on_preset_color_changed)
        color_row.addWidget(self.color_combo, 1)

        self.custom_color_btn = QPushButton("Custom color…")
        self.custom_color_btn.clicked.connect(self._pick_custom_color)
        color_row.addWidget(self.custom_color_btn)
        layout.addLayout(color_row)

        self.color_preview = QLabel()
        self.color_preview.setFixedHeight(24)
        layout.addWidget(self.color_preview)
        self._update_color_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _is_preset_color(color: str) -> bool:
        return any(value == color for _, value in COLOR_OPTIONS if value)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _set_marker_combo(self, marker: str) -> None:
        """Select a marker in the combo, adding it if not in the matplotlib registry list."""
        if not marker:
            self._set_combo_by_data(self.marker_combo, "")
            return
        idx = self.marker_combo.findData(marker)
        if idx >= 0:
            self.marker_combo.setCurrentIndex(idx)
            return
        code = normalize_plot_marker(marker)
        if not code:
            self._set_combo_by_data(self.marker_combo, "")
            return
        label = marker_display_label(code)
        self.marker_combo.addItem(label, code)
        self.marker_combo.setCurrentIndex(self.marker_combo.count() - 1)

    def _marker_from_combo(self) -> str:
        """Read the marker code from the marker combo."""
        data = self.marker_combo.currentData()
        if data is not None:
            return normalize_plot_marker(data)
        return marker_from_display_name(self.marker_combo.currentText())

    def _resolved_color(self) -> str:
        if self._custom_color:
            return self._custom_color
        data = self.color_combo.currentData()
        return str(data) if data else ""

    def _on_preset_color_changed(self) -> None:
        self._custom_color = ""
        self._update_color_preview()

    def _pick_custom_color(self) -> None:
        initial = QColor(self._custom_color or self._resolved_color() or "#1f77b4")
        color = QColorDialog.getColor(initial, self, "Series color")
        if not color.isValid():
            return
        self._custom_color = color.name()
        self.color_combo.blockSignals(True)
        self.color_combo.setCurrentIndex(0)
        self.color_combo.blockSignals(False)
        self._update_color_preview()

    def _update_color_preview(self) -> None:
        resolved = self._resolved_color()
        if not resolved:
            self.color_preview.setText("Preview: automatic color (matplotlib cycle)")
            self.color_preview.setStyleSheet("background: palette(base); border: 1px solid palette(mid);")
            return
        self.color_preview.setText(f"Preview: {resolved}")
        self.color_preview.setStyleSheet(
            f"background-color: {resolved}; border: 1px solid palette(mid); color: white;"
        )

    def style(self) -> SeriesStyle:
        """Return the style edited in this dialog."""
        linestyle = self.linestyle_combo.currentData()
        return SeriesStyle(
            color=self._resolved_color(),
            linestyle=str(linestyle) if linestyle is not None else "-",
            marker=self._marker_from_combo(),
            display_name=self.display_name_edit.text().strip(),
        )
