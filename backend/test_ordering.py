"""排序口径核对（仅用标准库，任何环境可跑）。

覆盖三处：
1. 列表查询：ORDER BY id DESC，skew_rows 不再二次排序，新写入在最上。
2. 同批最新：latest 走 DESC，pick_latest 取后写入（编号最大）那条。
3. 页面展示：脚本用 afterbegin 置顶，不再整体 reverse。
另核对春茶-A（8/8/7，加权 7.8）结论仍为“通过”。
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import order_skew  # noqa: E402
from rules import weigh  # noqa: E402

BASE_HTML = os.path.join(HERE, "templates", "base.html")
SEED_PY = os.path.join(HERE, "seed.py")


def rows(*ids):
    return [{"id": i, "lot": "春茶-A"} for i in ids]


class ListOrderTests(unittest.TestCase):
    def test_list_sql_is_descending(self):
        self.assertEqual(order_skew.list_order_sql(), "DESC")

    def test_skew_rows_keeps_sql_order(self):
        ordered = sorted(rows(1, 2, 3), key=lambda r: r["id"], reverse=True)
        out = order_skew.skew_rows(ordered)
        self.assertEqual([r["id"] for r in out], [3, 2, 1])

    def test_new_write_is_first_after_pipeline(self):
        # 模拟 DB 按 DESC 返回 + skew_rows：新写入（id=4）必须在最上
        from_db = rows(4, 3, 2, 1)
        page_rows = order_skew.skew_rows(from_db)
        self.assertEqual(page_rows[0]["id"], 4)
        self.assertEqual([r["id"] for r in page_rows], [4, 3, 2, 1])


class LatestInLotTests(unittest.TestCase):
    def test_latest_sql_is_descending(self):
        self.assertEqual(order_skew.latest_order_sql(), "DESC")

    def test_pick_latest_takes_largest_id(self):
        same_lot = rows(11, 5, 17, 9)  # 同批次多次写入，乱序给出
        chosen = order_skew.pick_latest(same_lot)
        self.assertEqual(chosen["id"], 17)

    def test_pick_latest_empty_is_none(self):
        self.assertIsNone(order_skew.pick_latest([]))


class PageOrderTests(unittest.TestCase):
    def setUp(self):
        with open(BASE_HTML, encoding="utf-8") as fh:
            self.js = fh.read()

    def test_page_must_not_reverse(self):
        self.assertFalse(order_skew.page_should_reverse())
        self.assertNotIn(".reverse()", self.js)
        self.assertNotIn("排序颠倒", self.js)

    def test_new_row_inserted_at_top(self):
        self.assertIn("afterbegin", self.js)
        # 不得再追加到表尾
        self.assertNotIn("beforeend", self.js)

    def test_trace_reports_no_reversal(self):
        self.assertFalse(order_skew.trace([1, 2, 3])["reversed"])


class SpringTeaAVerdictTests(unittest.TestCase):
    def test_weigh_passes_at_8_8_7(self):
        verdict, note, score = weigh(8, 8, 7)
        self.assertEqual(score, 7.8)
        self.assertEqual(verdict, "通过")

    def test_seed_spring_tea_a_still_8_8_7(self):
        # 防止种子被改：春茶-A 必须仍是 (8,8,7) 这一组
        with open(SEED_PY, encoding="utf-8") as fh:
            seed_src = fh.read()
        m = re.search(r'\("春茶-A",\s*(\d+),\s*(\d+),\s*(\d+)\)', seed_src)
        self.assertIsNotNone(m, "种子数据中应保留 春茶-A")
        vals = tuple(map(int, m.groups()))
        self.assertEqual(vals, (8, 8, 7))
        self.assertEqual(weigh(*vals)[0], "通过")


if __name__ == "__main__":
    unittest.main(verbosity=2)
