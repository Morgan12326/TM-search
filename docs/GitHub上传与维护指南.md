# GitHub 上传与维护指南

## 目标

- GitHub 仓库只保存代码、测试、工具和文档。
- `data/`、APK、桌面 ZIP、EXE、签名材料和构建产物不进入普通 Git 历史。
- 普通用户从 Releases 下载成品或数据包。
- 开发者下载源码后，通过 `scripts/fetch_data.py` 恢复数据。
- GitHub Issues 和 Pull Requests 用于收集问题与代码贡献。

仓库地址：

```text
https://github.com/Morgan12326/TM-search
```

当前建议保持 Private，确认代码、数据和成品包的发布范围后再考虑 Public。

## 本地仓库状态

本项目已经添加以下准备文件：

- `.gitignore`
- `CONTRIBUTING.md`
- `DATA-NOTICE.md`
- `SECURITY.md`
- `.github/ISSUE_TEMPLATE/`
- `.github/pull_request_template.md`
- `.github/workflows/ci.yml`
- `scripts/fetch_data.py`
- `data/README.md`

`data/` 中只有 `README.md` 会进入 Git，其余数据全部忽略。

## 第一次连接 GitHub

本机当前 HTTPS 443 连接 GitHub 不稳定，但 SSH 22 可用，因此推荐使用 SSH。

### 1. 生成 SSH 密钥

如果没有现成密钥，在 PowerShell 中执行：

```powershell
ssh-keygen -t ed25519 -C "Morgan12326@users.noreply.github.com"
```

默认保存到：

```text
%USERPROFILE%\.ssh\id_ed25519
```

私钥绝不能上传或发送给任何人。

### 2. 把公钥添加到 GitHub

显示公钥：

```powershell
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
```

复制完整内容，打开：

```text
GitHub -> Settings -> SSH and GPG keys -> New SSH key
```

标题可以填写：

```text
Codex Windows
```

### 3. 测试连接

```powershell
ssh -T git@github.com
```

看到 `successfully authenticated` 即表示连接成功。

### 4. 首次提交

在本项目根目录执行：

```powershell
git init -b main
git config user.name "Morgan12326"
git config user.email "Morgan12326@users.noreply.github.com"
git remote add origin git@github.com:Morgan12326/TM-search.git
```

检查准备提交的文件：

```powershell
git status --short
git add .gitignore CONTRIBUTING.md DATA-NOTICE.md SECURITY.md README.md
git add .github app data/README.md docs scripts tests tools 启动型月搜索.bat
git status --short
```

确认 `data/` 中除 `README.md` 外的文件均未进入暂存区。

提交：

```powershell
git commit -m "Initial private repository preparation"
```

如果远程仓库已经有 README 等初始提交，先执行：

```powershell
git pull --rebase origin main
```

push：

```powershell
git push -u origin main
```

## 数据获取方式

### 数据可以受控分发

创建 GitHub Release，例如：

```text
v1.1.7
```

附加数据资产：

```text
TM-Search-Data-v1.1.7.zip
TM-Search-Data-v1.1.7.sha256.txt
```

开发者执行：

```powershell
python scripts/fetch_data.py --url <数据包URL> --sha256 <SHA256>
```

也可以使用环境变量：

```powershell
$env:TM_SEARCH_DATA_URL = "<数据包URL>"
$env:TM_SEARCH_DATA_SHA256 = "<SHA256>"
python scripts/fetch_data.py
```

### 数据不能公开

- 不上传数据 ZIP。
- 不上传包含数据的桌面 ZIP 和 APK。
- Public 仓库只保留代码和文档。
- 使用者必须自行提供有权使用的完整 `data/`。

## Issues 和 Pull Requests

### Issues

仓库 Settings 中确认 Issues 已开启。

Public 仓库中任何 GitHub 用户都可以提交 Issue；Private 仓库中只有协作者可以提交。

### Pull Requests

贡献者流程：

1. Fork 仓库。
2. 从 `main` 建立功能分支。
3. 修改代码并运行测试。
4. 向本仓库 `main` 提交 PR。

建议对 `main` 开启分支保护：

- Require a pull request before merging
- Require conversation resolution
- Require status checks
- Do not allow force pushes
- Do not allow deletions

## 上线前检查

- [ ] `data/` 中没有被 Git 跟踪的数据文件
- [ ] 没有 APK、ZIP、EXE、签名文件或密码
- [ ] 已删除 `$null`、缓存和临时文件
- [ ] README 运行步骤与实际情况一致
- [ ] 已确定代码许可证
- [ ] 已确认数据是否允许公开再发布
- [ ] `python -m app.server` 可以启动
- [ ] Python 和 Node 测试结果已记录

## 常用命令

```powershell
git status
git diff
git add <明确列出的文件>
git commit -m "说明"
git push
```
