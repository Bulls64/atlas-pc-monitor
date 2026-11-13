import pytest

from atlas import formatting as f

GIB = 1024**3


@pytest.mark.parametrize(
    ("value", "expected"),
    [(8 * GIB, "8 Go"), (16 * GIB, "16 Go"), (int(15.9 * GIB), "15,9 Go"), (512, "512 o"), (0, "0 o"), (4 * 1024**2, "4 Mo")],
)
def test_fmt_binary(value, expected):
    assert f.fmt_binary(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(500107862016, "500,1 Go"), (1000204886016, "1 To"), (2 * 10**18, "2000 Po"), ("512110190592", "512,1 Go")],
)
def test_fmt_decimal(value, expected):
    assert f.fmt_decimal(value) == expected


@pytest.mark.parametrize("value", [None, "", "abc", -1024, float("nan"), True])
def test_invalid_sizes_give_dash(value):
    assert f.fmt_binary(value) == f.EMPTY
    assert f.fmt_decimal(value) == f.EMPTY


def test_other_formatters():
    assert f.fmt_mhz(3201) == "3,2 GHz"
    assert f.fmt_mhz(800) == "800 MHz"
    assert f.fmt_mhz(0) == f.EMPTY
    assert f.fmt_code(26, f.MEMORY_TYPES) == "DDR4"
    assert f.fmt_code(34, f.MEMORY_TYPES) == "DDR5"
    assert f.fmt_code(99, f.MEMORY_TYPES) == "Code 99"
    assert f.fmt_media("SSD") == "SSD"
    assert f.fmt_media("3") == "Disque dur (HDD)"
    assert f.fmt_media(4) == "SSD"
    assert f.fmt_bus("NVMe") == "NVMe"
    assert f.fmt_bus(17) == "NVMe"
    assert f.fmt_date("2023-08-14") == "14/08/2023"
    assert f.fmt_date("2026-11-09T08:00:00") == "09/11/2026 08:00"
    assert f.fmt_date("pas une date") == "pas une date"
    assert f.fmt_uptime("2026-11-09T08:00:00", "2026-11-11T10:30:00+01:00") == "2 j 2 h"
    assert f.fmt_uptime(None, "2026-11-11T10:30:00") == f.EMPTY
    assert f.fmt_diagonal(34, 19).startswith("15,3 pouces")
    assert f.fmt_bool(True) == "Oui"
    assert f.fmt_bool(None) == f.EMPTY


def test_memory_helpers_and_stamp():
    sticks = [{"SMBIOSMemoryType": 26, "FormFactor": 12}, {"SMBIOSMemoryType": 26, "FormFactor": 0}, {"SMBIOSMemoryType": 34}]
    assert f.memory_types(sticks) == ["DDR4", "DDR5"]
    assert f.memory_forms(sticks) == ["SO-DIMM"]
    assert f.fmt_stamp("2026-11-13T10:30:00+01:00") == "13/11/2026 10:30"
    assert f.fmt_stamp(None) == f.EMPTY
    assert f.fmt_binary(1024**6 * 3) == "3072 Po"  # au-delà de la dernière unité, on reste en Po
