# ******************************************************************************
#                                  pySimBlocks
#                     Copyright (c) 2026 Université de Lille & INRIA
# ******************************************************************************

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF

from pySimBlocks.gui.models.block_instance import BlockInstance
from pySimBlocks.gui.models.visual_group import BoundaryPort, VisualGroup
from pySimBlocks.gui.undo_redo.commands import ConnectionSnapshot

if TYPE_CHECKING:
    from pySimBlocks.gui.graphics.block_item import BlockItem
    from pySimBlocks.gui.project_controller import ProjectController


@dataclass
class ClipboardBlock:
    """Serializable block data for copy/paste."""

    source_uid: str
    category: str
    block_type: str
    name: str
    parameters: dict[str, Any]
    layout: dict[str, Any]


@dataclass
class DiagramClipboard:
    """In-memory clipboard for diagram selections."""

    blocks: list[ClipboardBlock] = field(default_factory=list)
    connections: list[ConnectionSnapshot] = field(default_factory=list)
    group: dict[str, Any] | None = None
    anchor_x: float = 0.0
    anchor_y: float = 0.0


@dataclass
class PasteResult:
    """Entities created by a paste operation (for undo)."""

    blocks: list[BlockInstance] = field(default_factory=list)
    connections: list = field(default_factory=list)
    group_uids: list[str] = field(default_factory=list)


def _layout_anchor(layouts: list[dict[str, Any]]) -> tuple[float, float]:
    if not layouts:
        return 0.0, 0.0
    return (
        min(float(layout.get("x", 0.0)) for layout in layouts),
        min(float(layout.get("y", 0.0)) for layout in layouts),
    )


def _offset_layout(layout: dict[str, Any], dx: float, dy: float) -> dict[str, Any]:
    out = dict(layout)
    out["x"] = float(out.get("x", 0.0)) + dx
    out["y"] = float(out.get("y", 0.0)) + dy
    return out


def capture_blocks_clipboard(
    controller: ProjectController,
    block_items: list[BlockItem],
) -> DiagramClipboard | None:
    """Capture selected blocks and their internal connections."""
    if not block_items:
        return None

    member_uids = {item.instance.uid for item in block_items}
    blocks: list[ClipboardBlock] = []
    layouts: list[dict[str, Any]] = []

    for item in block_items:
        instance = item.instance
        layout = controller._capture_block_layout(instance)
        layouts.append(layout)
        blocks.append(
            ClipboardBlock(
                source_uid=instance.uid,
                category=instance.meta.category,
                block_type=instance.meta.type,
                name=instance.name,
                parameters=instance.parameters.copy(),
                layout=layout,
            )
        )

    connections: list[ConnectionSnapshot] = []
    for connection in controller.project_state.connections:
        src_uid = connection.src_block().uid
        dst_uid = connection.dst_block().uid
        if src_uid in member_uids and dst_uid in member_uids:
            connections.append(controller._capture_connection_snapshot(connection))

    anchor_x, anchor_y = _layout_anchor(layouts)
    return DiagramClipboard(
        blocks=blocks,
        connections=connections,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
    )


def capture_group_clipboard(
    controller: ProjectController,
    group: VisualGroup,
) -> DiagramClipboard | None:
    """Capture a visual group, its members, and internal connections."""
    block_items: list[BlockItem] = []
    layouts: list[dict[str, Any]] = []
    blocks: list[ClipboardBlock] = []

    for member_uid in group.members:
        block = controller._find_block_by_uid(member_uid)
        if block is None:
            continue
        layout = dict(group.member_layouts.get(member_uid, {}))
        if not layout:
            item = controller.view.get_block_item_from_instance(block)
            if item is not None:
                layout = controller._capture_block_layout(block)
        layouts.append(layout)
        blocks.append(
            ClipboardBlock(
                source_uid=block.uid,
                category=block.meta.category,
                block_type=block.meta.type,
                name=block.name,
                parameters=block.parameters.copy(),
                layout=layout,
            )
        )
        item = controller.view.get_block_item_from_instance(block)
        if item is not None:
            block_items.append(item)

    if not blocks:
        return None

    member_uids = {block.source_uid for block in blocks}
    connections: list[ConnectionSnapshot] = []
    for connection in controller.project_state.connections:
        src_uid = connection.src_block().uid
        dst_uid = connection.dst_block().uid
        if src_uid in member_uids and dst_uid in member_uids:
            connections.append(controller._capture_connection_snapshot(connection))

    group_layout = group.layout or {}
    anchor_x = float(group_layout.get("x", _layout_anchor(layouts)[0]))
    anchor_y = float(group_layout.get("y", _layout_anchor(layouts)[1]))

    return DiagramClipboard(
        blocks=blocks,
        connections=connections,
        group=copy.deepcopy(group.to_dict()),
        anchor_x=anchor_x,
        anchor_y=anchor_y,
    )


def capture_selection_clipboard(controller: ProjectController) -> DiagramClipboard | None:
    """Capture the current diagram selection for copy."""
    from pySimBlocks.gui.graphics.block_item import BlockItem
    from pySimBlocks.gui.graphics.group_item import GroupItem

    selected = controller.view.diagram_scene.selectedItems()
    groups = [item for item in selected if isinstance(item, GroupItem)]
    blocks = [item for item in selected if isinstance(item, BlockItem)]

    if len(groups) == 1 and not blocks:
        return capture_group_clipboard(controller, groups[0].group)
    if blocks:
        return capture_blocks_clipboard(controller, blocks)
    return None


def _remap_connection(
    snapshot: ConnectionSnapshot,
    uid_map: dict[str, str],
    dx: float = 0.0,
    dy: float = 0.0,
) -> ConnectionSnapshot | None:
    if snapshot.src_block_uid not in uid_map or snapshot.dst_block_uid not in uid_map:
        return None
    points: list[QPointF] | None = None
    if snapshot.points:
        points = [QPointF(point.x() + dx, point.y() + dy) for point in snapshot.points]
    return ConnectionSnapshot(
        src_block_uid=uid_map[snapshot.src_block_uid],
        src_port_name=snapshot.src_port_name,
        dst_block_uid=uid_map[snapshot.dst_block_uid],
        dst_port_name=snapshot.dst_port_name,
        points=points,
    )


def _duplicate_group(
    controller: ProjectController,
    template: dict[str, Any],
    uid_map: dict[str, str],
    dx: float,
    dy: float,
    parent_uid: str | None,
) -> VisualGroup:
    group = VisualGroup.from_dict(copy.deepcopy(template))
    group.uid = uuid.uuid4().hex
    group.name = controller._make_unique_group_name(group.name)
    group.parent_uid = parent_uid
    group.members = [uid_map[uid] for uid in template.get("members", []) if uid in uid_map]

    member_layouts: dict[str, dict[str, Any]] = {}
    for old_uid, layout in (template.get("member_layouts") or {}).items():
        if old_uid not in uid_map:
            continue
        member_layouts[uid_map[old_uid]] = dict(layout)
    group.member_layouts = member_layouts

    if group.layout:
        group.layout = _offset_layout(dict(group.layout), dx, dy)

    new_boundaries: list[BoundaryPort] = []
    for boundary in group.boundary_ports:
        remapped = BoundaryPort(
            uid=uuid.uuid4().hex,
            direction=boundary.direction,
            linked_port_uid="",
            external_port_uid="",
            origin=boundary.origin,
            linked_connection_uid="",
            label=boundary.label,
            proxy_uid=uuid.uuid4().hex,
            proxy_layout=dict(boundary.proxy_layout) if boundary.proxy_layout else {},
        )
        if boundary.linked_port_uid and ":" in boundary.linked_port_uid:
            old_uid, port_name = boundary.linked_port_uid.split(":", 1)
            if old_uid in uid_map:
                remapped.linked_port_uid = f"{uid_map[old_uid]}:{port_name}"
        new_boundaries.append(remapped)
    group.boundary_ports = new_boundaries

    controller.project_state.visual_groups.append(group)
    controller._rebuild_group_boundary_ports(group)
    controller.ensure_group_boundary_proxies(group)
    return group


def paste_clipboard(
    controller: ProjectController,
    clipboard: DiagramClipboard,
    origin: QPointF,
    *,
    parent_group_uid: str | None = None,
) -> PasteResult:
    """Paste clipboard contents at ``origin`` without pushing undo."""
    result = PasteResult()
    if not clipboard.blocks:
        return result

    dx = float(origin.x()) - clipboard.anchor_x
    dy = float(origin.y()) - clipboard.anchor_y
    uid_map: dict[str, str] = {}

    for block_data in clipboard.blocks:
        meta = controller.resolve_block_meta(block_data.category, block_data.block_type)
        block = BlockInstance(meta)
        block.parameters = block_data.parameters.copy()
        block.name = block_data.name
        if clipboard.group is not None:
            layout = dict(block_data.layout)
        else:
            layout = _offset_layout(block_data.layout, dx, dy)
        created = controller._add_block(block, layout)
        uid_map[block_data.source_uid] = created.uid
        result.blocks.append(created)
        if parent_group_uid is not None and clipboard.group is None:
            controller._add_member_to_group(parent_group_uid, created.uid, layout)

    for snapshot in clipboard.connections:
        remapped = _remap_connection(snapshot, uid_map, dx, dy)
        if remapped is None:
            continue
        connection = controller._add_connection_from_snapshot(remapped)
        if connection is not None:
            result.connections.append(connection)

    if clipboard.group is not None:
        group = _duplicate_group(
            controller,
            clipboard.group,
            uid_map,
            dx,
            dy,
            parent_group_uid,
        )
        result.group_uids.append(group.uid)

    controller.view.refresh_visual_groups()
    return result


def undo_paste(controller: ProjectController, result: PasteResult) -> None:
    """Remove entities created by a paste operation."""
    for group_uid in result.group_uids:
        if group_uid in controller.view.view_stack:
            controller.view.navigate_out_of_group(group_uid)
        controller._remove_visual_group(group_uid)

    for connection in list(result.connections):
        controller._remove_connection(connection, refresh_boundaries=False)

    for block in list(result.blocks):
        controller._remove_block(block)

    controller.view.refresh_visual_groups()
