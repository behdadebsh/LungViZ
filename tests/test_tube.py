import numpy as np
import pytest

from LungViZ.tube import build_tube_surface


def _branch_geometry():
    coordinates = np.asarray(
        [
            [-1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [1.0, 0.5, 0.0],
            [1.0, -0.5, 0.0],
        ]
    )
    edges = np.asarray([[0, 1], [1, 2], [1, 3]])
    radii = np.asarray([0.30, 0.20, 0.10])
    return coordinates, edges, radii


def test_smooth_tubes_have_flat_terminal_caps_without_node_glyphs():
    coordinates, edges, radii = _branch_geometry()

    tube = build_tube_surface(
        coordinates, edges, radii, smooth_joins=True, sides=8
    )

    assert tube.vertices.shape == (75, 3)
    assert tube.faces.shape == (72, 3)
    assert tube.vertex_nodes.shape == (75,)
    assert tube.face_edges.shape == (72,)
    assert np.all(tube.faces >= 0)
    assert np.all(tube.faces < len(tube.vertices))
    assert set(tube.face_edges) == {0, 1, 2}

    for terminal_node in (0, 2, 3):
        matching = tube.vertices[tube.vertex_nodes == terminal_node]
        assert np.any(np.all(np.isclose(matching, coordinates[terminal_node]), axis=1))


def test_disabling_smoothing_caps_each_independent_cylinder():
    coordinates, edges, radii = _branch_geometry()

    smooth = build_tube_surface(
        coordinates, edges, radii, smooth_joins=True, sides=8
    )
    separate = build_tube_surface(
        coordinates, edges, radii, smooth_joins=False, sides=8
    )

    assert separate.vertices.shape == (102, 3)
    assert separate.faces.shape == (96, 3)
    assert len(separate.faces) > len(smooth.faces)


def test_tube_surface_rejects_radius_count_mismatch():
    coordinates, edges, _radii = _branch_geometry()

    with pytest.raises(ValueError, match="one tube radius"):
        build_tube_surface(coordinates, edges, np.asarray([0.1, 0.2]))
