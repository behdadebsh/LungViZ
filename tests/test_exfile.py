from pathlib import Path

import numpy as np
import pytest

from LungViZ.exfile import ExFileError, parse_exelem, parse_exnode


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


def test_parse_exelem_connectivity():
    document = parse_exelem(EXAMPLES / "sample.exelem")

    assert len(document.elements) == 3
    assert document.elements[1].dimension == 1
    assert document.elements[1].identifier == (2, 0, 0)
    assert document.elements[1].node_ids == (2, 3)


def test_node_without_field_header_is_rejected(tmp_path):
    path = tmp_path / "bad.exnode"
    path.write_text("Group name: bad\nNode: 1\n 0 0 0\n", encoding="utf-8")

    with pytest.raises(ExFileError, match="no preceding #Fields"):
        parse_exnode(path)

