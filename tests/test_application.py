import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from LungViZ.application import LungVizApplication
from LungViZ.model import MeshScene, PointScene
from LungViZ.volume import CTVolume


EXAMPLES = Path(__file__).parents[1] / "examples"


class FakeStructure:
    def __init__(self):
        self.scalars = {}
        self.vectors = {}
        self.radius_quantity = None
        self.removed = False
        self.gizmo_enabled = False
        self.transform = np.eye(4)
        self.ignored_planes = []

    def add_scalar_quantity(self, name, values, **options):
        self.scalars[name] = (values, options)
        return SimpleNamespace()

    def add_vector_quantity(self, name, values, **options):
        self.vectors[name] = (values, options)
        return SimpleNamespace()

    def set_node_radius_quantity(self, name, autoscale=True):
        self.radius_quantity = (name, autoscale)

    def clear_node_radius_quantity(self):
        self.radius_quantity = None

    def set_transform_gizmo_enabled(self, enabled):
        self.gizmo_enabled = enabled

    def remove(self):
        self.removed = True

    def set_transform(self, transform):
        self.transform = np.asarray(transform)

    def get_transform(self):
        return self.transform

    def set_ignore_slice_plane(self, name, ignored):
        if ignored:
            self.ignored_planes.append(name)


class FakePlane:
    next_id = 1

    def __init__(self):
        self.pose = None
        self.removed = False
        self.name = f"plane-{FakePlane.next_id}"
        FakePlane.next_id += 1

    def set_pose(self, position, normal):
        self.pose = (np.asarray(position), np.asarray(normal))

    def set_draw_plane(self, enabled):
        pass

    def set_draw_widget(self, enabled):
        pass

    def set_grid_line_color(self, color):
        pass

    def set_transparency(self, value):
        pass

    def remove(self):
        self.removed = True

    def get_name(self):
        return self.name


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

    def register_volume_grid(self, name, dimensions, low, high, **options):
        structure = FakeStructure()
        self.structures[name] = structure
        return structure

    def add_scene_slice_plane(self):
        return FakePlane()


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
    assert region.network.radius_quantity == ("radius: radius", True)


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

    assert "CT / scan" in fake.structures
    assert len(app.slice_planes) == 3
    np.testing.assert_allclose(app.ct_structure.transform, transform)
    np.testing.assert_allclose(app.slice_planes[0].pose[0], [11, 23, 36])
    np.testing.assert_allclose(app.slice_planes[0].pose[1], [1, 0, 0])
    assert len(app.regions) == 1
    assert len(region.network.ignored_planes) == 3
