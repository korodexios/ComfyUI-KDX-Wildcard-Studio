"""example_workflows/*.json: structurally valid, match the node contract, nothing pinned."""

import json
import os
import re

import pytest
from _helpers import ROOT

from kdx_console.nodes import KDX_Console

FOLDER = os.path.join(ROOT, "example_workflows")
FILES = sorted(f for f in os.listdir(FOLDER) if f.endswith(".json"))


def load(name):
    with open(os.path.join(FOLDER, name), encoding="utf-8") as f:
        return json.load(f)


def test_examples_exist():
    assert len(FILES) >= 3
    assert all(f.startswith("KDX Wildcard Studio - ") for f in FILES)


@pytest.mark.parametrize("name", FILES)
def test_links_are_consistent(name):
    wf = load(name)
    nodes = {n["id"]: n for n in wf["nodes"]}
    for link in wf["links"]:
        lid, src, src_slot, dst, dst_slot, _typ = link[:6]
        assert lid in (nodes[src]["outputs"][src_slot].get("links") or [])
        assert nodes[dst]["inputs"][dst_slot]["link"] == lid


@pytest.mark.parametrize("name", FILES)
def test_console_node_matches_contract_and_is_not_pinned(name):
    wf = load(name)
    consoles = [n for n in wf["nodes"] if n["type"] == "KDX_Console"]
    assert len(consoles) == 1
    node = consoles[0]
    assert node["widgets_values"][0] == ""  # pin empty -> normal run
    assert [o["name"] for o in node["outputs"]] == list(KDX_Console.RETURN_NAMES)
    assert [o["type"] for o in node["outputs"]] == list(KDX_Console.RETURN_TYPES)


@pytest.mark.parametrize("name", FILES)
def test_has_read_me_note(name):
    wf = load(name)
    assert any(n["type"] == "MarkdownNote" for n in wf["nodes"])


@pytest.mark.parametrize("name", FILES)
def test_no_private_addresses(name):
    with open(os.path.join(FOLDER, name), encoding="utf-8") as f:
        text = f.read()
    assert not re.search(r"\b(10|192\.168|172\.(1[6-9]|2\d|3[01]))\.\d+\.\d+", text)
    assert not re.search(r"/home/|[A-Z]:\\\\Users", text)


def test_llm_example_wires_llm_enabled_into_chat():
    wf = load("KDX Wildcard Studio - 3 overrides and LLM switch.json")
    nodes = {n["id"]: n for n in wf["nodes"]}
    console = next(n for n in wf["nodes"] if n["type"] == "KDX_Console")
    chat = next(n for n in wf["nodes"] if n["type"] == "KDX_LLM_Chat")
    links = {lk[0]: lk for lk in wf["links"]}
    src_slot = [o["name"] for o in console["outputs"]].index("llm_enabled")
    inp = next(i for i in chat["inputs"] if i["name"] == "llm_enabled")
    _lid, src, slot, dst, _dslot, typ = links[inp["link"]][:6]
    assert (nodes[src]["type"], slot, dst, typ) == ("KDX_Console", src_slot, chat["id"], "BOOLEAN")
    assert "widget" not in inp  # a socket in KDX-LLM 0.9.0, not a widget
    assert not any(n["type"] == "ComfySwitchNode" for n in wf["nodes"])
