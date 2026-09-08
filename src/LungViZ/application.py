"""Interactive Polyscope application for regional EX data and CT volumes."""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass, field
from itertools import permutations
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

from .exfile import ExFileError, load_ex_file, write_exnode_coordinates
from .model import ElementDocument, MeshScene, NodeDocument, PointScene, SurfaceScene
from .scene import (
    build_mesh_scene,
    build_point_scene,
    coordinate_field_names,
    edge_scalar_variants,
    scalar_variants,
)
from .surface import SURFACE_EXTENSIONS, load_surface_scene
from .volume import CTVolume, load_dicom_directory, load_nifti


def choose_ex_files() -> Sequence[str]:
    """Choose EX or triangulated-surface files for a new region."""

    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilenames(
            title="Load EX or surface geometry",
            filetypes=[
                ("Supported geometry", "*.exnode *.exelem *.exdata *.stl *.ply"),
                ("OpenCMISS EX files", "*.exnode *.exelem *.exdata"),
                ("Triangulated surfaces", "*.stl *.ply"),
                ("All files", "*.*"),
            ],
        )
    finally:
        root.destroy()


def choose_dicom_directory() -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(title="Choose a DICOM series folder")
    finally:
        root.destroy()


def choose_nifti_file() -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilename(
            title="Choose a NIfTI CT volume",
            filetypes=[("NIfTI images", "*.nii *.nii.gz"), ("All files", "*.*")],
        )
    finally:
        root.destroy()


def choose_exnode_export_path(source: Path) -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    extension = (
        source.suffix.lower() if source.suffix.lower() == ".exdata" else ".exnode"
    )
    file_label = (
        "OpenCMISS EX data files"
        if extension == ".exdata"
        else "OpenCMISS EX node files"
    )
    try:
        return filedialog.asksaveasfilename(
            title="Export edited node coordinates",
            initialdir=str(source.parent),
            initialfile=f"{source.stem}_edited{extension}",
            defaultextension=extension,
            filetypes=[(file_label, f"*{extension}"), ("All files", "*.*")],
        )
    finally:
        root.destroy()


def choose_screenshot_path(default_extension: str = ".png") -> str:
    """Choose a named PNG or JPEG destination for the current view."""

    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    default_extension = default_extension.lower()
    if default_extension not in {".png", ".jpg"}:
        default_extension = ".png"
    try:
        return filedialog.asksaveasfilename(
            title="Save LungViZ screenshot",
            initialdir=str(Path.cwd()),
            initialfile=f"lungviz_view{default_extension}",
            defaultextension=default_extension,
            filetypes=[
                ("PNG image", "*.png"),
                ("JPEG image", "*.jpg"),
            ],
        )
    finally:
        root.destroy()


def _finite_for_display(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    replacement = float(np.median(finite)) if finite.size else 0.0
    return np.nan_to_num(values, nan=replacement, posinf=replacement, neginf=replacement)


def _edge_radii_to_node_radii(
    edge_radii: np.ndarray, edges: np.ndarray, node_count: int
) -> np.ndarray:
    """Derive display-only shared radii so incident tubes meet continuously."""

    radii = np.asarray(edge_radii, dtype=float).reshape(-1)
    connectivity = np.asarray(edges, dtype=int)
    if radii.size != len(connectivity):
        raise ValueError("Each rendered edge must have one radius")
    squared_sum = np.zeros(node_count, dtype=float)
    incident_count = np.zeros(node_count, dtype=int)
    squared = np.square(np.clip(radii, 0.0, None))
    np.add.at(squared_sum, connectivity[:, 0], squared)
    np.add.at(squared_sum, connectivity[:, 1], squared)
    np.add.at(incident_count, connectivity[:, 0], 1)
    np.add.at(incident_count, connectivity[:, 1], 1)
    node_radii = np.zeros(node_count, dtype=float)
    connected = incident_count > 0
    node_radii[connected] = np.sqrt(
        squared_sum[connected] / incident_count[connected]
    )
    return node_radii


def _edge_radii_to_mean_node_radii(
    edge_radii: np.ndarray, edges: np.ndarray, node_count: int
) -> np.ndarray:
    """Match Polyscope's inferred node radius for an edge-radius quantity."""

    radii = np.asarray(edge_radii, dtype=float).reshape(-1)
    connectivity = np.asarray(edges, dtype=int)
    if radii.size != len(connectivity):
        raise ValueError("Each rendered edge must have one radius")
    radius_sum = np.zeros(node_count, dtype=float)
    incident_count = np.zeros(node_count, dtype=int)
    clipped = np.clip(radii, 0.0, None)
    np.add.at(radius_sum, connectivity[:, 0], clipped)
    np.add.at(radius_sum, connectivity[:, 1], clipped)
    np.add.at(incident_count, connectivity[:, 0], 1)
    np.add.at(incident_count, connectivity[:, 1], 1)
    node_radii = np.zeros(node_count, dtype=float)
    connected = incident_count > 0
    node_radii[connected] = radius_sum[connected] / incident_count[connected]
    return node_radii


def _endpoint_cap_positions(
    coordinates: np.ndarray, edges: np.ndarray, node_radii: np.ndarray
) -> np.ndarray:
    """Inset degree-one display nodes so their rounded caps end at the true tips."""

    points = np.asarray(coordinates, dtype=float)
    connectivity = np.asarray(edges, dtype=int)
    radii = np.asarray(node_radii, dtype=float).reshape(-1)
    if radii.size != len(points):
        raise ValueError("Each rendered node must have one radius")
    result = points.copy()
    if not len(connectivity):
        return result

    degrees = np.zeros(len(points), dtype=int)
    np.add.at(degrees, connectivity[:, 0], 1)
    np.add.at(degrees, connectivity[:, 1], 1)
    neighbours = np.full(len(points), -1, dtype=int)
    neighbours[connectivity[:, 0]] = connectivity[:, 1]
    neighbours[connectivity[:, 1]] = connectivity[:, 0]
    endpoints = np.flatnonzero(degrees == 1)
    if not endpoints.size:
        return result

    directions = points[neighbours[endpoints]] - points[endpoints]
    lengths = np.linalg.norm(directions, axis=1)
    valid = lengths > np.finfo(float).eps
    if not np.any(valid):
        return result
    endpoints = endpoints[valid]
    directions = directions[valid]
    lengths = lengths[valid]
    shifts = np.minimum(
        np.clip(radii[endpoints], 0.0, None),
        0.45 * lengths,
    )
    result[endpoints] += directions * (shifts / lengths)[:, None]
    return result


def _log10_colour_values(values: np.ndarray) -> tuple[np.ndarray, float, int]:
    """Return log10 display values, clamping non-positive entries to the floor."""

    raw = np.asarray(values, dtype=float)
    positive = raw[np.isfinite(raw) & (raw > 0.0)]
    if not positive.size:
        raise ValueError("A logarithmic colour scale requires at least one positive value")
    floor = float(positive.min())
    non_positive_count = int(np.count_nonzero(np.isfinite(raw) & (raw <= 0.0)))
    safe = np.where(np.isfinite(raw) & (raw > 0.0), raw, floor)
    return np.log10(safe), floor, non_positive_count


def _display_indices(size: int, maximum: int = 384) -> np.ndarray:
    if size <= maximum:
        return np.arange(size, dtype=int)
    return np.unique(np.linspace(0, size - 1, maximum).round().astype(int))


def _slice_geometry(volume: CTVolume, axis: int, index: int):
    """Create a downsampled rectangular mesh for one native CT slice."""

    plane_axes = [candidate for candidate in range(3) if candidate != axis]
    first_indices = _display_indices(volume.values.shape[plane_axes[0]])
    second_indices = _display_indices(volume.values.shape[plane_axes[1]])
    first, second = np.meshgrid(first_indices, second_indices, indexing="ij")
    vertices = np.zeros((first.size, 3), dtype=float)
    vertices[:, axis] = index * volume.spacing[axis]
    vertices[:, plane_axes[0]] = first.ravel() * volume.spacing[plane_axes[0]]
    vertices[:, plane_axes[1]] = second.ravel() * volume.spacing[plane_axes[1]]

    grid = np.arange(first.size, dtype=int).reshape(first.shape)
    faces = np.column_stack(
        (
            grid[:-1, :-1].ravel(),
            grid[1:, :-1].ravel(),
            grid[1:, 1:].ravel(),
            grid[:-1, 1:].ravel(),
        )
    )
    return vertices, faces


def _sample_volume(volume: CTVolume, vertices: np.ndarray, transform: np.ndarray):
    """Trilinearly sample the CT at transformed plane vertices."""

    homogeneous = np.column_stack((vertices, np.ones(len(vertices), dtype=float)))
    world = homogeneous @ np.asarray(transform, dtype=float).T
    local = world @ np.linalg.inv(volume.transform).T
    coordinates = local[:, :3] / volume.spacing
    shape = np.asarray(volume.values.shape, dtype=int)
    valid = np.all((coordinates >= 0) & (coordinates <= shape - 1), axis=1)
    clipped = np.clip(coordinates, 0, shape - 1)
    lower = np.floor(clipped).astype(int)
    upper = np.minimum(lower + 1, shape - 1)
    fraction = clipped - lower

    sampled = np.full(len(vertices), volume.display_range[0], dtype=float)
    if not np.any(valid):
        return sampled
    lo = lower[valid]
    hi = upper[valid]
    weight = fraction[valid]
    data = volume.values
    c00 = data[lo[:, 0], lo[:, 1], lo[:, 2]] * (1 - weight[:, 0]) + data[
        hi[:, 0], lo[:, 1], lo[:, 2]
    ] * weight[:, 0]
    c01 = data[lo[:, 0], lo[:, 1], hi[:, 2]] * (1 - weight[:, 0]) + data[
        hi[:, 0], lo[:, 1], hi[:, 2]
    ] * weight[:, 0]
    c10 = data[lo[:, 0], hi[:, 1], lo[:, 2]] * (1 - weight[:, 0]) + data[
        hi[:, 0], hi[:, 1], lo[:, 2]
    ] * weight[:, 0]
    c11 = data[lo[:, 0], hi[:, 1], hi[:, 2]] * (1 - weight[:, 0]) + data[
        hi[:, 0], hi[:, 1], hi[:, 2]
    ] * weight[:, 0]
    c0 = c00 * (1 - weight[:, 1]) + c10 * weight[:, 1]
    c1 = c01 * (1 - weight[:, 1]) + c11 * weight[:, 1]
    sampled[valid] = c0 * (1 - weight[:, 2]) + c1 * weight[:, 2]
    return sampled


def _grayscale(values: np.ndarray, display_range) -> np.ndarray:
    low, high = display_range
    scale = high - low if high > low else 1.0
    intensity = np.clip((values - low) / scale, 0.0, 1.0)
    intensity = np.nan_to_num(intensity, nan=0.0)
    return np.repeat(intensity[:, None], 3, axis=1)


def _anatomical_plane_axes(volume: CTVolume):
    """Match voxel axes to left/right, anterior/posterior, and inferior/superior."""

    directions = np.abs(volume.world_axes)
    voxel_axes = max(
        permutations(range(3)),
        key=lambda assignment: sum(
            directions[world_axis, voxel_axis]
            for world_axis, voxel_axis in enumerate(assignment)
        ),
    )
    return (
        ("Axial", voxel_axes[2]),
        ("Coronal", voxel_axes[1]),
        ("Sagittal", voxel_axes[0]),
    )


@dataclass
class RegionState:
    """All data and UI state belonging to one node-identifier namespace."""

    key: int
    name: str
    paths: List[Path] = field(default_factory=list)
    node_documents: List[NodeDocument] = field(default_factory=list)
    data_documents: List[NodeDocument] = field(default_factory=list)
    element_documents: List[ElementDocument] = field(default_factory=list)
    surface_paths: List[Path] = field(default_factory=list)
    edit_documents: List[NodeDocument] = field(default_factory=list)
    scene: MeshScene | PointScene | SurfaceScene | None = None
    structures: List[object] = field(default_factory=list)
    field_structure: object | None = None
    field_structure_name: str = ""
    network: object | None = None
    scalar_values: Dict[str, np.ndarray] = field(default_factory=dict)
    scalar_locations: Dict[str, str] = field(default_factory=dict)
    scalar_options: List[str] = field(default_factory=list)
    radius_options: List[str] = field(default_factory=lambda: ["Constant"])
    coordinate_index: int = 0
    scalar_index: int = 0
    log_flow_colours: bool = False
    log_flow_bounds: Dict[str, tuple[float, float]] = field(default_factory=dict)
    radius_index: int = 0
    radius_scale: float = 0.25
    smooth_radius_joins: bool = True
    transform_gizmo: bool = False
    surface_opacity: float = 0.65
    transform: np.ndarray = field(default_factory=lambda: np.eye(4, dtype=float))
    message: str = ""
    warnings: List[str] = field(default_factory=list)
    edit_mode: bool = False
    edit_selected: List[int] = field(default_factory=list)
    edit_handles: object | None = None
    edit_selection_structure: object | None = None
    edit_gizmo: object | None = None
    edit_handle_name: str = ""
    edit_selection_name: str = ""
    edit_original_coordinates: np.ndarray | None = None
    edit_original_node_ids: np.ndarray | None = None
    edit_translation: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=float)
    )
    edit_absolute: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    edit_undo: List["NodeEdit"] = field(default_factory=list)
    edit_redo: List["NodeEdit"] = field(default_factory=list)
    edit_gizmo_transform: np.ndarray | None = None
    edit_mouse_active: bool = False
    edit_mouse_history: "NodeEdit | None" = None


@dataclass
class NodeEdit:
    indices: np.ndarray
    before: np.ndarray
    after: np.ndarray
    kind: str = "numeric"


@dataclass
class CTSliceState:
    name: str
    axis: int
    index: int
    structure: object
    base_vertices: np.ndarray
    transform: np.ndarray
    visible: bool = False
    transform_gizmo: bool = False


class LungVizApplication:
    def __init__(self) -> None:
        self.regions: List[RegionState] = []
        self.selected_region_index = 0
        self._next_region_key = 1
        self.ct_volume: CTVolume | None = None
        self.ct_slices: List[CTSliceState] = []
        self.selected_ct_slice_index = 0
        self._node_pick_shift = False
        self._node_pick_control = False
        self.screenshot_transparent_background = False
        self._native_screenshot_snapshot: Dict[Path, tuple[int, int]] | None = None
        self.message = "Load each mesh or standalone node set as its own region."

    @property
    def selected_region(self) -> RegionState | None:
        if not self.regions:
            return None
        self.selected_region_index = min(self.selected_region_index, len(self.regions) - 1)
        return self.regions[self.selected_region_index]

    @property
    def loaded_paths(self) -> List[Path]:
        return [path for region in self.regions for path in region.paths]

    @property
    def scene(self):
        region = self.selected_region
        return region.scene if region else None

    def _unique_region_name(self, requested: str) -> str:
        requested = requested.strip() or "region"
        used = {region.name for region in self.regions}
        if requested not in used:
            return requested
        suffix = 2
        while f"{requested} ({suffix})" in used:
            suffix += 1
        return f"{requested} ({suffix})"

    def _parse_paths(self, region: RegionState, paths: Sequence[str | Path]) -> List[str]:
        errors: List[str] = []
        for raw_path in paths:
            path = Path(raw_path).expanduser().resolve()
            if path in region.paths:
                continue
            try:
                if path.suffix.lower() in SURFACE_EXTENSIONS:
                    region.paths.append(path)
                    region.surface_paths.append(path)
                    continue
                document = load_ex_file(path)
            except (ExFileError, OSError) as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            region.paths.append(path)
            if isinstance(document, ElementDocument):
                region.element_documents.append(document)
            elif document.is_data:
                region.data_documents.append(document)
            else:
                region.node_documents.append(document)
        return errors

    def load_files_as_regions(
        self, paths: Sequence[str | Path]
    ) -> List[RegionState]:
        """Load EX files together and each surface as an independent region."""

        ex_paths: List[str | Path] = []
        surface_paths: List[str | Path] = []
        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() in SURFACE_EXTENSIONS:
                surface_paths.append(raw_path)
            else:
                ex_paths.append(raw_path)
        loaded: List[RegionState] = []
        if ex_paths:
            region = self.load_region(ex_paths)
            if region is not None:
                loaded.append(region)
        for surface_path in surface_paths:
            region = self.load_region([surface_path])
            if region is not None:
                loaded.append(region)
        return loaded

    def _files_dropped(self, paths: Sequence[str]) -> None:
        self.load_files_as_regions(paths)

    def load_region(
        self, paths: Sequence[str | Path], name: str | None = None
    ) -> RegionState | None:
        """Load one selection into a new, isolated node namespace."""

        if not paths:
            return None
        region = RegionState(key=self._next_region_key, name=name or "region")
        self._next_region_key += 1
        errors = self._parse_paths(region, paths)
        if not region.paths:
            self.message = " | ".join(errors) if errors else "No files were loaded."
            return None

        group_names = [
            document.group_name
            for document in (
                region.node_documents + region.element_documents + region.data_documents
            )
            if document.group_name
        ]
        inferred_name = name or (group_names[0] if group_names else region.paths[0].stem)
        region.name = self._unique_region_name(inferred_name)
        self.regions.append(region)
        self.selected_region_index = len(self.regions) - 1
        self._register_region(region)
        namespace_group_names = [
            document.group_name
            for document in region.node_documents
            if document.group_name
        ] + [
            document.group_name
            for document in region.element_documents
            if document.group_name and any(element.node_ids for element in document.elements)
        ]
        if len(set(namespace_group_names)) > 1:
            region.warnings.append(
                "The selected files declare multiple group names. They are isolated from "
                "other loads, but load each intended region separately for fully independent IDs."
            )
        if errors:
            region.message = f"{region.message} Import errors: {' | '.join(errors)}"
        self.message = f"Loaded region {region.name!r}."
        return region

    def load_paths(self, paths: Sequence[str | Path]) -> None:
        """Backward-compatible alias: one call creates one region."""

        self.load_region(paths)

    def add_to_selected_region(self, paths: Sequence[str | Path]) -> None:
        region = self.selected_region
        if region is None:
            self.load_region(paths)
            return
        errors = self._parse_paths(region, paths)
        self._register_region(region)
        if errors:
            region.message = f"{region.message} Import errors: {' | '.join(errors)}"

    def _remove_region_structures(self, region: RegionState) -> None:
        if region.field_structure is not None:
            try:
                region.transform = np.asarray(region.field_structure.get_transform())
            except AttributeError:
                pass
        if region.edit_gizmo is not None:
            try:
                region.edit_gizmo.remove()
            except (AttributeError, RuntimeError):
                pass
        for structure in region.structures:
            try:
                structure.remove()
            except (AttributeError, RuntimeError):
                pass
        region.structures.clear()
        region.field_structure = None
        region.field_structure_name = ""
        region.network = None
        region.edit_handles = None
        region.edit_selection_structure = None
        region.edit_gizmo = None
        region.edit_handle_name = ""
        region.edit_selection_name = ""
        region.edit_gizmo_transform = None

    def _add_point_fields(
        self, structure, scene: PointScene, *, identifier_name: str = "node identifier"
    ) -> Dict[str, np.ndarray]:
        structure.add_scalar_quantity(identifier_name, scene.node_ids.astype(float), enabled=False)
        values = dict(scalar_variants(scene))
        for field_name, field_values in values.items():
            structure.add_scalar_quantity(
                field_name, _finite_for_display(field_values), enabled=False
            )
        for field_name, scene_field in scene.fields.items():
            if scene_field.values.shape[1] in (2, 3) and field_name != scene.coordinate_field:
                structure.add_vector_quantity(
                    field_name, _finite_for_display(scene_field.values), enabled=False
                )
        return values

    def _register_region(self, region: RegionState) -> None:
        import polyscope as ps

        self._remove_region_structures(region)
        region.scene = None
        region.edit_documents = []
        region.scalar_values.clear()
        region.scalar_locations.clear()
        region.scalar_options.clear()
        region.radius_options = ["Constant"]
        region.warnings.clear()
        region.message = ""
        coordinate_documents = (
            region.node_documents
            if region.node_documents
            else region.data_documents[:1]
        )
        coordinate_options = coordinate_field_names(coordinate_documents)
        coordinate_name = (
            coordinate_options[min(region.coordinate_index, len(coordinate_options) - 1)]
            if coordinate_options
            else None
        )

        if region.node_documents and region.element_documents:
            try:
                mesh = build_mesh_scene(
                    region.node_documents, region.element_documents, coordinate_name
                )
                region.scene = mesh
                region.edit_documents = list(region.node_documents)
                structure_name = f"{region.name} / 1D mesh"
                network = ps.register_curve_network(
                    structure_name,
                    mesh.coordinates,
                    mesh.edges,
                    radius=0.006,
                )
                network.add_scalar_quantity(
                    "node identifier", mesh.node_ids.astype(float), enabled=False
                )
                network.add_scalar_quantity(
                    "element identifier",
                    mesh.edge_element_ids.astype(float),
                    defined_on="edges",
                    enabled=False,
                )
                node_scalars = dict(scalar_variants(mesh))
                region.scalar_values.update(node_scalars)
                region.scalar_locations.update(
                    {field_name: "nodes" for field_name in node_scalars}
                )
                for field_name, values in node_scalars.items():
                    network.add_scalar_quantity(
                        field_name, _finite_for_display(values), enabled=False
                    )
                for field_name, values in edge_scalar_variants(mesh).items():
                    display_name = f"{field_name} [elements]"
                    region.scalar_values[display_name] = values
                    region.scalar_locations[display_name] = "edges"
                    network.add_scalar_quantity(
                        display_name,
                        _finite_for_display(values),
                        defined_on="edges",
                        enabled=False,
                    )
                for field_name, scene_field in mesh.fields.items():
                    if (
                        scene_field.values.shape[1] in (2, 3)
                        and field_name != mesh.coordinate_field
                    ):
                        network.add_vector_quantity(
                            field_name,
                            _finite_for_display(scene_field.values),
                            enabled=False,
                        )
                for field_name, scene_field in mesh.edge_fields.items():
                    if scene_field.values.shape[1] in (2, 3):
                        network.add_vector_quantity(
                            field_name,
                            _finite_for_display(scene_field.values),
                            defined_on="edges",
                            enabled=False,
                        )
                region.network = network
                region.field_structure = network
                region.field_structure_name = structure_name
                region.structures.append(network)
                region.warnings.extend(mesh.warnings)
                region.message = (
                    f"{mesh.original_node_count} nodes, {len(mesh.edges)} rendered segments"
                )
            except ExFileError as exc:
                region.message = f"Mesh could not be built: {exc}"
                try:
                    points = build_point_scene(region.node_documents, coordinate_name)
                    region.scene = points
                    region.edit_documents = list(region.node_documents)
                    structure_name = (
                        f"{region.name} / nodes (connectivity unavailable)"
                    )
                    cloud = ps.register_point_cloud(
                        structure_name,
                        points.coordinates,
                        radius=0.008,
                    )
                    region.scalar_values = self._add_point_fields(cloud, points)
                    region.scalar_locations.update(
                        {field_name: "nodes" for field_name in region.scalar_values}
                    )
                    region.field_structure = cloud
                    region.field_structure_name = structure_name
                    region.structures.append(cloud)
                    region.warnings.extend(points.warnings)
                except ExFileError:
                    pass

        elif region.node_documents:
            try:
                points = build_point_scene(region.node_documents, coordinate_name)
                region.scene = points
                region.edit_documents = list(region.node_documents)
                structure_name = f"{region.name} / nodes"
                cloud = ps.register_point_cloud(
                    structure_name, points.coordinates, radius=0.008
                )
                region.scalar_values = self._add_point_fields(cloud, points)
                region.scalar_locations.update(
                    {field_name: "nodes" for field_name in region.scalar_values}
                )
                region.field_structure = cloud
                region.field_structure_name = structure_name
                region.structures.append(cloud)
                region.warnings.extend(points.warnings)
                region.message = f"{len(points.node_ids)} standalone nodes"
            except ExFileError as exc:
                region.message = f"Node cloud could not be built: {exc}"
        elif region.element_documents:
            contains_fields = any(document.fields for document in region.element_documents)
            if contains_fields:
                region.message = (
                    "Element fields loaded; add the matching exnode and connectivity "
                    "exelem files to this region."
                )
            else:
                region.message = "Connectivity loaded; add an exnode file to this region."

        for data_index, document in enumerate(region.data_documents, start=1):
            try:
                data_coordinate = (
                    coordinate_name
                    if not region.node_documents and data_index == 1
                    else None
                )
                points = build_point_scene([document], data_coordinate)
            except ExFileError as exc:
                region.warnings.append(f"{document.path.name}: {exc}")
                continue
            label = document.group_name or document.path.stem or f"data {data_index}"
            structure_name = f"{region.name} / data / {label}"
            cloud = ps.register_point_cloud(
                structure_name, points.coordinates, radius=0.008
            )
            point_values = self._add_point_fields(
                cloud, points, identifier_name="point identifier"
            )
            if region.scene is None:
                region.scene = points
                region.edit_documents = [document]
                region.field_structure = cloud
                region.field_structure_name = structure_name
                region.scalar_values = point_values
                region.scalar_locations.update(
                    {field_name: "nodes" for field_name in point_values}
                )
                region.message = f"{len(points.node_ids)} standalone data points"
            region.structures.append(cloud)
            region.warnings.extend(points.warnings)

        if region.surface_paths:
            try:
                surface = load_surface_scene(region.surface_paths)
                structure_name = f"{region.name} / triangulated surface"
                surface_structure = ps.register_surface_mesh(
                    structure_name,
                    surface.vertices,
                    surface.faces,
                    smooth_shade=True,
                    transparency=region.surface_opacity,
                )
                region.scene = surface
                region.edit_documents = []
                region.network = None
                region.field_structure = surface_structure
                region.field_structure_name = structure_name
                region.scalar_values.clear()
                region.scalar_locations.clear()
                region.structures.append(surface_structure)
                region.warnings.extend(surface.warnings)
                if region.node_documents or region.element_documents or region.data_documents:
                    region.warnings.append(
                        "Surface and EX files were loaded together. Load them as separate "
                        "regions for independent controls."
                    )
                region.message = (
                    f"{len(surface.vertices)} surface vertices, "
                    f"{len(surface.faces)} triangles"
                )
            except ExFileError as exc:
                region.message = f"Surface could not be built: {exc}"

        region.scalar_options = list(region.scalar_values)
        region.radius_options = ["Constant"] + region.scalar_options
        region.scalar_index = min(
            region.scalar_index, max(0, len(region.scalar_options) - 1)
        )
        if region.network is not None and region.scalar_index == 0:
            for preferred_location in ("edges", "nodes"):
                matching_index = next(
                    (
                        index
                        for index, field_name in enumerate(region.scalar_options)
                        if "flow" in field_name.lower()
                        and region.scalar_locations.get(field_name) == preferred_location
                    ),
                    None,
                )
                if matching_index is not None:
                    region.scalar_index = matching_index
                    self._set_scalar(region)
                    break
        region.radius_index = min(region.radius_index, len(region.radius_options) - 1)
        if region.network is not None and region.radius_index == 0:
            for preferred_location in ("edges", "nodes"):
                matching_index = next(
                    (
                        index
                        for index, field_name in enumerate(
                            region.radius_options[1:], start=1
                        )
                        if "radius" in field_name.lower()
                        and region.scalar_locations.get(field_name) == preferred_location
                    ),
                    None,
                )
                if matching_index is not None:
                    region.radius_index = matching_index
                    self._set_radius(region)
                    break
        for structure in region.structures:
            try:
                structure.set_transform(region.transform)
            except AttributeError:
                pass
        self._set_region_gizmo(region, region.transform_gizmo)
        if region.edit_mode and isinstance(region.scene, (MeshScene, PointScene)):
            self._create_edit_structures(region)

    def _set_region_gizmo(self, region: RegionState, enabled: bool) -> None:
        if enabled and region.edit_mode:
            self._set_edit_mode(region, False)
        region.transform_gizmo = enabled
        for structure in region.structures:
            try:
                structure.set_transform_gizmo_enabled(
                    enabled and structure is region.field_structure
                )
            except AttributeError:
                pass

    def _sync_region_transforms(self) -> None:
        for region in self.regions:
            if not region.transform_gizmo or region.field_structure is None:
                continue
            try:
                region.transform = np.asarray(region.field_structure.get_transform())
            except AttributeError:
                continue
            for structure in region.structures:
                if structure is region.field_structure:
                    continue
                try:
                    structure.set_transform(region.transform)
                except AttributeError:
                    pass

    def _set_scalar(self, region: RegionState) -> None:
        if region.field_structure is None or not region.scalar_options:
            return
        name = region.scalar_options[region.scalar_index]
        display_name = name
        display_values = region.scalar_values[name]
        map_range = None
        if region.log_flow_colours and "flow" in name.lower():
            try:
                display_values, _floor, _clamped = _log10_colour_values(display_values)
                display_name = f"log10({name})"
                lower, upper, _data_lower, _data_upper = self._log_flow_bounds(
                    region, name
                )
                map_range = (np.log10(lower), np.log10(upper))
            except ValueError as exc:
                region.message = str(exc)
        options = {"enabled": True}
        if region.network is not None:
            options["defined_on"] = region.scalar_locations.get(name, "nodes")
        if map_range is not None:
            options["vminmax"] = map_range
        region.field_structure.add_scalar_quantity(
            display_name, _finite_for_display(display_values), **options
        )

    @staticmethod
    def _log_flow_bounds(
        region: RegionState, name: str
    ) -> tuple[float, float, float, float]:
        """Return valid original-unit bounds for a flow field's log colour map."""

        values = region.scalar_values[name]
        positive = values[np.isfinite(values) & (values > 0.0)]
        if not positive.size:
            raise ValueError(
                "A logarithmic colour scale requires at least one positive value"
            )
        data_lower = float(positive.min())
        data_upper = float(positive.max())
        lower, upper = region.log_flow_bounds.get(name, (data_lower, data_upper))
        if not np.isfinite(lower) or not np.isfinite(upper):
            lower, upper = data_lower, data_upper
        lower = float(np.clip(lower, data_lower, data_upper))
        upper = float(np.clip(upper, data_lower, data_upper))
        if lower >= upper:
            lower, upper = data_lower, data_upper
        if lower >= upper:
            upper = float(np.nextafter(lower, np.inf))
        region.log_flow_bounds[name] = (lower, upper)
        return lower, upper, data_lower, data_upper

    def _set_radius(self, region: RegionState) -> None:
        if region.network is None:
            return
        region.network.clear_node_radius_quantity()
        region.network.clear_edge_radius_quantity()
        if isinstance(region.scene, MeshScene):
            region.network.update_node_positions(region.scene.coordinates)
        if region.radius_index == 0:
            return
        name = region.radius_options[region.radius_index]
        values = (
            np.clip(_finite_for_display(region.scalar_values[name]), 0.0, None)
            * region.radius_scale
        )
        quantity_name = f"radius: {name}"
        location = region.scalar_locations.get(name, "nodes")
        if location == "edges" and isinstance(region.scene, MeshScene):
            if region.smooth_radius_joins:
                quantity_name = f"smoothed radius: {name}"
                node_values = _edge_radii_to_node_radii(
                    values, region.scene.edges, len(region.scene.coordinates)
                )
                region.network.update_node_positions(
                    _endpoint_cap_positions(
                        region.scene.coordinates, region.scene.edges, node_values
                    )
                )
                region.network.add_scalar_quantity(
                    quantity_name, node_values, defined_on="nodes", enabled=False
                )
                region.network.set_node_radius_quantity(quantity_name, autoscale=False)
                return
            else:
                node_values = _edge_radii_to_mean_node_radii(
                    values, region.scene.edges, len(region.scene.coordinates)
                )
                region.network.update_node_positions(
                    _endpoint_cap_positions(
                        region.scene.coordinates, region.scene.edges, node_values
                    )
                )
        elif location == "nodes" and isinstance(region.scene, MeshScene):
            region.network.update_node_positions(
                _endpoint_cap_positions(
                    region.scene.coordinates, region.scene.edges, values
                )
            )
        region.network.add_scalar_quantity(
            quantity_name, values, defined_on=location, enabled=False
        )
        if location == "edges":
            region.network.set_edge_radius_quantity(quantity_name, autoscale=False)
        else:
            region.network.set_node_radius_quantity(quantity_name, autoscale=False)

    def _set_surface_opacity(self, region: RegionState, opacity: float) -> None:
        if not isinstance(region.scene, SurfaceScene) or region.field_structure is None:
            return
        region.surface_opacity = float(np.clip(opacity, 0.0, 1.0))
        region.field_structure.set_transparency(region.surface_opacity)

    def save_screenshot(self, destination: str | Path | None = None) -> Path | None:
        """Save the current rendered view to a user-selected image path."""

        import polyscope as ps

        if destination is None:
            destination = choose_screenshot_path()
        if not destination:
            return None
        target = Path(destination).expanduser().resolve()
        if not target.suffix:
            target = target.with_suffix(".png")
        if target.suffix.lower() not in {".png", ".jpg"}:
            raise ValueError("Screenshots must use a .png or .jpg extension")
        transparent_background = (
            self.screenshot_transparent_background
            and target.suffix.lower() == ".png"
        )
        ps.screenshot(
            str(target),
            transparent_bg=transparent_background,
            include_UI=False,
        )
        if self._native_screenshot_snapshot is not None:
            self._native_screenshot_snapshot = self._native_screenshot_files()
        self.message = f"Saved screenshot to {target}."
        return target

    @staticmethod
    def _native_screenshot_files() -> Dict[Path, tuple[int, int]]:
        """Return signatures for files created by Polyscope's native button."""

        screenshots: Dict[Path, tuple[int, int]] = {}
        for extension in ("png", "jpg"):
            for path in Path.cwd().glob(f"screenshot_*.{extension}"):
                index = path.stem.removeprefix("screenshot_")
                if len(index) != 6 or not index.isdigit():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                screenshots[path.resolve()] = (stat.st_mtime_ns, stat.st_size)
        return screenshots

    def _consume_native_screenshot(self) -> None:
        """Turn a native numbered screenshot into an interactive Save As action."""

        current = self._native_screenshot_files()
        previous = self._native_screenshot_snapshot
        self._native_screenshot_snapshot = current
        if previous is None:
            return
        changed = [
            path for path, signature in current.items() if previous.get(path) != signature
        ]
        if not changed:
            return

        source = max(changed, key=lambda path: current[path][0])
        try:
            destination = choose_screenshot_path(source.suffix)
            if not destination:
                self.message = f"Screenshot kept at {source}."
                return
            target = Path(destination).expanduser().resolve()
            if not target.suffix:
                target = target.with_suffix(source.suffix)
            if target.suffix.lower() not in {".png", ".jpg"}:
                raise ValueError("Screenshots must use a .png or .jpg extension")
            if target == source:
                self.message = f"Saved screenshot to {target}."
            elif target.suffix.lower() == source.suffix.lower():
                shutil.copyfile(source, target)
                source.unlink()
                self.message = f"Saved screenshot to {target}."
            else:
                self.save_screenshot(target)
                source.unlink()
        except (OSError, RuntimeError, ValueError) as exc:
            self.message = f"Could not rename screenshot; it remains at {source}: {exc}"
        finally:
            self._native_screenshot_snapshot = self._native_screenshot_files()

    def _consume_screenshot_shortcut(self, psim) -> None:
        """Open the named screenshot dialog without duplicating Polyscope's button."""

        io = psim.GetIO()
        if not (
            io.KeyCtrl
            and io.KeyShift
            and psim.IsKeyPressed(psim.ImGuiKey_S, False)
        ):
            return
        try:
            self.save_screenshot()
        except (OSError, RuntimeError, ValueError) as exc:
            self.message = f"Could not save screenshot: {exc}"

    def _remove_edit_selection_structure(self, region: RegionState) -> None:
        gizmo = region.edit_gizmo
        if gizmo is not None:
            try:
                gizmo.remove()
            except (AttributeError, RuntimeError):
                pass
        region.edit_gizmo = None
        structure = region.edit_selection_structure
        if structure is not None:
            try:
                structure.remove()
            except (AttributeError, RuntimeError):
                pass
            region.structures = [item for item in region.structures if item is not structure]
        region.edit_selection_structure = None
        region.edit_selection_name = ""
        region.edit_gizmo_transform = None
        region.edit_mouse_active = False
        region.edit_mouse_history = None

    def _remove_edit_structures(self, region: RegionState) -> None:
        self._remove_edit_selection_structure(region)
        structure = region.edit_handles
        if structure is not None:
            try:
                structure.remove()
            except (AttributeError, RuntimeError):
                pass
            region.structures = [item for item in region.structures if item is not structure]
        region.edit_handles = None
        region.edit_handle_name = ""

    @staticmethod
    def _edit_point_count(region: RegionState) -> int:
        if isinstance(region.scene, MeshScene):
            return region.scene.original_node_count
        if isinstance(region.scene, PointScene):
            return len(region.scene.node_ids)
        return 0

    def _update_edit_handles(self, region: RegionState) -> None:
        if (
            not isinstance(region.scene, (MeshScene, PointScene))
            or region.edit_handles is None
        ):
            return
        count = self._edit_point_count(region)
        coordinates = region.scene.coordinates[:count]
        region.edit_handles.update_point_positions(coordinates)
        colors = np.tile(np.asarray([0.72, 0.76, 0.82]), (count, 1))
        if region.edit_selected:
            colors[np.asarray(region.edit_selected, dtype=int)] = [1.0, 0.28, 0.04]
        region.edit_handles.add_color_quantity(
            "Node edit selection", colors, enabled=True
        )

    def _rebuild_edit_selection_structure(self, region: RegionState) -> None:
        import polyscope as ps

        self._remove_edit_selection_structure(region)
        if (
            not isinstance(region.scene, (MeshScene, PointScene))
            or not region.edit_selected
        ):
            return
        selected = np.asarray(region.edit_selected, dtype=int)
        coordinates = region.scene.coordinates[selected]
        name = f"{region.name} / selected edit nodes / {region.key}"
        structure = ps.register_point_cloud(
            name,
            coordinates,
            radius=0.012,
            color=(1.0, 0.28, 0.04),
        )
        structure.set_transform(region.transform)
        centroid = np.mean(coordinates, axis=0)
        world_centroid = (
            np.asarray(region.transform, dtype=float)
            @ np.asarray([centroid[0], centroid[1], centroid[2], 1.0])
        )[:3]
        gizmo = ps.add_transformation_gizmo(
            f"{region.name} / node translation gizmo / {region.key}"
        )
        gizmo.set_allow_translation(True)
        gizmo.set_allow_rotation(False)
        gizmo.set_allow_scaling(False)
        gizmo.set_interact_in_local_space(False)
        gizmo_transform = np.eye(4, dtype=float)
        gizmo_transform[:3, 3] = world_centroid
        gizmo.set_transform(gizmo_transform)
        region.edit_selection_structure = structure
        region.edit_gizmo = gizmo
        region.edit_selection_name = name
        region.edit_gizmo_transform = gizmo_transform.copy()
        region.structures.append(structure)

    def _create_edit_structures(self, region: RegionState) -> None:
        import polyscope as ps

        self._remove_edit_structures(region)
        if not isinstance(region.scene, (MeshScene, PointScene)):
            return
        count = self._edit_point_count(region)
        name = f"{region.name} / editable nodes / {region.key}"
        handles = ps.register_point_cloud(
            name,
            region.scene.coordinates[:count],
            radius=0.008,
            color=(0.72, 0.76, 0.82),
        )
        handles.set_transform(region.transform)
        region.edit_handles = handles
        region.edit_handle_name = name
        region.structures.append(handles)
        self._update_edit_handles(region)
        self._rebuild_edit_selection_structure(region)

    def _set_edit_mode(self, region: RegionState, enabled: bool) -> None:
        if enabled and not isinstance(region.scene, (MeshScene, PointScene)):
            region.message = "Point editing requires loaded EXNODE or EXDATA coordinates."
            return
        region.edit_mode = enabled
        if not enabled:
            self._remove_edit_structures(region)
            region.message = "Node edit mode disabled."
            return
        if region.transform_gizmo:
            self._set_region_gizmo(region, False)
        assert isinstance(region.scene, (MeshScene, PointScene))
        count = self._edit_point_count(region)
        node_ids = region.scene.node_ids[:count]
        if (
            region.edit_original_coordinates is None
            or region.edit_original_node_ids is None
            or not np.array_equal(region.edit_original_node_ids, node_ids)
        ):
            region.edit_original_coordinates = region.scene.coordinates[:count].copy()
            region.edit_original_node_ids = node_ids.copy()
            region.edit_undo.clear()
            region.edit_redo.clear()
        self._create_edit_structures(region)
        region.message = "Point edit mode enabled; click handles to select points."

    def _select_edit_nodes(self, region: RegionState, indices: Sequence[int]) -> None:
        if not isinstance(region.scene, (MeshScene, PointScene)):
            return
        count = self._edit_point_count(region)
        region.edit_selected = sorted(
            {int(index) for index in indices if 0 <= int(index) < count}
        )
        if region.edit_selected:
            region.edit_absolute = np.mean(
                region.scene.coordinates[np.asarray(region.edit_selected, dtype=int)], axis=0
            )
        self._update_edit_handles(region)
        self._rebuild_edit_selection_structure(region)

    def _write_node_positions(
        self, region: RegionState, indices: np.ndarray, positions: np.ndarray
    ) -> None:
        assert isinstance(region.scene, (MeshScene, PointScene))
        coordinate_field = region.scene.coordinate_field
        node_ids = region.scene.node_ids[indices]
        positions_by_id = {
            int(node_id): position for node_id, position in zip(node_ids, positions)
        }
        for document in region.edit_documents:
            for node in document.nodes:
                position = positions_by_id.get(node.identifier)
                values = node.fields.get(coordinate_field)
                if position is not None and values is not None:
                    values[: min(3, len(values))] = position[: min(3, len(values))]

    def _refresh_region_after_edit(
        self, region: RegionState, *, update_selection_structure: bool
    ) -> None:
        assert isinstance(region.scene, (MeshScene, PointScene))
        previous = region.scene
        coordinate_name = previous.coordinate_field
        if isinstance(previous, MeshScene):
            updated = build_mesh_scene(
                region.edit_documents, region.element_documents, coordinate_name
            )
            if (
                updated.coordinates.shape != previous.coordinates.shape
                or not np.array_equal(updated.edges, previous.edges)
            ):
                raise ExFileError(
                    "Editing changed the rendered mesh topology unexpectedly"
                )
        else:
            updated = build_point_scene(region.edit_documents, coordinate_name)
            if (
                updated.coordinates.shape != previous.coordinates.shape
                or not np.array_equal(updated.node_ids, previous.node_ids)
            ):
                raise ExFileError(
                    "Editing changed the rendered point identifiers unexpectedly"
                )
        region.scene = updated
        if isinstance(updated, MeshScene):
            assert region.network is not None
            region.network.update_node_positions(updated.coordinates)
        else:
            assert region.field_structure is not None
            region.field_structure.update_point_positions(updated.coordinates)
        for field_name, values in scalar_variants(updated).items():
            region.scalar_values[field_name] = values
            region.field_structure.add_scalar_quantity(
                field_name, _finite_for_display(values), enabled=False
            )
        if region.scalar_options:
            self._set_scalar(region)
        self._set_radius(region)
        self._update_edit_handles(region)
        if update_selection_structure:
            self._rebuild_edit_selection_structure(region)
        elif region.edit_selection_structure is not None and region.edit_selected:
            selected = np.asarray(region.edit_selected, dtype=int)
            region.edit_selection_structure.update_point_positions(
                updated.coordinates[selected]
            )

    def _set_node_positions(
        self,
        region: RegionState,
        indices: Sequence[int],
        positions: np.ndarray,
        *,
        record: bool = True,
        kind: str = "numeric",
        update_selection_structure: bool = True,
    ) -> None:
        if not isinstance(region.scene, (MeshScene, PointScene)):
            return
        index_array = np.asarray(indices, dtype=int)
        if not index_array.size:
            return
        new_positions = np.asarray(positions, dtype=float).reshape((-1, 3))
        if len(new_positions) != len(index_array) or not np.all(np.isfinite(new_positions)):
            raise ValueError("Edited node coordinates must be finite x, y, z values")
        before = region.scene.coordinates[index_array].copy()
        if np.allclose(before, new_positions):
            return
        self._write_node_positions(region, index_array, new_positions)
        self._refresh_region_after_edit(
            region, update_selection_structure=update_selection_structure
        )
        after = region.scene.coordinates[index_array].copy()
        if record:
            if kind == "mouse" and region.edit_mouse_history is not None:
                previous_edit = region.edit_mouse_history
                if np.array_equal(previous_edit.indices, index_array):
                    previous_edit.after = after.copy()
                else:
                    region.edit_mouse_history = None
            if kind != "mouse" or region.edit_mouse_history is None:
                edit = NodeEdit(index_array.copy(), before, after.copy(), kind)
                region.edit_undo.append(edit)
                if kind == "mouse":
                    region.edit_mouse_history = edit
            region.edit_redo.clear()
        if len(region.edit_selected) == 1:
            region.edit_absolute = region.scene.coordinates[
                region.edit_selected[0]
            ].copy()
        region.message = f"Moved {len(index_array)} point(s)."

    def _translate_selected_nodes(
        self, region: RegionState, translation: np.ndarray, *, kind: str = "numeric"
    ) -> None:
        if (
            not isinstance(region.scene, (MeshScene, PointScene))
            or not region.edit_selected
        ):
            return
        indices = np.asarray(region.edit_selected, dtype=int)
        delta = np.asarray(translation, dtype=float)
        self._set_node_positions(
            region,
            indices,
            region.scene.coordinates[indices] + delta,
            kind=kind,
            update_selection_structure=kind != "mouse",
        )

    def _undo_node_edit(self, region: RegionState) -> None:
        if not region.edit_undo:
            return
        region.edit_mouse_history = None
        edit = region.edit_undo.pop()
        self._set_node_positions(region, edit.indices, edit.before, record=False)
        region.edit_redo.append(edit)
        region.message = f"Undid movement of {len(edit.indices)} node(s)."

    def _redo_node_edit(self, region: RegionState) -> None:
        if not region.edit_redo:
            return
        edit = region.edit_redo.pop()
        self._set_node_positions(region, edit.indices, edit.after, record=False)
        region.edit_undo.append(edit)
        region.message = f"Redid movement of {len(edit.indices)} node(s)."

    def _reset_selected_nodes(self, region: RegionState) -> None:
        if region.edit_original_coordinates is None or not region.edit_selected:
            return
        indices = np.asarray(region.edit_selected, dtype=int)
        self._set_node_positions(
            region, indices, region.edit_original_coordinates[indices], kind="reset"
        )

    def _reset_all_nodes(self, region: RegionState) -> None:
        if region.edit_original_coordinates is None:
            return
        indices = np.arange(len(region.edit_original_coordinates), dtype=int)
        self._set_node_positions(
            region, indices, region.edit_original_coordinates, kind="reset"
        )

    def export_edited_exnode(
        self, region: RegionState, destination: str | Path | None = None
    ) -> Path | None:
        if not isinstance(region.scene, (MeshScene, PointScene)):
            return None
        coordinate_field = region.scene.coordinate_field
        document = next(
            (
                item
                for item in region.edit_documents
                if coordinate_field in item.fields
                and any(coordinate_field in node.fields for node in item.nodes)
            ),
            None,
        )
        if document is None:
            raise ExFileError("No coordinate EXNODE is available to export")
        if destination is None:
            destination = choose_exnode_export_path(document.path)
        if not destination:
            return None
        exported = write_exnode_coordinates(document, destination, coordinate_field)
        region.message = f"Exported edited coordinates to {exported.name}."
        return exported

    def _consume_node_pick(self, ps, psim) -> None:
        region = self.selected_region
        if (
            region is None
            or not region.edit_mode
            or not isinstance(region.scene, (MeshScene, PointScene))
        ):
            return
        io = None
        mouse_clicked = False
        try:
            io = psim.GetIO()
            current_shift = bool(io.KeyShift)
            current_control = bool(io.KeyCtrl)
            try:
                mouse_clicked = psim.IsMouseClicked(psim.ImGuiMouseButton_Left)
            except AttributeError:
                try:
                    mouse_clicked = bool(io.MouseClicked[0])
                except AttributeError:
                    mouse_clicked = False
            if mouse_clicked:
                self._node_pick_shift = current_shift
                self._node_pick_control = current_control
        except AttributeError:
            current_shift = psim.IsKeyDown(psim.ImGuiKey_LeftShift) or psim.IsKeyDown(
                psim.ImGuiKey_RightShift
            )
            current_control = psim.IsKeyDown(
                psim.ImGuiKey_LeftCtrl
            ) or psim.IsKeyDown(psim.ImGuiKey_RightCtrl)
            self._node_pick_shift = current_shift
            self._node_pick_control = current_control

        picked = None
        if (
            mouse_clicked
            and io is not None
            and not bool(getattr(io, "WantCaptureMouse", False))
        ):
            try:
                direct_pick = ps.pick(screen_coords=io.MousePos)
                if direct_pick.is_hit:
                    picked = direct_pick
            except (AttributeError, RuntimeError):
                pass
        if picked is None:
            try:
                if not ps.have_selection():
                    return
                picked = ps.get_selection()
            except (AttributeError, RuntimeError):
                return

        index = None
        if picked.structure_name == region.edit_handle_name:
            index = picked.structure_data.get("index", picked.local_index)
        elif picked.structure_name == region.edit_selection_name:
            local_index = int(picked.structure_data.get("index", picked.local_index))
            if 0 <= local_index < len(region.edit_selected):
                index = region.edit_selected[local_index]
        elif picked.structure_name == region.field_structure_name:
            element_type = str(
                picked.structure_data.get("element_type", "node")
            ).lower()
            if isinstance(region.scene, PointScene) or element_type == "node":
                index = picked.structure_data.get("index", picked.local_index)
        if index is None or not 0 <= int(index) < self._edit_point_count(region):
            return

        shift = current_shift or self._node_pick_shift
        control = current_control or self._node_pick_control
        selected = set(region.edit_selected)
        index = int(index)
        if control:
            if index in selected:
                selected.remove(index)
            else:
                selected.add(index)
        elif shift:
            selected.add(index)
        else:
            selected = {index}
        self._select_edit_nodes(region, sorted(selected))
        ps.reset_selection()
        self._node_pick_shift = False
        self._node_pick_control = False

    def _sync_node_edit_gizmo(self, psim) -> None:
        region = self.selected_region
        if (
            region is None
            or not region.edit_mode
            or not region.edit_selected
            or region.edit_gizmo is None
            or region.edit_gizmo_transform is None
        ):
            return
        try:
            transform = np.asarray(region.edit_gizmo.get_transform(), dtype=float)
        except (AttributeError, RuntimeError):
            return
        if transform.shape != (4, 4):
            return
        if not np.allclose(transform, region.edit_gizmo_transform):
            world_delta = transform[:3, 3] - region.edit_gizmo_transform[:3, 3]
            if np.linalg.norm(world_delta) > 1e-12:
                local_delta = np.linalg.solve(region.transform[:3, :3], world_delta)
                region.edit_mouse_active = True
                self._translate_selected_nodes(region, local_delta, kind="mouse")
            region.edit_gizmo_transform = transform.copy()

        mouse_down = psim.IsMouseDown(psim.ImGuiMouseButton_Left)
        if region.edit_mouse_active and not mouse_down:
            region.edit_mouse_active = False
            region.edit_mouse_history = None
            self._rebuild_edit_selection_structure(region)

    def remove_selected_region(self) -> None:
        region = self.selected_region
        if region is None:
            return
        self._remove_region_structures(region)
        self.regions.remove(region)
        self.selected_region_index = min(
            self.selected_region_index, max(0, len(self.regions) - 1)
        )
        self.message = f"Removed region {region.name!r}."

    def _remove_ct(self) -> None:
        for slice_state in self.ct_slices:
            try:
                slice_state.structure.remove()
            except (AttributeError, RuntimeError):
                pass
        self.ct_slices.clear()
        self.ct_volume = None

    def load_ct(self, volume: CTVolume) -> None:
        self._remove_ct()
        self.ct_volume = volume
        self.reset_ct_planes()
        self.message = f"Loaded CT {volume.name!r}; enable the slices you want to inspect."

    def unload_ct(self) -> None:
        if self.ct_volume is None:
            return
        name = self.ct_volume.name
        self._remove_ct()
        self.message = f"Unloaded CT {name!r}."

    def _update_ct_slice(self, slice_state: CTSliceState) -> None:
        if self.ct_volume is None:
            return
        values = _sample_volume(
            self.ct_volume, slice_state.base_vertices, slice_state.transform
        )
        slice_state.structure.update_vertex_positions(slice_state.base_vertices)
        slice_state.structure.add_color_quantity(
            "CT grayscale",
            _grayscale(values, self.ct_volume.display_range),
            defined_on="vertices",
            enabled=True,
        )

    def _sync_ct_slice_transforms(self) -> None:
        if self.ct_volume is None:
            return
        for slice_state in self.ct_slices:
            try:
                transform = np.asarray(slice_state.structure.get_transform(), dtype=float)
            except AttributeError:
                continue
            if transform.shape == (4, 4) and not np.allclose(
                transform, slice_state.transform
            ):
                slice_state.transform = transform
                self._update_ct_slice(slice_state)

    def _set_ct_slice_gizmo(self, selected_index: int, enabled: bool) -> None:
        for index, slice_state in enumerate(self.ct_slices):
            active = enabled and index == selected_index
            slice_state.transform_gizmo = active
            try:
                slice_state.structure.set_transform_gizmo_enabled(active)
            except AttributeError:
                pass
        if enabled and self.ct_slices:
            selected = self.ct_slices[selected_index]
            selected.visible = True
            selected.structure.set_enabled(True)

    def reset_ct_planes(self) -> None:
        import polyscope as ps

        if self.ct_volume is None:
            return
        for slice_state in self.ct_slices:
            try:
                slice_state.structure.remove()
            except (AttributeError, RuntimeError):
                pass
        self.ct_slices.clear()
        self.selected_ct_slice_index = 0
        for name, axis in _anatomical_plane_axes(self.ct_volume):
            index = self.ct_volume.values.shape[axis] // 2
            vertices, faces = _slice_geometry(self.ct_volume, axis, index)
            structure = ps.register_surface_mesh(
                f"CT / {self.ct_volume.name} / {name}",
                vertices,
                faces,
                enabled=False,
                edge_width=0.0,
                smooth_shade=False,
                back_face_policy="identical",
            )
            structure.set_transform(self.ct_volume.transform)
            slice_state = CTSliceState(
                name=name,
                axis=axis,
                index=index,
                structure=structure,
                base_vertices=vertices,
                transform=np.asarray(self.ct_volume.transform, dtype=float).copy(),
            )
            self._update_ct_slice(slice_state)
            self.ct_slices.append(slice_state)

    def clear(self) -> None:
        import polyscope as ps

        self._remove_ct()
        for region in self.regions:
            self._remove_region_structures(region)
        ps.remove_all_structures()
        self.regions.clear()
        self.selected_region_index = 0
        self.ct_volume = None
        self.message = "Scene cleared."

    def _draw_node_edit_panel(self, psim, region: RegionState) -> None:
        if not isinstance(region.scene, (MeshScene, PointScene)):
            return
        changed, enabled = psim.Checkbox("Edit nodes / data points", region.edit_mode)
        if changed:
            self._set_edit_mode(region, enabled)
        if not region.edit_mode:
            return

        psim.TextWrapped(
            "Click a point handle to select it. Shift-click adds points and Ctrl-click "
            "toggles them. Drag the selection with the translation arrows."
        )
        if psim.Button("Select all points"):
            self._select_edit_nodes(
                region, range(self._edit_point_count(region))
            )
        psim.SameLine()
        if psim.Button("Clear selection"):
            self._select_edit_nodes(region, [])

        selected_ids = region.scene.node_ids[
            np.asarray(region.edit_selected, dtype=int)
        ] if region.edit_selected else np.asarray([], dtype=int)
        psim.TextUnformatted(f"Selected points: {len(selected_ids)}")
        if selected_ids.size:
            preview = ", ".join(str(value) for value in selected_ids[:8])
            if len(selected_ids) > 8:
                preview += ", ..."
            psim.TextWrapped(f"Node IDs: {preview}")

        changed, translation = psim.InputFloat3(
            "Translation delta", region.edit_translation
        )
        if changed:
            region.edit_translation = np.asarray(translation, dtype=float)
        if psim.Button("Apply translation") and region.edit_selected:
            try:
                self._translate_selected_nodes(region, region.edit_translation)
                region.edit_translation = np.zeros(3, dtype=float)
            except (ExFileError, ValueError) as exc:
                region.message = f"Could not move nodes: {exc}"

        if len(region.edit_selected) == 1:
            changed, absolute = psim.InputFloat3(
                "Absolute position", region.edit_absolute
            )
            if changed:
                region.edit_absolute = np.asarray(absolute, dtype=float)
            if psim.Button("Set absolute position"):
                try:
                    self._set_node_positions(
                        region, region.edit_selected, region.edit_absolute
                    )
                except (ExFileError, ValueError) as exc:
                    region.message = f"Could not move node: {exc}"

        if psim.Button("Undo point edit"):
            self._undo_node_edit(region)
        psim.SameLine()
        if psim.Button("Redo point edit"):
            self._redo_node_edit(region)
        if psim.Button("Reset selected points"):
            self._reset_selected_nodes(region)
        psim.SameLine()
        if psim.Button("Reset all points"):
            self._reset_all_nodes(region)
        if psim.Button("Export edited EX file..."):
            try:
                self.export_edited_exnode(region)
            except (ExFileError, OSError) as exc:
                region.message = f"Could not export EX file: {exc}"

    def _draw_region_panel(self, psim) -> None:
        if psim.Button("Load geometry as new region..."):
            try:
                selected = choose_ex_files()
                if selected:
                    self.load_files_as_regions(selected)
            except Exception as exc:
                self.message = f"Could not load geometry region: {exc}"

        region = self.selected_region
        if self.regions:
            changed, value = psim.Combo(
                "Region",
                self.selected_region_index,
                [item.name for item in self.regions],
            )
            if changed:
                self.selected_region_index = value
                region = self.selected_region
            if psim.Button("Add files to region..."):
                try:
                    selected = choose_ex_files()
                    if selected:
                        self.add_to_selected_region(selected)
                except Exception as exc:
                    self.message = f"Could not add files: {exc}"
            psim.SameLine()
            if psim.Button("Remove region"):
                self.remove_selected_region()
                region = self.selected_region

        if region is None:
            psim.TextWrapped(
                "Choose all files belonging to one mesh together. Load another node set "
                "with the new-region button so repeated IDs stay independent."
            )
            return

        psim.TextWrapped(region.message)
        psim.TextUnformatted(f"Files: {len(region.paths)}")
        if isinstance(region.scene, MeshScene):
            psim.TextUnformatted(f"Mesh nodes: {region.scene.original_node_count}")
            if len(region.scene.node_ids) > region.scene.original_node_count:
                psim.TextUnformatted(
                    f"Hermite display samples: {len(region.scene.node_ids) - region.scene.original_node_count}"
                )
            psim.TextUnformatted(f"Segments: {len(region.scene.edges)}")
        elif isinstance(region.scene, PointScene):
            psim.TextUnformatted(f"Points: {len(region.scene.node_ids)}")
        elif isinstance(region.scene, SurfaceScene):
            psim.TextUnformatted(f"Surface vertices: {len(region.scene.vertices)}")
            psim.TextUnformatted(f"Triangles: {len(region.scene.faces)}")

        if isinstance(region.scene, SurfaceScene):
            changed, opacity = psim.SliderFloat(
                "Surface opacity", region.surface_opacity, 0.0, 1.0
            )
            if changed:
                self._set_surface_opacity(region, opacity)
            psim.TextWrapped(
                "Opacity is independent for each surface region: 0 is transparent "
                "and 1 is opaque."
            )

        changed, enabled = psim.Checkbox("Alignment transform gizmo", region.transform_gizmo)
        if changed:
            self._set_region_gizmo(region, enabled)
        self._draw_node_edit_panel(psim, region)

        coordinate_options = coordinate_field_names(region.edit_documents)
        if coordinate_options:
            changed, value = psim.Combo(
                "Coordinates", region.coordinate_index, coordinate_options
            )
            if changed:
                region.coordinate_index = value
                self._register_region(region)
        if region.scalar_options:
            changed, value = psim.Combo(
                "Colour by", region.scalar_index, region.scalar_options
            )
            if changed:
                region.scalar_index = value
                self._set_scalar(region)
            if psim.Button("Apply colour field"):
                self._set_scalar(region)
            selected_name = region.scalar_options[region.scalar_index]
            selected = region.scalar_values[selected_name]
            finite = selected[np.isfinite(selected)]
            if finite.size:
                psim.TextUnformatted(f"Range: {finite.min():.6g} to {finite.max():.6g}")
            if "flow" in selected_name.lower():
                changed, logarithmic = psim.Checkbox(
                    "Logarithmic flow colours", region.log_flow_colours
                )
                if changed:
                    region.log_flow_colours = logarithmic
                    self._set_scalar(region)
                if region.log_flow_colours:
                    try:
                        _logged, floor, clamped = _log10_colour_values(selected)
                        lower, upper, data_lower, data_upper = self._log_flow_bounds(
                            region, selected_name
                        )
                        bounds_changed = False
                        if data_lower < data_upper:
                            lower_changed, new_lower = psim.SliderFloat(
                                "Flow colour lower bound",
                                lower,
                                data_lower,
                                data_upper,
                                "%.6g",
                                psim.ImGuiSliderFlags_Logarithmic,
                            )
                            upper_changed, new_upper = psim.SliderFloat(
                                "Flow colour upper bound",
                                upper,
                                data_lower,
                                data_upper,
                                "%.6g",
                                psim.ImGuiSliderFlags_Logarithmic,
                            )
                            if lower_changed or upper_changed:
                                lower = float(new_lower)
                                upper = float(new_upper)
                                if lower >= upper:
                                    if lower_changed and not upper_changed:
                                        lower = float(np.nextafter(upper, -np.inf))
                                    else:
                                        upper = float(np.nextafter(lower, np.inf))
                                region.log_flow_bounds[selected_name] = (lower, upper)
                                lower, upper, _data_lower, _data_upper = (
                                    self._log_flow_bounds(region, selected_name)
                                )
                                bounds_changed = True
                        if psim.Button("Reset flow colour bounds"):
                            region.log_flow_bounds.pop(selected_name, None)
                            lower, upper, _data_lower, _data_upper = (
                                self._log_flow_bounds(region, selected_name)
                            )
                            bounds_changed = True
                        if bounds_changed:
                            self._set_scalar(region)
                        psim.TextUnformatted(
                            f"Active flow bounds: {lower:.6g} to {upper:.6g}"
                        )
                        psim.TextUnformatted(
                            "Polyscope log10 bounds: "
                            f"{np.log10(lower):.6g} to {np.log10(upper):.6g}"
                        )
                        if clamped:
                            psim.TextWrapped(
                                f"{clamped} non-positive value(s) use the lowest colour "
                                f"at the smallest positive flow ({floor:.6g})."
                            )
                        psim.TextWrapped(
                            "Display only: colours use log10(flow); imported flow values "
                            "and exported files are unchanged."
                        )
                    except ValueError as exc:
                        psim.TextWrapped(str(exc))

            if region.network is not None:
                changed, value = psim.Combo(
                    "Tube radius", region.radius_index, region.radius_options
                )
                if changed:
                    region.radius_index = value
                    self._set_radius(region)
                changed, radius_scale = psim.SliderFloat(
                    "Radius scale",
                    region.radius_scale,
                    0.001,
                    10.0,
                    "%.3g x",
                    psim.ImGuiSliderFlags_Logarithmic,
                )
                if changed:
                    region.radius_scale = float(radius_scale)
                    self._set_radius(region)
                if psim.Button("Use physical radius (1 x)"):
                    region.radius_scale = 1.0
                    self._set_radius(region)
                if region.radius_index > 0:
                    radius_name = region.radius_options[region.radius_index]
                    if region.scalar_locations.get(radius_name) == "edges":
                        changed, smooth_joins = psim.Checkbox(
                            "Smooth tube joins", region.smooth_radius_joins
                        )
                        if changed:
                            region.smooth_radius_joins = smooth_joins
                            self._set_radius(region)
                        psim.TextWrapped(
                            "Display only: uses shared node radii to cover tube joins. "
                            "Rounded inlet and terminal caps end at the original node "
                            "coordinates without protruding as node blobs. The loaded "
                            "geometry, connectivity, and radius field are unchanged."
                        )
                    raw_radius = region.scalar_values[radius_name]
                    finite_radius = raw_radius[np.isfinite(raw_radius)]
                    if finite_radius.size:
                        psim.TextUnformatted(
                            "Displayed radius range: "
                            f"{finite_radius.min() * region.radius_scale:.6g} to "
                            f"{finite_radius.max() * region.radius_scale:.6g}"
                        )
                psim.TextWrapped(
                    "Colour maps values without changing geometry. Tube radius changes "
                    "thickness independently. Fields marked [elements] belong to vessel "
                    "segments; unmarked fields belong to nodes. Flow uses a linear colour "
                    "range, adjustable in Polyscope's Scene panel. Radius scale multiplies "
                    "the imported values; 1 x uses their physical coordinate units."
                )

        if region.warnings and psim.TreeNode("Import warnings"):
            for warning in region.warnings:
                psim.BulletText(warning)
            psim.TreePop()
        if psim.TreeNode("Region files"):
            for path in region.paths:
                psim.BulletText(path.name)
            psim.TreePop()

    def _draw_ct_panel(self, psim) -> None:
        if psim.Button("Load DICOM folder..."):
            try:
                selected = choose_dicom_directory()
                if selected:
                    self.load_ct(load_dicom_directory(selected))
            except Exception as exc:
                self.message = f"Could not load DICOM: {exc}"
        psim.SameLine()
        if psim.Button("Load NIfTI..."):
            try:
                selected = choose_nifti_file()
                if selected:
                    self.load_ct(load_nifti(selected))
            except Exception as exc:
                self.message = f"Could not load NIfTI: {exc}"

        if self.ct_volume is not None:
            volume = self.ct_volume
            psim.TextUnformatted(f"CT: {volume.name}")
            psim.TextUnformatted(
                f"Voxels: {volume.values.shape[0]} x {volume.values.shape[1]} x {volume.values.shape[2]}"
            )
            psim.TextUnformatted(
                "Spacing: " + " x ".join(f"{value:.4g}" for value in volume.spacing)
            )
            if psim.Button("Reset CT slices"):
                self.reset_ct_planes()
            psim.SameLine()
            if psim.Button("Unload CT"):
                self.unload_ct()
                return

            for slice_state in self.ct_slices:
                changed, visible = psim.Checkbox(
                    f"Show {slice_state.name}", slice_state.visible
                )
                if changed:
                    slice_state.visible = visible
                    slice_state.structure.set_enabled(visible)
                changed, index = psim.SliderInt(
                    f"{slice_state.name} slice",
                    slice_state.index,
                    0,
                    volume.values.shape[slice_state.axis] - 1,
                )
                if changed:
                    slice_state.index = index
                    slice_state.base_vertices, _faces = _slice_geometry(
                        volume, slice_state.axis, index
                    )
                    self._update_ct_slice(slice_state)

            if self.ct_slices:
                changed, selected_index = psim.Combo(
                    "Plane to rotate",
                    self.selected_ct_slice_index,
                    [slice_state.name for slice_state in self.ct_slices],
                )
                if changed:
                    self._set_ct_slice_gizmo(self.selected_ct_slice_index, False)
                    self.selected_ct_slice_index = selected_index
                selected = self.ct_slices[self.selected_ct_slice_index]
                changed, enabled = psim.Checkbox(
                    "Plane transform gizmo", selected.transform_gizmo
                )
                if changed:
                    self._set_ct_slice_gizmo(
                        self.selected_ct_slice_index, enabled
                    )
            psim.TextWrapped(
                "The three slices start hidden. Use the sliders to move through native "
                "axial, coronal, and sagittal sections. The transform gizmo can translate "
                "or rotate one selected plane and the grayscale image is resampled."
            )
            if volume.warnings and psim.TreeNode("CT warnings"):
                for warning in volume.warnings:
                    psim.BulletText(warning)
                psim.TreePop()

    def callback(self) -> None:
        import polyscope as ps
        import polyscope.imgui as psim

        self._sync_region_transforms()
        self._sync_ct_slice_transforms()
        self._sync_node_edit_gizmo(psim)
        self._consume_node_pick(ps, psim)
        self._consume_native_screenshot()
        self._consume_screenshot_shortcut(psim)
        psim.TextUnformatted("LungViZ")
        psim.TextWrapped(self.message)
        psim.SeparatorText("Geometry regions")
        self._draw_region_panel(psim)
        psim.SeparatorText("CT volume")
        self._draw_ct_panel(psim)
        psim.Separator()
        if psim.Button("Clear everything"):
            self.clear()
        psim.TextWrapped(
            "Polyscope's Scene panel provides picking, field colour maps, screenshots, "
            "visibility, and per-structure options. Press Ctrl+Shift+S for a named "
            "screenshot in a chosen folder."
        )

    def run(self, initial_paths: Sequence[str | Path] = ()) -> None:
        import polyscope as ps

        ps.set_program_name("LungViZ")
        ps.init()
        self._native_screenshot_snapshot = self._native_screenshot_files()
        ps.set_ground_plane_mode("none")
        ps.set_navigation_style("free")
        ps.set_files_dropped_callback(self._files_dropped)
        if initial_paths:
            self.load_files_as_regions(initial_paths)
        ps.set_user_callback(self.callback)
        ps.show()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lungviz",
        description=(
            "Inspect OpenCMISS EX data, triangulated surfaces, and CT volumes "
            "in Polyscope."
        ),
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Optional EX files to load together as the first region",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    LungVizApplication().run(args.files)
    return 0
