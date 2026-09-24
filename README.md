# 茶叶拼配审评台

审评员对一个拼配批次打香气、滋味、汤色。服务端按 0.3 / 0.5 / 0.2 加权，7 分及以上通过。提交后只替换表格里新的一行，不整页跳转。

这是制茶审评，不是菜谱，也不是饮食记录。

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3192 |
| 应用 | http://localhost:8192 |
| PostgreSQL | localhost:54392 |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| taster | tea123456 | 可审评 |
| observer | look123456 | 只看 |

## 启动

```bash
cd projects/13-tea-blend-cupping
docker compose up --build
```

## 验收

1. taster 登录后看到春茶-A 通过、夏茶-C 不通过。
2. 再提交一组高分，新行出现在表头，页面不整页刷新。
3. observer 登录后没有提交表单。

## 核对用例

列表查询、同批最新、页面展示三处排序口径均有自动化核对：

```bash
cd backend
python -m unittest test_ordering test_app_ordering -v
```

`test_ordering` 只用标准库；`test_app_ordering` 走真实路由（用假游标断言 SQL 排序方向与渲染顺序），需 flask/psycopg2，容器内已装。
