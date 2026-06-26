from pySimBlocks.gui.main_window import MainWindow


def _create_window(qtbot, tmp_path):
    window = MainWindow(tmp_path)
    window.confirm_discard_or_save = lambda _action_name: True
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.isVisible())
    return window


def _first_port(block, direction: str):
    for port in block.ports:
        if port.direction == direction:
            return port
    raise AssertionError(f"No {direction} port on {block.name}")


def _select_items(view, *items):
    view.diagram_scene.clearSelection()
    for item in items:
        item.setSelected(True)


def test_group_block_with_existing_subgroup(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    controller = window.project_controller
    view = window.view

    a = controller.add_block("sources", "constant")
    b = controller.add_block("operators", "gain")
    c = controller.add_block("operators", "sum")
    inner = controller.group_blocks([a, b], name="Inner")

    assert inner is not None
    parent = controller.group_blocks(
        [c],
        child_group_uids=[inner.uid],
        name="Outer",
    )

    assert parent is not None
    assert parent.parent_uid is None
    assert inner.parent_uid == parent.uid
    assert parent.child_group_uids == [inner.uid]
    assert set(parent.members) == {c.uid}


def test_nested_group_visibility_at_root_and_inside_parent(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    controller = window.project_controller
    view = window.view

    a = controller.add_block("sources", "constant")
    b = controller.add_block("operators", "gain")
    c = controller.add_block("operators", "sum")
    inner = controller.group_blocks([a, b], name="Inner")
    parent = controller.group_blocks([c], child_group_uids=[inner.uid], name="Outer")

    view.refresh_visual_groups()
    assert view.get_block_item_from_instance(a).isVisible() is False
    assert view.group_items[inner.uid].isVisible() is False
    assert view.group_items[parent.uid].isVisible() is True

    view.enter_group(parent.uid)
    assert view.get_block_item_from_instance(c).isVisible() is True
    assert view.get_block_item_from_instance(a).isVisible() is False
    assert view.group_items[inner.uid].isVisible() is True


def test_group_selected_block_and_subgroup_from_context_menu(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    controller = window.project_controller
    view = window.view

    a = controller.add_block("sources", "constant")
    b = controller.add_block("operators", "gain")
    c = controller.add_block("operators", "sum")
    inner = controller.group_blocks([a, b], name="Inner")

    _select_items(
        view,
        view.get_block_item_from_instance(c),
        view.group_items[inner.uid],
    )
    controller.group_selected_blocks()

    outer = next(
        group
        for group in controller.project_state.visual_groups
        if group.uid != inner.uid
    )
    assert outer.child_group_uids == [inner.uid]
    assert inner.parent_uid == outer.uid


def test_ungroup_parent_promotes_child_groups(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    controller = window.project_controller

    a = controller.add_block("sources", "constant")
    b = controller.add_block("operators", "gain")
    c = controller.add_block("operators", "sum")
    inner = controller.group_blocks([a, b], name="Inner")
    parent = controller.group_blocks([c], child_group_uids=[inner.uid], name="Outer")

    assert controller.ungroup(parent.uid)
    promoted = controller.project_state.get_visual_group(inner.uid)
    assert promoted is not None
    assert promoted.parent_uid is None
    assert controller.project_state.get_visual_group(parent.uid) is None


def test_create_subgroup_inside_parent_view(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    controller = window.project_controller
    view = window.view

    a = controller.add_block("sources", "constant")
    b = controller.add_block("operators", "gain")
    c = controller.add_block("operators", "sum")
    parent = controller.group_blocks([a, b, c], name="Parent")
    view.enter_group(parent.uid)

    child = controller.group_blocks([a, b], name="Child", parent_uid=parent.uid)

    assert child is not None
    assert child.parent_uid == parent.uid
    assert child.uid in parent.child_group_uids
    assert set(parent.members) == {c.uid}
    assert set(child.members) == {a.uid, b.uid}


def test_cross_group_connection_visible_at_root(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    controller = window.project_controller
    view = window.view

    a = controller.add_block("sources", "constant")
    b = controller.add_block("operators", "gain")
    c = controller.add_block("operators", "sum")
    d = controller.add_block("operators", "gain")
    controller.group_blocks([a, b], name="GroupA")
    controller.group_blocks([c, d], name="GroupB")

    controller.add_connection(_first_port(b, "output"), _first_port(c, "input"))
    view.refresh_visual_groups()

    connection = next(iter(controller.project_state.connections))
    assert view.connections[connection].isVisible() is True


def test_cross_child_connection_visible_inside_parent(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    controller = window.project_controller
    view = window.view

    a = controller.add_block("sources", "constant")
    b = controller.add_block("operators", "gain")
    c = controller.add_block("operators", "sum")
    d = controller.add_block("operators", "gain")
    inner_a = controller.group_blocks([a, b], name="InnerA")
    inner_b = controller.group_blocks([c, d], name="InnerB")
    parent = controller.group_blocks(
        [],
        child_group_uids=[inner_a.uid, inner_b.uid],
        name="Parent",
    )
    assert parent is not None

    controller.add_connection(_first_port(b, "output"), _first_port(c, "input"))
    view.refresh_visual_groups()

    connection = next(iter(controller.project_state.connections))
    conn_item = view.connections[connection]
    assert conn_item.isVisible() is False

    view.enter_group(parent.uid)
    view.refresh_visual_groups()
    assert conn_item.isVisible() is True


def test_delete_group_removes_nested_members_and_child_groups(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    controller = window.project_controller

    sum_err = controller.add_block("operators", "sum")
    controller_block = controller.add_block("controllers", "state_feedback")
    sum_plant = controller.add_block("operators", "sum")
    system = controller.add_block("systems", "linear_state_space")
    regulator = controller.group_blocks([sum_err, controller_block], name="Regulator")
    plant = controller.group_blocks([sum_plant, system], name="Plant")
    control_loop = controller.group_blocks(
        [],
        child_group_uids=[regulator.uid, plant.uid],
        name="ControlLoop",
    )
    assert control_loop is not None

    member_uids = {
        sum_err.uid,
        controller_block.uid,
        sum_plant.uid,
        system.uid,
    }
    assert controller.delete_group(control_loop.uid)

    assert controller.project_state.get_visual_group(control_loop.uid) is None
    assert controller.project_state.get_visual_group(regulator.uid) is None
    assert controller.project_state.get_visual_group(plant.uid) is None
    for uid in member_uids:
        assert controller._find_block_by_uid(uid) is None

    window.undo_manager.stack.undo()
    assert controller.project_state.get_visual_group(control_loop.uid) is not None
    for uid in member_uids:
        assert controller._find_block_by_uid(uid) is not None
