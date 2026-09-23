# 架构

Pixort 由三个可独立运行的部分组成：**后端 API**、**前端静态站点**、以及打包脚本。
后端不关心界面长什么样，前端不关心数据存在哪里——两者只通过 HTTP + JSON 说话。

```
浏览器（frontend/）
        │  HTTP + JSON / 图片二进制
        ▼
backend/pixort_api/server.py     ThreadingHTTPServer，把 socket 变成 Request
        │
        ▼
backend/pixort_api/app.py        Application.handle
        ├── /api/**   → Router → routes/ → services/ → repository → SQLite
        └── 其他路径  → frontend/ 里的静态文件
```

## 一次请求的路径

1. `server.py` 解析请求行、头部与请求体，组装成 `Request`（`http_kit.py`），
   超过 `MAX_BODY_BYTES` 直接拒绝。
2. `Application.handle()` 按路径分流：`/api/` 开头交给路由表，其余按静态文件处理。
3. `Router` 用预编译的正则匹配路径，把 `{artist_id}` 这类占位符填进 `request.params`。
4. 路由函数（`routes/*.py`）只做三件事：校验参数、调用下层、把结果包成 `Response`。
5. 业务副作用（图片落盘、缩略图、备份包、库扫描）在 `services/`，
   纯 SQL 在 `repository.py`，连接与事务在 `db.py`。
6. 抛出的 `HttpError` / `ValueError` / `NotFound` 统一被 `Application.handle()`
   捕获并翻译成 400 / 404 / 409 / 500，响应体统一是
   `{"error": {"message": …, "details": …}}`。

## 后端分层

| 层 | 文件 | 职责 | 不该做的事 |
| --- | --- | --- | --- |
| 传输 | `server.py` | socket、请求体大小限制、请求解析 | 业务判断 |
| 应用 | `app.py` | 路由分发、错误映射、CORS、静态托管 | 直接写 SQL |
| 路由 | `routes/*.py` | 参数解析、组装响应 | 直接操作文件系统 |
| 服务 | `services/*.py` | 导入、缩略图、备份、扫描等副作用 | 拼 HTTP 响应 |
| 仓储 | `repository.py` | 纯 SQL，返回 dict | 抛 HTTP 异常 |
| 数据 | `db.py` | 连接参数、事务、schema 与增量迁移 | 了解业务字段含义 |

约定的回报是**可测试性**：`backend/tests/test_api.py` 直接构造 `Application`，
不需要真的监听端口。

## 数据模型

SQLite，四张表（schema 版本 3，是桌面版数据库的超集）：

| 表 | 说明 |
| --- | --- |
| `artists` | 画师，`name` 唯一 |
| `characters` | 角色，`name` 唯一 |
| `illustrations` | 作品。`artist_id` / `character_id` 外键 `ON DELETE SET NULL`；另有 `tags`（逗号分隔的自由文本）、`rating`、`width/height/file_size/checksum`、`sort_order`（画师内的手动顺序） |
| `app_settings` | 键值配置，值以 JSON 存储 |

升级策略是**只增不改**：`_COLUMN_MIGRATIONS` 里登记的新列在启动时用
`ALTER TABLE ADD COLUMN` 补齐，所以旧的 `illustration_manager.db` 可以直接接着用，
不需要导出再导入。`PRAGMA foreign_keys=ON` 与 `journal_mode=WAL` 在每次连接时设置。

## 磁盘布局

源码运行时，一切都在数据根目录下：

```
Pixort/
├── illustration_manager.db        数据库（含 -wal / -shm）
├── illustrations/<画师>/<文件>     原图
├── archive_illustrations/         删除时归档的文件
└── .cache/{thumbnails,tmp,exports}
```

用 EXE 运行时规则不变，只是默认值移动（见 `settings.py` 的 `FROZEN` 分支）：
`frontend/` 这类**资源**从 `sys._MEIPASS` 解包目录读，**数据库、图片、缓存**写在
可执行文件旁边，所以迁移时把整个文件夹拷走即可。所有路径都能用
`PIXORT_DATA_ROOT` / `PIXORT_DB` / `PIXORT_ILLUSTRATIONS` 等环境变量覆盖。

`resolve_illustration_path()` 会把任何越出插画目录的路径拒掉（403），除非显式打开
`PIXORT_ALLOW_EXTERNAL_FILES`——数据库里的 `file_path` 是历史遗留字段，不能无条件信任。

## 前端架构

没有构建步骤：浏览器直接跑原生 ES 模块，`python -m http.server` 就能打开。

| 文件 | 职责 |
| --- | --- |
| `js/main.js` | 启动、全局事件、快捷键、hash 路由、渲染调度 |
| `js/state.js` | 单例 store，`set()` 后通知订阅者 |
| `js/api.js` | **唯一的网络出口**；同时负责「真实后端 / 演示数据」的切换 |
| `js/demo.js` | 内置示例库，与真实 API 同名同形 |
| `js/dom.js` | `el()` 建元素、格式化辅助 |
| `js/overlay.js` | 对话框 / 查看器的焦点管理与 Esc 关闭 |
| `js/views/*.js` | 纯渲染函数：`(host, state, handlers) => void` |
| `css/*.css` | `tokens → base → layout → components → views`，按顺序覆盖 |

数据流是单向的：

```
用户操作 → handlers（main.js）→ api.xxx() → store.set() → render() → 视图重绘
```

视图不持有状态，也不发请求；状态只在 `state.js`，请求只在 `api.js`。
正因为视图统一 `import { api } from '../api.js'`，静态演示才只需在 `api.js` 末尾
换一个实现：

```js
export const api = IS_DEMO ? demoApi : liveApi;
```

## 两种托管形态

| | 本地完整版 | 静态演示版 |
| --- | --- | --- |
| 数据 | SQLite + 本地图片 | `frontend/js/demo.js` 内存数据 |
| 启动 | `python backend/run.py` 或 `Pixort.exe` | 任意静态服务器 / GitHub Pages |
| 前端来源 | 后端直接托管 `frontend/` | `tools/build_pages.py` 生成的 `_site/` |
| 判据 | 默认 | `?demo=1`、`window.PIXORT_DEMO`、`file://`、`*.github.io` |

静态演示版由三个小东西拼成：

1. `tools/build_pages.py` 把 `frontend/` 复制成 `_site/`，在入口 `<script>` 前插入
   `window.PIXORT_DEMO = true`，再写一个 `.nojekyll`（否则 Jekyll 会跳过下划线开头的路径）。
2. `js/demo.js` 顶替网络层：20 条虚构作品指向 `frontend/demo/` 里 8 张几何 SVG 占位图，
   写操作只改内存。
3. `.github/workflows/pages.yml` 在每次推送到 `main` / `master` 时重新组装并发布。

路由用 hash（`#/work/5`）而不是 History API，所以静态托管不需要任何 SPA 回退规则——
把 `index.html` 丢进任意目录都能直接从详情页链接打开。

## 为什么这么选

* **标准库 http.server**：宿主机器零依赖，`pip install` 只在需要缩略图时才必要。
  代价是没有现成的并发优化，因此用 `ThreadingHTTPServer` + 每请求一个连接，
  并靠 SQLite 的 WAL 与 `busy_timeout` 处理并发写。
* **前端不用框架**：界面状态有限（筛选条件 + 一个详情对象），一个 1.6 KB 的
  store 就够了；换来的是零构建、零 `node_modules`，`frontend/` 永远可以整目录直传。
* **图片走 `/content` 接口**：前端拿到的是 URL 而不是磁盘路径，浏览器无法探测宿主
  文件系统，也让「同一份前端既能连本机后端、又能连远端后端」成为可能。