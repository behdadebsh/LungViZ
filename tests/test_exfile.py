from pathlib import Path

import numpy as np
import pytest

from LungViZ.exfile import (
    ExFileError,
    parse_exelem,
    parse_exnode,
    write_exnode_coordinates,
)


EXAMPLES = Path(__file__).parents[1] / "examples"


def test_parse_exnode_fields_and_values():
    document = parse_exnode(EXAMPLES / "sample.exnode")

    assert document.group_name == "sample_airway"
    assert len(document.nodes) == 4
    assert set(document.fields) == {"coordinates", "radius", "pressure", "flow"}
    np.testing.assert_allclose(document.nodes[1].fields["coordinates"], [1, 0, 0])
    np.testing.assert_allclose(document.nodes[1].fields["pressure"], [11])


def test_parse_exdata_is_marked_as_data():
    document = parse_exnode(EXAMPLES / "sample.exdata")

    assert document.is_data
    assert len(document.nodes) == 2
    assert document.nodes[0].fields["measured_pressure"][0] == pytest.approx(12.5)


def test_parse_derivatives_versions_and_fortran_exponents(tmp_path):
    path = tmp_path / "versions.exnode"
    path.write_text(
        """Group name: variants
#Fields=1
1) signal, field, rectangular cartesian, #Components=1
 value. Value index=1, #Derivatives=1 (d/ds1), #Versions=2
Node: 7
 1.25D+01 2.0 99.0 3.0
""",
        encoding="utf-8",
    )

    document = parse_exnode(path)
    assert document.nodes[0].fields["signal"][0] == pytest.approx(12.5)


def test_duplicate_component_value_indices_are_laid_out_sequentially(tmp_path):
    path = tmp_path / "repeated_indices.exnode"
    path.write_text(
        """Group name: exported_tree
#Fields=1
1) coordinates, coordinate, rectangular cartesian, #Components=3
 x. Value index=1, #Derivatives=0
 y. Value index=1, #Derivatives=0
 z. Value index=1, #Derivatives=0
Node: 1
 32.5 -201.7 1335.9
Node: 2
 25.5 -200.5 1348.2
""",
        encoding="utf-8",
    )

    document = parse_exnode(path)

    np.testing.assert_allclose(
        document.nodes[0].fields["coordinates"], [32.5, -201.7, 1335.9]
    )
    assert [
        component.value_index for component in document.fields["coordinates"].components
    ] == [0, 1, 2]
    assert len(document.warnings) == 2
    assert "coordinates.y" in document.warnings[0]

    document.nodes[0].fields["coordinates"][:] = [1.25, 2.5, 3.75]
    exported_path = tmp_path / "repeated_indices_edited.exnode"
    write_exnode_coordinates(document, exported_path, "coordinates")
    np.testing.assert_allclose(
        parse_exnode(exported_path).nodes[0].fields["coordinates"],
        [1.25, 2.5, 3.75],
    )


def test_parse_exelem_connectivity():
    document = parse_exelem(EXAMPLES / "sample.exelem")

    assert len(document.elements) == 3
    assert document.elements[1].dimension == 1
    assert document.elements[1].identifier == (2, 0, 0)
    assert document.elements[1].node_ids == (2, 3)


def test_parse_grid_based_element_field_values(tmp_path):
    path = tmp_path / "flow.exelem"
    path.write_text(
        """Group name: perfusion
Shape. Dimension=1
#Scale factor sets=0
#Nodes=0
#Fields=1
1)flow, field, rectangular cartesian, #Components=1
 flow. l.Lagrange, no modify, grid based.
 #xi1=1
Element: 1 0 0
 Values:
  0.70000E+05 0.70000E+05
Element: 2 0 0
 Values:
  10.0 14.0
""",
        encoding="utf-8",
    )

    document = parse_exelem(path)

    assert document.fields["flow"].component_value_counts == (2,)
    assert document.elements[0].node_ids == ()
    np.testing.assert_allclose(document.elements[0].fields["flow"], [70000.0])
    np.testing.assert_allclose(document.elements[1].fields["flow"], [12.0])


def test_node_without_field_header_is_rejected(tmp_path):
    path = tmp_path / "bad.exnode"
    path.write_text("Group name: bad\nNode: 1\n 0 0 0\n", encoding="utf-8")

    with pytest.raises(ExFileError, match="no preceding #Fields"):
        parse_exnode(path)


def test_export_edited_coordinates_preserves_other_node_fields(tmp_path):
    document = parse_exnode(EXAMPLES / "sample.exnode")
    document.nodes[1].fields["coordinates"][:] = [9.5, 8.5, 7.5]
    destination = tmp_path / "edited.exnode"

    write_exnode_coordinates(document, destination, "coordinates")
    exported = parse_exnode(destination)

    np.testing.assert_allclose(exported.nodes[1].fields["coordinates"], [9.5, 8.5, 7.5])
    np.testing.assert_allclose(exported.nodes[1].fields["pressure"], [11.0])
    np.testing.assert_allclose(
        parse_exnode(EXAMPLES / "sample.exnode").nodes[1].fields["coordinates"],
        [1.0, 0.0, 0.0],
    )
