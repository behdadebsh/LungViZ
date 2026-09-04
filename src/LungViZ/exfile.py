"""Readers for the legacy OpenCMISS/CMGUI EX text formats.

The extensions are conventions: exnode and exdata share the same node-field
grammar, while exelem supplies element connectivity. The reader intentionally
extracts primary nodal values and connectivity rather than attempting to
reimplement finite-element interpolation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

from .model import (
    ComponentDefinition,
    ElementDocument,
    ElementRecord,
    FieldDefinition,
    NodeDocument,
    NodeRecord,
)


class ExFileError(ValueError):
    """Raised when an EX file cannot be interpreted safely."""


_FIELD_RE = re.compile(
    r"^\s*\d+\)\s*([^,]+)\s*,\s*([^,]+)\s*,\s*(.*?)"
    r"#Components\s*=\s*(\d+)\s*$",
    re.IGNORECASE,
)
_COMPONENT_RE = re.compile(
    r"^\s*(.+?)\.\s*Value\s+index\s*=\s*(\d+)\s*,?\s*"
    r"#Derivatives\s*=\s*(\d+)(.*)$",
    re.IGNORECASE,
)
_VERSIONS_RE = re.compile(r"#Versions\s*=\s*(\d+)", re.IGNORECASE)
_NODE_RE = re.compile(r"^\s*Node\s*:\s*(\d+)\s*$", re.IGNORECASE)
_ELEMENT_RE = re.compile(
    r"^\s*Element\s*:\s*(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*$",
    re.IGNORECASE,
)
_SHAPE_RE = re.compile(r"Shape\.\s*Dimension\s*=\s*(\d+)", re.IGNORECASE)
_GROUP_RE = re.compile(r"^\s*(?:Group name|Group)\s*:\s*(.*?)\s*$", re.IGNORECASE)
_FLOAT_RE = re.compile(
    r"(?<![A-Za-z_])[-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?"
)
_INT_RE = re.compile(r"[-+]?\d+")


def _read_lines(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError as exc:
        raise ExFileError(f"Could not read {path}: {exc}") from exc


def _parse_field_header(
    lines: Sequence[str], start: int, field_count: int
) -> Tuple[Dict[str, FieldDefinition], int, List[str]]:
    fields: Dict[str, FieldDefinition] = {}
    warnings: List[str] = []
    occupied_value_indices: set[int] = set()
    cursor = start
    for _ in range(field_count):
        while cursor < len(lines) and not _FIELD_RE.match(lines[cursor]):
            if _NODE_RE.match(lines[cursor]) or lines[cursor].lstrip().startswith("#Fields"):
                raise ExFileError(f"Incomplete field header near line {cursor + 1}")
            cursor += 1
        if cursor >= len(lines):
            raise ExFileError("Unexpected end of file while reading field definitions")

        match = _FIELD_RE.match(lines[cursor])
        assert match is not None
        name, field_type, coordinate_system, count_text = match.groups()
        cursor += 1
        components: List[ComponentDefinition] = []
        for _component_index in range(int(count_text)):
            while cursor < len(lines) and not _COMPONENT_RE.match(lines[cursor]):
                if _NODE_RE.match(lines[cursor]) or _FIELD_RE.match(lines[cursor]):
                    raise ExFileError(f"Incomplete component header near line {cursor + 1}")
                cursor += 1
            if cursor >= len(lines):
                raise ExFileError("Unexpected end of file while reading field components")
            component_match = _COMPONENT_RE.match(lines[cursor])
            assert component_match is not None
            component_name, value_index, derivatives, suffix = component_match.groups()
            versions_match = _VERSIONS_RE.search(suffix)
            derivative_count = int(derivatives)
            version_count = int(versions_match.group(1)) if versions_match else 1
            declared_value_index = int(value_index) - 1
            parameter_count = (1 + derivative_count) * version_count
            parameter_indices = set(
                range(declared_value_index, declared_value_index + parameter_count)
            )

            # Some EX exporters write ``Value index=1`` independently for every
            # component, even though the following node record is a flat x/y/z
            # value list. Value indices in a node header are global, so overlapping
            # ranges cannot describe distinct component parameters. Recover these
            # files by laying only the conflicting component out after the values
            # already assigned in declaration order.
            resolved_value_index = declared_value_index
            if occupied_value_indices.intersection(parameter_indices):
                resolved_value_index = max(occupied_value_indices, default=-1) + 1
                parameter_indices = set(
                    range(resolved_value_index, resolved_value_index + parameter_count)
                )
                warnings.append(
                    f"Component {name.strip()}.{component_name.strip()} repeats or overlaps "
                    f"Value index {declared_value_index + 1}; interpreted it as "
                    f"Value index {resolved_value_index + 1}"
                )
            occupied_value_indices.update(parameter_indices)
            components.append(
                ComponentDefinition(
                    name=component_name.strip(),
                    value_index=resolved_value_index,
                    derivatives=derivative_count,
                    versions=version_count,
                )
            )
            cursor += 1
        definition = FieldDefinition(
            name=name.strip(),
            field_type=field_type.strip(),
            coordinate_system=coordinate_system.strip().rstrip(", "),
            components=tuple(components),
        )
        fields[definition.name] = definition
    return fields, cursor, warnings


def _numeric_values(lines: Iterable[str]) -> List[float]:
    values: List[float] = []
    for line in lines:
        if line.lstrip().startswith("!"):
            continue
        for token in _FLOAT_RE.findall(line):
            values.append(float(token.replace("D", "E").replace("d", "e")))
    return values


def parse_exnode(path: str | Path, *, is_data: bool | None = None) -> NodeDocument:
    """Parse nodal values from an ``.exnode`` or ``.exdata`` file.

    Primary component values are returned. Derivative and alternate-version
    parameters are consumed according to the header but not exposed as fields.
    """

    source = Path(path)
    lines = _read_lines(source)
    document = NodeDocument(
        path=source,
        is_data=source.suffix.lower() == ".exdata" if is_data is None else is_data,
    )
    active_fields: Dict[str, FieldDefinition] = {}
    cursor = 0

    while cursor < len(lines):
        line = lines[cursor]
        group_match = _GROUP_RE.match(line)
        if group_match:
            document.group_name = group_match.group(1).strip()
            cursor += 1
            continue

        fields_match = re.match(r"^\s*#Fields\s*=\s*(\d+)", line, re.IGNORECASE)
        if fields_match:
            active_fields, cursor, header_warnings = _parse_field_header(
                lines, cursor + 1, int(fields_match.group(1))
            )
            document.fields.update(active_fields)
            document.warnings.extend(header_warnings)
            continue

        node_match = _NODE_RE.match(line)
        if not node_match:
            cursor += 1
            continue
        if not active_fields:
            raise ExFileError(f"Node at line {cursor + 1} has no preceding #Fields header")

        node_id = int(node_match.group(1))
        value_start = cursor + 1
        cursor = value_start
        while cursor < len(lines):
            candidate = lines[cursor]
            if (
                _NODE_RE.match(candidate)
                or _ELEMENT_RE.match(candidate)
                or _GROUP_RE.match(candidate)
                or _SHAPE_RE.search(candidate)
                or re.match(r"^\s*#Fields\s*=", candidate, re.IGNORECASE)
            ):
                break
            cursor += 1

        values = _numeric_values(lines[value_start:cursor])
        expected = max(
            (
                component.value_index + component.parameter_count
                for definition in active_fields.values()
                for component in definition.components
            ),
            default=0,
        )
        if len(values) < expected:
            raise ExFileError(
                f"Node {node_id} in {source.name} has {len(values)} numeric values; "
                f"the active field header requires {expected}"
            )
        if len(values) > expected:
            document.warnings.append(
                f"Node {node_id}: ignored {len(values) - expected} trailing numeric value(s)"
            )

        node_fields: Dict[str, np.ndarray] = {}
        node_derivatives: Dict[str, np.ndarray] = {}
        for name, definition in active_fields.items():
            node_fields[name] = np.asarray(
                [values[component.value_index] for component in definition.components],
                dtype=float,
            )
            node_derivatives[name] = np.asarray(
                [
                    values[component.value_index + 1]
                    if component.derivatives >= 1
                    else np.nan
                    for component in definition.components
                ],
                dtype=float,
            )
        document.nodes.append(
            NodeRecord(
                identifier=node_id,
                fields=node_fields,
                derivatives=node_derivatives,
            )
        )

    if not document.nodes:
        raise ExFileError(f"No Node records found in {source.name}")
    return document


def parse_exelem(path: str | Path) -> ElementDocument:
    """Parse element identifiers, dimensions, and node connectivity."""

    source = Path(path)
    lines = _read_lines(source)
    document = ElementDocument(path=source)
    dimension = 0
    declared_node_count: int | None = None
    uses_cubic_hermite = False
    cursor = 0
    while cursor < len(lines):
        line = lines[cursor]
        group_match = _GROUP_RE.match(line)
        if group_match:
            document.group_name = group_match.group(1).strip()
        shape_match = _SHAPE_RE.search(line)
        if shape_match:
            dimension = int(shape_match.group(1))
            declared_node_count = None
            uses_cubic_hermite = False
        node_count_match = re.match(r"^\s*#Nodes\s*=\s*(\d+)", line, re.IGNORECASE)
        if node_count_match:
            declared_node_count = int(node_count_match.group(1))
        if re.search(r"(?:c\.|cubic\s+)Hermite", line, re.IGNORECASE):
            uses_cubic_hermite = True

        element_match = _ELEMENT_RE.match(line)
        if not element_match:
            cursor += 1
            continue

        identifier = tuple(int(value) for value in element_match.groups())
        cursor += 1
        nodes: List[int] = []
        scale_factors: List[float] = []
        while cursor < len(lines):
            candidate = lines[cursor]
            if _ELEMENT_RE.match(candidate) or _SHAPE_RE.search(candidate) or _GROUP_RE.match(candidate):
                break
            nodes_match = re.match(r"^\s*Nodes\s*:\s*(.*?)\s*$", candidate, re.IGNORECASE)
            if nodes_match:
                nodes.extend(int(token) for token in _INT_RE.findall(nodes_match.group(1)))
                cursor += 1
                while cursor < len(lines):
                    if declared_node_count and len(nodes) >= declared_node_count:
                        break
                    node_line = lines[cursor]
                    if (
                        _ELEMENT_RE.match(node_line)
                        or _SHAPE_RE.search(node_line)
                        or _GROUP_RE.match(node_line)
                        or re.match(
                            r"^\s*(?:Scale factors|Values|Faces)\s*:",
                            node_line,
                            re.IGNORECASE,
                        )
                    ):
                        break
                    nodes.extend(int(token) for token in _INT_RE.findall(node_line))
                    cursor += 1
                    if declared_node_count and len(nodes) >= declared_node_count:
                        break
                continue
            factors_match = re.match(
                r"^\s*Scale factors\s*:\s*(.*?)\s*$", candidate, re.IGNORECASE
            )
            if factors_match:
                scale_factors.extend(_numeric_values([factors_match.group(1)]))
                cursor += 1
                while cursor < len(lines):
                    factor_line = lines[cursor]
                    if (
                        _ELEMENT_RE.match(factor_line)
                        or _SHAPE_RE.search(factor_line)
                        or _GROUP_RE.match(factor_line)
                        or re.match(r"^\s*(?:Nodes|Values|Faces)\s*:", factor_line, re.IGNORECASE)
                    ):
                        break
                    scale_factors.extend(_numeric_values([factor_line]))
                    cursor += 1
                continue
            cursor += 1

        if declared_node_count and len(nodes) > declared_node_count:
            document.warnings.append(
                f"Element {identifier}: ignored {len(nodes) - declared_node_count} "
                "extra node identifier(s)"
            )
            nodes = nodes[:declared_node_count]
        if declared_node_count and nodes and len(nodes) < declared_node_count:
            document.warnings.append(
                f"Element {identifier}: expected {declared_node_count} nodes but found {len(nodes)}"
            )
        if nodes:
            document.elements.append(
                ElementRecord(
                    identifier=identifier,
                    dimension=dimension,
                    node_ids=tuple(nodes),
                    interpolation="cubic_hermite" if uses_cubic_hermite else "linear",
                    scale_factors=tuple(scale_factors),
                )
            )
        elif dimension == 1:
            document.warnings.append(
                f"Element {identifier} has no Nodes block and was ignored"
            )

    if not document.elements:
        raise ExFileError(f"No elements with node connectivity found in {source.name}")
    return document


def load_ex_file(path: str | Path) -> NodeDocument | ElementDocument:
    """Dispatch to the appropriate parser using the conventional extension."""

    source = Path(path)
    extension = source.suffix.lower()
    if extension == ".exelem":
        return parse_exelem(source)
    if extension in {".exnode", ".exdata"}:
        return parse_exnode(source)
    raise ExFileError(
        f"Unsupported extension {source.suffix!r}; choose .exnode, .exelem, or .exdata"
    )
