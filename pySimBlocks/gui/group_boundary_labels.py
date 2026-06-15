# ******************************************************************************
#                                  pySimBlocks
#                     Copyright (c) 2026 Université de Lille & INRIA
# ******************************************************************************

from __future__ import annotations

from pySimBlocks.gui.services.group_boundary_service import find_port
from pySimBlocks.gui.models.visual_group import BoundaryPort, VisualGroup


def _port_display(port) -> str:
    return str(port.display_as or port.name)


def boundary_port_label(
    state: ProjectState,
    group: VisualGroup,
    boundary: BoundaryPort,
) -> str:
    """Return the flow label for a group boundary port.

    Input boundaries show the external source port (where the signal comes from).
    Output boundaries show the external destination port (where the signal goes).
    """
    if boundary.origin == "manual" and not boundary.linked_connection_uid:
        external = find_port(state, boundary.external_port_uid)
        if external is not None:
            return _port_display(external)

    linked = boundary.linked_port_uid
    if not linked or ":" not in linked:
        return ""
    member_uid, member_port_name = linked.split(":", 1)
    members = set(group.members)
    for connection in state.connections:
        external_port = _external_port_for_boundary(
            connection, members, boundary.direction, member_uid, member_port_name
        )
        if external_port is not None:
            return _port_display(external_port)
    return ""


def _external_port_for_boundary(
    connection: ConnectionInstance,
    members: set[str],
    direction: str,
    member_uid: str,
    member_port_name: str,
):
    if direction == "input":
        if (
            connection.dst_block().uid == member_uid
            and connection.dst_port.name == member_port_name
            and connection.src_block().uid not in members
        ):
            return connection.src_port
    elif (
        connection.src_block().uid == member_uid
        and connection.src_port.name == member_port_name
        and connection.dst_block().uid not in members
    ):
        return connection.dst_port
    return None
