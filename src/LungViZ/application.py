"""Interactive Polyscope application for LungViZ."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Sequence

import numpy as np

from .exfile import ExFileError, load_ex_file
from .model import ElementDocument, MeshScene, NodeDocument
from .scene import build_mesh_scene, coordinate_field_names, scalar_variants


def choose_files() -> Sequence[str]:
    """Open a native multi-file picker without adding a GUI dependency."""

    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:  # pragma: no cover - platform Python packaging issue
        raise RuntimeError("This Python installation does not include tkinter") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilenames(
            title="Load OpenCMISS EX files",
            filetypes=[
                ("OpenCMISS EX files", "*.exnode *.exelem *.exdata"),
                ("All files", "*.*"),
            ],
        )
    finally:
        root.destroy()


def _finite_for_display(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    replacement = float(np.median(finite)) if finite.size else 0.0
    return np.nan_to_num(values, nan=replacement, posinf=replacement, neginf=replacement)


class LungVizApplication:
    def __init__(self) -> None:
        self.node_documents: List[NodeDocument] = []
        self.data_documents: List[NodeDocument] = []
        self.element_documents: List[ElementDocument] = []
        self.loaded_paths: List[Path] = []
        self.scene: MeshScene | None = None
        self.message = "Load matching .exnode and .exelem files to begin."
        self.coordinate_index = 0
        self.scalar_index = 0
        self.radius_index = 0
        self.radius_options = ["Constant"]
        self.scalar_options: List[str] = []
        self.scalar_values = {}
        self.network = None

    def clear(self) -> None:
        import polyscope as ps

        ps.remove_all_structures()
        self.node_documents.clear()
        self.data_documents.clear()
        self.element_documents.clear()
        self.loaded_paths.clear()
        self.scene = None
        self.network = None
        self.scalar_options.clear()
        self.scalar_values = {}
        self.radius_options = ["Constant"]
        self.coordinate_index = self.scalar_index = self.radius_index = 0
        self.message = "Scene cleared."

    def load_paths(self, paths: Sequence[str | Path]) -> None:
        errors: List[str] = []
        for raw_path in paths:
            path = Path(raw_path).expanduser().resolve()
            if path in self.loaded_paths:
                continue
            try:
                document = load_ex_file(path)
            except (ExFileError, OSError) as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            self.loaded_paths.append(path)
            if isinstance(document, ElementDocument):
                self.element_documents.append(document)
            elif document.is_data:
                self.data_documents.append(document)
            else:
                self.node_documents.append(document)

        if self.node_documents and self.element_documents:
            self.rebuild_scene()
        elif self.loaded_paths:
            self.message = "Loaded files; add both mesh coordinates (.exnode) and connectivity (.exelem)."
        if errors:
            self.message = " | ".join(errors)

    def rebuild_scene(self) -> None:
        import polyscope as ps

        options = coordinate_field_names(self.node_documents)
        coordinate_name = options[min(self.coordinate_index, len(options) - 1)] if options else None
        try:
            self.scene = build_mesh_scene(
                self.node_documents, self.element_documents, coordinate_name
            )
        except ExFileError as exc:
            self.message = str(exc)
            return

        ps.remove_all_structures()
        scene = self.scene
        self.network = ps.register_curve_network(
            "1D mesh", scene.coordinates, scene.edges, radius=0.006
        )
        self.network.add_scalar_quantity(
            "node identifier", scene.node_ids.astype(float), enabled=False
        )
        self.network.add_scalar_quantity(
            "element identifier",
            scene.edge_element_ids.astype(float),
            defined_on="edges",
            enabled=False,
        )

        self.scalar_values = dict(scalar_variants(scene))
        self.scalar_options = list(self.scalar_values)
        for name, values in self.scalar_values.items():
            self.network.add_scalar_quantity(name, _finite_for_display(values), enabled=False)
        for field_name, field in scene.fields.items():
            if field.values.shape[1] in (2, 3) and field_name != scene.coordinate_field:
                self.network.add_vector_quantity(
                    field_name, _finite_for_display(field.values), enabled=False
                )

        self.radius_options = ["Constant"] + self.scalar_options
        self.scalar_index = min(self.scalar_index, max(0, len(self.scalar_options) - 1))
        self.radius_index = min(self.radius_index, len(self.radius_options) - 1)
        self._register_data_clouds()
        self.message = f"Loaded {len(scene.node_ids)} nodes and {len(scene.edges)} line segments."

    def _register_data_clouds(self) -> None:
        import polyscope as ps

        for document_index, document in enumerate(self.data_documents, start=1):
            coordinates = coordinate_field_names([document])
            if not coordinates:
                continue
            coordinate_name = coordinates[0]
            points = []
            records = []
            for record in document.nodes:
                if coordinate_name not in record.fields:
                    continue
                coordinate = np.zeros(3, dtype=float)
                raw = record.fields[coordinate_name]
                coordinate[: min(3, raw.size)] = raw[:3]
                points.append(coordinate)
                records.append(record)
            if not points:
                continue
            label = document.group_name or document.path.stem or f"data {document_index}"
            cloud = ps.register_point_cloud(f"data: {label}", np.asarray(points), radius=0.008)
            cloud.add_scalar_quantity(
                "point identifier",
                np.asarray([record.identifier for record in records], dtype=float),
            )
            for field_name, definition in document.fields.items():
                if field_name == coordinate_name:
                    continue
                values = np.full((len(records), len(definition.components)), np.nan)
                for index, record in enumerate(records):
                    if field_name in record.fields:
                        values[index] = record.fields[field_name]
                if values.shape[1] == 1:
                    cloud.add_scalar_quantity(
                        field_name, _finite_for_display(values[:, 0]), enabled=False
                    )
                else:
                    for component_index, component in enumerate(definition.components):
                        cloud.add_scalar_quantity(
                            f"{field_name}.{component.name}",
                            _finite_for_display(values[:, component_index]),
                            enabled=False,
                        )

    def _set_scalar(self) -> None:
        if self.network is None or not self.scalar_options:
            return
        name = self.scalar_options[self.scalar_index]
        self.network.add_scalar_quantity(
            name, _finite_for_display(self.scalar_values[name]), enabled=True
        )

    def _set_radius(self) -> None:
        if self.network is None:
            return
        if self.radius_index == 0:
            self.network.clear_node_radius_quantity()
            return
        name = self.radius_options[self.radius_index]
        values = np.clip(_finite_for_display(self.scalar_values[name]), 0.0, None)
        internal_name = f"radius: {name}"
        self.network.add_scalar_quantity(internal_name, values, enabled=False)
        self.network.set_node_radius_quantity(internal_name, autoscale=True)

    def callback(self) -> None:
        import polyscope.imgui as psim

        psim.TextUnformatted("LungViZ EX Mesh Viewer")
        psim.Separator()
        if psim.Button("Load EX files..."):
            try:
                selected = choose_files()
                if selected:
                    self.load_paths(selected)
            except Exception as exc:  # keep GUI alive after platform dialog errors
                self.message = f"Could not open file picker: {exc}"
        psim.SameLine()
        if psim.Button("Clear"):
            self.clear()

        psim.TextWrapped(self.message)
        psim.Separator()
        psim.TextUnformatted(f"Files: {len(self.loaded_paths)}")
        if self.scene is not None:
            psim.TextUnformatted(f"Nodes: {len(self.scene.node_ids)}")
            psim.TextUnformatted(f"Segments: {len(self.scene.edges)}")
            psim.TextUnformatted(f"Data points: {sum(len(doc.nodes) for doc in self.data_documents)}")

            coordinate_options = coordinate_field_names(self.node_documents)
            if coordinate_options:
                changed, value = psim.Combo(
                    "Coordinates", self.coordinate_index, coordinate_options
                )
                if changed:
                    self.coordinate_index = value
                    self.rebuild_scene()
            if self.scalar_options:
                changed, value = psim.Combo("Colour field", self.scalar_index, self.scalar_options)
                if changed:
                    self.scalar_index = value
                    self._set_scalar()
                if psim.Button("Show selected field"):
                    self._set_scalar()
                selected = self.scalar_values[self.scalar_options[self.scalar_index]]
                finite = selected[np.isfinite(selected)]
                if finite.size:
                    psim.TextUnformatted(f"Range: {finite.min():.6g} to {finite.max():.6g}")

                changed, value = psim.Combo(
                    "Radius field", self.radius_index, self.radius_options
                )
                if changed:
                    self.radius_index = value
                    self._set_radius()

            if self.scene.warnings and psim.TreeNode("Import warnings"):
                for warning in self.scene.warnings:
                    psim.BulletText(warning)
                psim.TreePop()
            if psim.TreeNode("Loaded files"):
                for path in self.loaded_paths:
                    psim.BulletText(path.name)
                psim.TreePop()
            if psim.TreeNode("Available fields"):
                for field in self.scene.fields.values():
                    components = ", ".join(field.component_names)
                    psim.BulletText(f"{field.name} ({components})")
                psim.TreePop()

        psim.Separator()
        psim.TextWrapped(
            "Use the Scene panel to toggle node/element identifiers, vectors, and data point fields. "
            "Click structures in the 3D view to inspect them."
        )

    def run(self, initial_paths: Sequence[str | Path] = ()) -> None:
        import polyscope as ps

        ps.set_program_name("LungViZ")
        ps.init()
        ps.set_ground_plane_mode("none")
        if initial_paths:
            self.load_paths(initial_paths)
        ps.set_user_callback(self.callback)
        ps.show()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lungviz",
        description="Interactively inspect OpenCMISS exnode, exelem, and exdata files.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Optional EX files to load when the viewer starts",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    application = LungVizApplication()
    application.run(args.files)
    return 0

