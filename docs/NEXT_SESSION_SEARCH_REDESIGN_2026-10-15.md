# 新会话交接：自然语言检索改造

日期：2026-10-15。此文是新的搜索开发会话的启动说明。
**当前产品优先级是检索；新增故事创作和阅读体验扩展暂缓。** 已有家庭
回忆、故事文字仍可作为合法检索来源，不需要等待故事功能继续开发。

### 后续源码进度：Web/手机联合检索闭环

当前本地增量已接入私有 workspace 的显式 v2 协商、Web/手机条件解释、
亲属中心视角与逐项匹配来源。恢复按原检索版本重读当前授权来源，不重发、
不重放打开动作或语音。旧客户端保持 v1；新客户端仅在明确“不支持版本”的
capability 响应时回退探测。JSON 上下文新增 search_version 标记；部署和
回滚前需检查新建 v2 对话状态的兼容性。详见[合同](ASSISTANT_JOINT_SEARCH_V2.md)。
最终检查记录见[当前状态](PROJECT_STATUS.md)，不沿用旧版本的通过结论。
下一批仍是真实人物/索引准入和私有相关性标注、视频日期基准、本地语义理解
与排序；真实账号预批准无需重复询问，但注册本身不自动开通权限。

### 已完成源码进度：第一批联合检索

后续已有可选的[私有亲属检索合同](PRIVATE_KINSHIP_SEARCH.md)：显式中心视角、
指定账号/相册 allowlist、当前已审核人物绑定、关系/撤权变更失效。真实家庭
图谱、中文姓名和待注册账号预批准均在 Git 外；不要复制到测试、文档或源码。
本地 draft 不代表账号创建、生产权限开通或 Windows 部署。
实现 `01cf409` 的完整本地 API profile 通过 1,552 tests / 988 subchecks
及生成数据演示；回执的起止 commit、源码输入哈希一致。29 项聚焦亲属/
权限测试通过。后续按私有批准计划绑定已注册账号，不凭显示姓名自动开通。

检索开发已隔离在 `codex/search-redesign-20261015` worktree，避免与并行的
`codex/story-first-guide-20261015` 会话互相写入。主 checkout 保留原状态。
[第一批合同](ASSISTANT_JOINT_SEARCH_V2.md) 记录显式协商的 search-v2 API：
当前合格 caption、未删除的照片回忆、已审核人物 any/all、日期和媒体类型
在同一权限/来源快照下联合过滤；返回来源依据，并使旧来源绑定失效。
暂不建立持久全文库，不修改原 `RefreshingPlaceIndex` 策略。

这批是本地 API 源码；Web/手机/私有 workspace 尚未接入，Windows 未部署。
后续先完成客户端协商、解释呈现和恢复检查，再推进视频日期基准及本地
typed 理解/排名。下面原交接状态仍指写作时的已提交/线上版本。

实现提交 `b7d605b` 的完整本地 API profile 已通过：1,519 tests / 939
subchecks，加生成数据演示；私有回执核对起止 commit 和源码输入哈希一致。
聚焦联合检索 19 项通过。早期两次主动中断的完整 profile 不算通过；本批
没有运行 Web/Android profile、Windows 或家庭真实相关性验收。

## 1. 目标与完成标准

让用户通过日常语言找到自己有权访问的照片和视频，例如：

- 找一下去年的视频；找一下去年九月的照片。
- 帮我查一下示例人物的照片；只看他和另一位家人一起出现的。
- 找在海边玩的照片；再缩小到九月；打开第二个结果。
- 找家人曾经讲过某件事的照片，即使照片说明没有逐字重复这句话。

后端需要把自然语言转为可检查的查询计划，联合现有文本、已确认人物、
日期、地点以及经过资格检查的语义/视觉证据，返回有相关性和匹配依据的
当前结果。验收以实际跨来源命中、条件正确和权限隔离为准。

本会话可以分批完成；第一批应交付可运行、可测试的检索路径。设计选择、
源码、合成数据检查、Windows 运行和真实用户相关性评价分别记录。

## 2. 先建立实际工作区状态

应用开发主仓库是 **PhotoHouse monorepo**，不要在旧后端/Android 拆分仓库
继续应用开发。启动时执行：

```sh
git status --short
git branch --show-current
git log -5 --oneline
cat AGENTS.md
```

写交接前的分支是 `codex/phone-conversation-navigation-20261010`，工作区干净。
搜索修复源码基线是 **`5e608acd27d90a2bf1ff9a2643b4140fefef03e3`**。
后续交接文档提交会使 HEAD 更新；不要为了匹配这个基线回退或覆盖工作。
只读核对差异后再继续，保留他人修改，优先复用现有 checkout/构建缓存。

### 必读资料

1. [检索诊断与改造方案](ASSISTANT_SEARCH_REVIEW_2026-10-15.md)。
2. [项目当前状态](PROJECT_STATUS.md)、[当前路线图](ROADMAP.md)。
3. [助手设计与权限边界](PERSONAL_ASSISTANT.md)。
4. [开发与检查命令](DEVELOPMENT.md)、[源码打包](SOURCE_PACKAGING.md)。
5. 涉及模型时读 [Provider 架构](MODEL_PROVIDER_ARCHITECTURE.md)；涉及上线时读
   [Operations](OPERATIONS.md) 和 [v60 发布记录](../clients/android/docs/PHONE_V60_RELEASE_2026-10-15.md)。

## 3. 源码、线上和设备状态必须分开

| 层次 | 已有证据 | 不能据此推断 |
| --- | --- | --- |
| 线上 API/Web | v60 源码 `53e3954725197906771b6dd6ca470a0d1d58da9d`；10月15日07:48北京时间切换完成，07:50独立核对通过 | 新会话时仍是同一运行状态，需要按操作需要重查 |
| 手机 OTA | v60 / `0.60-reading-comfort`，原证书和图标，完整可信 HTTPS 读回通过 | 每台手机都已安装或所有语音场景通过 |
| 用户反馈 | 用户报告试用了新 APK，并通过拾光助手进行了搜索；服务器回执对应近期请求 | 尚无本轮 ADB 版本/完整设备验收证据；不要把连接手机设为本地开发前置条件 |
| 本地搜索修复 | `5e608ac` 已提交，尚未部署；没有新签名 APK | 当前 Windows 已包含这次解析修复 |
| 数据/其他运行 | 既有 schema `a0c9d2e4f817`；v60 发布恢复了五个上传 worker，保留 API 启动触发器；TV OTA v30 | 任务 Running 等于索引完整、队列完成、模型已加载或推理质量合格 |

这次交接写作不重新检查 Windows，也不执行任何发布、服务切换或模型调用。
私有诊断附录由本地操作者提供，放在 Git 外；源码开发可以先使用合成数据。

## 4. 已确认的问题

以下是10月15日上午只读诊断与源码追踪的结论；具体家庭请求和数量不进 Git。

1. 请求已到服务器。ASR 和 turn 的 HTTP 200/`succeeded` 表示处理完成；
   `clarification`、`unsupported` 和 0 条结果仍可能使用户体验失败。
2. 日常表达中的“一下”、查一下、我想找和英文礼貌前缀没有完整解析。
3. 有一次“找”被 ASR 识别成了“照”。不能默默改写原文或假定用户要执行
   拍摄/搜索；保留识别文本并提供更正/澄清路径。
4. 当前检查的媒体索引只启用 `date/locations/media`，没有 reviewed people
   或 face assignments。数据库有说明和人脸，不等于这条搜索链路已使用它们。
5. 日期搜索使用 `assets.taken_at`；检查范围的视频缺少该字段。
   文件名有大量日期线索，但导出/下载时间不一定是拍摄时间。
6. `DiscoveryReads.search` 有 literal caption filter，助手没有把一般内容
   查询接到它。媒体检索主要按 ID 倒序，不是统一的语义相关性排名。
7. saved-memory 搜索是另一个显式协商的 workspace 路径，目前按短语匹配
   story 标题/章节或 memoir 标题/引言，没有统一所有素材证据。

## 5. 已完成的修复：先保留，再扩展

`5e608ac` 修改共享服务端 `assistant.py`：

- 常用中英文查询前缀能进入原有受保护检索；日期与实体条件保持完整。
- 对疑似“照一下/找一下”请求更正，不自动执行查询或修改识别文本。
- 澄清时说明当前未启用的人物/照片说明/标签检索。
- 日期搜索空结果说明缺失拍摄日期会被排除，不自动放宽过滤。

接口、已有 context/结果 shape、schema 和 APK 均未变化。
新增测试 `test_assistant_conversational_search.py` 已加入 `tools/check.py api`。
五个测试方法及其子场景通过；共享 HTTP 检查组合 **63 项**通过，工具
check-driver **13 项**通过。修复前的九个正向/ASR 断言失败已被复现。
这些范围有重叠，不相加；完整 API/Android/Web 发布 profile 尚未重跑。

## 6. 关键源码入口

| 文件/对象 | 用途与注意事项 |
| --- | --- |
| `server/backend/app/access/assistant.py` | `_turn`、前缀、年月解析、facet 实体匹配、后续结果上下文 |
| `server/backend/app/access/assistant_workspace_transport.py` | 私有 turn 协调；普通素材检索回到共享 `_turn`，saved-memory 需要协商 |
| `server/backend/app/access/discovery.py` | `DiscoveryReads`；权限先于元数据读取，source digest/binding、资源预算和过滤 |
| `server/backend/app/access/discovery_provider.py`、`discovery_index.py` | reviewed 人物/别名/人工 assignment、索引来源与加载约束 |
| `server/backend/app/access/stories.py` | 现有 `Stories.search` 联合照片回忆、caption 和部分已接纳 annotation；先评估复用 |
| `server/backend/app/access/assistant_memory_discovery.py`、`assistant_memory_intent.py` | 已保存故事/回忆录的独立 literal 搜索 |
| `server/backend/app/access/date_hints.py` | 展示用 filename/received hints；不等于拍摄时间修复 |
| `server/backend/app/access/visual_candidates.py`、`visual_vector_loader.py` | 视觉候选与模型/向量身份边界；不代表当前助手已使用语义检索 |
| `server/backend/app/access/assistant_journal.py`、`assistant_workspace_store.py` | 私有回执/会话；不属于共享照片全文索引的数据源 |
| `tools/check.py`、`docs/feature-source-changes.json` | 显式检查清单和每次变更的源码哈希记录 |

`RefreshingPlaceIndex` 当前验证要求 enabled 恰为 date/locations/media。
不能直接塞入 caption/people 来绕过校验。设计新的受控来源/查询适配或独立
派生投影，保留同样的权限、来源变更和删除失效约束。

助手 facet 遍历当前上限500项，reviewed roster 允许更多。设计按授权名称
查候选，避免简单增加循环导致每个 turn 重复扫描全部元数据。

## 7. 推荐实施顺序

### A. 先定合同，并交付文本/人物的可运行切片

写清内部版本化 `SearchPlan`、来源适配器和结果解释合同；内部合同不能
直接冒充已发布 JSON。查询计划至少包括媒体类型、日期范围/基准、人物
候选及 any/all、地点、内容短语、否定与不确定性、当前上下文。

先用现有受保护 reader 和合成数据跑通 caption/人工照片回忆与已确认人物
的联合查找。针对是否引入派生全文库作出明确选择；派生内容按 library、
asset、source revision 和处理版本绑定，可重建，不复制原始媒体。
人物只使用有依据的身份/别名；“妈妈”等亲属称谓需要用户自己的映射。

建立来源更新、withdrawal、删除、换库/退出和旧索引失效检查，再接入线上
家庭数据。索引准备和真实数据库操作是后续独立运行门槛。

### B. 让视频日期可用且可信

准备有界只读元数据调查：嵌入时间、时区、现有字段、文件名线索。
设计 `capture/filename/received` 明示查询基准和 UI 说明。用户明确选择
文件名日期之前，不能悄悄把它当作拍摄时间。

新增 wire/context 字段要做版本协商与旧客户端测试；不要直接给严格解码的
v60 过滤结构加字段。回填真实数据库另做审查与操作授权。

### C. 加入可替换的本地语义理解与排名

保留常见表达的快速路径；复杂表达交给 Windows 本地、可替换的理解适配器
提出 typed query plan。服务端校验身份、条件、权限和支持能力。
模型不产生 SQL、权限、任意 ID、文件/URL 操作或管理指令。

在相同语料上比较 lexical、语义和视觉候选，去重并排序，保留人物/日期
等硬条件。验证中文短词、同义表达、语种混合、否定、多人“同时出现”和
多轮“只看九月的”。新模型与现有向量的 modality/dimension/model/preprocessing
必须相容；不要把已下载模型或 catalog 声明当成可运行证明。

### D. Web/手机呈现与可观测性

用共享后端，显示已理解条件、日期基准和每张结果为什么匹配。明确区分
无匹配、未索引、未知日期、人物歧义与服务不可用。后续选择绑定当前
结果顺序/版本；恢复的历史不能直接重新执行旧动作。

诊断区分 ASR 原文、用户更正、解析结果、已解析实体、数据覆盖、候选数和
排名耗时。扩展持久记录要保持私有30天保留政策并走 schema/版本门槛；
不要把私人聊天/诊断文本放入共享素材检索库。

## 8. 必须验证的行为

- 中英文口语改写能形成正确条件；保留原请求与更正来源。
- 人物、两人同时出现、明确否定和日期范围不会被静默放宽。
- 两字中文（海边、妈妈）、同义内容、caption/回忆冲突能给出可解释结果。
- 时间未知、文件名时间冲突、跨年/月和参考时区有确定行为。
- 不泄露其他库的身份、素材、片段、计数；撤权/删除/withdrawal 后旧命中失效。
- 无模型/超时仍有可说明的退化路径，不隐式请求第三方云。
- 结果去重、排序、分页及“打开第二个”的当前上下文一致。
- 中文默认、长文本与大字号的 Web/手机过滤解释可操作，语音 Pause/End 保留。

合成语料验证解析和安全合同；真实相关性需要私有人工标注结果集。分别报告
意图/过滤正确率、Recall/Precision@K、无结果原因和延迟，不把单个模型回复
或合成测试通过称为检索质量达标。目标阈值应先基于基线和用户相关性标注确定。

## 9. 检查与交付约定

在仓库根运行当前局部回归：

```sh
.venv/bin/python -m unittest discover -s server/tests/security -p 'test_assistant_conversational_search.py'
.venv/bin/python -m unittest discover -s tools/tests -p 'test_check.py'
.venv/bin/python tools/verify_current_source.py
git diff --check
```

按改动范围运行 HTTP/discovery/索引/生命周期测试；形成发布候选时按
`docs/DEVELOPMENT.md` 跑完整 API profile，界面或客户端合同变化时追加相应
Web/Android 检查和渲染。源码打包使用已提交不可变版本，检查固定 allowlist。

更新 source ledger、简明状态和本交接的完成/剩余项。保留一个写入所有者；
只有适用指令要求且任务有独立切片时才使用子代理。不要为了交接重建重复
worktree、下载模型或复制 Windows 数据到 Mac。

本用户请求授权的是交接写作；本地实现可由下方新会话启动指令接续。
旧 v60 发布已经完成，其一次性执行文件/授权不能重放给新版本。新的 Windows
写入、上线、重启、数据变更、APK 签名或发布需检查该操作的实际已有授权；
没有则先完成可审查准备。只读诊断不需要变成重复的服务控制审批。

## 10. 给新会话的启动指令

```text
请在 PhotoHouse monorepo 工作。先读 AGENTS.md 和
 docs/NEXT_SESSION_SEARCH_REDESIGN_2026-10-15.md，
再读 docs/ASSISTANT_SEARCH_REVIEW_2026-10-15.md。
核对当前分支、HEAD 和未提交修改；5e608ac 是已有搜索修复，不要覆盖或回退。
故事创作暂缓，优先完整的自然语言素材检索：人物、照片说明、已有回忆、
日期、地点和后续语义/视觉排名。先说明关键设计选择，然后实现第一批可运行
的受保护文本/人物检索及合成回归，按交接继续下一批。
本地分析、源码修改和相关检查可以继续；Windows 新操作和发布按 AGENTS
检查具体授权。保持纯本地处理、当前用户/相册权限和原始资料来源区分。
线上仍是 v60，5e608ac 尚未部署；源码、模型、运行和用户验收分别报告。
```
