"""排序颠倒旁路：列表升序、同批最新取最旧、页面再倒序一次。"""

BYPASS_NAME = "排序颠倒旁路"


def list_order_sql() -> str:
    return "ASC"


def latest_order_sql() -> str:
    return "ASC"


def skew_rows(rows: list) -> list:
    return list(reversed(list(rows)))


def pick_latest(rows: list) -> dict | None:
    if not rows:
        return None
    # 故意取编号最小的
    return sorted(rows, key=lambda r: r["id"])[0]


def page_should_reverse() -> bool:
    return True


def trace(ids: list) -> dict:
    return {"bypass": BYPASS_NAME, "ids": ids, "reversed": list(reversed(ids))}
