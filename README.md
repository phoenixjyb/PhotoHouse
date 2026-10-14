# 拾光相册 · PhotoHouse

PhotoHouse 是可纯本地部署的家庭记忆中心：原始资料保存在家庭自己的设备或服务器，
照片、视频、录音和文字共同承载可以讲述、阅读和聆听的故事。
后端、Web、Android 手机与 TV 在 [PhotoHouse 主仓库](https://github.com/phoenixjyb/PhotoHouse)
共同维护；旧应用仓库按[整合规则](docs/REPOSITORY_TRANSITION.md)保留为历史与私有运行参考。

## 现在在哪里

截至 **2026-10-14**：API/Web v58 对应源码已部署，手机 **v58** 已签名并发布到
Windows HTTPS OTA，TV OTA 保持 **v30**。原图标和签名保留。手机安装、家庭实际
语音体验与投影仪检查仍需验证；发布成功不等于这些体验已验收。

[当前状态](docs/PROJECT_STATUS.md)记录源码、运行配置及验收边界，
[v58 试用说明](clients/android/docs/PHONE_V58_TEST_GUIDE_ZH.md)给出已核对的语音短句。
源码检验、托管 CI、APK、服务及实体设备是独立证据；本次文档审查没有刷新远端
GitHub 分支/CI 状态，也没有自动发布当前工作分支。

## 产品体验

- **影像资料库**：按资料库、相册和日期浏览，上传、审核、查看准备状态并播放。
- **共同回忆**：添加文字或录音，明确保存原始贡献、署名及来源；转写和润色是派生结果。
- **故事与回忆录**：组合影像、章节与家人贡献，阅读、手动朗读并检查素材来源。
- **拾光助手**：手机/Web 的私人对话与前台语音入口；在当前结果中检索故事、打开指定故事、
  朗读开篇，显示听取/处理/播放状态，并提供暂停与结束。

手机用于记录和交谈，Web 用于整理与共同编辑，TV 用于已发布的家庭观看。
当前语音轮流听取与播放。自动故事生成、标题提供者、共享回忆分组和回忆录
编辑/版本能力有源码与资格检查，但在本次观察的运行配置中仍关闭；
AI 文本需要来源核验和用户审阅。详见[功能矩阵](docs/FEATURES.md)和[下一步](docs/ROADMAP.md)。

## 开始开发

推荐 Python 3.12。从仓库根目录运行：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r config/requirements-dev.lock
.venv/bin/python tools/doctor.py
.venv/bin/python tools/check.py api
```

CPU API 检查使用生成的数据，不需要 GPU、模型权重或家庭服务器。
`tools/check.py memory`、`windows-cpu`、`android`、`web` 是明确的检查 profile。
Windows 使用 `.venv\Scripts\python.exe`；安装与命令详情见
[开发指南](docs/DEVELOPMENT.md#cpu-quick-start)和[环境自检](docs/DEVELOPMENT_ENVIRONMENT.md)。
工具检查环境不会安装依赖或启动服务，检测通过也不等于测试通过。

Android 使用 JDK 17、SDK platform 34 和项目指定 build tools：

```sh
.venv/bin/python tools/check.py android
```

它执行 JVM 检查、lint 和未配置家庭服务器的 debug 构建，不签署发布 APK、安装设备或发布 OTA。
[Android README](clients/android/README.md)列出模块和局部命令。
Web 可选的 Node/Playwright/Chromium 合成检查见[Web 开发](docs/WEB_DEVELOPMENT.md)；
它使用已有工具，不访问家庭服务。[Development](docs/DEVELOPMENT.md)保留按版本的测试与 CI 记录，
当前本地/交付结果见[状态页](docs/PROJECT_STATUS.md)，不把旧计数当成当前全部源码的 CI 结果。

## 结构与文档

| 目录 | 内容 |
| --- | --- |
| [`server/`](server/README.md) | 受保护 API、Web、SQLite 契约、独立 worker 和测试 |
| [`clients/android/`](clients/android/README.md) | 手机、TV、共享 Kotlin 模块与协议 |
| [`models/`](models/README.md) | 可替换模型/服务的源码目录清单与禁用示例，不包含权重 |
| [`config/`](config/examples/README.md) | 审阅过的配置示例与依赖锁 |
| [`docs/`](docs/README.md) | 当前状态、架构、功能、路线图、领域契约及历史证据 |
| [`tools/`](docs/DEVELOPMENT.md) | 环境、检查、模型清单、源码打包和来源核验 |
| [`examples/`](examples/generated-demo/README.md) | 合成数据演示 |
| [`branding/`](branding/README.md) / `third_party/` | 授权图标、第三方许可证与归属 |

[架构](docs/ARCHITECTURE.md)说明权限、多个数据存储、语音和媒体处理边界。
[模型架构](docs/MODEL_PROVIDER_ARCHITECTURE.md)区分已有适配器、可投影配置、运行安装和质量验证。
`models/catalog.json` 不启动模型，也不自动选择部署；可用 `python3 tools/model_catalog.py --json` 离线核对。
模型、原始媒体、私有配置、凭据及签名材料保留在运行环境，模型许可证分别确认。
[运维说明](docs/OPERATIONS.md)定义资格检查、操作授权、备份、回滚与交付；
源码仓库还不是一条命令即可安装的家庭生产系统。

## 贡献与许可证

阅读 [CONTRIBUTING.md](CONTRIBUTING.md)、[AGENTS.md](AGENTS.md)及
[本次架构审查](docs/ARCHITECTURE_REVIEW_2026-10-14.md)。使用合成素材和临时数据库，保持跨端协议兼容，
为变更更新领域文档、状态/路线图和来源清单。没有导入旧仓库的私有 Git 历史。

家庭照片、录音、数据库、人脸/影像向量、模型权重、凭据及签名密钥不能进入 Git。
漏洞报告方式见 [SECURITY.md](SECURITY.md)。第一方代码采用 [Apache-2.0](LICENSE)；
第三方与模型保留各自许可证，见 [归属说明](THIRD_PARTY_NOTICES.md)和[素材来源](docs/ASSET_PROVENANCE.md)。

## 项目介绍与家庭记忆中心

[打开项目介绍网站](https://photohouse-family-memories.yanbophx.chatgpt.site)，
或查看[网站源码](website/README.md)。网站用插画和虚构示例解释 PhotoHouse 的目的与功能。
[家庭记忆中心设计](docs/FAMILY_MEMORY_HUB.md)规划长篇口述、亲属与事件线索、多人补充及
有来源的章节与回忆录；长录音和自动合写仍需后续开发与验收。
