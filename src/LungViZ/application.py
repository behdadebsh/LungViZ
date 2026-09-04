"""Interactive Polyscope application for regional EX data and CT volumes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

from .exfile import ExFileError, load_ex_file
from .model import ElementDocument, MeshScene, NodeDocument, PointScene
from .scene import (
    build_mesh_scene,
    build_point_scene,
    coordinate_field_names,
    scalar_variants,
)
from .volume import CTVolume, load_dicom_directory, load_nifti


def choose_ex_files() -> Sequence[str]:
    """Choose the files which make up one isolated EX region."""

    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilenames(
            title="Load one EX region",
            filetypes=[
                ("OpenCMISS EX files", "*.exnode *.exelem *.exdata"),
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


def _finite_for_display(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    replacement = float(np.median(finite)) if finite.size else 0.0
    return np.nan_to_num(values, nan=replacement, posinf=replacement, neginf=replacement)


@dataclass
class RegionState:
    """All data and UI state belonging to one node-identifier namespace."""

    key: int
    name: str
    paths: List[Path] = field(default_factory=list)
    node_documents: List[NodeDocument] = field(default_factory=list)
    data_documents: List[NodeDocument] = field(default_factory=list)
    element_documents: List[ElementDocument] = field(default_factory=list)
    scene: MeshScene | PointScene | None = None
    structures: List[object] = field(default_factory=list)
    field_structure: object | None = None
    network: object | None = None
    scalar_values: Dict[str, np.ndarray] = field(default_factory=dict)
    scalar_options: List[str] = field(default_factory=list)
    radius_options: List[str] = field(default_factory=lambda: ["Constant"])
    coordinate_index: int = 0
    scalar_index: int = 0
    radius_index: int = 0
    transform_gizmo: bool = False
    transform: np.ndarray = field(default_factory=lambda: np.eye(4, dtype=float))
    message: str = ""
    warnings: List[str] = field(default_factory=list)


class LungVizApplication:
    def __init__(self) -> None:
        self.regions: List[RegionState] = []
        self.selected_region_index = 0
        self._next_region_key = 1
        self.ct_volume: CTVolume | None = None
        self.ct_structure = None
        self.slice_planes: List[object] = []
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
        if len(set(group_names)) > 1:
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
        for structure in region.structures:
            try:
                structure.remove()
            except (AttributeError, RuntimeError):
                pass
        region.structures.clear()
        region.field_structure = None
        region.network = None

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
        region.scalar_values.clear()
        region.scalar_options.clear()
        region.radius_options = ["Constant"]
        region.warnings.clear()
        region.message = ""
        coordinate_options = coordinate_field_names(region.node_documents)
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
                network = ps.register_curve_network(
                    f"{region.name} / 1D mesh",
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
                region.scalar_values = dict(scalar_variants(mesh))
                for field_name, values in region.scalar_values.items():
                    network.add_scalar_quantity(
                        field_name, _finite_for_display(values), enabled=False
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
                region.network = network
                region.field_structure = network
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
                    cloud = ps.register_point_cloud(
                        f"{region.name} / nodes (connectivity unavailable)",
                        points.coordinates,
                        radius=0.008,
                    )
                    region.scalar_values = self._add_point_fields(cloud, points)
                    region.field_structure = cloud
                    region.structures.append(cloud)
                    region.warnings.extend(points.warnings)
                except ExFileError:
                    pass

        elif region.node_documents:
            try:
                points = build_point_scene(region.node_documents, coordinate_name)
                region.scene = points
                cloud = ps.register_point_cloud(
                    f"{region.name} / nodes", points.coordinates, radius=0.008
                )
                region.scalar_values = self._add_point_fields(cloud, points)
                region.field_structure = cloud
                region.structures.append(cloud)
                region.warnings.extend(points.warnings)
                region.message = f"{len(points.node_ids)} standalone nodes"
            except ExFileError as exc:
                region.message = f"Node cloud could not be built: {exc}"
        elif region.element_documents:
            region.message = "Connectivity loaded; add an exnode file to this region."

        for data_index, document in enumerate(region.data_documents, start=1):
            try:
                points = build_point_scene([document])
            except ExFileError as exc:
                region.warnings.append(f"{document.path.name}: {exc}")
                continue
            label = document.group_name or document.path.stem or f"data {data_index}"
            cloud = ps.register_point_cloud(
                f"{region.name} / data / {label}", points.coordinates, radius=0.008
            )
            self._add_point_fields(cloud, points, identifier_name="point identifier")
            region.structures.append(cloud)
            region.warnings.extend(points.warnings)

        region.scalar_options = list(region.scalar_values)
        region.radius_options = ["Constant"] + region.scalar_options
        region.scalar_index = min(
            region.scalar_index, max(0, len(region.scalar_options) - 1)
        )
        region.radius_index = min(region.radius_index, len(region.radius_options) - 1)
        for structure in region.structures:
            try:
                structure.set_transform(region.transform)
            except AttributeError:
                pass
            for plane in self.slice_planes:
                try:
                    structure.set_ignore_slice_plane(plane.get_name(), True)
                except AttributeError:
                    pass
        self._set_region_gizmo(region, region.transform_gizmo)

    def _set_region_gizmo(self, region: RegionState, enabled: bool) -> None:
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
        region.field_structure.add_scalar_quantity(
            name, _finite_for_display(region.scalar_values[name]), enabled=True
        )

    def _set_radius(self, region: RegionState) -> None:
        if region.network is None:
            return
        if region.radius_index == 0:
            region.network.clear_node_radius_quantity()
            return
        name = region.radius_options[region.radius_index]
        values = np.clip(_finite_for_display(region.scalar_values[name]), 0.0, None)
        quantity_name = f"radius: {name}"
        region.network.add_scalar_quantity(quantity_name, values, enabled=False)
        region.network.set_node_radius_quantity(quantity_name, autoscale=True)

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
        for plane in self.slice_planes:
            try:
                plane.remove()
            except (AttributeError, RuntimeError):
                pass
        self.slice_planes.clear()
        if self.ct_structure is not None:
            try:
                self.ct_structure.remove()
            except (AttributeError, RuntimeError):
                pass
        self.ct_structure = None

    def load_ct(self, volume: CTVolume) -> None:
        import polyscope as ps

        self._remove_ct()
        self.ct_volume = volume
        self.ct_structure = ps.register_volume_grid(
            f"CT / {volume.name}",
            volume.values.shape,
            (0.0, 0.0, 0.0),
            volume.bound_high,
            edge_width=0.0,
        )
        self.ct_structure.set_transform(volume.transform)
        self.ct_structure.add_scalar_quantity(
            "CT intensity",
            volume.values,
            defined_on="nodes",
            enabled=True,
            cmap="blues",
            vminmax=volume.display_range,
        )
        self.reset_ct_planes()
        self.message = f"Loaded CT volume {volume.name!r}."

    def reset_ct_planes(self) -> None:
        import polyscope as ps

        if self.ct_volume is None:
            return
        for plane in self.slice_planes:
            try:
                plane.remove()
            except (AttributeError, RuntimeError):
                pass
        self.slice_planes.clear()
        for axis_index, color in enumerate(
            ((0.9, 0.25, 0.25), (0.25, 0.9, 0.25), (0.25, 0.45, 0.95))
        ):
            plane = ps.add_scene_slice_plane()
            plane.set_pose(
                self.ct_volume.center_world,
                self.ct_volume.world_axes[:, axis_index],
            )
            plane.set_draw_plane(True)
            plane.set_draw_widget(True)
            plane.set_grid_line_color(color)
            plane.set_transparency(0.18)
            self.slice_planes.append(plane)
        for region in self.regions:
            for structure in region.structures:
                for plane in self.slice_planes:
                    try:
                        structure.set_ignore_slice_plane(plane.get_name(), True)
                    except AttributeError:
                        pass

    def clear(self) -> None:
        import polyscope as ps

        self._remove_ct()
        ps.remove_all_structures()
        self.regions.clear()
        self.selected_region_index = 0
        self.ct_volume = None
        self.message = "Scene cleared."

    def _draw_region_panel(self, psim) -> None:
        if psim.Button("Load EX as new region..."):
            try:
                selected = choose_ex_files()
                if selected:
                    self.load_region(selected)
            except Exception as exc:
                self.message = f"Could not load EX region: {exc}"

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

        changed, enabled = psim.Checkbox("Alignment transform gizmo", region.transform_gizmo)
        if changed:
            self._set_region_gizmo(region, enabled)

        coordinate_options = coordinate_field_names(region.node_documents)
        if coordinate_options:
            changed, value = psim.Combo(
                "Coordinates", region.coordinate_index, coordinate_options
            )
            if changed:
                region.coordinate_index = value
                self._register_region(region)
        if region.scalar_options:
            changed, value = psim.Combo(
                "Colour field", region.scalar_index, region.scalar_options
            )
            if changed:
                region.scalar_index = value
                self._set_scalar(region)
            if psim.Button("Show selected field"):
                self._set_scalar(region)
            selected = region.scalar_values[region.scalar_options[region.scalar_index]]
            finite = selected[np.isfinite(selected)]
            if finite.size:
                psim.TextUnformatted(f"Range: {finite.min():.6g} to {finite.max():.6g}")

            if region.network is not None:
                changed, value = psim.Combo(
                    "Radius field", region.radius_index, region.radius_options
                )
                if changed:
                    region.radius_index = value
                    self._set_radius(region)

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
            if psim.Button("Reset three CT planes"):
                self.reset_ct_planes()
            psim.TextWrapped(
                "Use each coloured plane widget to translate or rotate its slice. "
                "Enable a region's alignment gizmo if its coordinate frame needs adjustment."
            )
            if volume.warnings and psim.TreeNode("CT warnings"):
                for warning in volume.warnings:
                    psim.BulletText(warning)
                psim.TreePop()

    def callback(self) -> None:
        import polyscope.imgui as psim

        self._sync_region_transforms()
        psim.TextUnformatted("LungViZ")
        psim.TextWrapped(self.message)
        psim.SeparatorText("EX regions")
        self._draw_region_panel(psim)
        psim.SeparatorText("CT volume")
        self._draw_ct_panel(psim)
        psim.Separator()
        if psim.Button("Clear everything"):
            self.clear()
        psim.TextWrapped(
            "Polyscope's Scene panel provides picking, field colour maps, screenshots, "
            "visibility, and per-structure options."
        )

    def run(self, initial_paths: Sequence[str | Path] = ()) -> None:
        import polyscope as ps

        ps.set_program_name("LungViZ")
        ps.init()
        ps.set_ground_plane_mode("none")
        if initial_paths:
            self.load_region(initial_paths)
        ps.set_user_callback(self.callback)
        ps.show()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lungviz",
        description="Inspect regional OpenCMISS EX data and CT volumes in Polyscope.",
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
