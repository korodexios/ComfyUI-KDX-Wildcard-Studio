"""Gallery: PNG text chunks are read without decoding pixels; only KDX Wildcard Studio images are listed."""

import json
import os
import struct
import time
import zlib

import _helpers  # noqa: F401

from kdx_console import api, gallery


def chunk(ctype: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def write_png(path, texts=(), size=(64, 32), itxt=()):
    ihdr = struct.pack(">IIBBBBB", size[0], size[1], 8, 2, 0, 0, 0)
    body = chunk(b"IHDR", ihdr)
    for k, v in texts:  # ComfyUI style: tEXt with UTF-8 bytes
        body += chunk(b"tEXt", k.encode("latin-1") + b"\0" + v.encode("utf-8"))
    for k, v in itxt:
        body += chunk(b"iTXt", k.encode() + b"\0\1\0\0\0" + zlib.compress(v.encode("utf-8")))
    body += chunk(b"IDAT", zlib.compress(b"\0" * 10)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(gallery.PNG_SIG + body)


USED = {"category": "life", "category_name": "Life › home", "template": "lounge_woman", "seed": 42, "index": 2,
        "repeat": 10, "mode": "sequential"}


def test_reads_text_and_size_and_utf8(tmp_path):
    p = tmp_path / "a.png"
    write_png(p, [("kdx_console", json.dumps({**USED, "prompt": "She is lying on the sofa — ü"}, ensure_ascii=False))],
              size=(1024, 576))
    m = gallery.image_meta(str(p))
    assert m["template"] == "lounge_woman" and m["seed"] == 42 and m["index"] == 2
    assert m["category_name"] == "Life › home"
    assert m["prompt"].endswith("— ü")
    assert (m["width"], m["height"]) == (1024, 576)


def test_itxt_compressed_is_read(tmp_path):
    p = tmp_path / "b.png"
    write_png(p, itxt=[("kdx_console", json.dumps(USED))])
    assert gallery.image_meta(str(p))["template"] == "lounge_woman"


def test_old_images_fall_back_to_the_longest_prompt_input(tmp_path):
    p = tmp_path / "c.png"
    graph = {"1": {"inputs": {"text": "x" * 200}}, "2": {"inputs": {"seed": 5, "t": "short"}}}
    write_png(p, [("kdx_console", json.dumps(USED)), ("prompt", json.dumps(graph))])
    assert gallery.image_meta(str(p))["prompt"] == "x" * 200


def test_foreign_and_broken_files_are_skipped(tmp_path):
    write_png(tmp_path / "other.png", [("prompt", "{}")])
    (tmp_path / "broken.png").write_bytes(b"not a png")
    write_png(tmp_path / "bad.png", [("kdx_console", "{nope")])
    assert gallery.Gallery().scan(str(tmp_path))["items"] == []


def test_scan_newest_first_subfolders_filters_limit_and_since(tmp_path):
    (tmp_path / "sub").mkdir()
    now = time.time()
    for i, (name, tpl, cat) in enumerate([("a.png", "lounge_woman", "life"), ("sub/b.png", "akt", "nsfw_solo"),
                                          ("c.png", "lounge_woman", "life")]):
        p = tmp_path / name
        write_png(p, [("kdx_console", json.dumps({**USED, "template": tpl, "category": cat}))])
        os.utime(p, (now - 100 + i * 10, now - 100 + i * 10))
    g = gallery.Gallery()
    items = g.scan(str(tmp_path))["items"]
    assert [x["filename"] for x in items] == ["c.png", "b.png", "a.png"]
    assert items[1]["subfolder"] == "sub" and items[1]["type"] == "output"
    assert [x["filename"] for x in g.scan(str(tmp_path), template="lounge_woman")["items"]] == ["c.png", "a.png"]
    assert [x["filename"] for x in g.scan(str(tmp_path), category="nsfw_solo")["items"]] == ["b.png"]
    res = g.scan(str(tmp_path), limit=1)
    assert len(res["items"]) == 1 and res["more"] is True
    assert [x["filename"] for x in g.scan(str(tmp_path), since=now - 95)["items"]] == ["c.png", "b.png"]


def test_cache_rereads_a_changed_file(tmp_path):
    p = tmp_path / "a.png"
    write_png(p, [("kdx_console", json.dumps(USED))])
    g = gallery.Gallery()
    assert g.scan(str(tmp_path))["items"][0]["seed"] == 42
    write_png(p, [("kdx_console", json.dumps({**USED, "seed": 7, "template": "x_longer_name"}))])
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert g.scan(str(tmp_path))["items"][0]["seed"] == 7


def test_api_query_and_errors(tmp_path):
    write_png(tmp_path / "a.png", [("kdx_console", json.dumps(USED))])
    status, d = api.get_gallery({"since": "0", "limit": "abc"}, root=str(tmp_path))
    assert status == 200 and d["ok"] and len(d["items"]) == 1
    assert gallery.parse_query({"since": "-5", "limit": "99999"}) == {"since": 0.0, "limit": 99999, "category": "",
                                                                       "template": ""}
    assert len(gallery.GALLERY.scan(str(tmp_path), limit=99999)["items"]) == 1  # clamped to MAX_LIMIT


def test_nsfw_templates_are_hidden_unless_the_setting_is_on(tmp_path):
    from kdx_console.store import Store

    out = tmp_path / "out"
    out.mkdir()
    for name, tpl in [("a.png", "portrait_woman"), ("b.png", "akt"), ("c.png", "sheer_duo"), ("d.png", "nsfw_two")]:
        write_png(out / name, [("kdx_console", json.dumps({**USED, "template": tpl}))])
    store = Store(root=str(tmp_path / "data"))
    gallery.GALLERY._cache.clear()
    _, d = api.get_gallery({}, root=str(out), store=store)
    assert [x["template"] for x in d["items"]] == ["portrait_woman"] and d["show_nsfw"] is False
    store.save_config({**store.load_config(), "show_nsfw": True})
    _, d = api.get_gallery({}, root=str(out), store=store)
    assert sorted(x["template"] for x in d["items"]) == ["akt", "nsfw_two", "portrait_woman", "sheer_duo"]


def test_show_nsfw_is_a_normalized_config_flag():
    from kdx_console import engine

    assert engine.default_config()["show_nsfw"] is False
    cfg, _ = engine.normalize_config({"show_nsfw": True})
    assert cfg["show_nsfw"] is True
