# Copyright (c) 2023 Contributors to COVESA
#
# This program and the accompanying materials are made available under the
# terms of the Mozilla Public License 2.0 which is available at
# https://www.mozilla.org/en-US/MPL/2.0/
#
# SPDX-License-Identifier: MPL-2.0

import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEST_UNITS = HERE / ".." / "vspec" / "test_units.yaml"
TEST_QUANT = HERE / ".." / "vspec" / "test_quantities.yaml"
BIN_DIR = HERE / ".." / ".." / "binary"


def check_expected_for_tool(tool_path, signal_name: str, grep_str: str, test_binary):
    stdin = f"m\n{signal_name}\n1\nq"
    cmd = f"{tool_path} {test_binary}"
    process = subprocess.run(cmd.split(), input=stdin, check=True, capture_output=True, text=True)
    print(process.stdout)
    assert grep_str in process.stdout


def test_binary(tmp_path):
    """
    Tests binary tools by generating binary file and using test parsers to interpret them and request
    some basic information.
    """

    test_binary = tmp_path / "test.binary"
    ctestparser = tmp_path / "ctestparser"
    gotestparser = tmp_path / "gotestparser"
    cmd = f"vspec export binary  -u {TEST_UNITS}"
    cmd += f" -q {TEST_QUANT} -s {HERE / 'test.vspec'} -o {test_binary}"
    subprocess.run(cmd.split(), check=True)
    cmd = f"cc {BIN_DIR / 'c_parser/testparser.c'} {BIN_DIR / 'c_parser/cparserlib.c'} -o {ctestparser}"
    subprocess.run(cmd.split(), check=True)
    cmd = f"go build -o {gotestparser} testparser.go"
    subprocess.run(cmd.split(), check=True, cwd=BIN_DIR / "go_parser")

    parsers = [ctestparser, gotestparser]
    for parser in parsers:
        check_expected_for_tool(parser, "A.String", "Node type=SENSOR", test_binary)
        check_expected_for_tool(parser, "A.Int", "Node type=ACTUATOR", test_binary)
        check_expected_for_tool(parser, "A.AllowedInt", "Node num of allowed values=3", test_binary)
        check_expected_for_tool(parser, "A.AllowedInt", "Node allowed value=0 at index=0", test_binary)
        check_expected_for_tool(parser, "A.AllowedInt", "Node allowed value=10 at index=1", test_binary)
        check_expected_for_tool(parser, "A.AllowedInt", "Node allowed value=20 at index=2", test_binary)
        check_expected_for_tool(parser, "A.AllowedString", "Node num of allowed values=2", test_binary)
        check_expected_for_tool(parser, "A.AllowedString", "Node allowed value=A at index=0", test_binary)
        check_expected_for_tool(parser, "A.AllowedString", "Node allowed value=B at index=1", test_binary)
        check_expected_for_tool(parser, "A.AllowedFloat", "Node num of allowed values=3", test_binary)
        check_expected_for_tool(parser, "A.AllowedFloat", "Node allowed value=1.1 at index=0", test_binary)
        check_expected_for_tool(parser, "A.AllowedFloat", "Node allowed value=2.54 at index=1", test_binary)
        check_expected_for_tool(parser, "A.AllowedFloat", "Node allowed value=3 at index=2", test_binary)

        check_expected_for_tool(parser, "A.EnumUint8", "Node num of allowed values=3", test_binary)
        check_expected_for_tool(parser, "A.EnumUint8", "Node allowed value=0 at index=0", test_binary)
        check_expected_for_tool(parser, "A.EnumUint8", "Node allowed value=1 at index=1", test_binary)
        check_expected_for_tool(parser, "A.EnumUint8", "Node allowed value=5 at index=2", test_binary)
        check_expected_for_tool(parser, "A.EnumUint8Array", "Node num of allowed values=2", test_binary)
        check_expected_for_tool(parser, "A.EnumUint8Array", "Node allowed value=0 at index=0", test_binary)
        check_expected_for_tool(parser, "A.EnumUint8Array", "Node allowed value=1 at index=1", test_binary)


def read_l8(data: bytes, pos: int) -> tuple[str, int]:
    length = data[pos]
    return data[pos + 1 : pos + 1 + length].decode(), pos + 1 + length


def read_l16(data: bytes, pos: int) -> tuple[str, int]:
    length = struct.unpack_from("=H", data, pos)[0]
    return data[pos + 2 : pos + 2 + length].decode(), pos + 2 + length


def parse_allowed(allowed: str) -> list[str]:
    """Split an allowed string, where each element is preceded by its length as two hex digits"""
    result = []
    pos = 0
    while pos < len(allowed):
        length = int(allowed[pos : pos + 2], 16)
        result.append(allowed[pos + 2 : pos + 2 + length])
        pos += 2 + length
    return result


def parse_binary(data: bytes) -> dict[str, dict]:
    """Minimal pure python parser of the binary format, returns a dict with the allowed/default per node name"""
    nodes: dict[str, dict] = {}

    def parse_node(pos: int) -> int:
        name, pos = read_l8(data, pos)
        _, pos = read_l8(data, pos)  # type
        pos += 1  # uuid
        _, pos = read_l16(data, pos)  # description
        datatype, pos = read_l8(data, pos)
        for _ in range(3):  # min, max, unit
            _, pos = read_l8(data, pos)
        allowed, pos = read_l16(data, pos)
        default, pos = read_l8(data, pos)
        _, pos = read_l8(data, pos)  # validate
        children = data[pos]
        pos += 1
        nodes[name] = {"datatype": datatype, "allowed": parse_allowed(allowed), "default": default}
        for _ in range(children):
            pos = parse_node(pos)
        return pos

    end = parse_node(0)
    assert end == len(data)
    return nodes


def test_binary_enum(tmp_path):
    """
    Enums are not part of the binary format as such, but the (numeric) enum values shall be exported as
    allowed values. Verified with a pure python parser so that no C/Go toolchain is needed.
    """
    test_binary = tmp_path / "test.binary"
    cmd = ["vspec", "export", "binary", "-u", str(TEST_UNITS), "-q", str(TEST_QUANT)]
    cmd += ["-s", str(HERE / "test.vspec"), "-o", str(test_binary)]
    subprocess.run(cmd, check=True)

    nodes = parse_binary(test_binary.read_bytes())
    assert nodes["EnumUint8"]["datatype"] == "uint8"
    assert nodes["EnumUint8"]["allowed"] == ["0", "1", "5"]
    assert nodes["EnumUint8"]["default"] == "1"
    assert nodes["EnumUint8Array"]["datatype"] == "uint8[]"
    assert nodes["EnumUint8Array"]["allowed"] == ["0", "1"]
    # 'allowed' is still exported as before, and signals without enum/allowed have no allowed values
    assert nodes["AllowedInt"]["allowed"] == ["0", "10", "20"]
    assert nodes["Int"]["allowed"] == []
