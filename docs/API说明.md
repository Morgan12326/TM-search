# API 说明

服务仅监听 `127.0.0.1`。所有接口使用 GET，并返回 UTF-8 JSON；静态页面返回 HTML、JavaScript 或 CSS。

| 路径 | 主要参数 | 返回内容 |
|---|---|---|
| `/api/suggest` | `q` | 查询联想 |
| `/api/search` | `q`, `scope`, `limit` | 综合搜索结果 |
| `/api/doc` | `id`, `block`, `q`, `start`, `end`, `chapter` | 文档阅读块 |
| `/api/list` | `q`, `work`, `scope`, `offset`, `limit`, `multi`, `terms` | 分页结果列表 |
| `/api/official` | `q`, `scope`, `offset`, `limit`, `multi` | 官方问答与访谈结果 |
| `/api/defs` | `q`, `scope`, `offset`, `limit`, `multi` | 词解卡片 |
| `/api/aliases` | 无 | 查询别名 |
| `/api/alias-data` | 无 | 别名目标与说明 |
| `/api/taxonomy` | 无 | 作品分类 |
| `/api/wiki/tree` | 无 | 百科目录树 |
| `/api/story/tree` | 无 | 剧情大全目录树 |
| `/api/story/leaf` | `key` | 剧情叶节点 |
| `/api/story/node` | `key` | 剧情节点和章节 |
| `/api/fgo/chapter` | `id` | FGO 官方章节兼容接口 |
| `/api/official/chapter` | `work`, `id` | 官方剧情章节 |
| `/api/wiki/leaf` | `key`, `offset`, `limit`, `filter`, `cat` | 百科叶节点内容 |
| `/api/status` | 无 | 构建版本、文档数、词条数和索引统计 |

## 兼容性

- 返回数组的顺序是业务结果的一部分，前端不会重新排序。
- 参数边界和默认值由 `app/http_server.py` 的 `do_GET()` 决定。
- 新接口应先更新本文档和对应测试，再修改前端调用。
