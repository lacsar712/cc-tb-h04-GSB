"""列表查询 / 同批最新 / 页面展示 三条链路的端到端核对。

用假游标接管数据库连接：既能断言 app 实际下发的 SQL 排序方向，
也能走通登录后的真实路由与模板渲染，不依赖 PostgreSQL。
缺 flask/psycopg2 时整体跳过（容器/CI 中二者由 requirements.txt 提供）。
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import app as flask_app
    from rules import weigh
    FLASK_AVAILABLE = True
except ImportError:  # pragma: no cover - 本机最小环境
    FLASK_AVAILABLE = False


@unittest.skipUnless(FLASK_AVAILABLE, "未安装 flask/psycopg2，跳过路由层用例")
class OrderingRouteTests(unittest.TestCase):
    def setUp(self):
        self.statements = []
        self._next_rows = []
        self._next_one = None
        flask_app.db = lambda: FakeConn(self)
        self.client = flask_app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = "taster"
            sess["role"] = "writer"

    def set_rows(self, rows):
        self._next_rows = rows

    # 1) 列表查询：SQL 必须 DESC，渲染后新写入在最上
    def test_list_query_desc_and_newest_on_top(self):
        self.set_rows([
            {"id": 3, "lot": "秋茶-G", "score": 9.0, "verdict": "通过", "note": "n3"},
            {"id": 2, "lot": "夏茶-C", "score": 4.5, "verdict": "不通过", "note": "n2"},
            {"id": 1, "lot": "春茶-A", "score": 7.8, "verdict": "通过", "note": "n1"},
        ])
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("ORDER BY id DESC", self.statements[-1])
        self.assertNotIn("ASC", self.statements[-1])
        # 渲染顺序即 3 -> 2 -> 1：秋茶-G 必须排在春茶-A 之前
        self.assertLess(html.index("秋茶-G"), html.index("春茶-A"))
        top = re.search(r"<tbody id=\"rows\">\s*<tr>\s*<td>([^<]+)</td>", html, re.S)
        self.assertIsNotNone(top)
        self.assertEqual(top.group(1), "秋茶-G")

    # 2) 同批最新：SQL 必须 DESC，且取到后写入编号（id 更大）
    def test_latest_in_lot_picks_later_write(self):
        older = {"id": 5, "lot": "春茶-A", "score": 7.1, "verdict": "通过", "note": "首轮"}
        newer = {"id": 9, "lot": "春茶-A", "score": 8.4, "verdict": "通过", "note": "复测"}
        self.set_rows([newer, older])  # DB 按 DESC 返回
        data = self.client.get("/api/latest?lot=春茶-A").get_json()
        self.assertIn("ORDER BY id DESC", self.statements[-1])
        self.assertEqual(data["id"], 9)
        self.assertEqual(data["note"], "复测")

    # 3) 页面展示：新提交的高分行返回 <tr>，且结论正确（HTMX 局部替换）
    def test_create_high_score_returns_passing_row(self):
        resp = self.client.post(
            "/cuppings",
            data={"lot": "春茶-A", "aroma": "8", "taste": "8", "liquor": "7"},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertTrue(html.strip().startswith("<tr>"))
        self.assertIn("春茶-A", html)
        self.assertIn("通过", html)
        self.assertIn("7.8", html)
        self.assertIn("INSERT INTO cuppings", self.statements[-1])

    # 春茶甲结论仍须是通过
    def test_spring_tea_a_threshold_is_pass(self):
        verdict, note, score = weigh(8, 8, 7)
        self.assertEqual((verdict, score), ("通过", 7.8))


class FakeCursor:
    def __init__(self, case):
        self.case = case

    def execute(self, statement, params=None):
        self.case.statements.append(statement)
        self.params = params

    def fetchall(self):
        return self.case._next_rows

    def fetchone(self):
        if self.case._next_one is not None:
            return self.case._next_one
        # INSERT ... RETURNING *：按入参拼出真实会写回的那行
        if self.params:
            lot, aroma, taste, liquor, score, verdict, note, created_by = self.params
            return {"id": 100, "lot": lot, "aroma": aroma, "taste": taste,
                    "liquor": liquor, "score": score, "verdict": verdict,
                    "note": note, "created_by": created_by}
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, case):
        self.case = case

    def cursor(self, cursor_factory=None):
        return FakeCursor(self.case)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


if __name__ == "__main__":
    unittest.main(verbosity=2)
