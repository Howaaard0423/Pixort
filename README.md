# [Pixort](https://howaaard0423.github.io/Pixort/)

## 画师 / 角色 / 作品 / 整理

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)   [![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 项目结构

```
Pixort/
├── backend/            后端 API（Python 标准库 + SQLite，零必需依赖）
│   ├── run.py          启动入口
│   ├── pixort_api/     路由 / 服务 / 数据访问分层
│   └── tests/          接口测试
├── frontend/           前端界面（原生 ES 模块，Swiss International Style）
│   ├── css/ js/        样式与视图
│   ├── demo/           静态演示用
│   └── assets/
├── tools/
│   └── build_pages.py  组装 GitHub Pages
├── docs/               架构、接口、代码审查记录
├── assets/             字体 / EXE 图标
├── pixort.spec         PyInstaller 打包脚本 → dist/Pixort.exe
├── build-exe.bat       一键打包
├── requirements.txt    可选依赖（不装也能跑）
├── requirements-dev.txt 开发与打包依赖
└── .github/workflows/  build-exe.yml 发版打包；pages.yml 发布静态演示站
```

---

## 快速开始

### 方式一：源码

```bash
python backend/run.py --open
```

终端会打印地址（默认 <http://127.0.0.1:8000/>）并自动打开浏览器，也可以双击 `start-backend.bat` 启动。要求 **Python 3.10+**，不需要安装任何第三方包。

可选的增强依赖：

| 可选依赖 | 解锁的能力 |
| --- | --- |
| `pillow` | 服务端缩略图、图片尺寸与朝向探测 |
| `pyzipper` | AES 加密的备份压缩包 |

```bash
python -m pip install -r requirements.txt   # 可选
```

### 方式二：EXE

可前往 [Releases](https://github.com/Howaaard0423/Pixort/releases) 页面获取。

也可以选择如下方法：

```bash
python -m pip install -r requirements-dev.txt
pyinstaller --clean --noconfirm pixort.spec     # 或者双击 build-exe.bat
```

产出位于 `dist/Pixort.exe` 。

* 双击即启动服务并在 EXE **旁边**生成 `illustration_manager.db`、 `illustrations/`、 `.cache/`，控制台窗口显示地址并自动打开浏览器；
* 换端口或数据目录：`Pixort.exe --port 8080 --data-root D:\Pictures`，迁移时把整个文件夹拷走即可。

---

## 数据安全

* 删除作品默认**归档**而不是直接删除文件。
* 删除画师只有在没有任何记录再引用该文件夹时才会移除目录。
* 备份恢复前会先校验压缩包结构，失败时自动回滚到原有数据。

---

## 许可证

MIT License

---
