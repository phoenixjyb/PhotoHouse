# 拾光相册 · PhotoHouse

让家人的照片、视频和背后的回忆，成为可以一起讲述、阅读和聆听的故事。
后端、Web、Android 手机与 Android TV 在同一个主仓库维护。

**后续开发统一在 [phoenixjyb/PhotoHouse](https://github.com/phoenixjyb/PhotoHouse) 进行。**
已审阅的初始导入通过 API／Android CI 并合入主分支；旧应用仓库保留为历史与私有运行资料参考，
迁移和退役规则见[仓库整合说明](docs/REPOSITORY_TRANSITION.md)。
私密漏洞报告已通过[GitHub Security Advisories](https://github.com/phoenixjyb/PhotoHouse/security/advisories/new)
启用。这个仓库发布源码，不会自动替换现有安装。

## 三种体验

- **影像资料库**：按资料库、日期与家庭语境浏览，查看上传和准备状态。
- **共同回忆**：添加文字或录音，检查转写结果后明确提交，保留原始贡献和署名。
- **故事与回忆录**：把影像、章节和家人的贡献串起来，阅读、朗读并查看素材来源。

手机用于记录和交谈，Web 用于整理与共同编辑，TV 用于家人一起观看。
AI 写作建议需要经过模型资格验证和用户审阅；自动故事生成仍是交付关卡。
回忆集手工编辑和助手待确认恢复已有源代码及合成浏览器覆盖；b1 编辑服务默认关闭，
这些检查不代表运行服务或模型质量验收。手机源码支持受保护的分组故事创建、审阅、
冲突恢复、整篇或章节贡献，以及可选的个人资料署名。标题建议提供者默认关闭；
本次源码更新未生成签名 APK，也未启用新的服务功能。
查看[故事体验说明](docs/STORY_EXPERIENCE.md)、[功能与验收清单](docs/FEATURES.md)、
[故事阅读导航](docs/STORY_READER_NAVIGATION.md)、[浏览器录音生命周期](docs/WEB_RECORDING_LIFECYCLE.md)、
[可选 Web 浏览器检查](docs/WEB_DEVELOPMENT.md)及[手机会话预览证据](clients/android/docs/ANDROID_CONVERSATION_PREVIEWS_2026-10-05.md)。
交付源码时使用[可重复的源码打包工具](docs/SOURCE_PACKAGING.md)。

## 开始开发

需要 Python 3.12。从仓库根目录运行：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r config/requirements-dev.lock
.venv/bin/python tools/check.py api
```

可先运行 `.venv/bin/python tools/doctor.py`（或 `--json`）检查现有环境，详见[离线环境自检](docs/DEVELOPMENT_ENVIRONMENT.md)。工具不会安装依赖或启动服务；检测通过也不代表测试通过。

如需只运行回忆录相关的 CPU 服务与契约检查，可运行 `.venv/bin/python tools/check.py memory`；
该聚焦 profile 通过 127 项测试和 76 个子测试。完整 API profile 也包含这些检查。

已合并的托管源码检查（PR #13，`2f17ed9`）通过 **936 项 API 测试和 558 个子测试**、无监听端口的合成演示及 92 项工具测试，使用新鲜的哈希锁定依赖安装。680/361 和初始导入等较早记录保留为历史结果。详情见[开发指南](docs/DEVELOPMENT.md)。
不需要 GPU、模型权重或家庭服务器。Windows 请使用 `.venv\Scripts\python.exe`。
Windows PowerShell 的完整 CPU setup、demo 与当前源码校验命令见[开发指南](docs/DEVELOPMENT.md)。
另有 `tools/check.py windows-cpu` 聚焦合成数据库、运行配置和源码包检查；
其独立 Windows CI 与真实家庭服务器验收分开，见[Windows CPU 检查](docs/WINDOWS_CPU_CHECKS.md)。

模型代码与权重分开管理：[模型与服务架构](docs/MODEL_PROVIDER_ARCHITECTURE.md)列出 VLM、
ASR、TTS、人脸与影像向量等适配器及更换规则。`models/catalog.json` 是源码清单，
不启动模型，也不自动选择运行配置。可用 `python3 tools/model_catalog.py --json` 离线核对；
权重、私有端点和凭据保留在运行主机，模型自己的许可证需分别确认。

Android 需要 JDK 17 和 Android SDK 34：

```sh
.venv/bin/python tools/check.py android
```

该命令执行共享模块测试、手机/TV 单元测试、lint 和未配置服务器的 debug 构建。
PR #13 的托管 Android CI 通过 812 项 JVM 测试和手机／TV 的 lint、debug 构建；
初始 773 项及更早的定向检查保留为历史记录。
构建后可运行 `.venv/bin/python tools/android_test_report.py` 只读汇总已有结果；它不重新执行测试。
具体环境、证据范围及限制见
[开发指南](docs/DEVELOPMENT.md)和[Android 验收记录](docs/local-android-acceptance.json)。

可选的 Web 合成浏览器 profile 需要已有的 Node、Playwright 和 Chromium；它不安装或下载工具，
也不连接家庭服务。运行方式和合成证据边界见 [Web 开发说明](docs/WEB_DEVELOPMENT.md)。

## 目录

```text
server/                 API、Web、数据库迁移、worker 和测试
clients/android/        手机、TV 及共享 Kotlin 模块
clients/android/contracts/  共享协议说明与示例
models/                 可选 provider 配置；不包含模型权重
branding/               主人授权的可选 PhotoHouse 原图标
config/                 经审查的配置模板和依赖锁文件
examples/               生成合成素材的演示
third_party/            上游许可证与归属说明
tools/                  开发检查与初始源码验收
```

[架构说明](docs/ARCHITECTURE.md) 定义权限、语音、素材来源和数据保留边界。
初始导入的文件及主动变更有可核验的清单；没有导入历史私有 Git 数据。

## 参与贡献

阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [AGENTS.md](AGENTS.md)。
使用合成素材、临时数据库，保持后端和客户端协议一致。家庭影像、原始录音、
凭据、数据库、人脸/影像向量、模型权重和签名材料不能进入源码仓库。
安全问题可通过已启用的 [GitHub 私密安全公告](https://github.com/phoenixjyb/PhotoHouse/security/advisories/new)报告，见 [SECURITY.md](SECURITY.md)。

## 许可证

第一方代码采用 [Apache-2.0](LICENSE)。第三方库和工具保留各自许可证，
见 [第三方归属说明](THIRD_PARTY_NOTICES.md) 与 [素材来源](docs/ASSET_PROVENANCE.md)。
