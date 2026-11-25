# November 24 functional delivery / 11 月 24 日功能修复交付

[PR #115](https://github.com/phoenixjyb/PhotoHouse/pull/115) merged the reviewed
integration into `main` at `c7a28ef`. Rust PR #114 is included with its history.
Windows now serves four application-file changes from that merged tree through
the qualified source overlay; its original base runtime and existing native
kernels remain in place.

- Search v2 accepts one exact reviewed place as a follow-up, retaining other filters.
- Month corrections retain the active search's unique year; ambiguous years still clarify.
- Blank or unchanged AI suggestions preserve authored chapter text and explicit save.
- Reopening Jude can retry a transient capability failure without submitting a turn or recording audio.

The bilingual `/roadmap/` is also live and was separately confirmed by the owner.
These fixes change existing user journeys, not the selected model/provider or
the scope of the assistant's tools. No APK, signing or OTA was published.

## Observed Windows result

The first candidate passed its API checks but grouping timed out in a Task
Scheduler snapshot before its native worker started. Both prior task XML hashes
were restored exactly, rollback HTTPS checks passed, and the old grouping task
subsequently completed normally. The failure remains preserved.

The successor uses `CREATE_NO_WINDOW` for that pinned PowerShell call. The same
argv, 22-second call limit, 40-second pre-worker admission, 240-second child and
300-second task remain; no retry or shortened acceptance was introduced.
A bounded pre-cutover snapshot completed in **1.203 seconds**. This read checked
the SYSTEM task identity; its administrator caller was not relabelled SYSTEM.
This demonstrates the mitigation worked in this run, not the precise original OS cause.

The actual source/import/ASGI preflight and four synthetic Search assertions
passed. All **16 existing trusted HTTPS checks and nine roadmap checks** passed.
The natural SYSTEM grouping run closed its native Job and handles and returned
`REFRESH_DEFERRED`, **zero updates**, for one library. It was not forced and does
not establish a completed index sweep or household relevance/grouping quality.

The temporary deployment controller was removed; source and owned-transport
audits passed after **180.058 seconds** offline. The operation was explicitly
released, with no active admission or cleanup. Existing Family importing and
its schedule were untouched. No media/database copies, model requests or native
rebuilds were part of this rollout. GitHub Actions remains cost-paused.

## 中文摘要

主仓库已整合 Rust、双语路线图与相关功能修复。Windows 已上线四项修复：地点追问、
月份纠正保留原年份、保留作者已写章节，以及小贾临时故障后的明确重开恢复。
首次部署因分组启动前的计划任务读取超时而回滚；后续采用无控制台启动，保留原时限，
并通过实际 Windows 检查、自然定时运行和完整清理后才确认交付。

本次分组返回“延后处理”，更新数为零，不能称为全库扫描或家庭质量验收。
模型、原始资料、自动导入定时设置及现有 Rust 内核未更换；GitHub CI 继续关闭。
家庭相关性、真实语音体验和新版手机／电视安装仍须分别验收。
