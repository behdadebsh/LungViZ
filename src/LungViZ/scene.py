"""Combine independently loaded EX files into arrays suitable for Polyscope."""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, Iterable, List, Mapping, Tuple

import numpy as np

from .exfile import ExFileError
from .model import ElementDocument, MeshScene, NodeDocument, SceneField


def coordinate_field_names(documents: Iterable[NodeDocument]) -> List[str]:
    names: List[str] = []
    for document in documents:
        for name, definition in document.fields.items():
            if definition.is_coordinate and name not in names:
                names.append(name)
    return names


def build_mesh_scene(
    node_documents: Iterable[NodeDocument],
    element_documents: Iterable[ElementDocument],
    coordinate_field: str | None = None,
) -> MeshScene:
    node_documents = list(node_documents)
    element_documents = list(element_documents)
    if not node_documents:
        raise ExFileError("Load at least one .exnode file to provide mesh coordinates")
    if not element_documents:
        raise ExFileError("Load at least one .exelem file to provide mesh connectivity")

    coordinate_options = coordinate_field_names(node_documents)
    if coordinate_field is None:
        coordinate_field = coordinate_options[0] if coordinate_options else ""
    if not coordinate_field:
        raise ExFileError("No coordinate field was found in the loaded node files")

    merged: "OrderedDict[int, Dict[str, np.ndarray]]" = OrderedDict()
    definitions = {}
    warnings: List[str] = []
    for document in node_documents:
        warnings.extend(document.warnings)
        definitions.update(document.fields)
        for node in document.nodes:
            merged.setdefault(node.identifier, {}).update(node.fields)

    usable_ids = [
        node_id
        for node_id, values in merged.items()
        if coordinate_field in values and np.all(np.isfinite(values[coordinate_field]))
    ]
    if not usable_ids:
        raise ExFileError(f"No nodes contain finite values for {coordinate_field!r}")
    index_by_id = {node_id: index for index, node_id in enumerate(usable_ids)}

    coordinates = np.full((len(usable_ids), 3), 0.0, dtype=float)
    for index, node_id in enumerate(usable_ids):
        raw = merged[node_id][coordinate_field]
        coordinates[index, : min(3, raw.size)] = raw[:3]

    edges: List[Tuple[int, int]] = []
    edge_element_ids: List[int] = []
    missing_ids = set()
    skipped_dimensions = set()
    for document in element_documents:
        warnings.extend(document.warnings)
        for element in document.elements:
            if element.dimension != 1:
                skipped_dimensions.add(element.dimension)
                continue
            for first, second in zip(element.node_ids, element.node_ids[1:]):
                if first not in index_by_id or second not in index_by_id:
                    missing_ids.update(
                        node_id
                        for node_id in (first, second)
                        if node_id not in index_by_id
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

    fields: Dict[str, SceneField] = {}
    for field_name, definition in definitions.items():
        component_count = len(definition.components)
        array = np.full((len(usable_ids), component_count), np.nan, dtype=float)
        for index, node_id in enumerate(usable_ids):
            raw = merged[node_id].get(field_name)
            if raw is not None:
                array[index, : min(component_count, raw.size)] = raw[:component_count]
        fields[field_name] = SceneField(
            name=field_name,
            component_names=tuple(component.name for component in definition.components),
            values=array,
        )

    return MeshScene(
        coordinates=coordinates,
        node_ids=np.asarray(usable_ids, dtype=int),
        edges=np.asarray(edges, dtype=int),
        edge_element_ids=np.asarray(edge_element_ids, dtype=int),
        fields=fields,
        coordinate_field=coordinate_field,
        warnings=warnings,
    )


def scalar_variants(scene: MeshScene) -> Mapping[str, np.ndarray]:
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

