# Android dictation status and error feedback · 2026-10-06

语音输入状态应能被屏幕阅读器感知，失败文案按当前界面语言显示。`MemoryDictationState.failure` 保留既有字符串兼容；新增 `failureCode` 作为稳定展示类别，UI 不解析错误字符串，也不展示原始异常或路径。

录音准备/进行中、转写中、转写完成、权限拒绝、其他阅读音频占用、语音不可用和处理失败都提供 polite live-region 语义。录音秒数单独展示，不放在 live region 中，避免计时器持续播报。

交互仍要求用户明确开始/停止录音、检查转写、插入消息草稿并发送。live announcement 只报告状态，不触发插入、重试或发送。音频所有权、scope fencing、取消与晚到响应清理保持由现有 store/recorder 流程管理。

## Evidence

- `:live-core:test --tests '*MemoryDictationTest'` exercises stable failure categories while checking the existing `failure` field remains populated with its historical value.
- `:connected:compileDebugKotlin` checks the Compose live-region implementation.
- `:connected:compileDebugAndroidTestKotlin` checks accessibility assertions for recording, transcription, completion, and localized errors.
- Root-run Android emulator suite `android/connected/build/outputs/androidTest-results/connected/debug/TEST-Medium_Phone_API_36.0(AVD) - 16-_connected-.xml` reports 7 tests, 0 failures: 5 dictation UI flows and 2 chapter-directory flows. It includes the synthetic-ASR emulator microphone flow. Root also reports the paired lint check passed.

The emulator run is not physical-phone or family acceptance and does not qualify a live speech provider or server behavior.
