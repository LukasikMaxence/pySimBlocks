# ******************************************************************************
#                                  pySimBlocks
#                     Copyright (c) 2026 Université de Lille & INRIA
# ******************************************************************************

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QStyle

from pySimBlocks.gui.models.visual_group import BoundaryPort

if TYPE_CHECKING:
    from pySimBlocks.gui.widgets.diagram_view import DiagramView


class GroupProxyPortItem(QGraphicsItem):
    """Single connection anchor on a GroupIn / GroupOut proxy block."""

    R = 6
    L = 15
    H = 10

    def __init__(self, is_output: bool, parent_proxy: "GroupProxyItem"):
        super().__init__(parent_proxy)
        self.is_output = is_output
        self.parent_proxy = parent_proxy

    def connection_anchor(self) -> QPointF:
        if self.is_output:
            local = QPointF(self.L, 0)
        else:
            local = QPointF(-self.R, 0)
        return self.mapToScene(local)

    def boundingRect(self) -> QRectF:
        return QRectF(-12, -12, 24, 24)

    def paint(self, painter, option, widget=None):
        t = self.parent_proxy.view.theme
        painter.setRenderHint(QPainter.Antialiasing)
        fill = t.port_out if self.is_output else t.port_in
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(t.block_border, 1))
        if self.is_output:
            path = QPainterPath()
            path.moveTo(0, -self.H)
            path.lineTo(0, self.H)
            path.lineTo(self.L, 0)
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.drawEllipse(-self.R, -self.R, 2 * self.R, 2 * self.R)


class GroupProxyItem(QGraphicsRectItem):
    """Render a GroupIn or GroupOut proxy inside a visual group."""

    WIDTH = 56.0
    HEIGHT = 36.0
    GRID_DX = 5
    GRID_DY = 5

    def __init__(self, boundary: BoundaryPort, view: "DiagramView"):
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)
        self.boundary = boundary
        self.view = view
        if self.is_group_in:
            self.external_port = GroupProxyPortItem(is_output=False, parent_proxy=self)
            self.member_port = GroupProxyPortItem(is_output=True, parent_proxy=self)
        else:
            self.member_port = GroupProxyPortItem(is_output=False, parent_proxy=self)
            self.external_port = GroupProxyPortItem(is_output=True, parent_proxy=self)

        rect = self.rect()
        mid_y = rect.height() / 2
        if self.is_group_in:
            self.external_port.setPos(0, mid_y)
            self.member_port.setPos(rect.width(), mid_y)
        else:
            self.member_port.setPos(0, mid_y)
            self.external_port.setPos(rect.width(), mid_y)

        layout = boundary.proxy_layout or {}
        self.setPos(QPointF(float(layout.get("x", 0.0)), float(layout.get("y", 0.0))))
        self.setFlag(QGraphicsRectItem.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable)
        self.setFlag(QGraphicsRectItem.ItemSendsScenePositionChanges)
        self.setZValue(0)
        self._interaction_start_pos: QPointF | None = None

    @property
    def is_group_in(self) -> bool:
        return self.boundary.direction == "input"

    @property
    def is_group_out(self) -> bool:
        return self.boundary.direction == "output"

    @property
    def label(self) -> str:
        return "In" if self.is_group_in else "Out"

    def member_anchor(self) -> QPointF:
        """Anchor facing group members (GroupIn out, GroupOut in)."""
        return self.member_port.connection_anchor()

    def external_anchor(self) -> QPointF:
        """Anchor facing the parent diagram (GroupIn in, GroupOut out)."""
        return self.external_port.connection_anchor()

    def paint(self, painter, option, widget=None):
        t = self.view.theme
        selected = bool(option.state & QStyle.State_Selected)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(t.block_bg_selected if selected else t.block_bg))
        painter.setPen(QPen(t.block_border_selected if selected else t.block_border, 2))
        painter.drawRect(self.rect())
        painter.setPen(QPen(t.text_selected if selected else t.text))
        painter.setFont(QFont("Sans Serif", 8, QFont.Bold))
        painter.drawText(self.rect(), int(Qt.AlignCenter), self.label)

    def mousePressEvent(self, event):
        self._interaction_start_pos = QPointF(self.pos())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        start_pos = self._interaction_start_pos
        end_pos = QPointF(self.pos())
        self._interaction_start_pos = None
        super().mouseReleaseEvent(event)
        if (
            start_pos is not None
            and start_pos != end_pos
            and self.view.project_controller is not None
            and self.view.current_view_group_uid is not None
        ):
            self.view.project_controller.execute_move_proxy_layout(
                self.view.current_view_group_uid,
                self.boundary.uid,
                start_pos,
                end_pos,
            )

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            x = round(value.x() / self.GRID_DX) * self.GRID_DX
            y = round(value.y() / self.GRID_DY) * self.GRID_DY
            return QPointF(x, y)

        if change == QGraphicsItem.ItemPositionHasChanged and self.view.project_controller:
            pos = self.pos()
            self.boundary.proxy_layout = {
                "x": float(pos.x()),
                "y": float(pos.y()),
            }
            self.view.on_proxy_moved(self)

        return super().itemChange(change, value)
