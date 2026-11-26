"""KDX Filename: pattern -> file-name prefix with the data of the run."""

import json
from datetime import datetime

import pytest

from kdx_console import filename, nodes
from kdx_console.engine import ConsoleError

NOW = datetime(2026, 11, 19, 7, 5, 9)
RUN = {"mode": "sequential", "category": "fashion", "category_name": "Fashion & outdoor", "template": "outdoor",
       "seed": 901421304, "system_prompt": "", "done": 1, "repeat": 3, "channel": "main", "llm_enabled": False,
       "index": 2, "repeat_left": 1, "time": 1795108553.1581397}


def test_template_and_date():
    assert filename.build("%template%_ZIT_%date:yyyyMMdd_hhmmss%", RUN, NOW) == "outdoor_ZIT_20261119_070509"


def test_the_users_pattern_with_single_s():
    # "hhmms": hh + mm + s (seconds without padding), as typed in a Save node
    assert filename.build("ZIT_%date:yyyyMMdd_hhmms%", RUN, NOW) == "ZIT_20261119_07059"


def test_other_keys_and_numbers():
    assert filename.build("%category%/%template%_%seed%_%index%of%repeat%", RUN, NOW) == "fashion/outdoor_901421304_2of3"
    assert filename.build("%llm_enabled%", RUN, NOW) == "false"
    assert filename.build("%TEMPLATE%", RUN, NOW) == "outdoor"  # case-insensitive keys


def test_values_are_file_safe_but_pattern_folders_stay():
    data = {"template": "art/cubism", "category_name": 'Fash: "ion" <x>?'}
    assert filename.build("%category_name%/%template%", data, NOW) == "Fash_ _ion_ _x_/art_cubism"
    assert filename.build("a/%template%", {"template": "../../x"}, NOW) == "a/_._x"  # no way out of the folder


def test_nested_and_list():
    data = {"a": {"b": "deep"}, "l": ["zero", "one"]}
    assert filename.build("%a.b%_%l.1%", data, NOW) == "deep_one"


def test_width_height_are_left_for_comfyui():
    assert filename.build("%template%_%width%x%height%", RUN, NOW) == "outdoor_%width%x%height%"


def test_plain_date_default():
    assert filename.build("%date%", {}, NOW) == "20261119_070509"
    assert filename.format_date("yy-M-d h:m:s", NOW) == "26-11-19 7_5_9"


def test_unknown_key_lists_available():
    with pytest.raises(filename.FilenameError) as e:
        filename.build("%nope%", RUN, NOW)
    assert "category_name" in str(e.value) and "%nope%" in str(e.value)


def test_empty_and_bad_input():
    with pytest.raises(filename.FilenameError):
        filename.build("   ", RUN, NOW)
    with pytest.raises(filename.FilenameError):
        filename.parse_data("not json")
    with pytest.raises(filename.FilenameError):
        filename.parse_data("[1]")
    assert filename.parse_data("") == {}
    assert filename.build("x_%date:yyyy%", {}, NOW) == "x_2026"


def test_node():
    out = nodes.KDX_Console_Filename().build(json.dumps(RUN), "%category%/%template%")
    assert out == ("fashion/outdoor",)
    assert nodes.KDX_Console_Filename.RETURN_TYPES == ("STRING",) == tuple("STRING" for _ in nodes.KDX_Console_Filename.RETURN_NAMES)
    assert nodes.NODE_CLASS_MAPPINGS["KDX_Console_Filename"] is nodes.KDX_Console_Filename
    with pytest.raises(ConsoleError):
        nodes.KDX_Console_Filename().build("{}", "%template%")
    it = nodes.KDX_Console_Filename.INPUT_TYPES()["required"]
    assert it["state_json"][1]["forceInput"] and "%date:" in it["pattern"][1]["default"]
