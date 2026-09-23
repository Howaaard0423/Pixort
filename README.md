# Pixort

画师 / 角色 / 作品的本地图库管理工具。仓库在原有 PySide6 单文件程序的基础上完成了
**前后端分离**：HTTP API 负责数据与图片，浏览器界面负责呈现。

```
Pixort/
├── backend/            后端 API（Python 标准库 + SQLite，零必需依赖）
│   ├── run.py          启动入口
│   ├── pixort_api/     路由 / 服务 / 数据访问分层
│   └── tests/          接口测试（17 项，全部通过）
├── frontend/           前端界面（原生 ES 模块，Swiss International Style）
├── assets/             字体 / EXE 图标
├── docs/               架构、接口、代码审查记录
├── pixort.spec         PyInstaller 打包脚本 → dist/Pixort.exe
├── build-exe.bat       一键打包
├── requirements.txt    可选依赖（不装也能跑）
├── requirements-dev.txt 开发与打包依赖
└── .github/workflows/  推送 v* 标签时自动打包 EXE 并发布
```

> **仓库里没有个人数据。** `illustration_manager.db`、`illustrations/`、`备份_*.zip`
> 已在 `.gitignore` 中排除，只存在于本机。

## 快速开始

### 方式一：直接跑源码

```bash
python backend/run.py --open
```

终端会打印地址（默认 <http://127.0.0.1:8000/>）并自动打开浏览器，也可以双击
`start-backend.bat`。要求 **Python 3.10+**，不需要安装任何第三方包。

可选的增强依赖：

| 可选依赖 | 解锁的能力 |
| --- | --- |
| `pillow` | 服务端缩略图、图片尺寸与朝向探测 |
| `pyzipper` | AES 加密的备份压缩包 |

```bash
python -m pip install -r requirements.txt   # 可选
```

### 方式二：用打包好的 EXE

见下一节。产物是单个 `dist/Pixort.exe`，目标机器**不需要装 Python**。

## 打包成单个 EXE

```bash
python -m pip install -r requirements-dev.txt
pyinstaller --clean --noconfirm pixort.spec     # 或者双击 build-exe.bat
```

产出的 `dist/Pixort.exe` 约 18 MB，后端与前端都封在里面：

* 双击即启动服务并在 EXE **旁边**生成 `illustration_manager.db`、`illustrations/`、
  `.cache/`，控制台窗口显示地址并自动打开浏览器；
* 换端口或数据目录：`Pixort.exe --port 8080 --data-root D:\Pictures`；
* 迁移时把整个文件夹拷走即可，图库与数据库都在里面；
* 推送 `v*` 标签（`git tag v2.0.0 && git push --tags`）时，
  `.github/workflows/build-exe.yml` 会自动跑测试、打包，并把 EXE 附到 Release。

## 上传到 GitHub

```bash
git init
git add .
git status          # 确认列表里没有 illustrations/、*.db、备份_*.zip、dist/
git commit -m "Pixort：前后端分离 + Swiss 风格网页界面"
git remote add origin <你的仓库地址>
git push -u origin main
```

* 二进制（EXE）建议走 Release，而不是提交进仓库——`dist/` 已在 `.gitignore` 中排除。
* 如果想发布 EXE：`git tag v2.0.0 && git push --tags`，工作流自动完成打包与发布。

## 前后端如何分离

* 后端只依赖 `sqlite3` + 标准库，对外是纯 JSON / 二进制接口，图片通过
  `/api/illustrations/{id}/content` 输出，不再直接读本地文件路径。
* 前端是**纯静态站点**：`frontend/` 可以直接丢给任意静态服务器。默认由后端托管；
  放在别处时用 `?api=http://127.0.0.1:8000` 或 `window.PIXORT_API_BASE` 指向后端
  （后端已开放 CORS）。

```bash
cd frontend && python -m http.server 5173      # 另开一个终端
# 浏览器打开 http://127.0.0.1:5173/?api=http://127.0.0.1:8000
```

## 界面

Swiss International Style（瑞士国际主义风格）：严格的模块化网格、Helvetica
字系、黑 / 白 / 一个红（`#e30613`）、无圆角无阴影、发丝线与版心对齐、数字即结构。

* 左侧索引栏：画师（可展开作品）、标签、角色
* 主区：网格 / 紧凑 / 宽松 / 列表四种视图密度
* 详情页：大图 + 元数据表（含尺寸、体积、SHA-256 校验值）
* 按 `G` 显示底层的 12 栏版式网格，按 `/` 聚焦搜索，`Esc` 关闭详情或全屏查看器

页面是「一屏高」的应用外壳：页头、控制栏、状态栏固定，只有作品区与索引栏滚动。
配色支持「跟随系统 / 浅色 / 深色」三种模式，保留自原桌面客户端。

## 常用命令

```bash
python backend/run.py --help                  # 全部参数
python backend/run.py --data-root D:/Pictures # 指定数据目录
python -m unittest discover -s backend/tests -t backend   # 运行测试
pyinstaller --clean --noconfirm pixort.spec   # 打包网页版 EXE
pyinstaller desktop/zzz_executeable_file.spec # 打包遗留的桌面客户端
```

## 文档

* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 分层结构与数据流
* [`docs/API.md`](docs/API.md) — 接口清单
* [`docs/CODE_REVIEW.md`](docs/CODE_REVIEW.md) — 代码审查记录与修复说明
* [`desktop/README.md`](desktop/README.md) — 桌面客户端说明

## 数据安全

* 删除作品默认**归档**而不是直接删除文件（`/api/illustrations/{id}?file=archive`）。
* 删除画师只有在没有任何记录再引用该文件夹时才会移除目录。
* 备份恢复前会先校验压缩包结构，失败时自动回滚到原有数据。
* 数据库升级是增量式的（`ALTER TABLE ADD COLUMN`），旧的
  `illustration_manager.db` 可以直接继续使用。