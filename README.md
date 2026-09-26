# 型月搜索

型月搜索是一个仅在本机运行的 Type-Moon 资料检索工具。服务使用 Python 标准库提供 HTTP API，前端为原生 JavaScript，不依赖 Flask、数据库或云服务。

## 运行要求

- Python 3.10 或更高版本
- 可选的 Node.js 18+，仅用于运行前端渲染测试
- `data/` 中必须有完整的运行数据

项目默认不跟踪 `data/`、临时文件和敏感材料。代码仓库不包含知识库时，搜索功能无法启动。

## 获取数据

如果维护者提供了数据包，可以校验并解压到 `data/`：

```powershell
python scripts/fetch_data.py
```

脚本会读取仓库根目录的 `data-manifest.json`，下载对应 Release 数据包并校验 SHA-256。也可以手动设置 `TM_SEARCH_DATA_URL` 和 `TM_SEARCH_DATA_SHA256` 覆盖默认值。完整说明见 [GitHub 上传与维护指南](docs/GitHub上传与维护指南.md)。

## 启动

在 Windows 中双击：

```text
启动型月搜索.bat
```

命令行启动：

```powershell
python -m app.server
```

也保留脚本方式：

```powershell
python app/server.py
```

默认地址为 `http://127.0.0.1:8765/`。

## 环境变量

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `TM_DICT_PORT` | `8765` | HTTP 服务端口 |
| `TM_DICT_NO_BROWSER` | 未设置 | 设为 `1` 时不自动打开浏览器 |

## 目录结构

```text
型月搜索/
├─ app/                 运行程序与前端资源
│  ├─ server.py         公共兼容入口
│  ├─ core.py           常量、文本工具和排序辅助
│  ├─ store.py          数据加载、索引和查询逻辑
│  ├─ http_server.py    HTTP 路由
│  ├─ main.py           服务启动
│  ├─ language_blocks.py
│  ├─ multi_term.py     多词检索
│  ├─ official_interviews.py
│  └─ web/
├─ tools/               数据重建、验证与导入工具
├─ tests/               Python 与 Node 测试
├─ data/                本地知识库和派生索引，默认不跟踪
├─ docs/                架构、数据、API 和维护说明
├─ 启动型月搜索.bat
└─ README.md
```

## 测试

从项目根目录执行：

```powershell
python -m unittest discover -s tests -v
node --test tests/test_render.mjs
```

Python 测试会读取完整 `data/`，耗时通常约一到两分钟。部分重建测试还依赖本机原始语料路径；这些路径在各测试文件顶部集中声明。

## 数据边界

- `data/` 是运行时数据，不是公开示例数据。
- 签名材料已移至项目外的 `../签名材料/`，不得上传或复制进代码仓库。
- `temp/`、缓存和本地生成文件不应进入版本控制。
- 本仓库当前未选择代码许可证；在公开仓库前必须补充 `LICENSE`。
- 数据来源、翻译授权和再发布范围应由维护者自行核实，详见 [数据与内容说明](DATA-NOTICE.md)。
- GitHub 上传、数据包和 Issue/PR 配置详见 [GitHub 上传与维护指南](docs/GitHub上传与维护指南.md)。

## 当前代码特点

运行代码已按职责拆分为核心工具、数据仓库、HTTP 路由、启动入口和兼容门面。`app.server` 仍保留原有公共名称，因此旧调用方式和新模块入口可以并存。修改检索或排序前应先阅读 [架构说明](docs/架构说明.md)，并运行全量测试。
