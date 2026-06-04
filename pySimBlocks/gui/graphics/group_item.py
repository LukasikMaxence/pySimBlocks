# ******************************************************************************
#                                  pySimBlocks
#                     Copyright (c) 2026 Université de Lille & INRIA
# ******************************************************************************

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QStyle

from pySimBlocks.gui.models.visual_group import BoundaryPort, VisualGroup

if TYPE_CHECKING:
    from pySimBlocks.gui.widgets.diagram_view import DiagramView


class GroupBoundaryPortItem(QGraphicsItem):
    """Visual port on a group rectangle border."""

    R = 6
    L = 15
    H = 10

    def __init__(self, boundary: BoundaryPort, parent_group: "GroupItem"):
        super().__init__(parent_group)
        self.boundary = boundary
        self.parent_group = parent_group
        self.setAcceptedMouseButtons(Qt.LeftButton)

    @property
    def is_input(self) -> bool:
        return self.boundary.direction == "input"

    def connection_anchor(self) -> QPointF:
        if self.is_input:
            local = QPointF(-self.R, 0)
        else:
            local = QPointF(self.L, 0)
        return self.mapToScene(local)

    def boundingRect(self) -> QRectF:
        return QRectF(-10, -10, 20, 20)

    def paint(self, painter, option, widget=None):
        t = self.parent_group.view.theme
        painter.setRenderHint(QPainter.Antialiasing)
        fill = t.port_in if self.is_input else t.port_out
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(t.block_border, 1))
        if self.is_input:
            painter.drawEllipse(-self.R, -self.R, 2 * self.R, 2 * self.R)
        else:
            from PySide6.QtGui import QPainterPath

            path = QPainterPath()
            path.moveTo(0, -self.H)
            path.lineTo(0, self.H)
            path.lineTo(self.L, 0)
            path.closeSubpath()
            painter.drawPath(path)


class GroupItem(QGraphicsRectItem):
    """Render a visual group container on the diagram."""

    MIN_WIDTH = 80.0
    MIN_HEIGHT = 50.0
    MARGIN = 16.0

    def __init__(self, group: VisualGroup, view: "DiagramView"):
        layout = group.layout or {}
        width = max(float(layout.get("width", 160.0)), self.MIN_WIDTH)
        height = max(float(layout.get("height", 100.0)), self.MIN_HEIGHT)
        super().__init__(0, 0, width, height)
        self.group = group
        self.view = view
        self.boundary_port_items: dict[str, GroupBoundaryPortItem] = {}

        x = float(layout.get("x", 0.0))
        y = float(layout.get("y", 0.0))
        self.setPos(QPointF(x, y))
        self.setFlag(QGraphicsRectItem.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable)
        self.setFlag(QGraphicsRectItem.ItemSendsScenePositionChanges)
        self.setZValue(-1)
        self.sync_boundary_ports()

    def sync_boundary_ports(self) -> None:
        """Rebuild boundary port items from group metadata."""
        for item in list(self.boundary_port_items.values()):
            item.setParentItem(None)
        self.boundary_port_items.clear()

        inputs = [p for p in self.group.boundary_ports if p.direction == "input"]
        outputs = [p for p in self.group.boundary_ports if p.direction == "output"]
        rect = self.rect()

        for index, boundary in enumerate(inputs):
            item = GroupBoundaryPortItem(boundary, self)
            y = rect.height() * (index + 1) / (len(inputs) + 1)
            item.setPos(0, y)
            self.boundary_port_items[boundary.uid] = item

        for index, boundary in enumerate(outputs):
            item = GroupBoundaryPortItem(boundary, self)
            y = rect.height() * (index + 1) / (len(outputs) + 1)
            item.setPos(rect.width(), y)
            self.boundary_port_items[boundary.uid] = item

    def get_boundary_anchor(self, boundary_uid: str) -> QPointF | None:
        port_item = self.boundary_port_items.get(boundary_uid)
        if port_item is None:
            return None
        return port_item.connection_anchor()

    def find_boundary_for_member_port(self, block_uid: str, port_name: str) -> str | None:
        key = f"{block_uid}:{port_name}"
        for boundary in self.group.boundary_ports:
            if boundary.linked_port_uid == key:
                return boundary.uid
        return None

    def paint(self, painter, option, widget=None):
        t = self.view.theme
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(t.block_bg))
        pen = QPen(t.block_border, 2, Qt.DashLine)
        if option.state & QStyle.State_Selected:  # type: ignore[name-defined]
            pen.setColor(t.selection)
            pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(self.rect())

        painter.setPen(QPen(t.text))
        painter.setFont(QFont("Sans Serif", 9, QFont.Bold))
        painter.drawText(
            self.rect().adjusted(4, 4, -4, -4),
            int(Qt.AlignTop | Qt.AlignHCenter),
            self.group.name,
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.view.project_controller:
            self._persist_layout()
            self.view.on_group_moved(self)
        return super().itemChange(change, value)

    def _persist_layout(self) -> None:
        pos = self.pos()
        rect = self.rect()
        self.group.layout = {
            "x": float(pos.x()),
            "y": float(pos.y()),
            "width": float(rect.width()),
            "height": float(rect.height()),
        }
        if self.view.project_controller:
            self.view.project_controller.make_dirty()

    def mouseDoubleClickEvent(self, event):
        self.view.enter_group(self.group.uid)
        event.accept()
