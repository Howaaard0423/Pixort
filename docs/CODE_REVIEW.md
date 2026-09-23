# 代码审查记录

分离前后端的过程中做了三轮通读，每一轮改完都跑一遍
`python -m unittest discover -s backend/tests -t backend`（17 项）与
`node --check`，界面部分用无头浏览器实际点过。下面只记录**真正改变了行为**的项，
纯粹的措辞调整不列。

## 一、数据层

| # | 现象 | 原因 | 处理 |
| --- | --- | --- | --- |
| 1 | 未指定画师的作品，手动顺序永远停在 0 | SQL 写的是 `WHERE artist_id = ?`，而 SQLite 里 `NULL = NULL` 不成立 | 改成 `artist_id IS ?`；`repository.next_sort_order()` 附了注释说明为什么不能用 `=` |
| 2 | 传入不存在的 `artist_id`，接口返回 500 和一句 `FOREIGN KEY constraint failed` | 外键直接交给 SQLite 报错 | 新增 `_validate_reference()`，写入前先查一次：不存在给 404「画师不存在」，不是整数给 400 |
| 3 | 标签筛选只能命中第一个标签 | `tags` 是逗号分隔的单列，`LIKE '%标签%'` 匹配不到 `"甲, 乙"` 里的「乙」——它前面有个空格 | 把列和关键词都补上分隔符、去掉空格再比（`TAG_MATCH_SQL` 与 `normalise_tag()` 成对出现，任何一边改了另一边要跟着改） |
| 4 | 搜索框里输入 `%` 会匹配到全部记录 | 用户输入被直接当成 `LIKE` 通配符 | `escape_like()` 转义 `%` `_` `\`，SQL 里显式声明 `ESCAPE '\'` |
| 5 | 空标签会在库里留下 `"a,,b"` 这种空洞 | 拆分时保留了空片段 | 拆分后丢弃空白项并去重（`split_tags()`） |

## 二、文件系统安全

| # | 现象 | 原因 | 处理 |
| --- | --- | --- | --- |
| 6 | 删除画师会连带删掉目录里的文件，哪怕还有记录指向它 | 原桌面版无条件 `shutil.rmtree` | `remove_folder_if_unreferenced()`：先遍历所有 `file_path`，确认没有记录落在这个目录里才删；否则原样保留并在响应里用 `folder_kept` 说明 |
| 7 | 判断「是否还有记录指向该目录」会漏判 | 用字符串前缀 `illustrations/<画师>/` 比对，老记录里存的是绝对路径就匹配不上 | 改为解析成真实路径后用 `Path.parents` 比较 |
| 8 | 数据库里一条被改过的 `file_path` 可以读取磁盘上任意文件 | `file_path` 是历史遗留的自由文本字段，直接 `open()` 了 | `resolve_illustration_path()` 统一收口：解析后必须仍在 `illustrations/` 之内，否则 403；确有需要时用 `PIXORT_ALLOW_EXTERNAL_FILES=1` 显式放行 |
| 9 | 静态文件服务可以跳出 `frontend/` | 相对路径里带 `..` | `resolve_within()` 收口，越界返回 403（`test_14` 覆盖） |
| 10 | 上传的备份包如果结构不对，恢复会写坏现有数据 | 边解压边写 | 先 `inspect_backup()` 校验结构与清单，恢复过程出错自动回滚（`services/transfer.py`） |

## 三、接口健壮性

| # | 现象 | 原因 | 处理 |
| --- | --- | --- | --- |
| 11 | 一次上传里有一个坏文件，整批都失败 | 异常直接往上冒 | 每个文件单独 `try`，逐条记录 `imported` / `skipped` / `failed`，最后汇总返回 |
| 12 | 请求体没有大小上限，一个大文件就能把内存吃满 | `http.server` 默认照单全收 | `settings.MAX_BODY_BYTES`（默认 512 MB + 8 MB）在读取前拦截 |
| 13 | `sort` 参数写错只是静默回退到默认排序 | `_SORT_CLAUSES.get(sort, 默认)` | 路由层先校验，未知排序返回 400 并列出可选项 |
| 14 | 分页参数可以传负数或超大值 | 未夹取范围 | `limit` 夹到 1–500，`offset` 不小于 0；响应带 `total` 与 `has_more` |
| 15 | 每个请求都新建连接，写在并发下偶发 `database is locked` | 默认 journal 模式 | 每次连接统一设 `journal_mode=WAL`、`busy_timeout=15000` |

## 四、前端

| # | 现象 | 原因 | 处理 |
| --- | --- | --- | --- |
| 16 | 全屏查看器里按「下一个」，图片不换 | 翻页只改了 store 里的详情对象，查看器把 `item` 存进了闭包，重开又会叠一层 `keydown` 监听 | `viewer.js` 暴露 `update(nextItem, nav)` 就地重绘，不重建 DOM，监听器只注册一次 |
| 17 | 批量导出后点列表里的备份，会把整个库重新打包一遍 | 列表项链接直接指向 `GET /api/transfer/export` | 列表改用 `GET /api/transfer/exports/{name}`，只取已有文件 |
| 18 | 鼠标滚轮滚不动页面 | `body` 用 `min-height:100vh`，页面被内容撑高，滚轮事件又落在带 `overscroll-behavior: contain` 的 `.stage` 上，滚动链在到达页面级滚动条之前就被掐断 | `body` 改成 `height:100vh/100dvh; overflow:hidden`，让应用外壳固定、只有 `.stage` 与索引栏内部滚动 |
| 19 | 按 G 显示网格后关不掉 | 写入时写 `body.dataset.grid`，CSS 读的是 `html[data-grid]`，两边不是同一个元素 | 以 `store.state.gridVisible` 为唯一真相源，`setGridVisible()` 同时更新 `body.dataset.grid`、按钮的 `aria-pressed` 与本地偏好 |

第 18、19 两条是实测复现的：第 18 条用 CDP 驱动真实滚轮，确认修复前 `.stage` 的
`scrollTop` 一直是 0，修复后能正常增长；第 19 条反复按 G，确认叠加层与按钮状态
同步开合。

## 五、打包与分发

| # | 现象 | 原因 | 处理 |
| --- | --- | --- | --- |
| 20 | 打包后的 EXE 找不到前端，把数据库写进临时目录 | `settings.py` 里所有路径都相对源码目录推算 | 增加 `FROZEN` 分支：资源从 `sys._MEIPASS` 读，数据库、图片、缓存写在可执行文件旁边 |
| 21 | EXE 双击后还要手动开浏览器 | 只打印了地址 | 冻结状态下默认等价于 `--open` |
| 22 | 用 `.bat` 启动时控制台中文是乱码，且日志卡着不输出 | 重定向后的流走系统 ANSI 代码页，且是块缓冲 | 非 tty 时 `reconfigure(encoding="utf-8", line_buffering=True)`；真实控制台不动，交给 Windows 自己处理 |
| 23 | 传了 `--data-root` 之后，`.cache/` 仍然生成在程序目录里 | 这个参数只搬了数据库、图片与归档目录，漏了缩略图缓存 | 一起搬到数据目录下，除非显式设置了 `PIXORT_CACHE`。否则「把整个文件夹拷走就能迁移」这句话只对了一半，而且会在源码目录或 EXE 旁边留下一堆派生文件 |

## 六、静态托管（GitHub Pages）

第 19 条修完之后，前端已经是一个不依赖后端的纯静态站点，于是顺手加了在线演示。
这一轮要注意的不是「怎么部署」，而是**别把个人图库顺手传上去**：

| # | 事项 | 处理 |
| --- | --- | --- |
| 24 | 静态站没有后端，任何请求都会打到 Pages 上并 404 | `js/api.js` 增加演示判据，`demo.js` 用同名同形的接口顶替网络层；视图层的 `import { api } from '../api.js'` 一行都不用改 |
| 25 | 演示判据不能影响本地开发 | 优先级定为：显式 `?demo=` > 显式 `?api=` > `window.PIXORT_DEMO` > `file://` 或 `*.github.io`。本机跑后端时域名是 `127.0.0.1`，不会误判 |
| 26 | 真实作品不能出现在公开页面上 | 示例库是 20 条虚构记录 + 4 个虚构画师，配图是 `frontend/demo/` 里 8 张自己画的 Swiss 风格几何 SVG，与真实数据毫无关系 |
| 27 | 演示模式下点「导出备份」会往 Pages 发请求 | `manageDialog.js` 先取 `api.exportUrl()`，为空就提示「请在本机运行后端」并返回 |
| 28 | 演示模式的写操作容易被误当成真的保存了 | 所有写操作只改内存；状态栏常驻红字「演示模式 · 数据不写入磁盘」，进入时弹一次说明 |
| 29 | 构建脚本注入的标记遇到自定义域名会失效 | 判据里保留了 `*.github.io` 兜底，同时构建产物是把 `window.PIXORT_DEMO = true` **写进 HTML**，因此换域名也照样生效 |
| 30 | Jekyll 会跳过下划线开头的路径 | 构建时写入 `.nojekyll` |
| 31 | 静态托管需要一个 SPA 回退规则 | 不需要：路由用的是 hash（`#/work/5`），任何路径都能直接打开 |
| 32 | 在 Windows 上，`tools/build_pages.py` 会因为预览服务没关而抛一串 `WinError 32` | `shutil.rmtree` 的报错信息看不出「谁占着目录」 | 改成 `ignore_errors=True` 后再检查目录是否真的消失，是的话打印「目录正被占用，请先停掉 `--serve`」并返回 1 |

## 七、已知取舍

这些是有意保留的，不是遗漏：

* **没有鉴权**。服务默认只监听 `127.0.0.1`，本来就是单人本地工具；改成 `--host 0.0.0.0`
  就等于把图库开放给局域网，请自行确认网络环境。
* **`http.server` 不是生产级服务器**。它的并发模型够本地使用，但别放到公网。
* **标签仍是单列自由文本**。查询靠 `LIKE` 折叠实现，规模上到十万条会变慢；
  真要扩就会拆成 `tags` + `illustration_tags` 两张表，接口形状可以不变。
* **`PIXORT_CORS_ORIGIN` 默认 `*`**。同样因为默认只听回环地址；对外暴露前请收紧。
* **演示数据里的文件体积是编的**。示例作品写的是 `.png` 与合理的 MB 数，
  真正加载的缩略图是 SVG 占位图，两者对不上是刻意的——仓库里不放真实作品。
