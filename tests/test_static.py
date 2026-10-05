import os
import re

STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def test_shell_references_exist():
    html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
    assert "<title>Transform</title>" in html
    for ref in re.findall(r'(?:src|href)="/static/([^"]+)"', html):
        assert os.path.exists(os.path.join(STATIC, ref)), ref
    for view in ["today", "plan", "weight", "history", "settings"]:
        assert os.path.exists(os.path.join(STATIC, "views", f"{view}.js")), view
    sw = open(os.path.join(STATIC, "sw.js"), encoding="utf-8").read()
    assert "addEventListener('push'" in sw and "notificationclick" in sw


def test_sw_served_at_root(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
