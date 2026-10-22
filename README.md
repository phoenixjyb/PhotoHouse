# 拾光相册 · PhotoHouse

PhotoHouse 是可纯本地部署的家庭记忆中心：原始资料保存在家庭自己的设备或服务器，
照片、视频、录音和文字共同承载可以讲述、阅读和聆听的故事。
后端、Web、Android 手机与 TV 在 [PhotoHouse 主仓库](https://github.com/phoenixjyb/PhotoHouse)
共同维护；旧应用仓库按[整合规则](docs/REPOSITORY_TRANSITION.md)保留为历史与私有运行参考。

## 现在在哪里

截至 **2026-10-22**，受保护搜索、照片分组和默认关闭的 AI 工具源码已通过
[PR #108](https://github.com/phoenixjyb/PhotoHouse/pull/108) 合并；合并提交
`a6dfe31` 与已审阅源码 `c5dd850` 的 Git tree 完全一致。托管 Windows/API、浏览器、
Android 与独立 Android fixture UI 检查通过；固定源码本地 API、生成演示及三条浏览器旅程也通过。
**Windows API/Web 已于 2026-10-22 11:48:33（北京时间）部署并通过独立原生后检**：
R3 核对了精确源码、293 个 API 源文件和新监听器；恢复与权限检查通过。独立的 125 公共站点
前后核验也通过，静态家具服务保持原样。首轮 R1 预检在维护或任务变更前拒绝，R2 在执行前退役。语义搜索与本地 AI 仍关闭，A0 schema `a0c9d2e4f817` 保持不变，
没有 F2 迁移或索引/身份/亲属范围扩展。手机 v75 / `0.75-gallery-search` 已由独立的
[PR #104](https://github.com/phoenixjyb/PhotoHouse/pull/104) 发布；真实设备与家庭体验仍待验收。PR #108 没有发布新 APK，TV v30 不变。
[本次搜索与源码发布记录](docs/SEARCH_RELEASE_2026-10-22.md)区分源码合并、运行部署与设备验收。

已交付的搜索包括人物/日期/媒体/文字联合条件、受保护的已确认人物与私有亲属关系、
中英混输和有上下文的后续筛选、结果解释，以及排除条件与严格条件的澄清保护。
这不代表任意模糊意图或视觉语义检索已经完成。详见
[搜索发布、能力与剩余门槛](docs/SEARCH_RELEASE_2026-10-20.md)；真实家庭设备体验仍待验收。

此前发布的 v74 在手机“导入进度 → 服务器记录”和 Web“我的上传”增加可展开的“处理详情”，
区分已收到、相册归属、后台处理及实际可观看状态。详见
[v74 发布与测试步骤](clients/android/docs/PHONE_V74_RELEASE_2026-10-20.md)。

[当前状态](docs/PROJECT_STATUS.md)区分源码、服务与家庭验收。
搜索 v2 Web/手机客户端已在 v62 交付；当前 API/Web 与手机版本见状态页。
托管 CI 的结果应绑定各 PR 的确切提交；本地和运行服务记录不能替代它。
[源码同步与部署边界](docs/REPOSITORY_SYNC_2026-10-15.md)说明 main、功能分支和公开安装工具的状态。

## 产品体验

已交付的[相似照片堆叠](docs/SIMILAR_PHOTO_STACKS.md)：
同页相近照片先显示代表图和数量，可展开、换封面或单独显示；所有原片保留。
Web 与手机均已提供该功能；跨页持久分组和真实照片分组质量仍需继续改进。

- **影像资料库**：按资料库、相册和日期浏览，上传、审核、查看准备状态并播放。
- **共同回忆**：添加文字或录音，明确保存原始贡献、署名及来源；转写和润色是派生结果。
- **故事与回忆录**：组合影像、章节与家人贡献，阅读、手动朗读并检查素材来源。
- **拾光助手**：手机/Web 的私人对话与前台语音入口；在当前结果中检索故事、打开指定故事、
  朗读开篇，显示听取/处理/播放状态，并提供暂停与结束。

手机用于记录和交谈，Web 用于整理与共同编辑，TV 用于已发布的家庭观看。
刚开始可以按[第一个故事指南](docs/FIRST_STORY_GUIDE_ZH.md)，把照片上的家人回忆
编排成已保存故事，再组合为回忆集；照片留言和故事是不同的内容层级。
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
