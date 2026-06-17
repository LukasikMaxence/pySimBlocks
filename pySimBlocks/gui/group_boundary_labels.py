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
    """Return the internal member-port label for a group boundary port."""
    if boundary.label.strip():
        return boundary.label.strip()
    linked = boundary.linked_port_uid
    if not linked:
        return ""
    internal = find_port(state, linked)
    if internal is None:
        return ""
    return _port_display(internal)
