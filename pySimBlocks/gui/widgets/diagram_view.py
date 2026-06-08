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

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QMenu

from pySimBlocks.gui.graphics.block_item import BlockItem
from pySimBlocks.gui.graphics.group_item import GroupItem
from pySimBlocks.gui.graphics.group_proxy_item import GroupProxyItem
from pySimBlocks.gui.graphics.connection_item import ConnectionItem, OrthogonalRoute
from pySimBlocks.gui.graphics.port_item import PortItem
from pySimBlocks.gui.graphics.theme import make_theme
from pySimBlocks.gui.group_ports import GROUP_IN_TYPE, GROUP_OUT_TYPE, GROUP_PORTS_CATEGORY
from pySimBlocks.gui.models.block_instance import BlockInstance
from pySimBlocks.gui.models.connection_instance import ConnectionInstance

if TYPE_CHECKING:
    from pySimBlocks.gui.project_controller import ProjectController


class DiagramView(QGraphicsView):
    """Interactive Qt graphics view for the block diagram canvas."""

    group_view_changed = Signal()

    def __init__(self):
        """Initialize the diagram view and configure scene behavior.

        Args:
            None.

        Raises:
            None.
        """
        super().__init__()
        self.diagram_scene = QGraphicsScene(self)
        self.setScene(self.diagram_scene)
        self.setAcceptDrops(True)

        self.setRenderHint(QPainter.Antialiasing)
        self.theme = make_theme()
        self.diagram_scene.setBackgroundBrush(self.theme.scene_bg)
        hints = QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(self._on_color_scheme_changed)
        app = QGuiApplication.instance()
        if hasattr(app, "paletteChanged"):
            app.paletteChanged.connect(lambda *_: QTimer.singleShot(0, self._apply_theme_from_system))
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        self.pending_port: PortItem | None = None
        self.temp_connection: ConnectionItem | None = None
        self.copied_block: BlockItem | None = None
        self.drop_event_pos: QPointF = QPointF(0, 0)
        self.project_controller: ProjectController | None
        self.block_items: dict[str, BlockItem] = {}
        self.group_items: dict[str, GroupItem] = {}
        self.proxy_items: dict[str, GroupProxyItem] = {}
        self.connections: dict[ConnectionInstance, ConnectionItem] = {}
        self.current_view_group_uid: str | None = None

        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.RubberBandDrag)

    # --------------------------------------------------------------------------
    # Public Methods
    # --------------------------------------------------------------------------

    def add_block(
        self,
        block_instance: BlockInstance,
        block_layout: dict[str, Any] | None = None,
    ) -> None:
        """Add a visual block item to the scene for the given block instance.

        Args:
            block_instance: The block model to represent visually.
            block_layout: Optional dict with position/size hints.
        """
        block_item = BlockItem(block_instance, self.drop_event_pos, self, block_layout)
        self.diagram_scene.addItem(block_item)
        self.block_items[block_instance.uid] = block_item

    def refresh_block_port(self, block_instance: BlockInstance) -> None:
        """Refresh the port visuals of the block item for the given instance.

        Args:
            block_instance: The block whose port items should be refreshed.
        """
        block_item = self.get_block_item_from_instance(block_instance)
        if block_item:
            block_item.refresh_ports()

    def remove_block(self, block_instance: BlockInstance) -> None:
        """Remove the visual block item for the given instance from the scene.

        Args:
            block_instance: The block whose visual item should be removed.
        """
        block_item = self.block_items[block_instance.uid]
        self.diagram_scene.removeItem(block_item)
        self.block_items.pop(block_instance.uid, None)

    def add_connection(
        self,
        connection_instance: ConnectionInstance,
        points: list[QPointF] | None = None,
    ) -> None:
        """Add a visual wire to the scene for the given connection instance.

        Args:
            connection_instance: The connection model to represent visually.
            points: Optional list of intermediate waypoints for the wire.
        """
        src_port_item = self.get_block_item_from_instance(connection_instance.src_block()).get_port_item(connection_instance.src_port.name)
        dst_port_item = self.get_block_item_from_instance(connection_instance.dst_block()).get_port_item(connection_instance.dst_port.name)
        connection_item = ConnectionItem(
            src_port_item, dst_port_item, connection_instance, points
        )
        self.connections[connection_instance] = connection_item
        self.diagram_scene.addItem(connection_item)

    def remove_connection(self, connection_instance: ConnectionInstance) -> None:
        """Remove the visual wire for the given connection instance from the scene.

        Args:
            connection_instance: The connection whose visual item should be removed.
        """
        connection_item = self.connections.pop(connection_instance, None)
        if connection_item:
            self.diagram_scene.removeItem(connection_item)

    def get_selected_block_instances(self) -> list[BlockInstance]:
        """Return block instances currently selected on the diagram."""
        selected = []
        for item in self.diagram_scene.selectedItems():
            if isinstance(item, BlockItem):
                selected.append(item.instance)
        return selected

    def get_selected_group_uid(self) -> str | None:
        """Return the UID of a selected group item, if any."""
        for item in self.diagram_scene.selectedItems():
            if isinstance(item, GroupItem):
                return item.group.uid
        return None

    def refresh_visual_groups(self) -> None:
        """Sync group items, member visibility, and connection display."""
        if self.project_controller is None:
            return

        state = self.project_controller.project_state
        all_member_uids: set[str] = set()
        for group in state.visual_groups:
            all_member_uids.update(group.members)

        active_uid = self.current_view_group_uid
        active_group = state.get_visual_group(active_uid) if active_uid else None

        known_group_uids = {g.uid for g in state.visual_groups}
        for uid in list(self.group_items.keys()):
            if uid not in known_group_uids:
                item = self.group_items.pop(uid)
                self.diagram_scene.removeItem(item)

        for group in state.visual_groups:
            item = self.group_items.get(group.uid)
            if item is None:
                item = GroupItem(group, self)
                self.diagram_scene.addItem(item)
                self.group_items[group.uid] = item
            else:
                item.group = group
                if group.layout:
                    item.apply_geometry(
                        QPointF(
                            float(group.layout.get("x", 0.0)),
                            float(group.layout.get("y", 0.0)),
                        ),
                        QRectF(
                            0,
                            0,
                            float(group.layout.get("width", 160.0)),
                            float(group.layout.get("height", 100.0)),
                        ),
                    )
                else:
                    item.sync_boundary_ports()

        if active_group is None:
            for block_uid, block_item in self.block_items.items():
                block_item.setVisible(block_uid not in all_member_uids)
            for group_uid, group_item in self.group_items.items():
                group_item.setVisible(True)
        else:
            member_set = set(active_group.members)
            for block_uid, block_item in self.block_items.items():
                block_item.setVisible(block_uid in member_set)
            for group_uid, group_item in self.group_items.items():
                group_item.setVisible(group_uid != active_group.uid)

        for conn_inst, conn_item in self.connections.items():
            src_uid = conn_inst.src_block().uid
            dst_uid = conn_inst.dst_block().uid

            if active_group is None:
                src_in = src_uid in all_member_uids
                dst_in = dst_uid in all_member_uids
                visible = not (src_in and dst_in)
            else:
                members = set(active_group.members)
                src_in = src_uid in members
                dst_in = dst_uid in members
                visible = src_in and dst_in or (src_in ^ dst_in)

            conn_item.setVisible(visible)
            if visible:
                conn_item.update_position()

        self._refresh_group_proxies(active_group)

    def _refresh_group_proxies(self, active_group) -> None:
        """Create or hide GroupIn/GroupOut proxy items for the active internal view."""
        if active_group is None:
            for item in self.proxy_items.values():
                item.setVisible(False)
            return

        active_boundary_uids = {boundary.uid for boundary in active_group.boundary_ports}
        for uid in list(self.proxy_items.keys()):
            if uid not in active_boundary_uids:
                item = self.proxy_items.pop(uid)
                self.diagram_scene.removeItem(item)

        for boundary in active_group.boundary_ports:
            item = self.proxy_items.get(boundary.uid)
            if item is None:
                item = GroupProxyItem(boundary, self)
                self.diagram_scene.addItem(item)
                self.proxy_items[boundary.uid] = item
            else:
                item.boundary = boundary
                if boundary.proxy_layout:
                    item.setPos(
                        QPointF(
                            float(boundary.proxy_layout.get("x", 0.0)),
                            float(boundary.proxy_layout.get("y", 0.0)),
                        )
                    )
            item.setVisible(True)

    def connection_anchor_for_port_item(self, port_item: PortItem) -> QPointF:
        """Return the scene anchor for a port, redirecting through group borders when collapsed."""
        block_uid = port_item.instance.block.uid
        port_name = port_item.instance.name

        active_uid = self.current_view_group_uid
        if active_uid and self.project_controller is not None:
            group = self.project_controller.project_state.get_visual_group(active_uid)
            if group is not None:
                external_anchor = self._proxy_anchor_for_external_port(group, port_item)
                if external_anchor is not None:
                    return external_anchor
            return port_item.connection_anchor()

        for group_item in self.group_items.values():
            if block_uid not in group_item.group.members:
                continue
            boundary_uid = group_item.find_boundary_for_member_port(block_uid, port_name)
            if boundary_uid is None:
                break
            anchor = group_item.get_boundary_anchor(boundary_uid)
            if anchor is not None:
                return anchor

        return port_item.connection_anchor()

    def _proxy_anchor_for_external_port(self, group, port_item: PortItem) -> QPointF | None:
        """In internal view, attach crossing wires to GroupIn/GroupOut proxies."""
        if self.project_controller is None:
            return None

        members = set(group.members)
        port_instance = port_item.instance
        for connection in self.project_controller.project_state.connections:
            if connection.src_port is not port_instance and connection.dst_port is not port_instance:
                continue

            src_uid = connection.src_block().uid
            dst_uid = connection.dst_block().uid
            src_in = src_uid in members
            dst_in = dst_uid in members
            if src_in == dst_in:
                continue

            if dst_in:
                member_uid, member_port_name = dst_uid, connection.dst_port.name
                external_port = connection.src_port
            else:
                member_uid, member_port_name = src_uid, connection.src_port.name
                external_port = connection.dst_port

            if external_port is not port_instance:
                continue

            linked_key = f"{member_uid}:{member_port_name}"
            for boundary in group.boundary_ports:
                if boundary.linked_port_uid != linked_key:
                    continue
                proxy = self.proxy_items.get(boundary.uid)
                if proxy is None:
                    return None
                return proxy.external_anchor()
        return None

    def on_proxy_moved(self, _proxy_item: GroupProxyItem) -> None:
        """Refresh wires after a group proxy is moved."""
        for conn_item in self.connections.values():
            conn_item.update_position()

    def on_connection_route_edited(
        self,
        connection_item: ConnectionItem,
        old_points: list[QPointF] | None,
        new_points: list[QPointF] | None,
    ) -> None:
        """Record a manual wire route edit on the undo/redo stack."""
        if self.project_controller is not None:
            self.project_controller.execute_edit_connection_route(
                connection_item.instance,
                old_points,
                new_points,
            )
        connection_item.update_position()

    def enter_group(self, group_uid: str) -> None:
        """Open the internal view of a visual group."""
        if self.project_controller is None:
            return
        group = self.project_controller.project_state.get_visual_group(group_uid)
        if group is None:
            return
        if self.current_view_group_uid and self.current_view_group_uid != group_uid:
            self._save_active_group_view_state()
        self.project_controller.ensure_group_boundary_proxies(group)
        self.current_view_group_uid = group_uid
        self.refresh_visual_groups()
        self.project_controller.apply_member_layouts(group)
        self.group_view_changed.emit()

    def exit_group_view(self) -> None:
        """Return to the root diagram view."""
        self._save_active_group_view_state()
        self.current_view_group_uid = None
        self.refresh_visual_groups()
        self.group_view_changed.emit()

    def _save_active_group_view_state(self) -> None:
        """Persist block and proxy positions for the active internal group view."""
        if self.project_controller is None or self.current_view_group_uid is None:
            return
        group = self.project_controller.project_state.get_visual_group(
            self.current_view_group_uid
        )
        if group is None:
            return
        self.project_controller.save_member_layouts(group)
        self.project_controller.save_proxy_layouts(group)

    def on_group_moved(self, group_item: GroupItem) -> None:
        """Refresh wires after a group container is moved."""
        for conn_inst, conn_item in self.connections.items():
            conn_item.update_position()

    def get_block_item_from_instance(self, block_instance: BlockInstance) -> BlockItem | None:
        """Return the visual BlockItem for the given block instance, or None.

        Args:
            block_instance: The block model to look up.

        Returns:
            The corresponding :class:`BlockItem`, or ``None`` if not found.
        """
        return self.block_items.get(block_instance.uid)

    def create_connection_event(self, port: PortItem) -> None:
        """Begin a wire-drag interaction from the given port item.

        Args:
            port: The port item from which the connection is being drawn.
        """
        if not self.pending_port:
            self.pending_port = port
            self.temp_connection = ConnectionItem(self.pending_port, None, None)
            self.diagram_scene.addItem(self.temp_connection)
            return

    def update_block_param_event(self, block_instance: BlockInstance, params: dict[str, Any]) -> None:
        """Delegate a parameter update for the given block to the project controller.

        Args:
            block_instance: The block to update.
            params: New parameter dict to apply.
        """
        self.project_controller.update_block_param(block_instance, params)

    def on_block_moved(self, block_item: BlockItem) -> None:
        """Mark the project dirty and refresh all wires connected to the moved block.

        Args:
            block_item: The block item that was repositioned.
        """
        if self.current_view_group_uid and self.project_controller is not None:
            group = self.project_controller.project_state.get_visual_group(
                self.current_view_group_uid
            )
            if (
                group is not None
                and block_item.instance.uid in group.members
            ):
                group.member_layouts[block_item.instance.uid] = (
                    self.project_controller._capture_block_layout(block_item.instance)
                )
        for conn_inst, conn_item in self.connections.items():
            if conn_inst.is_block_involved(block_item.instance):
                conn_item.update_position()

    def on_block_ports_refreshed(self, block_item: BlockItem) -> None:
        """Refresh all wire positions after the ports of a block have been updated.

        Args:
            block_item: The block item whose ports were refreshed.
        """
        for conn_inst, conn_item in self.connections.items():
            if conn_inst.is_block_involved(block_item.instance):
                conn_item.update_position()

    def dragEnterEvent(self, event) -> None:
        """Accept drag events that carry text MIME data.

        Args:
            event: Qt drag-enter event.
        """
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        """Accept proposed drag-move actions unconditionally.

        Args:
            event: Qt drag-move event.
        """
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        """Handle a block drop by adding the corresponding block to the project.

        Args:
            event: Qt drop event carrying ``"category:block_type"`` text.
        """
        self.drop_event_pos = self.mapToScene(event.position().toPoint())
        category, block_type = event.mimeData().text().split(":")
        if category == GROUP_PORTS_CATEGORY:
            if self.current_view_group_uid is None or self.project_controller is None:
                return
            direction = "input" if block_type == GROUP_IN_TYPE else "output"
            self.project_controller.add_manual_boundary_port(
                self.current_view_group_uid,
                direction,
                self.drop_event_pos,
            )
        else:
            self.project_controller.add_block(category, block_type)
        event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:
        """Handle keyboard shortcuts for copy, paste, delete, zoom, rotate, and center.

        Args:
            event: Qt key-press event.
        """
        # UNDO / REDO
        if event.matches(QKeySequence.Undo):
            self.project_controller.undo_manager.undo()
            event.accept()
            return
        if event.matches(QKeySequence.Redo):
            self.project_controller.undo_manager.redo()
            event.accept()
            return
        if (
            event.key() == Qt.Key_Z
            and event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)
        ):
            self.project_controller.undo_manager.redo()
            event.accept()
            return

        # COPY
        if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            selected = [i for i in self.diagram_scene.selectedItems() if isinstance(i, BlockItem)]
            if selected:
                self.copied_block = selected[0]
            return

        # PASTE
        if event.key() == Qt.Key_V and event.modifiers() & Qt.ControlModifier:
            if self.copied_block:
                self.drop_event_pos = self.copied_block.pos() + QPointF(30, 30)
                self.project_controller.add_copy_block(self.copied_block.instance)
            return

        # DELETE
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            return

        # ZOOM IN / OUT
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal) and event.modifiers() & Qt.ControlModifier:
            self.scale_view(1.15)
            return

        if event.key() == Qt.Key_Minus and event.modifiers() & Qt.ControlModifier:
            self.scale_view(1 / 1.15)
            return

        # GROUP / UNGROUP
        if (
            event.key() == Qt.Key_G
            and event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)
        ):
            self.project_controller.group_selected_blocks()
            event.accept()
            return
        if (
            event.key() == Qt.Key_U
            and event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)
        ):
            self.project_controller.ungroup_selected_group()
            event.accept()
            return

        if event.key() == Qt.Key_Escape and self.current_view_group_uid is not None:
            self.exit_group_view()
            event.accept()
            return

        # ROTATE BLOCK
        if event.key() == Qt.Key_R and event.modifiers() & Qt.ControlModifier:
            selected = [i for i in self.diagram_scene.selectedItems()
                        if isinstance(i, BlockItem)]
            for item in selected:
                self.project_controller.execute_toggle_orientation(item.instance)
            return

        # CENTER VIEW
        if event.key() == Qt.Key_Space and not event.modifiers():
            self._center_on_diagram()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        """Zoom the view when Ctrl is held, otherwise scroll normally.

        Args:
            event: Qt wheel event.
        """
        if event.modifiers() & Qt.ControlModifier:
            zoom_factor = 1.15
            if event.angleDelta().y() > 0:
                self.scale_view(zoom_factor)
            else:
                self.scale_view(1 / zoom_factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Update the temporary wire endpoint while dragging from a port.

        Args:
            event: Qt mouse-move event.
        """
        if self.temp_connection:
            pos = self.mapToScene(event.position().toPoint())
            self.temp_connection.update_temp_position(pos)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Complete or cancel a wire drag on mouse release.

        Args:
            event: Qt mouse-release event.
        """
        if not self.pending_port:
            super().mouseReleaseEvent(event)
            return

        pos = self.mapToScene(event.position().toPoint())
        items = self.diagram_scene.items(pos)
        port = next((i for i in items if isinstance(i, PortItem)), None)
        if not port:
            self._cancel_temp_connection()
            return

        self.project_controller.add_connection(self.pending_port.instance, port.instance)
        self._cancel_temp_connection()

    def contextMenuEvent(self, event) -> None:
        """Show diagram context menu for grouping actions."""
        if self.project_controller is None:
            super().contextMenuEvent(event)
            return

        menu = QMenu(self)
        selected_blocks = self.get_selected_block_instances()
        selected_group_uid = self.get_selected_group_uid()

        group_action = menu.addAction("Group")
        group_action.setEnabled(len(selected_blocks) >= 2)
        group_action.triggered.connect(self.project_controller.group_selected_blocks)

        ungroup_action = menu.addAction("Ungroup")
        ungroup_action.setEnabled(selected_group_uid is not None)
        if selected_group_uid is not None:
            ungroup_action.triggered.connect(
                lambda: self.project_controller.ungroup(selected_group_uid)
            )

        if self.current_view_group_uid is not None:
            exit_action = menu.addAction("Go up")
            exit_action.triggered.connect(self.exit_group_view)
            add_in = menu.addAction("Add input")
            add_in.triggered.connect(self._add_manual_group_input)
            add_out = menu.addAction("Add output")
            add_out.triggered.connect(self._add_manual_group_output)

        menu.exec(event.globalPos())

    def delete_selected(self) -> None:
        """Remove all selected blocks and connections from the project."""
        selected_items = list(self.diagram_scene.selectedItems())
        if not selected_items:
            return
        self.project_controller.begin_macro("Delete Selection")
        try:
            for item in selected_items:
                if isinstance(item, GroupItem):
                    self.project_controller.ungroup(item.group.uid)
                elif isinstance(item, BlockItem):
                    self.project_controller.remove_block(item.instance)
                elif isinstance(item, ConnectionItem):
                    self.project_controller.remove_connection(item.instance)
        finally:
            self.project_controller.end_macro()

    def clear_scene(self) -> None:
        """Remove all blocks and connections from the scene and reset state."""
        self.diagram_scene.clear()
        self.block_items.clear()
        self.group_items.clear()
        self.proxy_items.clear()
        self.connections.clear()
        self.current_view_group_uid = None
        self.temp_connection = None
        self.pending_port = None

    def scale_view(self, factor: float) -> None:
        """Scale the view by ``factor``, clamped to the allowed zoom range.

        Args:
            factor: Multiplicative zoom factor to apply.
        """
        current_scale = self.transform().m11()
        min_scale, max_scale = 0.2, 5.0

        new_scale = current_scale * factor
        if min_scale <= new_scale <= max_scale:
            self.scale(factor, factor)


    # --------------------------------------------------------------------------
    # Private Methods
    # --------------------------------------------------------------------------

    def _cancel_temp_connection(self) -> None:
        """Remove the temporary wire and reset the pending-port state."""
        self.diagram_scene.removeItem(self.temp_connection)
        self.temp_connection = None
        self.pending_port = None

    def _on_color_scheme_changed(self, *_) -> None:
        """Schedule a theme refresh after the system colour scheme changes."""
        QTimer.singleShot(0, self._apply_theme_from_system)

    def _apply_theme_from_system(self) -> None:
        """Reload the theme and repaint all scene items to match the system palette."""
        self.theme = make_theme()
        self.diagram_scene.setBackgroundBrush(self.theme.scene_bg)
        self._refresh_theme_items()
        self.viewport().update()
        self.diagram_scene.update()

    def _refresh_theme_items(self) -> None:
        """Update colours on all block and connection items to match the current theme."""
        for block in self.block_items.values():
            block.update()
            for port in block.port_items:
                port.label.setDefaultTextColor(self.theme.text)
                port.update()

        for conn in self.connections.values():
            conn.setPen(QPen(self.theme.wire, 2))
            conn.update_position()
            conn.update()

        for group in self.group_items.values():
            group.update()

        for proxy in self.proxy_items.values():
            proxy.update()

    def _add_manual_group_input(self) -> None:
        self._add_manual_group_boundary("input")

    def _add_manual_group_output(self) -> None:
        self._add_manual_group_boundary("output")

    def _add_manual_group_boundary(self, direction: str) -> None:
        if self.project_controller is None or self.current_view_group_uid is None:
            return
        origin = self.mapToScene(self.viewport().rect().center())
        self.project_controller.add_manual_boundary_port(
            self.current_view_group_uid,
            direction,
            origin,
        )

    def _center_on_diagram(self) -> None:
        """Fit the view to the bounding rect of all scene items with a small margin."""
        scene = self.diagram_scene
        items_rect = scene.itemsBoundingRect()

        if items_rect.isNull():
            return

        # Un peu de marge pour éviter que ça colle aux bords
        margin = 40
        items_rect.adjust(-margin, -margin, margin, margin)

        scene.setSceneRect(items_rect)
        self.fitInView(items_rect, Qt.KeepAspectRatio)
