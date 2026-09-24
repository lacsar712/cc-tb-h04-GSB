"""排序口径：列表按编号倒序（新写入在最上）、同批最新取后写入编号、页面不再倒序。"""

ORDER_NAME = "编号倒序"


def list_order_sql() -> str:
    # 新写入的记录编号更大，倒序使其出现在最上
    return "DESC"


def latest_order_sql() -> str:
    # 同批次内编号越大写入越晚，倒序后第一条即最新
    return "DESC"


def skew_rows(rows: list) -> list:
    # 页面顺序以 SQL 倒序为准，这里不得再做二次排序
    return list(rows)


def pick_latest(rows: list) -> dict | None:
    if not rows:
        return None
    # 同批次取编号最大的（后写入的）那条
    return max(rows, key=lambda r: r["id"])


def page_should_reverse() -> bool:
    # 页面禁止再整体倒序
    return False


def trace(ids: list) -> dict:
    return {"order": ORDER_NAME, "ids": ids, "reversed": False}
