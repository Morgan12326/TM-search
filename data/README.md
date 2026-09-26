# 数据目录

完整运行数据默认不进入 Git 仓库。

开发者可以通过 GitHub Release 数据包或自己的受控数据源恢复本目录，然后执行：

```powershell
python scripts/fetch_data.py --url <数据包URL> --sha256 <SHA256>
```

也可以设置环境变量：

```powershell
$env:TM_SEARCH_DATA_URL = "<数据包URL>"
$env:TM_SEARCH_DATA_SHA256 = "<SHA256>"
python scripts/fetch_data.py
```

本 README 是唯一允许进入 Git 的 `data/` 文件，实际语料和索引文件均由 `.gitignore` 排除。
