"""Load triangulated surface formats for Polyscope."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

from .exfile import ExFileError
from .model import SurfaceScene


SURFACE_EXTENSIONS = {".stl", ".ply"}


def load_surface_scene(paths: Iterable[str | Path]) -> SurfaceScene:
    """Load and combine STL/PLY files into one indexed triangle surface."""

    import trimesh

    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    warnings: list[str] = []
    vertex_offset = 0

    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if path.suffix.lower() not in SURFACE_EXTENSIONS:
            raise ExFileError(f"Unsupported surface format {path.suffix!r}")
        try:
            loaded = trimesh.load_mesh(path, process=True)
        except Exception as exc:
            raise ExFileError(f"Could not read surface {path.name}: {exc}") from exc

        mesh_vertices = np.asarray(loaded.vertices, dtype=float)
        mesh_faces = np.asarray(loaded.faces, dtype=np.int64)
        if mesh_vertices.ndim != 2 or mesh_vertices.shape[1] != 3:
            raise ExFileError(f"{path.name} does not contain 3D vertices")
        if mesh_faces.ndim != 2 or mesh_faces.shape[1] != 3:
            raise ExFileError(f"{path.name} does not contain triangulated faces")
        if not len(mesh_vertices) or not len(mesh_faces):
            raise ExFileError(f"{path.name} contains no drawable triangles")
        if not np.all(np.isfinite(mesh_vertices)):
            raise ExFileError(f"{path.name} contains non-finite vertex coordinates")
        if np.min(mesh_faces) < 0 or np.max(mesh_faces) >= len(mesh_vertices):
            raise ExFileError(f"{path.name} contains invalid face indices")

        vertices.append(mesh_vertices)
        faces.append(mesh_faces + vertex_offset)
        vertex_offset += len(mesh_vertices)

    if not vertices:
        raise ExFileError("No STL or PLY surface files were provided")
    return SurfaceScene(
        vertices=np.vstack(vertices),
        faces=np.vstack(faces),
        warnings=warnings,
    )
