# 接口

后端是一个普通的 HTTP 服务，默认监听 `http://127.0.0.1:8000`。
所有接口返回 JSON（图片接口返回二进制），并且都带 CORS 头，前端可以放在别的域上。

## 约定

* **成功**：业务数据直接放在顶层，集合形如 `{"items": [...], "total": 12}`。
* **失败**：统一是
  ```json
  { "error": { "message": "人话解释", "details": null } }
  ```
  状态码只用 400（参数错）/ 403（越权路径）/ 404 / 405 / 409（重名）/ 500。
* **标签**：读写都用字符串或数组皆可，分隔符接受 `,` `，` `、` `;` `；`，
  写入时去重、去空白。
* **时间**：ISO-8601（秒精度），例如 `2026-05-22T09:14:00`。
* **分页**：`limit`（默认 120，上限 500）+ `offset`，响应里有 `total` 与 `has_more`。
* **每个作品对象**都额外带三个由服务端补上的字段：

  | 字段 | 含义 |
  | --- | --- |
  | `file_exists` | 磁盘上是否真的能找到这个文件 |
  | `url` | 原图地址 `/api/illustrations/{id}/content` |
  | `thumbnail_url` | 缩略图地址 `/api/illustrations/{id}/thumbnail` |
  | `download_url` | 带 `download=1` 的原图地址，点了直接存盘 |

## 库信息

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 存活探针。返回版本、当前时间、Python 版本、缩略图实现（`pillow` / `none`）、数据目录 |
| GET | `/api/stats` | 计数器：作品 / 画师 / 角色总数、评分分布、标签数、缺失文件数、磁盘用量 |
| GET | `/api/tree` | 画师 → 作品的树，用于左侧索引栏一次性加载 |
| GET | `/api/tags` | 全部标签及出现次数，按 `(-次数, 名称)` 排序 |
| GET | `/api/formats` | 支持的图片扩展名 |
| GET | `/api/settings` / PUT `/api/settings` | 读写键值配置，值按 JSON 存 |
| POST | `/api/library/maintenance` | 扫描磁盘并修正数据库 |

`/api/library/maintenance` 的请求体：

```json
{ "repair": true, "refresh_metadata": true, "dedupe": false, "dry_run": true }
```

默认 `dry_run: true`，也就是只报告不落笔；确认无误后再传 `dry_run: false`。
报告包含缺失文件、尺寸/体积待补的记录、重复项与孤儿文件。

## 画师 / 角色

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/artists` | 画师列表（含作品数） |
| POST | `/api/artists` | `{"name": "…"}`，重名返回 409 |
| PATCH | `/api/artists/{id}` | `{"name": "新名字"}`，同时会重命名磁盘上的同名文件夹 |
| DELETE | `/api/artists/{id}` | `?delete_files=false` 可以只解除关联 |
| POST | `/api/artists/merge` | `{"source_id": 1, "target_id": 2}`，把作品全部改挂到目标画师后删除源画师 |
| GET | `/api/characters` | 角色列表 |
| POST | `/api/characters` | `{"name": "…"}` |
| PATCH | `/api/characters/{id}` | 改名 |
| DELETE | `/api/characters/{id}` | 删除 |

删除画师时不会立刻动磁盘：只有当**数据库里再没有任何记录**指向那个文件夹时才会移除，
否则原样保留，并在响应里用 `folder_kept` 说明。

## 作品

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/illustrations` | 列表 + 筛选 |
| GET | `/api/illustrations/{id}` | 单条 |
| POST | `/api/illustrations` | 为服务器上**已存在**的文件建一条记录 |
| PATCH | `/api/illustrations/{id}` | 局部更新 |
| DELETE | `/api/illustrations/{id}` | 删除记录并处理文件 |
| POST | `/api/illustrations/bulk-update` | 批量改评分/画师/角色，或批量加减标签 |
| POST | `/api/illustrations/upload` | `multipart/form-data` 上传，一步到位 |
| POST | `/api/illustrations/scan-local` | 预演：这些服务器路径里有多少张图 |
| POST | `/api/illustrations/import-local` | 真正导入这些服务器路径 |

### 列表的筛选参数

| 参数 | 说明 |
| --- | --- |
| `q` | 关键词，同时匹配标题、画师、角色、标签（`LIKE` 通配符已转义） |
| `tag` | 单个标签的精确命中 |
| `artist_id` / `artist_name` | 按画师 |
| `character_id` | 按角色 |
| `rating` | 评分等于 |
| `rating_min` | 评分大于等于 |
| `unassigned=1` | 只看「未分类」 |
| `sort` | `created_desc`（默认）/ `created_asc` / `updated_desc` / `title_asc` / `title_desc` / `rating_desc` / `artist_asc` / `manual` |
| `limit` / `offset` | 分页 |

### 更新与删除

`PATCH` 接受的字段只有这几个，其它键会被忽略：`artist_id`、`character_id`、
`title`、`tags`、`rating`（自动夹到 0–5）、`remark`、`sort_order`。
传进来的外键会先查一遍再写，遇到不存在的 id 返回 400 而不是 SQLite 的 500。

`DELETE` 用 `file` 参数决定文件怎么处理：

| `file=` | 行为 |
| --- | --- |
| `archive`（默认） | 移动到 `archive_illustrations/<画师>/` |
| `delete` | 直接删除文件 |
| `keep` | 只删记录，文件留在原处 |

响应里的 `file_action` 会说明实际结果（`mode` 与 `moved_to`）。

### 批量更新

```json
{ "ids": [1, 2, 3], "rating": 5, "tags_add": ["精选"], "tags_remove": ["待定"] }
```

`ids` 必填；`rating` 这类普通字段是**覆盖**，`tags_add` / `tags_remove` 是在原有
标签上做增删。整个过程在一个事务里，全成功或全回滚。

### 上传

`POST /api/illustrations/upload`，`multipart/form-data`：

| 字段 | 说明 |
| --- | --- |
| `files`（可重复） | 图片本体 |
| `relative_path`（可重复） | 与 `files` 一一对应的相对路径，用来推断画师文件夹 |
| `artist` / `artist_mode` | 指定画师名；`artist_mode=auto` 时从目录结构推断 |
| `character` / `tags` / `rating` | 建记录时一并写入 |
| `skip_duplicates` | 默认 true，按 SHA-256 跳过已入库的图 |

单个文件失败不会中断整批，响应里逐条给出 `imported` / `skipped` / `failed`。

## 图片

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/illustrations/{id}/content` | 原图。`?width=1600` 会返回缩放后的版本（64–2560） |
| GET | `/api/illustrations/{id}/content?download=1` | 同上，但带 `Content-Disposition` 直接下载 |
| GET | `/api/illustrations/{id}/thumbnail` | 缩略图，`?width=` 默认 320 |
| GET | `/media/{相对路径}` | 兼容桌面版生成的旧链接 |

两者都返回强 `ETag`，浏览器第二次访问会拿到 304。缩略图缓存写在
`.cache/thumbnails/`，没有装 Pillow 时退化成直接返回原图。

## 备份与恢复

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/transfer/export` | 现场生成备份并下载。`?database_only=1` 只打包数据库，`?password=…` 加密 |
| GET | `/api/transfer/exports` | 列出导出目录里已有的备份包 |
| DELETE | `/api/transfer/exports` | 清空导出目录 |
| GET | `/api/transfer/exports/{name}` | 下载已有的备份包 |
| POST | `/api/transfer/inspect` | 上传（或 `?path=` 指定）备份包，只做校验与预览 |
| POST | `/api/transfer/restore` | 恢复备份 |

`inspect` / `restore` 可以传 `multipart/form-data`（字段名 `archive`），
也可以用 `?path=<服务器上的路径>`。`restore` 必须先看一次预览，再带 `confirm=1`
提交，否则会返回 202 让你确认；恢复过程中出错会自动回滚到原数据。

## 在浏览器里试

```bash
python backend/run.py --open
# 打开 http://127.0.0.1:8000/api/health、/api/stats、/api/illustrations?limit=5
```