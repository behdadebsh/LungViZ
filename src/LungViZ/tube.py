"""Display-only triangulated tubes for one-dimensional mesh scenes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TubeSurfaceGeometry:
    """A tube mesh plus mappings back to the rendered curve network."""

    vertices: np.ndarray
    faces: np.ndarray
    vertex_nodes: np.ndarray
    face_edges: np.ndarray


def _node_degrees(edges: np.ndarray, node_count: int) -> np.ndarray:
    degrees = np.zeros(node_count, dtype=int)
    np.add.at(degrees, edges[:, 0], 1)
    np.add.at(degrees, edges[:, 1], 1)
    return degrees


def _shared_node_radii(
    edge_radii: np.ndarray, edges: np.ndarray, node_count: int
) -> np.ndarray:
    """Use an RMS junction radius without adding any node-shaped geometry."""

    squared_sum = np.zeros(node_count, dtype=float)
    incident_count = np.zeros(node_count, dtype=int)
    squared = np.square(edge_radii)
    np.add.at(squared_sum, edges[:, 0], squared)
    np.add.at(squared_sum, edges[:, 1], squared)
    np.add.at(incident_count, edges[:, 0], 1)
    np.add.at(incident_count, edges[:, 1], 1)
    result = np.zeros(node_count, dtype=float)
    connected = incident_count > 0
    result[connected] = np.sqrt(
        squared_sum[connected] / incident_count[connected]
    )
    return result


def build_tube_surface(
    coordinates: np.ndarray,
    edges: np.ndarray,
    edge_radii: np.ndarray,
    *,
    smooth_joins: bool = True,
    sides: int = 8,
    overlap_factor: float = 0.75,
) -> TubeSurfaceGeometry:
    """Build cylindrical/frustum surfaces without Polyscope node spheres.

    In smooth mode, incident tubes share an interpolated junction radius and are
    extended slightly through internal nodes. The overlap closes angular gaps at
    bends and bifurcations without inserting a spherical node glyph. Degree-one
    ends remain at their actual coordinate and receive a flat cap.
    """

    points = np.asarray(coordinates, dtype=float)
    connectivity = np.asarray(edges, dtype=int)
    radii = np.clip(np.asarray(edge_radii, dtype=float).reshape(-1), 0.0, None)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Tube coordinates must be an N x 3 array")
    if connectivity.ndim != 2 or connectivity.shape[1] != 2:
        raise ValueError("Tube connectivity must be an E x 2 array")
    if radii.size != len(connectivity):
        raise ValueError("Each rendered edge must have one tube radius")
    if sides < 3:
        raise ValueError("A tube requires at least three sides")
    if np.any(connectivity < 0) or np.any(connectivity >= len(points)):
        raise ValueError("Tube connectivity contains an invalid node index")

    if not np.all(np.isfinite(points)) or not np.all(np.isfinite(radii)):
        raise ValueError("Tube coordinates and radii must be finite")

    displacements = points[connectivity[:, 1]] - points[connectivity[:, 0]]
    lengths = np.linalg.norm(displacements, axis=1)
    valid = lengths > np.finfo(float).eps
    if not np.any(valid):
        raise ValueError("The mesh has no non-zero-length edges to render as tubes")
    original_edge_indices = np.flatnonzero(valid)
    connectivity = connectivity[valid]
    radii = radii[valid]
    displacements = displacements[valid]
    lengths = lengths[valid]

    edge_count = len(connectivity)
    start_nodes = connectivity[:, 0]
    end_nodes = connectivity[:, 1]
    directions = displacements / lengths[:, None]
    references = np.eye(3)[np.argmin(np.abs(directions), axis=1)]
    first = np.cross(directions, references)
    first /= np.linalg.norm(first, axis=1)[:, None]
    second = np.cross(directions, first)

    degrees = _node_degrees(connectivity, len(points))
    shared_radii = (
        _shared_node_radii(radii, connectivity, len(points))
        if smooth_joins
        else None
    )
    angles = np.linspace(0.0, 2.0 * np.pi, sides, endpoint=False)
    radial_directions = (
        np.cos(angles)[None, :, None] * first[:, None, :]
        + np.sin(angles)[None, :, None] * second[:, None, :]
    )

    if smooth_joins:
        start_radii = shared_radii[start_nodes]
        end_radii = shared_radii[end_nodes]
        start_overlaps = np.where(
            degrees[start_nodes] > 1,
            np.minimum(overlap_factor * start_radii, 0.25 * lengths),
            0.0,
        )
        end_overlaps = np.where(
            degrees[end_nodes] > 1,
            np.minimum(overlap_factor * end_radii, 0.25 * lengths),
            0.0,
        )
    else:
        start_radii = radii
        end_radii = radii
        start_overlaps = np.zeros(edge_count, dtype=float)
        end_overlaps = np.zeros(edge_count, dtype=float)

    start_centers = points[start_nodes] - directions * start_overlaps[:, None]
    end_centers = points[end_nodes] + directions * end_overlaps[:, None]
    rings = np.stack(
        (
            start_centers[:, None, :]
            + start_radii[:, None, None] * radial_directions,
            end_centers[:, None, :]
            + end_radii[:, None, None] * radial_directions,
        ),
        axis=1,
    )
    side_vertices = rings.reshape((-1, 3))
    side_vertex_nodes = np.stack(
        (
            np.repeat(start_nodes[:, None], sides, axis=1),
            np.repeat(end_nodes[:, None], sides, axis=1),
        ),
        axis=1,
    ).reshape(-1)

    side = np.arange(sides)[None, :]
    following = (side + 1) % sides
    bases = (np.arange(edge_count) * (2 * sides))[:, None]
    start_ring = bases + side
    end_ring = bases + sides + side
    start_following = bases + following
    end_following = bases + sides + following
    first_faces = np.stack((start_ring, end_following, end_ring), axis=2)
    second_faces = np.stack((start_ring, start_following, end_following), axis=2)
    side_faces = np.concatenate((first_faces, second_faces), axis=1).reshape((-1, 3))
    side_face_edges = np.repeat(original_edge_indices, 2 * sides)

    start_caps = (
        np.ones(edge_count, dtype=bool)
        if not smooth_joins
        else degrees[start_nodes] == 1
    )
    end_caps = (
        np.ones(edge_count, dtype=bool)
        if not smooth_joins
        else degrees[end_nodes] == 1
    )
    start_cap_edges = np.flatnonzero(start_caps)
    end_cap_edges = np.flatnonzero(end_caps)
    cap_edges = np.concatenate((start_cap_edges, end_cap_edges))
    cap_is_end = np.concatenate(
        (
            np.zeros(len(start_cap_edges), dtype=bool),
            np.ones(len(end_cap_edges), dtype=bool),
        )
    )
    cap_nodes = np.where(cap_is_end, end_nodes[cap_edges], start_nodes[cap_edges])
    cap_centers = np.where(
        cap_is_end[:, None], end_centers[cap_edges], start_centers[cap_edges]
    )
    cap_radii = np.where(
        cap_is_end, end_radii[cap_edges], start_radii[cap_edges]
    )
    cap_rings = (
        cap_centers[:, None, :]
        + cap_radii[:, None, None] * radial_directions[cap_edges]
    )
    cap_vertices = np.concatenate(
        (cap_rings, cap_centers[:, None, :]), axis=1
    ).reshape((-1, 3))
    cap_vertex_nodes = np.repeat(cap_nodes, sides + 1)
    cap_bases = len(side_vertices) + (
        np.arange(len(cap_edges)) * (sides + 1)
    )[:, None]
    cap_ring = cap_bases + side
    cap_following = cap_bases + following
    cap_centers_indices = np.broadcast_to(cap_bases + sides, cap_ring.shape)
    start_cap_faces = np.stack(
        (cap_centers_indices, cap_following, cap_ring), axis=2
    )
    end_cap_faces = np.stack(
        (cap_centers_indices, cap_ring, cap_following), axis=2
    )
    cap_faces = np.where(
        cap_is_end[:, None, None], end_cap_faces, start_cap_faces
    ).reshape((-1, 3))
    cap_face_edges = np.repeat(original_edge_indices[cap_edges], sides)

    return TubeSurfaceGeometry(
        vertices=np.concatenate((side_vertices, cap_vertices), axis=0),
        faces=np.concatenate((side_faces, cap_faces), axis=0),
        vertex_nodes=np.concatenate((side_vertex_nodes, cap_vertex_nodes)),
        face_edges=np.concatenate((side_face_edges, cap_face_edges)),
    )
