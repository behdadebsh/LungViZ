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

