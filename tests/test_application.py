import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from LungViZ.application import (
    LungVizApplication,
    _anatomical_plane_axes,
    _log10_colour_values,
    _sample_volume,
    _slice_geometry,
)
from LungViZ.exfile import parse_exnode
from LungViZ.model import MeshScene, PointScene, SurfaceScene
from LungViZ.volume import CTVolume


EXAMPLES = Path(__file__).parents[1] / "examples"


class FakeStructure:
    def __init__(self):
        self.scalars = {}
        self.colors = {}
        self.vectors = {}
        self.radius_quantity = None
        self.edge_radius_quantity = None
        self.removed = False
        self.gizmo_enabled = False
        self.transform = np.eye(4)
        self.enabled = True
        self.transparency = 1.0
        self.vertices = None
        self.faces = None
        self.points = None
        self.node_positions = None

    def add_scalar_quantity(self, name, values, **options):
        self.scalars[name] = (values, options)
        return SimpleNamespace()

    def add_vector_quantity(self, name, values, **options):
        self.vectors[name] = (values, options)
        return SimpleNamespace()

    def add_color_quantity(self, name, values, **options):
        self.colors[name] = (np.asarray(values), options)
        return SimpleNamespace()

    def update_vertex_positions(self, vertices):
        self.vertices = np.asarray(vertices)

    def update_point_positions(self, points):
        self.points = np.asarray(points)

    def update_node_positions(self, nodes):
        self.node_positions = np.asarray(nodes)

    def set_enabled(self, enabled):
        self.enabled = enabled

    def set_transparency(self, transparency):
        self.transparency = transparency

    def set_node_radius_quantity(self, name, autoscale=True):
        self.radius_quantity = (name, autoscale)

    def clear_node_radius_quantity(self):
        self.radius_quantity = None

    def set_edge_radius_quantity(self, name, autoscale=True):
        self.edge_radius_quantity = (name, autoscale)

    def clear_edge_radius_quantity(self):
        self.edge_radius_quantity = None

    def set_transform_gizmo_enabled(self, enabled):
        self.gizmo_enabled = enabled

    def remove(self):
        self.removed = True

    def set_transform(self, transform):
        self.transform = np.asarray(transform)

    def get_transform(self):
        return self.transform


class FakeTransformationGizmo:
    def __init__(self, name):
        self.name = name
        self.transform = np.eye(4)
        self.allow_translation = True
        self.allow_rotation = True
        self.allow_scaling = True
        self.interact_in_local_space = True
        self.removed = False

    def set_transform(self, transform):
        self.transform = np.asarray(transform)

    def get_transform(self):
        return self.transform

    def set_allow_translation(self, enabled):
        self.allow_translation = enabled

    def set_allow_rotation(self, enabled):
        self.allow_rotation = enabled

    def set_allow_scaling(self, enabled):
        self.allow_scaling = enabled

    def set_interact_in_local_space(self, enabled):
        self.interact_in_local_space = enabled

    def remove(self):
        self.removed = True


class FakePolyscope:
    def __init__(self):
        self.structures = {}
        self.gizmos = {}
        self.selection = None
        self.pick_result = SimpleNamespace(is_hit=False)

    def remove_all_structures(self):
        self.structures.clear()

    def register_curve_network(self, name, nodes, edges, **options):
        structure = FakeStructure()
        self.structures[name] = structure
        return structure

    def register_point_cloud(self, name, points, **options):
        structure = FakeStructure()
        structure.points = np.asarray(points)
        self.structures[name] = structure
        return structure

    def register_surface_mesh(self, name, vertices, faces, **options):
        structure = FakeStructure()
        structure.vertices = np.asarray(vertices)
        structure.faces = np.asarray(faces)
        structure.enabled = options.get("enabled", True)
        structure.transparency = options.get("transparency", 1.0)
        self.structures[name] = structure
        return structure

    def set_program_name(self, name):
        self.program_name = name

    def init(self):
        self.initialized = True

    def set_ground_plane_mode(self, mode):
        self.ground_plane_mode = mode

    def set_navigation_style(self, style):
        self.navigation_style = style

    def set_files_dropped_callback(self, callback):
        self.files_dropped_callback = callback

    def set_user_callback(self, callback):
        self.user_callback = callback

    def show(self):
        self.shown = True

    def screenshot(self, filename, *, transparent_bg, include_UI):
        self.saved_screenshot = (filename, transparent_bg, include_UI)

    def add_transformation_gizmo(self, name):
        gizmo = FakeTransformationGizmo(name)
        self.gizmos[name] = gizmo
        return gizmo

    def have_selection(self):
        return self.selection is not None

    def get_selection(self):
        return self.selection

    def reset_selection(self):
        self.selection = None

    def pick(self, *, screen_coords):
        self.last_pick_coords = screen_coords
        return self.pick_result


def test_application_loads_mesh_data_and_visual_quantities(monkeypatch):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()

    app.load_paths(
        [
            EXAMPLES / "sample.exnode",
            EXAMPLES / "sample.exelem",
            EXAMPLES / "sample.exdata",
        ]
    )

    assert app.scene is not None
    assert len(app.loaded_paths) == 3
    region = app.selected_region
    assert region is not None
    assert "pressure" in region.scalar_options
    assert "sample_airway / 1D mesh" in fake.structures
    assert "sample_airway / data / sample_measurements" in fake.structures
    assert "node identifier" in region.network.scalars
    assert "element identifier" in region.network.scalars

    region.scalar_index = region.scalar_options.index("pressure")
    app._set_scalar(region)
    assert region.network.scalars["pressure"][1]["enabled"]

    region.radius_index = region.radius_options.index("radius")
    app._set_radius(region)
    assert region.network.radius_quantity == ("radius: radius", False)
    np.testing.assert_allclose(
        region.network.scalars["radius: radius"][0],
        region.scalar_values["radius"] * 0.25,
    )


def test_regions_keep_repeated_node_identifiers_isolated(monkeypatch, tmp_path):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()
    mesh_region = app.load_region(
        [EXAMPLES / "sample.exnode", EXAMPLES / "sample.exelem"]
    )
    separate_nodes = tmp_path / "separate.exnode"
    separate_nodes.write_text(
        """Group name: landmarks
#Fields=1
1) coordinates, coordinate, rectangular cartesian, #Components=3
 x. Value index=1, #Derivatives=0
 y. Value index=2, #Derivatives=0
 z. Value index=3, #Derivatives=0
Node: 1
 100 200 300
Node: 2
 101 201 301
""",
        encoding="utf-8",
    )
    landmark_region = app.load_region([separate_nodes])

    assert len(app.regions) == 2
    assert isinstance(mesh_region.scene, MeshScene)
    assert isinstance(landmark_region.scene, PointScene)
    np.testing.assert_array_equal(mesh_region.scene.node_ids, [1, 2, 3, 4])
    np.testing.assert_array_equal(landmark_region.scene.node_ids, [1, 2])
    np.testing.assert_allclose(landmark_region.scene.coordinates[0], [100, 200, 300])
    np.testing.assert_allclose(mesh_region.scene.coordinates[0], [0, 0, 0])


def test_node_edit_translation_updates_connected_mesh_and_supports_history(
    monkeypatch, tmp_path
):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()
    region = app.load_region(
        [EXAMPLES / "sample.exnode", EXAMPLES / "sample.exelem"]
    )
    original = region.scene.coordinates[: region.scene.original_node_count].copy()
    original_edges = region.scene.edges.copy()

    app._set_edit_mode(region, True)
    app._select_edit_nodes(region, [1, 3])
    app._translate_selected_nodes(region, np.asarray([2.0, -1.0, 0.5]))

    np.testing.assert_allclose(region.scene.coordinates[1], original[1] + [2, -1, 0.5])
    np.testing.assert_allclose(region.scene.coordinates[3], original[3] + [2, -1, 0.5])
    np.testing.assert_allclose(region.scene.coordinates[0], original[0])
    np.testing.assert_array_equal(region.scene.edges, original_edges)
    np.testing.assert_allclose(region.network.node_positions, region.scene.coordinates)
    assert len(region.edit_undo) == 1

    app._undo_node_edit(region)
    np.testing.assert_allclose(
        region.scene.coordinates[: region.scene.original_node_count], original
    )
    app._redo_node_edit(region)
    np.testing.assert_allclose(region.scene.coordinates[1], original[1] + [2, -1, 0.5])

    exported_path = app.export_edited_exnode(region, tmp_path / "edited.exnode")
    exported = parse_exnode(exported_path)
    np.testing.assert_allclose(
        exported.nodes[1].fields["coordinates"], original[1] + [2, -1, 0.5]
    )


def test_standalone_exnode_and_exdata_regions_can_edit_points(monkeypatch):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()
    mesh_region = app.load_region(
        [EXAMPLES / "sample.exnode", EXAMPLES / "sample.exelem"]
    )
    point_region = app.load_region([EXAMPLES / "sample.exnode"])

    assert isinstance(point_region.scene, PointScene)
    mesh_original = mesh_region.scene.coordinates.copy()
    point_original = point_region.scene.coordinates[[0, 2]].copy()
    app._set_edit_mode(point_region, True)
    app._select_edit_nodes(point_region, [0, 2])
    app._translate_selected_nodes(point_region, np.asarray([0.1, 0.2, 0.3]))

    np.testing.assert_allclose(
        point_region.scene.coordinates[[0, 2]], point_original + [0.1, 0.2, 0.3]
    )
    np.testing.assert_allclose(
        point_region.field_structure.points, point_region.scene.coordinates
    )
    np.testing.assert_allclose(mesh_region.scene.coordinates, mesh_original)

    data_region = app.load_region([EXAMPLES / "sample.exdata"])
    assert isinstance(data_region.scene, PointScene)
    assert data_region.edit_documents == data_region.data_documents
    data_original = data_region.scene.coordinates[1].copy()
    app._set_edit_mode(data_region, True)
    app._select_edit_nodes(data_region, [1])
    app._translate_selected_nodes(data_region, np.asarray([-0.5, 0.0, 0.0]))
    np.testing.assert_allclose(
        data_region.scene.coordinates[1], data_original + [-0.5, 0.0, 0.0]
    )
    np.testing.assert_allclose(
        data_region.field_structure.points, data_region.scene.coordinates
    )


def test_stl_and_ply_load_as_independent_transparent_surface_regions(
    monkeypatch, tmp_path
):
    stl_path = tmp_path / "wall.stl"
    stl_path.write_text(
        """solid wall
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 0 1 0
 endloop
endfacet
endsolid wall
""",
        encoding="utf-8",
    )
    ply_path = tmp_path / "surface.ply"
    ply_path.write_text(
        """ply
format ascii 1.0
element vertex 4
property float x
property float y
property float z
element face 2
property list uchar int vertex_indices
end_header
0 0 0
1 0 0
1 1 0
0 1 0
3 0 1 2
3 0 2 3
""",
        encoding="utf-8",
    )
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()

    regions = app.load_files_as_regions([stl_path, ply_path])

    assert len(regions) == 2
    assert all(isinstance(region.scene, SurfaceScene) for region in regions)
    assert len(regions[0].scene.faces) == 1
    assert len(regions[1].scene.faces) == 2
    assert regions[0].field_structure.transparency == 0.65
    app._set_surface_opacity(regions[0], 0.25)
    assert regions[0].surface_opacity == 0.25
    assert regions[0].field_structure.transparency == 0.25
    assert regions[1].field_structure.transparency == 0.65


def test_run_uses_free_camera_and_installs_file_drop_loader(monkeypatch):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()

    app.run()

    assert fake.navigation_style == "free"
    assert fake.files_dropped_callback == app._files_dropped


def test_named_screenshot_uses_selected_path_and_background(monkeypatch, tmp_path):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()
    destination = tmp_path / "airway-flow.png"

    result = app.save_screenshot(destination)

    assert result == destination.resolve()
    assert fake.saved_screenshot == (str(destination.resolve()), False, False)
    assert str(destination.resolve()) in app.message

    app.screenshot_transparent_background = True
    transparent_destination = tmp_path / "airway-transparent.png"
    app.save_screenshot(transparent_destination)
    assert fake.saved_screenshot == (
        str(transparent_destination.resolve()),
        True,
        False,
    )
    jpg_destination = tmp_path / "airway-flow.jpg"
    app.save_screenshot(jpg_destination)
    assert fake.saved_screenshot == (str(jpg_destination.resolve()), False, False)


def test_named_screenshot_shortcut_uses_save_dialog(monkeypatch):
    app = LungVizApplication()
    saved = []
    monkeypatch.setattr(app, "save_screenshot", lambda: saved.append(True))
    psim = SimpleNamespace(
        ImGuiKey_S=83,
        GetIO=lambda: SimpleNamespace(KeyCtrl=True, KeyShift=True),
        IsKeyPressed=lambda key, repeat: key == 83 and repeat is False,
    )

    app._consume_screenshot_shortcut(psim)

    assert saved == [True]


def test_log_colour_values_clamp_non_positive_entries_to_positive_floor():
    logged, floor, clamped = _log10_colour_values(
        np.asarray([100.0, 0.0, -3.0, 0.1, np.nan])
    )

    assert floor == 0.1
    assert clamped == 2
    np.testing.assert_allclose(logged, [2.0, -1.0, -1.0, -1.0, -1.0])


def test_native_screenshot_button_opens_save_as_and_moves_capture(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    app = LungVizApplication()
    app._native_screenshot_snapshot = app._native_screenshot_files()
    native_capture = tmp_path / "screenshot_000000.png"
    native_capture.write_bytes(b"native screenshot")
    destination = tmp_path / "named-airway.png"
    monkeypatch.setattr(
        "LungViZ.application.choose_screenshot_path", lambda extension: str(destination)
    )

    app._consume_native_screenshot()

    assert destination.read_bytes() == b"native screenshot"
    assert not native_capture.exists()
    assert str(destination.resolve()) in app.message


def test_cancelled_native_screenshot_keeps_numbered_capture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    app = LungVizApplication()
    app._native_screenshot_snapshot = app._native_screenshot_files()
    native_capture = tmp_path / "screenshot_000000.jpg"
    native_capture.write_bytes(b"native screenshot")
    monkeypatch.setattr(
        "LungViZ.application.choose_screenshot_path", lambda extension: ""
    )

    app._consume_native_screenshot()

    assert native_capture.exists()
    assert "kept at" in app.message


def test_mouse_gizmo_translation_is_live_and_coalesces_to_one_undo(monkeypatch):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()
    region = app.load_region(
        [EXAMPLES / "sample.exnode", EXAMPLES / "sample.exelem"]
    )
    original = region.scene.coordinates[[1, 3]].copy()
    app._set_edit_mode(region, True)
    app._select_edit_nodes(region, [1, 3])

    mouse = SimpleNamespace(
        down=True,
        ImGuiMouseButton_Left=0,
        IsMouseDown=lambda _button: mouse.down,
    )
    gizmo = region.edit_gizmo
    assert gizmo is not None
    assert gizmo.allow_translation
    assert not gizmo.allow_rotation
    assert not gizmo.allow_scaling
    assert not gizmo.interact_in_local_space
    gizmo.transform[0, 3] += 0.25
    app._sync_node_edit_gizmo(mouse)
    gizmo.transform[0, 3] += 0.25
    app._sync_node_edit_gizmo(mouse)

    np.testing.assert_allclose(
        region.scene.coordinates[[1, 3]], original + [0.5, 0, 0]
    )
    np.testing.assert_allclose(
        region.edit_selection_structure.points,
        region.scene.coordinates[[1, 3]],
    )
    assert len(region.edit_undo) == 1

    mouse.down = False
    app._sync_node_edit_gizmo(mouse)
    app._undo_node_edit(region)
    np.testing.assert_allclose(region.scene.coordinates[[1, 3]], original)


def test_mouse_pick_replaces_and_shift_adds_node_selection(monkeypatch):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()
    region = app.load_region(
        [EXAMPLES / "sample.exnode", EXAMPLES / "sample.exelem"]
    )
    app._set_edit_mode(region, True)
    io = SimpleNamespace(KeyShift=False, KeyCtrl=False)
    mouse = SimpleNamespace(clicked=True)
    psim = SimpleNamespace(
        GetIO=lambda: io,
        ImGuiMouseButton_Left=0,
        IsMouseClicked=lambda _button: mouse.clicked,
        ImGuiKey_LeftShift=1,
        ImGuiKey_RightShift=2,
        ImGuiKey_LeftCtrl=3,
        ImGuiKey_RightCtrl=4,
        IsKeyDown=lambda _key: False,
    )

    fake.selection = SimpleNamespace(
        structure_name=region.edit_handle_name,
        structure_data={"index": 1},
        local_index=1,
    )
    app._consume_node_pick(fake, psim)
    assert region.edit_selected == [1]

    fake.selection = None
    io.KeyShift = True
    mouse.clicked = True
    app._consume_node_pick(fake, psim)

    io.KeyShift = False
    mouse.clicked = False
    fake.selection = SimpleNamespace(
        structure_name=region.edit_handle_name,
        structure_data={"index": 3},
        local_index=3,
    )
    app._consume_node_pick(fake, psim)
    assert region.edit_selected == [1, 3]

    io.KeyCtrl = True
    mouse.clicked = True
    fake.selection = SimpleNamespace(
        structure_name=region.edit_handle_name,
        structure_data={"index": 1},
        local_index=1,
    )
    app._consume_node_pick(fake, psim)
    assert region.edit_selected == [3]


def test_shift_click_uses_direct_viewport_pick(monkeypatch):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()
    region = app.load_region(
        [EXAMPLES / "sample.exnode", EXAMPLES / "sample.exelem"]
    )
    app._set_edit_mode(region, True)
    app._select_edit_nodes(region, [0])
    io = SimpleNamespace(
        KeyShift=True,
        KeyCtrl=False,
        MousePos=(320.0, 240.0),
        WantCaptureMouse=False,
    )
    psim = SimpleNamespace(
        GetIO=lambda: io,
        ImGuiMouseButton_Left=0,
        IsMouseClicked=lambda _button: True,
    )
    fake.pick_result = SimpleNamespace(
        is_hit=True,
        structure_name=region.edit_handle_name,
        structure_data={"index": 2},
        local_index=2,
    )

    app._consume_node_pick(fake, psim)

    assert region.edit_selected == [0, 2]
    assert fake.last_pick_coords == (320.0, 240.0)


def test_element_flow_colours_edges_and_radius_controls_edge_thickness(
    monkeypatch, tmp_path
):
    field_path = tmp_path / "per_element.exelem"
    field_path.write_text(
        """Group name: sample_airway
Shape. Dimension=1
#Scale factor sets=0
#Nodes=0
#Fields=2
1)flow, field, rectangular cartesian, #Components=1
 flow. l.Lagrange, no modify, grid based.
 #xi1=1
2)radius_perf, field, rectangular cartesian, #Components=1
 radius_perf. l.Lagrange, no modify, grid based.
 #xi1=1
Element: 1 0 0
 Values:
  100 100 0.30 0.30
Element: 2 0 0
 Values:
  60 60 0.20 0.20
Element: 3 0 0
 Values:
  40 40 0.10 0.10
""",
        encoding="utf-8",
    )
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    app = LungVizApplication()

    region = app.load_region(
        [EXAMPLES / "sample.exnode", EXAMPLES / "sample.exelem", field_path]
    )

    assert region.scalar_locations["flow [elements]"] == "edges"
    assert region.network.scalars["flow [elements]"][1]["defined_on"] == "edges"
    assert region.scalar_options[region.scalar_index] == "flow [elements]"
    assert region.network.scalars["flow [elements]"][1]["enabled"]
    region.log_flow_colours = True
    app._set_scalar(region)
    logged_flow, log_options = region.network.scalars["log10(flow [elements])"]
    np.testing.assert_allclose(
        logged_flow, np.log10(region.scalar_values["flow [elements]"])
    )
    assert log_options["defined_on"] == "edges"
    assert log_options["enabled"]
    np.testing.assert_allclose(log_options["vminmax"], np.log10([40.0, 100.0]))
    original_flow = region.scalar_values["flow [elements]"].copy()
    region.log_flow_bounds["flow [elements]"] = (50.0, 80.0)
    app._set_scalar(region)
    logged_flow, log_options = region.network.scalars["log10(flow [elements])"]
    np.testing.assert_allclose(logged_flow, np.log10(original_flow))
    np.testing.assert_allclose(log_options["vminmax"], np.log10([50.0, 80.0]))
    np.testing.assert_array_equal(
        region.scalar_values["flow [elements]"], original_flow
    )
    assert region.radius_options[region.radius_index] == "radius_perf [elements]"
    assert region.network.radius_quantity == (
        "smoothed radius: radius_perf [elements]",
        False,
    )
    assert region.network.edge_radius_quantity is None
    expected_node_radii = np.asarray(
        [0.30, np.sqrt((0.30**2 + 0.20**2 + 0.10**2) / 3), 0.20, 0.10]
    )
    np.testing.assert_allclose(
        region.network.scalars["smoothed radius: radius_perf [elements]"][0],
        expected_node_radii * 0.25,
    )

    region.radius_scale = 0.1
    app._set_radius(region)
    np.testing.assert_allclose(
        region.network.scalars["smoothed radius: radius_perf [elements]"][0],
        expected_node_radii * 0.1,
    )

    region.smooth_radius_joins = False
    app._set_radius(region)
    assert region.network.radius_quantity is None
    assert region.network.edge_radius_quantity == (
        "radius: radius_perf [elements]",
        False,
    )
    np.testing.assert_allclose(
        region.network.scalars["radius: radius_perf [elements]"][0],
        region.scalar_values["radius_perf [elements]"] * 0.1,
    )

    assert region.network.scalars["flow [elements]"][1]["defined_on"] == "edges"


def test_ct_volume_registers_world_transform_and_three_planes(monkeypatch, tmp_path):
    fake = FakePolyscope()
    monkeypatch.setitem(sys.modules, "polyscope", fake)
    transform = np.eye(4)
    transform[:3, 3] = [10, 20, 30]
    volume = CTVolume(
        name="scan",
        source=tmp_path,
        values=np.zeros((3, 4, 5), dtype=np.float32),
        spacing=np.asarray([1.0, 2.0, 3.0]),
        transform=transform,
        display_range=(-1000.0, 400.0),
    )
    app = LungVizApplication()
    region = app.load_region(
        [EXAMPLES / "sample.exnode", EXAMPLES / "sample.exelem"]
    )

    app.load_ct(volume)

    assert "CT / scan / Axial" in fake.structures
    assert "CT / scan / Coronal" in fake.structures
    assert "CT / scan / Sagittal" in fake.structures
    assert len(app.ct_slices) == 3
    assert [slice_state.name for slice_state in app.ct_slices] == [
        "Axial",
        "Coronal",
        "Sagittal",
    ]
    assert all(not slice_state.visible for slice_state in app.ct_slices)
    assert all(not slice_state.structure.enabled for slice_state in app.ct_slices)
    axial = app.ct_slices[0]
    np.testing.assert_allclose(axial.structure.transform, transform)
    np.testing.assert_allclose(axial.base_vertices[:, 2], 6.0)
    colors = axial.structure.colors["CT grayscale"][0]
    np.testing.assert_allclose(colors[:, 0], colors[:, 1])
    np.testing.assert_allclose(colors[:, 1], colors[:, 2])
    assert len(app.regions) == 1

    app._set_ct_slice_gizmo(0, True)
    assert axial.visible
    assert axial.structure.enabled
    assert axial.transform_gizmo

    structures = [slice_state.structure for slice_state in app.ct_slices]
    app.unload_ct()
    assert app.ct_volume is None
    assert app.ct_slices == []
    assert all(structure.removed for structure in structures)


def test_ct_slice_sampling_tracks_translated_and_rotated_plane(tmp_path):
    grid = np.indices((3, 4, 5), dtype=float)
    values = grid[0] + 10 * grid[1] + 100 * grid[2]
    volume = CTVolume(
        name="gradient",
        source=tmp_path,
        values=values,
        spacing=np.ones(3),
        transform=np.eye(4),
        display_range=(0.0, 500.0),
    )
    vertices, _faces = _slice_geometry(volume, axis=2, index=2)

    sampled = _sample_volume(volume, vertices, np.eye(4))
    np.testing.assert_allclose(sampled, values[:, :, 2].ravel())

    translated = np.eye(4)
    translated[0, 3] = 0.5
    sampled = _sample_volume(volume, vertices, translated)
    valid = vertices[:, 0] < 2
    np.testing.assert_allclose(
        sampled[valid], values[:, :, 2].ravel()[valid] + 0.5
    )


def test_anatomical_plane_names_follow_permuted_volume_axes(tmp_path):
    transform = np.eye(4)
    transform[:3, :3] = np.asarray(
        [[0, 0, 1], [1, 0, 0], [0, 1, 0]], dtype=float
    )
    volume = CTVolume(
        name="permuted",
        source=tmp_path,
        values=np.zeros((2, 3, 4)),
        spacing=np.ones(3),
        transform=transform,
        display_range=(0.0, 1.0),
    )

    assert _anatomical_plane_axes(volume) == (
        ("Axial", 1),
        ("Coronal", 0),
        ("Sagittal", 2),
    )
