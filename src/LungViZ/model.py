"""Data structures shared by the EX parsers and visualisation layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


@dataclass(frozen=True)
class ComponentDefinition:
    name: str
    value_index: int
    derivatives: int = 0
    versions: int = 1

    @property
    def parameter_count(self) -> int:
        return (1 + self.derivatives) * self.versions


@dataclass(frozen=True)
class FieldDefinition:
    name: str
    field_type: str
    coordinate_system: str
    components: Tuple[ComponentDefinition, ...]

    @property
    def is_coordinate(self) -> bool:
        return self.field_type.lower() == "coordinate" or self.name.lower() in {
            "coordinate",
            "coordinates",
        }


@dataclass
class NodeRecord:
    identifier: int
    fields: Dict[str, np.ndarray]
    derivatives: Dict[str, np.ndarray] = field(default_factory=dict)


@dataclass
class NodeDocument:
    path: Path
    group_name: str = ""
    fields: Dict[str, FieldDefinition] = field(default_factory=dict)
    nodes: List[NodeRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    is_data: bool = False


@dataclass(frozen=True)
class ElementFieldDefinition:
    name: str
    field_type: str
    coordinate_system: str
    component_names: Tuple[str, ...]
    component_value_counts: Tuple[int, ...]

    @property
    def value_count(self) -> int:
        return sum(self.component_value_counts)


@dataclass(frozen=True)
class ElementRecord:
    identifier: Tuple[int, int, int]
    dimension: int
    node_ids: Tuple[int, ...]
    interpolation: str = "linear"
    scale_factors: Tuple[float, ...] = ()
    fields: Dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def display_identifier(self) -> int:
        return next((value for value in self.identifier if value), 0)


@dataclass
class ElementDocument:
    path: Path
    group_name: str = ""
    fields: Dict[str, ElementFieldDefinition] = field(default_factory=dict)
    elements: List[ElementRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class SceneField:
    name: str
    component_names: Tuple[str, ...]
    values: np.ndarray


@dataclass
class MeshScene:
    coordinates: np.ndarray
    node_ids: np.ndarray
    edges: np.ndarray
    edge_element_ids: np.ndarray
    fields: Dict[str, SceneField]
    coordinate_field: str
    edge_fields: Dict[str, SceneField] = field(default_factory=dict)
    original_node_count: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class PointScene:
    coordinates: np.ndarray
    node_ids: np.ndarray
    fields: Dict[str, SceneField]
    coordinate_field: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class SurfaceScene:
    vertices: np.ndarray
    faces: np.ndarray
    warnings: List[str] = field(default_factory=list)
