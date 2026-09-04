from pathlib import Path

import numpy as np

from LungViZ.exfile import parse_exelem, parse_exnode
from LungViZ.scene import build_mesh_scene, scalar_variants


EXAMPLES = Path(__file__).parents[1] / "examples"


def test_build_1d_scene_with_fields_and_identifiers():
    nodes = parse_exnode(EXAMPLES / "sample.exnode")
    elements = parse_exelem(EXAMPLES / "sample.exelem")

    scene = build_mesh_scene([nodes], [elements])

    assert scene.coordinates.shape == (4, 3)
    np.testing.assert_array_equal(scene.node_ids, [1, 2, 3, 4])
    np.testing.assert_array_equal(scene.edges, [[0, 1], [1, 2], [1, 3]])
    np.testing.assert_array_equal(scene.edge_element_ids, [1, 2, 3])
    np.testing.assert_allclose(scene.fields["radius"].values[:, 0], [0.18, 0.15, 0.11, 0.10])


def test_scalar_variants_include_vector_components_and_magnitude():
    nodes = parse_exnode(EXAMPLES / "sample.exnode")
    elements = parse_exelem(EXAMPLES / "sample.exelem")
    scene = build_mesh_scene([nodes], [elements])

    variants = scalar_variants(scene)

    assert "coordinates.x" in variants
    assert "coordinates.magnitude" in variants
    assert "pressure" in variants


def test_cubic_hermite_elements_use_derivatives_and_scale_factors(tmp_path):
    node_path = tmp_path / "curve.exnode"
    node_path.write_text(
        """Group name: curve
#Fields=1
1) coordinates, coordinate, rectangular cartesian, #Components=3
 x. Value index=1, #Derivatives=1 (d/ds1)
 y. Value index=3, #Derivatives=1 (d/ds1)
 z. Value index=5, #Derivatives=1 (d/ds1)
Node: 1
 0 1 0 1 0 0
Node: 2
 1 1 0 -1 0 0
""",
        encoding="utf-8",
    )
    element_path = tmp_path / "curve.exelem"
    element_path.write_text(
        """Group name: curve
Shape. Dimension=1 line
#Scale factor sets=1
c.Hermite, #Scale factors=2
#Nodes=2
#Fields=1
1) coordinates, coordinate, rectangular cartesian, #Components=3
 x. c.Hermite, no modify, standard node based.
   #Nodes=2
 y. c.Hermite, no modify, standard node based.
   #Nodes=2
 z. c.Hermite, no modify, standard node based.
   #Nodes=2
Element: 1 0 0
 Nodes:
  1 2
 Scale factors:
  1.0 1.0
""",
        encoding="utf-8",
    )

    nodes = parse_exnode(node_path)
    elements = parse_exelem(element_path)
    scene = build_mesh_scene([nodes], [elements], hermite_subdivisions=4)

    assert elements.elements[0].interpolation == "cubic_hermite"
    assert elements.elements[0].scale_factors == (1.0, 1.0)
    assert scene.original_node_count == 2
    assert scene.coordinates.shape == (5, 3)
    assert scene.edges.shape == (4, 2)
    np.testing.assert_allclose(scene.coordinates[3], [0.5, 0.25, 0.0])
    np.testing.assert_allclose(scene.fields["coordinates"].values[3], [0.5, 0.25, 0.0])
