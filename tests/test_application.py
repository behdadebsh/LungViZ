import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from LungViZ.application import (
    LungVizApplication,
    _anatomical_plane_axes,
    _sample_volume,
    _slice_geometry,
)
from LungViZ.model import MeshScene, PointScene
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
        self.vertices = None
        self.faces = None

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

    def set_enabled(self, enabled):
        self.enabled = enabled

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

class FakePolyscope:
    def __init__(self):
        self.structures = {}

    def remove_all_structures(self):
        self.structures.clear()

    def register_curve_network(self, name, nodes, edges, **options):
        structure = FakeStructure()
        self.structures[name] = structure
        return structure

    def register_point_cloud(self, name, points, **options):
        structure = FakeStructure()
        self.structures[name] = structure
        return structure

    def register_surface_mesh(self, name, vertices, faces, **options):
        structure = FakeStructure()
        structure.vertices = np.asarray(vertices)
        structure.faces = np.asarray(faces)
        structure.enabled = options.get("enabled", True)
        self.structures[name] = structure
        return structure


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
    assert region.radius_options[region.radius_index] == "radius_perf [elements]"
    assert region.network.edge_radius_quantity == (
        "radius: radius_perf [elements]",
        False,
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
