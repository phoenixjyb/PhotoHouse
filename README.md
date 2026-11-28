# 拾光相册 · PhotoHouse

## Product roadmap / 产品路线图

[English / 中文 dashboard](docs/product-roadmap/index.html) · [Maintenance / 维护](docs/product-roadmap/README.md).

The bilingual snapshot separates recorded delivery, source-ready work, gaps and next steps.
双语快照分别展示已交付记录、源码就绪工作、差距与下一步。Windows 的 `/roadmap/` 已上线并经用户确认。

## 11 月 25 日源码整合 / November 25 source integration

`main` includes bilingual Search refinements, recent memory groups and reviewable
story drafts made from saved groups. Photo descriptions load on demand and
prepared videos start their two protected checks together. See the
[audit reconciliation](docs/AUDIT_RECONCILIATION_2026-11-24.md) for local
verification and remaining product work. The Windows release is recorded below.

`main` 已合并中英文搜索追问、近期回忆组，以及从已保存的回忆组生成待审阅故事草稿的功能。
照片描述按需加载，已准备的视频可并行执行两项受保护的播放检查。
[审计对照表](docs/AUDIT_RECONCILIATION_2026-11-24.md)记录本地验证与待完成工作。
Windows 交付记录见下方。

## Windows 交付：2026-11-24

[PR #115](https://github.com/phoenixjyb/PhotoHouse/pull/115) 已合并到 main（`c7a28ef`），包含 Rust PR #114。
Windows 已通过受保护的源码覆盖方式上线四项修复：地点追问、月份纠正保留原年份、
空白 AI 建议保留作者原章节，以及小贾临时故障后的明确重开恢复。
现有基础运行环境、Rust 内核、模型与自动导入定时设置保留。

16 项既有 HTTPS 检查与 9 项路线图检查通过；分组的自然 SYSTEM 运行正常关闭，
但返回 `REFRESH_DEFERRED`、更新数为 0，不能称为全库扫描或家庭质量验收。
实际清理、离线等待与所有权检查完成后才确认交付。GitHub CI 继续暂停。
详见[本次交付与边界](docs/RELEASE_2026-11-24_FUNCTIONAL_FIXES.md)。下方较早记录保留各自日期与范围。


PhotoHouse 是可纯本地部署的家庭记忆中心：原始资料保存在家庭自己的设备或服务器，
照片、视频、录音和文字共同承载可以讲述、阅读和聆听的故事。
后端、Web、Android 手机与 TV 在 [PhotoHouse 主仓库](https://github.com/phoenixjyb/PhotoHouse)
共同维护；旧应用仓库按[整合规则](docs/REPOSITORY_TRANSITION.md)保留为历史与私有运行参考。

## 11 月 24 日 Web 设计与 Windows 交付

参考 Google Modern Web Guidance，统一了小贾对话界面、控件与配色，改用独立滚动的对话区，
并检查键盘访问、小屏和放大文字、对比度及减少动画设置。切换语言时，空闲私密对话会在
重新确认权限后恢复文字与未发送草稿，不会自动提交或开启麦克风。搜索细化、语音状态与故事选择的
生成数据浏览器检查通过；新版界面及上述四项修复现已部署到 Windows，家庭实际试用仍单独记录。
详见[设计审查与交付边界](docs/WEB_DESIGN_REVIEW_2026-11-24.md)。GitHub CI 继续暂停。

早期两次新版界面部署曾被启动校验的 PowerShell 查询超时阻断，均已回滚并保留失败记录。
[查询预算修复](docs/WINDOWS_PLAYBACK_QUERY_BUDGET.md)通过 19 项本地测试与 8 次 Windows 只读查询，
其中一次实际耗时 35 秒；新上限为 45 秒，仍受原有 900 秒总预算约束。
该修复后来已安装到 SYSTEM 启动链，新界面与双语路线图已交付；
本次后续功能修复及另一处计划任务快照超时的处理见上述交付记录。

## 历史交付：2026-10-29

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

## 故事润色与助手模型角色（早期资格记录）

本节保留当时的资格与部署边界，不作为当前启用角色的自动探测；11 月 24 日交付没有更换模型或云服务。

当前源码将故事润色和 Search/小贾助手配置为两个本地模型角色：故事润色使用
Qwen3-4B-Instruct-2507，Search/小贾保留现有 qwen2.5-1.5b-instruct-q4-k-m-trial。
润色保留原稿，
只生成需要作者审阅的草稿；姓名校正仅使用公共规范名称与已授权家庭上下文，
不会猜测私人身份。私有 SQLite 副本上的 native qualification 覆盖运行中主动
取消、实际 30 秒过期和生日故事生成三个案例，共用时 134.468 秒。测试观察到上下文拼写与
重复语句有所改善，但标题仍不理想，仍需人工审阅。这不代表功能已部署或通过
实体设备/家庭验收；新的角色、人名校正和云校对界面尚未上线，当前 Windows
rollout 在产生效果前被拦截。Search 与照片分组仍走现有路径。

可选云校对默认关闭且未配置。每次发送前都会显示完整请求，并要求作者对该请求
明确同意；不会在后台发送。对话连续性来自应用管理、已授权且保留的历史，不是
模型自带记忆或不受限 agent。角色配置、资源上限和 qualification 边界见[技术说明](docs/STORY_GROUNDING_AND_CLOUD_PROOFREADING.md)。

上述是 Windows 服务与源码证据。**真实麦克风/扬声器及家庭体验仍待用户试用**；
本次没有发布新 Android/TV 安装包，也没有证明所有可选模型和功能均已启用。
[交付记录](docs/RELEASE_2026-10-29.md)保留测试、部署和未完成项的边界；
[小贾使用与语音恢复](docs/JUDE_ASSISTANT.md)、[当前状态](docs/PROJECT_STATUS.md)、[功能矩阵](docs/FEATURES.md)和
[路线图](docs/ROADMAP.md)分别说明现状、能力和下一步。

**GitHub Actions 因成本暂停。** 不启用、触发、重跑工作流，或推送会触发它们的修改，
直到维护者明确恢复。继续使用本地检查；GitLab CI 是独立配置，不能假设已接通。

## 10 月 30 日改进交付（历史记录）

以下“尚未合并／部署”描述当时状态；后续主仓库整合及本次交付以上方 11 月 24 日记录为准。

更紧凑的聊天界面和有界对话上下文已在 Windows 部署（源码 `daa7e14`；
这一增量尚未合并到 main）。实际 HTTPS 验证了两轮搜索、历史读取、同请求恢复，
以及“去年九月份的照片 → 只看视频”保留日期条件。新分组刷新也完成了首轮 SYSTEM 运行。

三轮语音演示尚未通过；本地发现“改成十月份”会丢失上一轮年份，修复已通过对应本地检查，
仍待部署。新的双语自然语音在依赖安装阶段失败，现有语音服务未改动。
保留原文、单独审阅与采纳的故事润色提案也仍待 Windows 交付。
详情见[当前状态](docs/PROJECT_STATUS.md#october-30-delivery-and-remaining-increments)。

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

推荐 Python 3.12。从仓库根目录运行。

**Windows PowerShell**：将开发仓库放在 D:，使用 Python 3.12.4 或更高的 3.12 版本。

```powershell
py -3.12 tools\windows_work.py dependencies python
.\.venv\Scripts\python.exe tools\doctor.py
.\.venv\Scripts\python.exe tools\check.py api
```

需要运行浏览器检查时，先安装 Node.js，再用
`py -3.12 tools\windows_work.py dependencies web` 安装锁定的 Web 工具。
两个安装命令默认将缓存与安装临时文件放在 `D:\PhotoHouseWork` 下。
如果工作目录仅对管理员开放，请使用管理员 PowerShell。
其他本地数据盘及权限说明见[存储策略](docs/STORAGE_POLICY.md)。

**macOS 和 Linux**：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r config/requirements-dev.lock
.venv/bin/python tools/doctor.py
.venv/bin/python tools/check.py api
```

CPU API 检查使用生成的数据，不需要 GPU、模型权重或家庭服务器。
`tools/check.py memory`、`windows-cpu`、`android`、`web` 是明确的检查 profile。
安装与命令详情见[开发指南](docs/DEVELOPMENT.md#cpu-quick-start)
和[环境自检](docs/DEVELOPMENT_ENVIRONMENT.md)。
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
