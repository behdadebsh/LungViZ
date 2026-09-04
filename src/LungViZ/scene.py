"""Build isolated Polyscope-ready scenes from OpenCMISS EX regions."""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, Iterable, List, Mapping, Tuple

import numpy as np

from .exfile import ExFileError
from .model import ElementDocument, MeshScene, NodeDocument, PointScene, SceneField


def coordinate_field_names(documents: Iterable[NodeDocument]) -> List[str]:
    names: List[str] = []
    for document in documents:
        for name, definition in document.fields.items():
            if definition.is_coordinate and name not in names:
                names.append(name)
    return names


def _merge_nodes(node_documents: Iterable[NodeDocument]):
    values: "OrderedDict[int, Dict[str, np.ndarray]]" = OrderedDict()
    derivatives: "OrderedDict[int, Dict[str, np.ndarray]]" = OrderedDict()
    definitions = {}
    warnings: List[str] = []
    for document in node_documents:
        warnings.extend(document.warnings)
        definitions.update(document.fields)
        for node in document.nodes:
            values.setdefault(node.identifier, {}).update(node.fields)
            derivatives.setdefault(node.identifier, {}).update(node.derivatives)
    return values, derivatives, definitions, warnings


def _field_arrays(usable_ids, merged, definitions):
    arrays: Dict[str, np.ndarray] = {}
    for field_name, definition in definitions.items():
        component_count = len(definition.components)
        values = np.full((len(usable_ids), component_count), np.nan, dtype=float)
        for index, node_id in enumerate(usable_ids):
            raw = merged[node_id].get(field_name)
            if raw is not None:
                values[index, : min(component_count, raw.size)] = raw[:component_count]
        arrays[field_name] = values
    return arrays


def build_point_scene(
    node_documents: Iterable[NodeDocument], coordinate_field: str | None = None
) -> PointScene:
    """Build an isolated point scene from one region's node documents."""

    node_documents = list(node_documents)
    if not node_documents:
        raise ExFileError("The region has no node data")
    coordinate_options = coordinate_field_names(node_documents)
    if coordinate_field is None:
        coordinate_field = coordinate_options[0] if coordinate_options else ""
    if not coordinate_field:
        raise ExFileError("No coordinate field was found in the region")

    merged, _derivatives, definitions, warnings = _merge_nodes(node_documents)
    usable_ids = [
        node_id
        for node_id, values in merged.items()
        if coordinate_field in values and np.all(np.isfinite(values[coordinate_field]))
    ]
    if not usable_ids:
        raise ExFileError(f"No nodes contain finite values for {coordinate_field!r}")

    coordinates = np.zeros((len(usable_ids), 3), dtype=float)
    for index, node_id in enumerate(usable_ids):
        raw = merged[node_id][coordinate_field]
        coordinates[index, : min(3, raw.size)] = raw[:3]

    arrays = _field_arrays(usable_ids, merged, definitions)
    fields = {
        name: SceneField(
            name=name,
            component_names=tuple(component.name for component in definitions[name].components),
            values=values,
        )
        for name, values in arrays.items()
    }
    return PointScene(
        coordinates=coordinates,
        node_ids=np.asarray(usable_ids, dtype=int),
        fields=fields,
        coordinate_field=coordinate_field,
        warnings=warnings,
    )


def _cubic_hermite(
    first: np.ndarray,
    first_derivative: np.ndarray,
    second: np.ndarray,
    second_derivative: np.ndarray,
    xi: float,
    first_scale: float,
    second_scale: float,
) -> np.ndarray:
    xi2 = xi * xi
    xi3 = xi2 * xi
    return (
        (2 * xi3 - 3 * xi2 + 1) * first
        + (xi3 - 2 * xi2 + xi) * first_derivative * first_scale
        + (-2 * xi3 + 3 * xi2) * second
        + (xi3 - xi2) * second_derivative * second_scale
    )


def build_mesh_scene(
    node_documents: Iterable[NodeDocument],
    element_documents: Iterable[ElementDocument],
    coordinate_field: str | None = None,
    *,
    hermite_subdivisions: int = 12,
) -> MeshScene:
    """Build a 1D scene, sampling cubic Hermite elements when defined."""

    node_documents = list(node_documents)
    element_documents = list(element_documents)
    if not node_documents:
        raise ExFileError("Load at least one .exnode file to provide mesh coordinates")
    if not element_documents:
        raise ExFileError("Load at least one .exelem file to provide mesh connectivity")
    if hermite_subdivisions < 1:
        raise ValueError("hermite_subdivisions must be at least 1")

    coordinate_options = coordinate_field_names(node_documents)
    if coordinate_field is None:
        coordinate_field = coordinate_options[0] if coordinate_options else ""
    if not coordinate_field:
        raise ExFileError("No coordinate field was found in the loaded node files")

    merged, derivatives, definitions, warnings = _merge_nodes(node_documents)
    usable_ids = [
        node_id
        for node_id, values in merged.items()
        if coordinate_field in values and np.all(np.isfinite(values[coordinate_field]))
    ]
    if not usable_ids:
        raise ExFileError(f"No nodes contain finite values for {coordinate_field!r}")
    index_by_id = {node_id: index for index, node_id in enumerate(usable_ids)}

    base_coordinates = np.zeros((len(usable_ids), 3), dtype=float)
    base_coordinate_derivatives = np.full((len(usable_ids), 3), np.nan, dtype=float)
    for index, node_id in enumerate(usable_ids):
        raw = merged[node_id][coordinate_field]
        base_coordinates[index, : min(3, raw.size)] = raw[:3]
        derivative = derivatives.get(node_id, {}).get(coordinate_field)
        if derivative is not None:
            base_coordinate_derivatives[index, : min(3, derivative.size)] = derivative[:3]
            if derivative.size < 3:
                base_coordinate_derivatives[index, derivative.size :] = 0.0

    base_fields = _field_arrays(usable_ids, merged, definitions)
    display_coordinates = [row.copy() for row in base_coordinates]
    display_node_ids = list(usable_ids)
    display_fields = {
        name: [row.copy() for row in values] for name, values in base_fields.items()
    }
    edges: List[Tuple[int, int]] = []
    edge_element_ids: List[int] = []
    missing_ids = set()
    skipped_dimensions = set()
    warned_missing_derivatives = False

    def append_interpolated(first_index: int, second_index: int, xi: float, point):
        new_index = len(display_coordinates)
        display_coordinates.append(point)
        display_node_ids.append(0)
        for field_name, values in base_fields.items():
            if field_name == coordinate_field:
                interpolated = point[: values.shape[1]]
            else:
                interpolated = (1.0 - xi) * values[first_index] + xi * values[second_index]
            display_fields[field_name].append(interpolated)
        return new_index

    for document in element_documents:
        warnings.extend(document.warnings)
        for element in document.elements:
            if element.dimension != 1:
                skipped_dimensions.add(element.dimension)
                continue
            if any(node_id not in index_by_id for node_id in element.node_ids):
                missing_ids.update(
                    node_id for node_id in element.node_ids if node_id not in index_by_id
                )
                continue

            if element.interpolation == "cubic_hermite" and len(element.node_ids) == 2:
                first_index = index_by_id[element.node_ids[0]]
                second_index = index_by_id[element.node_ids[1]]
                first_derivative = base_coordinate_derivatives[first_index]
                second_derivative = base_coordinate_derivatives[second_index]
                can_interpolate = np.all(np.isfinite(first_derivative)) and np.all(
                    np.isfinite(second_derivative)
                )
                if can_interpolate and hermite_subdivisions > 1:
                    first_scale = element.scale_factors[0] if element.scale_factors else 1.0
                    second_scale = (
                        element.scale_factors[1]
                        if len(element.scale_factors) > 1
                        else first_scale
                    )
                    previous = first_index
                    for xi in np.linspace(0.0, 1.0, hermite_subdivisions + 1)[1:-1]:
                        point = _cubic_hermite(
                            base_coordinates[first_index],
                            first_derivative,
                            base_coordinates[second_index],
                            second_derivative,
                            float(xi),
                            first_scale,
                            second_scale,
                        )
                        current = append_interpolated(
                            first_index, second_index, float(xi), point
                        )
                        edges.append((previous, current))
                        edge_element_ids.append(element.display_identifier)
                        previous = current
                    edges.append((previous, second_index))
                    edge_element_ids.append(element.display_identifier)
                    continue
                if not can_interpolate and not warned_missing_derivatives:
                    warnings.append(
                        "Cubic Hermite interpolation was declared but coordinate derivatives "
                        "were unavailable; affected elements use straight segments"
                    )
                    warned_missing_derivatives = True

            for first, second in zip(element.node_ids, element.node_ids[1:]):
                if first == second:
                    warnings.append(
                        f"Element {element.identifier} contains a repeated node {first}; "
                        "the zero-length segment was skipped"
                    )
                    continue
                edges.append((index_by_id[first], index_by_id[second]))
                edge_element_ids.append(element.display_identifier)

    if skipped_dimensions:
        warnings.append(
            "Ignored non-1D element dimensions: "
            + ", ".join(str(value) for value in sorted(skipped_dimensions))
        )
    if missing_ids:
        warnings.append(
            f"Skipped connectivity referencing {len(missing_ids)} node(s) without coordinates"
        )
    if not edges:
        raise ExFileError("No drawable 1D connectivity matched the loaded coordinate nodes")

    fields = {
        name: SceneField(
            name=name,
            component_names=tuple(component.name for component in definitions[name].components),
            values=np.asarray(values, dtype=float),
        )
        for name, values in display_fields.items()
    }
    return MeshScene(
        coordinates=np.asarray(display_coordinates, dtype=float),
        node_ids=np.asarray(display_node_ids, dtype=int),
        edges=np.asarray(edges, dtype=int),
        edge_element_ids=np.asarray(edge_element_ids, dtype=int),
        fields=fields,
        coordinate_field=coordinate_field,
        original_node_count=len(usable_ids),
        warnings=warnings,
    )


def scalar_variants(scene: MeshScene | PointScene) -> Mapping[str, np.ndarray]:
    """Return display-ready scalar component and magnitude arrays."""

    variants: "OrderedDict[str, np.ndarray]" = OrderedDict()
    for field_name, field in scene.fields.items():
        if field.values.shape[1] == 1:
            variants[field_name] = field.values[:, 0]
            continue
        for index, component_name in enumerate(field.component_names):
            variants[f"{field_name}.{component_name}"] = field.values[:, index]
        variants[f"{field_name}.magnitude"] = np.linalg.norm(field.values, axis=1)
    return variants
