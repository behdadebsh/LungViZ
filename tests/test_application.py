import sys
from pathlib import Path
from types import SimpleNamespace

from LungViZ.application import LungVizApplication


EXAMPLES = Path(__file__).parents[1] / "examples"


class FakeStructure:
    def __init__(self):
        self.scalars = {}
        self.vectors = {}
        self.radius_quantity = None

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
    assert "pressure" in app.scalar_options
    assert "1D mesh" in fake.structures
    assert "data: sample_measurements" in fake.structures
    assert "node identifier" in app.network.scalars
    assert "element identifier" in app.network.scalars

    app.scalar_index = app.scalar_options.index("pressure")
    app._set_scalar()
    assert app.network.scalars["pressure"][1]["enabled"]

    app.radius_index = app.radius_options.index("radius")
    app._set_radius()
    assert app.network.radius_quantity == ("radius: radius", True)

