"""排序核对用例：列表查询、同批最新、页面展示三处，以及春茶-A 结论。

在容器内运行：cd /app && python -m unittest discover -v
"""

import re
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from rules import weigh

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BACKEND_DIR / "templates"


class FakeCursor:
    def __init__(self, rows=None, one=None):
        self.rows = list(rows or [])
        self.one = one
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        if self.one is not None:
            return self.one
        return self.rows[0] if self.rows else None

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, cursor_factory=None):
        return self._cursor

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def row(cid, lot, verdict="通过", score=7.8, note="加权分达到放行线"):
    return {
        "id": cid,
        "lot": lot,
        "aroma": 8.0,
        "taste": 8.0,
        "liquor": 7.0,
        "score": score,
        "verdict": verdict,
        "note": note,
        "created_by": "taster",
    }


def row_cells(html):
    """取 tbody 中每行的单元格文本，按页面从上到下的顺序。"""
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, re.S).group(1)
    out = []
    for tr in re.finditer(r"<tr>(.*?)</tr>", body, re.S):
        cells = tuple(re.sub(r"\s+", "", c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr.group(1), re.S))
        if cells:
            out.append(cells)
    return out


class OrderingTestBase(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = "taster"
            sess["role"] = "writer"


class ListQueryTest(OrderingTestBase):
    """列表查询：新写入出现在最上。"""

    def test_sql_is_descending(self):
        cur = FakeCursor(rows=[])
        with patch.object(app, "db", lambda: FakeConn(cur)):
            resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        sql = cur.executed[-1][0]
        self.assertIn("ORDER BY id DESC", sql)
        self.assertNotIn("ASC", sql)

    def test_rows_rendered_newest_first_without_python_reversal(self):
        rows = [
            row(3, "新茶-D"),
            row(2, "夏茶-C", verdict="不通过", score=4.7, note="加权分低于放行线"),
            row(1, "春茶-A"),
        ]
        cur = FakeCursor(rows=rows)
        with patch.object(app, "db", lambda: FakeConn(cur)):
            html = self.client.get("/").get_data(as_text=True)
        cells = row_cells(html)
        self.assertEqual([c[0] for c in cells], ["新茶-D", "夏茶-C", "春茶-A"])
        self.assertEqual([c[2] for c in cells], ["通过", "不通过", "通过"])


class LatestInBatchTest(OrderingTestBase):
    """同批最新：必须落到后写入的（最大）编号。"""

    def test_sql_orders_desc_and_limits_one(self):
        cur = FakeCursor(one=row(3, "春茶-A"))
        with patch.object(app, "db", lambda: FakeConn(cur)):
            resp = self.client.get("/api/latest?lot=春茶-A")
        self.assertEqual(resp.status_code, 200)
        sql, params = cur.executed[-1]
        self.assertIn("ORDER BY id DESC", sql)
        self.assertIn("LIMIT 1", sql)
        self.assertEqual(params, ("春茶-A",))

    def test_picks_later_id_of_same_batch(self):
        earlier = row(1, "春茶-A", score=7.8)
        later = row(4, "春茶-A", score=8.1)
        cur = FakeCursor(one=later)
        with patch.object(app, "db", lambda: FakeConn(cur)):
            data = self.client.get("/api/latest?lot=春茶-A").get_json()
        self.assertEqual(data["id"], later["id"])
        self.assertGreater(data["id"], earlier["id"])
        self.assertEqual(data["lot"], "春茶-A")

    def test_unknown_lot_is_empty(self):
        cur = FakeCursor(one=None)
        with patch.object(app, "db", lambda: FakeConn(cur)):
            data = self.client.get("/api/latest?lot=不存在").get_json()
        self.assertEqual(data, {})


class PageDisplayTest(OrderingTestBase):
    """页面展示：服务端降序直出，前端不得再倒序。"""

    def test_no_reverse_script_in_base_template(self):
        base = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        self.assertNotIn("reverse", base)
        self.assertNotIn("beforeend", base)
        self.assertIn("afterbegin", base)

    def test_tbody_is_descending_and_new_hx_row_goes_to_top(self):
        rows = [row(5, "新茶-D"), row(2, "夏茶-C", verdict="不通过", score=4.7)]
        with patch.object(app, "db", lambda: FakeConn(FakeCursor(rows=rows))):
            html = self.client.get("/").get_data(as_text=True)
        self.assertEqual([c[0] for c in row_cells(html)], ["新茶-D", "夏茶-C"])

        cur = FakeCursor(one=row(6, "春茶-A", score=8.1))
        with patch.object(app, "db", lambda: FakeConn(cur)):
            resp = self.client.post(
                "/cuppings",
                data={"lot": "春茶-A", "aroma": "9", "taste": "8", "liquor": "8"},
                headers={"HX-Request": "true"},
            )
        self.assertEqual(resp.status_code, 200)
        fragment = resp.get_data(as_text=True)
        self.assertIn("春茶-A", fragment)
        self.assertIn("通过", fragment)


class BypassRemovedTest(unittest.TestCase):
    """颠倒旁路模块及其调用不应残留。"""

    def test_order_skew_module_gone(self):
        self.assertFalse((BACKEND_DIR / "order_skew.py").exists())

    def test_app_source_has_no_skew_or_interpolated_order(self):
        source = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("skew", source)
        self.assertNotIn("order_skew", source)
        self.assertNotIn("ORDER BY id ASC", source)


class SpringTeaAVerdictTest(unittest.TestCase):
    """春茶-A（春茶甲）结论仍须是通过。"""

    def test_rule_passes_at_seed_scores(self):
        verdict, note, score = weigh(8, 8, 7)
        self.assertEqual(verdict, "通过")
        self.assertGreaterEqual(score, 7)

    def test_seed_like_rows_render_as_pass_and_latest_still_passes(self):
        rows = [
            row(4, "春茶-A", score=8.1),
            row(2, "夏茶-C", verdict="不通过", score=4.7, note="加权分低于放行线"),
            row(1, "春茶-A", score=7.8),
        ]
        client = app.app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = "taster"
            sess["role"] = "writer"

        with patch.object(app, "db", lambda: FakeConn(FakeCursor(rows=rows))):
            html = client.get("/").get_data(as_text=True)
        spring_rows = [c for c in row_cells(html) if c[0] == "春茶-A"]
        self.assertTrue(spring_rows)
        self.assertTrue(all(c[2] == "通过" for c in spring_rows))
        self.assertIn('class="pass">通过', html)

        with patch.object(app, "db", lambda: FakeConn(FakeCursor(one=rows[0]))):
            data = client.get("/api/latest?lot=春茶-A").get_json()
        self.assertEqual(data["id"], 4)
        self.assertEqual(data["verdict"], "通过")


if __name__ == "__main__":
    unittest.main()
