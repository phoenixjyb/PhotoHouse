# 拾光相册 · PhotoHouse

PhotoHouse 是可纯本地部署的家庭记忆中心：原始资料保存在家庭自己的设备或服务器，
照片、视频、录音和文字共同承载可以讲述、阅读和聆听的故事。
后端、Web、Android 手机与 TV 在 [PhotoHouse 主仓库](https://github.com/phoenixjyb/PhotoHouse)
共同维护；旧应用仓库按[整合规则](docs/REPOSITORY_TRANSITION.md)保留为历史与私有运行参考。

## 当前交付：2026-10-29

[PR #111](https://github.com/phoenixjyb/PhotoHouse/pull/111) 已合并到 main
（`e808e3083af61bdbc4beae366d24da35340c5ad6`）。对应 API/Web 和新版
**小贾 · Jude** 对话界面已部署到 Windows；这是有日期的交付记录，不是自动探测的在线状态。

- **搜索**：受保护的中英条件搜索、人物/日期/媒体筛选、解释、澄清和请求恢复。
  本次 Windows HTTPS 中英查询各返回 20 张授权结果；不能据此推断全库语义覆盖率。
- **照片分组**：库级索引、跨页堆叠、私有封面/分离选择，以及每 15 分钟的 SYSTEM 刷新。
  两页读取、首轮刷新和两次后续刷新已验证；原片保留。活动/共同回忆分组是另一项功能。
- **小贾助手**：新版 Web 对话布局、紧凑控件和明确的听取/处理/播放状态；
  当前模型工具 profile 仅执行受保护的只读影像搜索，不提供通用 shell 或自动改写家庭资料。
- **本地语音**：Windows 实际语音合成 → 识别 → 同请求回执 → 搜索 → 回复音频通过，
  返回 20 张照片，全链路 28.688 秒。恢复的转写先供审阅，不自动发送或重开麦克风。
  用户明确开始的前台语音会话可轮流听取与播放，暂停/结束及生命周期中断仍有效。
- **故事草稿**：选定来源生成了结构有效、来源 ID 合法、非空且标记 `needs_review` 的未保存草稿。
  文笔质量暂缓评估；生成结果不会自动保存或发布。

上述是 Windows 服务与源码证据。**真实麦克风/扬声器及家庭体验仍待用户试用**；
本次没有发布新 Android/TV 安装包，也没有证明所有可选模型和功能均已启用。
[交付记录](docs/RELEASE_2026-10-29.md)保留测试、部署和未完成项的边界；
[小贾使用与语音恢复](docs/JUDE_ASSISTANT.md)、[当前状态](docs/PROJECT_STATUS.md)、[功能矩阵](docs/FEATURES.md)和
[路线图](docs/ROADMAP.md)分别说明现状、能力和下一步。

**GitHub Actions 因成本暂停。** 不启用、触发、重跑工作流，或推送会触发它们的修改，
直到维护者明确恢复。继续使用本地检查；GitLab CI 是独立配置，不能假设已接通。

## 10 月 30 日改进进度（尚未上线）

用户试用后的下一版已在本地实现：更紧凑的聊天界面、中文月份理解、多轮条件细化、
有界对话上下文，以及保留原文、单独审阅和采纳的故事润色提案。
这些改动通过了对应本地检查，但 **不能当作 Windows 已部署功能**。
当前交付基线仍为上面的 10 月 29 日版本。新的双语自然语音也仍待运行验证。
详情见[当前状态](docs/PROJECT_STATUS.md#october-30-source-increment-not-deployed)。

## 产品体验

手机用于记录和交谈，Web 用于整理与共同编辑，TV 用于单独授权的家庭观看。
资料库是权限边界；相册是选片集合；家人原始贡献、转写、故事和回忆录是不同的内容层级。

- **影像资料库**：浏览照片/视频，上传并审阅归属，区分收到、后台处理和可播放状态。
- **共同回忆**：保留文字或录音的原始贡献、署名和来源；转写及润色属于派生结果。
- **故事与回忆录**：编排影像、章节和已审阅来源，阅读、手动朗读及明确保存。
- **拾光助手**：在当前账号和资料库内对话、查找资料、查看回执，并使用已实现的故事阅读操作。

从[第一个故事指南](docs/FIRST_STORY_GUIDE_ZH.md)开始；长录音自动编排、多人自动合写、
更广泛的自主 agent 动作及跨设备家庭体验仍是后续工作。不同部署需分别配置与验证，
示例配置默认关闭可选提供者，不会继承家庭服务器的启用状态。

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
[API 包检查](docs/API_PACKAGE_INSPECTION.md)提供只读核验：将固定 ZIP 与明确 Git 提交逐字节比较，
不解压、不运行候选代码、不触碰家庭数据或服务。

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
