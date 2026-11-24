# Bilingual product roadmap / 双语产品路线图

Open [the interactive roadmap](index.html) locally. The deployment route is
`/roadmap/`; `/roadmap` redirects there and keeps the selected language.
This source addition does not by itself establish Windows deployment.

可在本地打开[交互式路线图](index.html)。部署入口为 `/roadmap/`；
`/roadmap` 会跳转至该地址并保留语言选择。源码新增本身不代表 Windows 已完成部署。

- English: `index.html?lang=en` or `/roadmap/?lang=en`.
- 中文：`index.html?lang=zh` 或 `/roadmap/?lang=zh`。
- The EN/中文 switch covers feature content, gaps, priorities, evidence labels,
  controls and accessibility labels. Filters and expanded details survive a
  language change. Search matches both translations.
- EN／中文切换覆盖功能内容、差距、优先方向、证据标签、控件和无障碍标签。
  切换语言时保留筛选与展开详情；搜索同时匹配两种语言。

## Meaning of status / 状态含义

“Recorded delivery” is dated evidence, not a live health signal. “Source ready”
is not activated. “In progress” identifies a concrete missing outcome. “Planned”
identifies future product work. Runtime, installed clients and family acceptance
remain separate. The page makes no server or model requests.

“已交付记录”是有日期的证据，不是实时健康信号。“源码已就绪”不等于已启用。
“进行中”指出具体尚缺成果；“计划中”代表后续产品工作。
运行环境、已安装客户端和家庭验收分别记录。本页不发送服务器或模型请求。

## Maintenance / 维护

Edit `data.js` as the single public content source. Every user-facing record must
have both `en` and `zh`. Update the snapshot date, runtime notice and affected
feature evidence together; keep dates and unaccepted outcomes explicit.
Do not add household names, paths, endpoints, transcripts, media, tokens or
private operation receipts. Evidence labels describe records; the companion
notes are a public summary, not a raw export of operator files.

以 `data.js` 为唯一公共内容源。所有面向用户的记录必须同时具备 `en` 与 `zh`。
同步更新快照日期、运行说明及受影响功能的证据，明确日期与尚未验收的成果。
不得添加家庭姓名、路径、端点、转写、媒体、令牌或私有操作回执。
证据标签描述相关记录；配套说明是公开摘要，不是操作文件的原始导出。

Regenerate the bilingual Markdown companion from the repository root:

从仓库根目录重新生成双语 Markdown 配套说明：

```sh
python3 tools/export_product_roadmap.py
```

Keep the five served files together: `index.html`, `styles.css`, `app.js`,
`data.js`, `roadmap.md`. No build, external font, CDN or network dependency is
needed. The server adapter exposes only this fixed allowlist; it never serves
other documentation or discovers runtime state. GitHub Actions stays paused.

五个部署文件须放在一起：`index.html`、`styles.css`、`app.js`、`data.js`、
`roadmap.md`。无需构建、外部字体、CDN 或网络依赖。服务器适配器仅提供固定白名单文件，
不会提供其他文档或探测运行状态。GitHub Actions 继续保持暂停。

Focused browser check (existing Playwright installation): / 浏览器专项检查（使用现有 Playwright）：

```sh
node tools/test_product_roadmap_browser.cjs
```

Use `PH_BROWSER_EXECUTABLE` to select an existing browser; optional
`PH_ROADMAP_SCREENSHOTS` writes previews outside the repository.
使用 `PH_BROWSER_EXECUTABLE` 选择已有浏览器；可通过 `PH_ROADMAP_SCREENSHOTS`
将预览图写到仓库之外。
