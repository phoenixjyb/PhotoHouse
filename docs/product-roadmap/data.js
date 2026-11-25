/* Public product records only. No runtime polling or household data. */
window.PHOTOHOUSE_ROADMAP = {
  "schema_version": 1,
  "updated_at": "2026-11-26",
  "snapshot_label": {
    "en": "26 November 2026 · reviewed snapshot",
    "zh": "2026 年 11 月 26 日 · 回顾快照"
  },
  "runtime_notice": {
    "severity": "info",
    "title": {
      "en": "Reviewed integration record",
      "zh": "部署与集成回顾记录"
    },
    "body": {
      "en": "Windows delivery records cover the bilingual roadmap, fullscreen viewer and the 25 November Search fix. The 26 November local build improves Jude recovery, saved memory groups and story review. Those changes await Windows rollout and household review.",
      "zh": "双语路线图、全屏浏览和 11 月 25 日搜索修复已有 Windows 交付记录。11 月 26 日的本地版本改进了小贾的请求恢复、已保存回忆组和故事审阅，仍待 Windows 发布与家庭试用。"
    }
  },
  "areas": [
    {
      "id": "access",
      "title": {
        "en": "Privacy & libraries",
        "zh": "隐私与相册库"
      }
    },
    {
      "id": "intake",
      "title": {
        "en": "Import & processing",
        "zh": "导入与处理"
      }
    },
    {
      "id": "search",
      "title": {
        "en": "Search & discovery",
        "zh": "搜索与发现"
      }
    },
    {
      "id": "grouping",
      "title": {
        "en": "Photo & memory grouping",
        "zh": "照片与记忆分组"
      }
    },
    {
      "id": "stories",
      "title": {
        "en": "Stories & oral history",
        "zh": "故事与口述历史"
      }
    },
    {
      "id": "assistant",
      "title": {
        "en": "Jude & voice",
        "zh": "小贾与语音"
      }
    },
    {
      "id": "clients",
      "title": {
        "en": "Web, phone & TV",
        "zh": "网页、手机与电视"
      }
    },
    {
      "id": "performance",
      "title": {
        "en": "Rust & reliability",
        "zh": "Rust 与可靠性"
      }
    },
    {
      "id": "operations",
      "title": {
        "en": "Installation & recovery",
        "zh": "安装与恢复"
      }
    }
  ],
  "priorities": [
    {
      "id": "now",
      "title": {
        "en": "Make Search refinement conversational",
        "zh": "让搜索条件能够自然逐轮细化"
      },
      "why": {
        "en": "Understand dates, retain the active filters across follow-up questions, and show what is actually being searched.",
        "zh": "理解日期表达，保留追问中的现有筛选条件，并清楚展示实际查找范围。"
      },
      "done_when": {
        "en": "A family member can find photos, narrow by person/date/place, change a condition and open a result without starting over.",
        "zh": "家人能够查找照片，按人物／日期／地点逐步缩小范围，修改条件并打开结果，无需反复从头描述。"
      }
    },
    {
      "id": "next",
      "title": {
        "en": "Make Jude useful across conversations",
        "zh": "让小贾在多轮对话中真正好用"
      },
      "why": {
        "en": "Find photos, refine conditions and explain results without losing scope or pretending an action succeeded.",
        "zh": "查找照片、逐轮细化条件、解释结果，同时保留范围约束，不把失败说成成功。"
      },
      "done_when": {
        "en": "A household can continue a search, inspect the applied conditions, reopen a result and cancel uncertain work clearly.",
        "zh": "家人可以继续查找、查看已生效条件、重新打开结果，并清楚地取消状态不明的请求。"
      }
    },
    {
      "id": "later",
      "title": {
        "en": "Turn contributions into reviewable memories",
        "zh": "把家庭素材整理成可审阅的记忆"
      },
      "why": {
        "en": "Preserve original words while proposing grounded corrections, readable stories and meaningful memory groups.",
        "zh": "保留原始表达，同时提供有依据的纠错、可读的故事与有意义的记忆分组。"
      },
      "done_when": {
        "en": "Authors can compare sources and drafts, resolve uncertainty and explicitly adopt changes; optional cloud work remains opt-in.",
        "zh": "作者能对照原始素材与草稿、处理不确定信息并明确采纳修改；可选云端处理始终需要主动同意。"
      }
    }
  ],
  "features": [
    {
      "id": "privacy-library-access",
      "area": "access",
      "stage": "delivered",
      "priority": "next",
      "title": {
        "en": "Private libraries & membership",
        "zh": "私密相册库与成员权限"
      },
      "summary": {
        "en": "Library membership bounds browsing, assistant requests and contributions.",
        "zh": "相册库成员权限约束浏览、助手请求与家庭贡献。"
      },
      "implementation": [
        {
          "en": "Protected API/Web routes and owner review are implemented.",
          "zh": "已实现受保护的 API／网页入口和所有者审核。"
        },
        {
          "en": "An owner can revoke an unused registration link by entering the same phone number after returning to the library.",
          "zh": "所有者再次进入相册库后，可以输入同一手机号撤销尚未使用的注册链接。"
        }
      ],
      "gaps": [
        {
          "en": "Permission changes and revoked access still need routine household walkthroughs.",
          "zh": "权限变更与撤销访问仍需持续通过家庭使用流程确认。"
        }
      ],
      "next_step": {
        "en": "Show the active library and explain permission refusals consistently.",
        "zh": "统一展示当前相册库，并清晰解释权限拒绝。"
      },
      "delivery_note": {
        "en": "Protected access is in the October 29 delivery record.",
        "zh": "受保护访问已记录于 10 月 29 日交付。"
      },
      "acceptance_note": {
        "en": "A dated delivery is separate from current account and device acceptance.",
        "zh": "有日期的交付与当前账户、设备验收分别记录。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "FEATURES.md · RELEASE_2026-10-29.md",
            "zh": "FEATURES.md · RELEASE_2026-10-29.md"
          },
          "at": "2026-10-29",
          "state": "verified"
        },
        {
          "kind": "source",
          "label": {
            "en": "Audit reconciliation · generated viewer checks",
            "zh": "审计对照记录 · 合成查看器测试"
          },
          "at": "2026-11-25",
          "state": "verified"
        },
        {
          "kind": "source",
          "label": {
            "en": "AUDIT_RECONCILIATION_2026-11-24.md",
            "zh": "AUDIT_RECONCILIATION_2026-11-24.md"
          },
          "at": "2026-11-25",
          "state": "verified"
        }
      ]
    },
    {
      "id": "upload-and-review",
      "area": "intake",
      "stage": "delivered",
      "priority": "next",
      "title": {
        "en": "Upload, approval & receipts",
        "zh": "上传、审核与回执"
      },
      "summary": {
        "en": "Import photos and videos with visible ownership and processing states.",
        "zh": "导入照片和视频，明确展示归属与处理状态。"
      },
      "implementation": [
        {
          "en": "Protected uploads, owner review and recoverable request receipts exist.",
          "zh": "已实现受保护上传、所有者审核与可恢复请求回执。"
        },
        {
          "en": "Android reviews selected file sizes, remembers an approved folder and requests metered-data consent for each transfer run.",
          "zh": "Android 会核对已选文件大小、记住所选授权文件夹，并在每次使用计费网络传输前征得同意。"
        }
      ],
      "gaps": [
        {
          "en": "Upload receipt, approval, gallery visibility and playable media are separate milestones.",
          "zh": "上传回执、审核通过、相册可见和媒体可播放是不同环节。"
        }
      ],
      "next_step": {
        "en": "Make interrupted imports and pending review easy to understand and resume.",
        "zh": "让中断导入和待审核状态易于理解、易于继续。"
      },
      "delivery_note": {
        "en": "API/Web upload delivery is recorded; the automatic intake pilot adds a later two-file path.",
        "zh": "已有 API／网页上传交付记录；后续自动导入试点补充了双文件流程。"
      },
      "acceptance_note": {
        "en": "Do not infer every phone upload or historical backlog is complete.",
        "zh": "不能据此认定所有手机上传或历史积压均已完成。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "UPLOAD_PREPARATION.md · PHONE_IMPORT_STATUS.md",
            "zh": "UPLOAD_PREPARATION.md · PHONE_IMPORT_STATUS.md"
          },
          "at": "2026-10-29",
          "state": "verified"
        },
        {
          "kind": "source",
          "label": {
            "en": "ANDROID_UPLOAD_RECOVERY.md",
            "zh": "ANDROID_UPLOAD_RECOVERY.md"
          },
          "at": "2026-11-25",
          "state": "verified"
        }
      ]
    },
    {
      "id": "automatic-intake",
      "area": "intake",
      "stage": "delivered",
      "priority": "next",
      "title": {
        "en": "Automatic Family importing",
        "zh": "家庭自动导入"
      },
      "summary": {
        "en": "A watched Family drop imports eligible media without duplicate retries.",
        "zh": "家庭投递目录可自动导入符合条件的媒体，重试不应产生重复项。"
      },
      "implementation": [
        {
          "en": "Photo/video pilot, gallery readback and duplicate-free retry preceded recurrence.",
          "zh": "先完成照片／视频试点、相册回读与无重复重试，再启用定时导入。"
        }
      ],
      "gaps": [
        {
          "en": "Long-running failures and rejected files need a clear owner-facing recovery view.",
          "zh": "长期运行中的失败与被拒文件仍需要清晰的所有者恢复界面。"
        }
      ],
      "next_step": {
        "en": "Expose recent import outcomes and actionable refusal reasons without copying media.",
        "zh": "展示近期导入结果与可操作的拒绝原因，不重复复制媒体。"
      },
      "delivery_note": {
        "en": "Automatic importing was completed in the November Family intake rollout and confirmed by the owner.",
        "zh": "11 月家庭导入部署已完成，所有者确认自动导入可用。"
      },
      "acceptance_note": {
        "en": "One scheduled run returned HTTP 503. A later run succeeded with the same task definition.",
        "zh": "一次定时运行返回 HTTP 503，之后在定时任务定义未修改的情况下成功运行。"
      },
      "evidence": [
        {
          "kind": "family",
          "label": {
            "en": "Family intake delivery and owner confirmation",
            "zh": "家庭导入交付与所有者确认"
          },
          "at": "2026-11-22",
          "state": "verified"
        },
        {
          "kind": "windows",
          "label": {
            "en": "Successful scheduled run after an HTTP 503",
            "zh": "HTTP 503 后定时导入运行成功"
          },
          "at": "2026-11-25",
          "state": "verified"
        }
      ]
    },
    {
      "id": "caption-processing",
      "area": "intake",
      "stage": "in_progress",
      "priority": "next",
      "title": {
        "en": "Captions & processing backlog",
        "zh": "描述生成与处理积压"
      },
      "summary": {
        "en": "Local processing enriches approved media while preserving original failures.",
        "zh": "本地处理为已审核媒体补充描述，同时保留原始失败记录。"
      },
      "implementation": [
        {
          "en": "Caption workers and legacy batch recovery paths are implemented.",
          "zh": "已实现描述处理工作进程与旧批次恢复流程。"
        }
      ],
      "gaps": [
        {
          "en": "No blanket completion claim exists for all old batches or media.",
          "zh": "尚不能宣称所有旧批次或媒体均处理完成。"
        }
      ],
      "next_step": {
        "en": "Surface per-batch progress, resume unfinished items and verify usable output.",
        "zh": "展示分批进度，只继续未完成项，并确认输出可用。"
      },
      "delivery_note": {
        "en": "Earlier Windows batch fixes are separate from whole-library completion.",
        "zh": "此前 Windows 批次修复不等于全库完成。"
      },
      "acceptance_note": {
        "en": "Processing success, factual quality and media playback require separate evidence.",
        "zh": "处理成功、事实质量和媒体播放需分别确认。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "FEATURES.md · PROJECT_STATUS.md",
            "zh": "FEATURES.md · PROJECT_STATUS.md"
          },
          "at": "2026-11-24",
          "state": "partial"
        }
      ]
    },
    {
      "id": "protected-media-browsing",
      "area": "clients",
      "stage": "delivered",
      "priority": "next",
      "title": {
        "en": "Protected gallery & playback",
        "zh": "受保护相册与播放"
      },
      "summary": {
        "en": "Browse authorized photos and videos through Web and client surfaces.",
        "zh": "通过网页和客户端浏览有权访问的照片与视频。"
      },
      "implementation": [
        {
          "en": "Gallery, detail and protected playback routes are implemented.",
          "zh": "已实现相册、详情和受保护播放入口。"
        },
        {
          "en": "Local Web checks verified on-demand descriptions and faster prepared-video startup under fixed response delays.",
          "zh": "本地网页测试验证了按需加载照片描述，并在固定响应延迟下缩短了已准备视频的启动时间。"
        }
      ],
      "gaps": [
        {
          "en": "Installed phone/TV versions and real device playback need their own acceptance.",
          "zh": "已安装手机／电视版本及真实设备播放仍需单独验收。"
        }
      ],
      "next_step": {
        "en": "Keep navigation, loading and playback errors consistent across screens.",
        "zh": "统一不同屏幕上的导航、加载与播放错误体验。"
      },
      "delivery_note": {
        "en": "Fullscreen browsing is live on Windows. The newer loading improvements have local evidence and await release.",
        "zh": "Windows 已上线全屏浏览。较新的加载改进已完成本地验证，仍待交付。"
      },
      "acceptance_note": {
        "en": "No physical device result is inferred from an API check.",
        "zh": "API 检查不能替代物理设备结果。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "FEATURES.md · RELEASE_2026-10-29.md",
            "zh": "FEATURES.md · RELEASE_2026-10-29.md"
          },
          "at": "2026-10-29",
          "state": "verified"
        }
      ]
    },
    {
      "id": "literal-search",
      "area": "search",
      "stage": "delivered",
      "priority": "next",
      "title": {
        "en": "Structured photo Search",
        "zh": "结构化照片搜索"
      },
      "summary": {
        "en": "Find authorized media by supported people, dates, places, type and indexed text.",
        "zh": "按支持的人物、日期、地点、类型和已索引文字查找有权访问的媒体。"
      },
      "implementation": [
        {
          "en": "Search API, Web results and bounded filter translation are implemented.",
          "zh": "已实现搜索 API、网页结果和有边界的条件转换。"
        },
        {
          "en": "The local Web client can prepare an exact date range or clear the current media type or text condition. You review and send each change.",
          "zh": "本地网页可拟定具体日期范围，或清除当前媒体类型及文字条件。由用户检查并发送每次修改。"
        },
        {
          "en": "When reviewed metadata fits the row limit and supplementary captions or notes exceed it, structured filters still work. Search asks for clarification when the request needs the unavailable text.",
          "zh": "当已核对的元数据符合行数上限，而补充说明或照片留言超出上限时，结构化筛选仍可使用。如果查询需要当前不可用的文字，搜索会请用户澄清。"
        }
      ],
      "gaps": [
        {
          "en": "Natural date expressions and unsupported conditions need clearer clarification.",
          "zh": "自然日期表达与不支持的条件需要更清楚的澄清。"
        }
      ],
      "next_step": {
        "en": "Show applied conditions, ask one useful clarification and preserve earlier constraints.",
        "zh": "展示已生效条件，提出有用的澄清问题，并保留前文约束。"
      },
      "delivery_note": {
        "en": "The 25 November Windows release includes the structured Search row-limit fix.",
        "zh": "11 月 25 日的 Windows 发布已包含结构化搜索的行数上限修复。"
      },
      "acceptance_note": {
        "en": "The fix passed a generated 100,000-asset scenario and a live Windows date search with two follow-ups. Representative family relevance still needs review.",
        "zh": "修复通过了 10 万项合成素材场景，以及 Windows 上真实日期搜索和两轮追问的验证。代表性家庭查询的相关性仍需评价。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "FEATURES.md · SEARCH_FUNCTIONAL_ACCEPTANCE.md",
            "zh": "FEATURES.md · SEARCH_FUNCTIONAL_ACCEPTANCE.md"
          },
          "at": "2026-11-23",
          "state": "verified"
        },
        {
          "kind": "windows",
          "label": {
            "en": "Live date and media filters across follow-ups",
            "zh": "真实搜索验证跨轮次保留日期和媒体类型"
          },
          "at": "2026-11-25",
          "state": "verified"
        },
        {
          "kind": "local",
          "label": {
            "en": "Generated Web check · exact dates and filter removal",
            "zh": "合成网页测试 · 具体日期和清除筛选"
          },
          "at": "2026-11-26",
          "state": "verified"
        }
      ]
    },
    {
      "id": "semantic-search",
      "area": "search",
      "stage": "in_progress",
      "priority": "next",
      "title": {
        "en": "Semantic discovery",
        "zh": "语义发现"
      },
      "summary": {
        "en": "Use local embeddings to complement exact filters and indexed text.",
        "zh": "用本地向量能力补充精确条件和已索引文字搜索。"
      },
      "implementation": [
        {
          "en": "Semantic source, scoped indexes and qualified Rust vector components exist.",
          "zh": "已有语义搜索源码、范围明确的索引与已验证 Rust 向量组件。"
        },
        {
          "en": "The quality scorecard marks an empty page as inconclusive when some items within the active filters have no semantic index.",
          "zh": "当当前筛选范围内仍有未建立语义索引的项目时，质量评分卡会将空结果标记为尚不能确认。"
        }
      ],
      "gaps": [
        {
          "en": "Coverage, relevance and enabled runtime configuration must be recorded per library.",
          "zh": "索引覆盖、相关性和已启用运行配置需按相册库记录。"
        }
      ],
      "next_step": {
        "en": "Compare real authorized queries and expose coverage before broadening use.",
        "zh": "对比真实授权查询，在扩大使用前展示覆盖情况。"
      },
      "delivery_note": {
        "en": "Component deployment does not establish complete semantic product acceptance.",
        "zh": "组件部署不等于完整语义搜索产品验收。"
      },
      "acceptance_note": {
        "en": "Synthetic speed and quality fixtures do not establish household usefulness.",
        "zh": "合成性能与质量样例不能代表家庭使用价值。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "SEMANTIC_SEARCH_PILOT.md · SEARCH_FUNCTIONAL_ACCEPTANCE.md",
            "zh": "SEMANTIC_SEARCH_PILOT.md · SEARCH_FUNCTIONAL_ACCEPTANCE.md"
          },
          "at": "2026-11-24",
          "state": "partial"
        },
        {
          "kind": "source",
          "label": {
            "en": "SEARCH_QUALITY_SCORECARD.md",
            "zh": "SEARCH_QUALITY_SCORECARD.md"
          },
          "at": "2026-11-25",
          "state": "verified"
        }
      ]
    },
    {
      "id": "scoped-external-search",
      "area": "search",
      "stage": "in_progress",
      "priority": "later",
      "title": {
        "en": "Permission-aware external search",
        "zh": "具备权限约束的外部搜索"
      },
      "summary": {
        "en": "Give approved clients a limited read-only view of one library.",
        "zh": "让获授权的客户端在单个相册库内获得有限的只读结果。"
      },
      "implementation": [
        {
          "en": "An internal reader enforces library scope, expiry, revocation and bounded metadata.",
          "zh": "内部读取接口已约束相册库范围、到期、撤销与元数据数量。"
        }
      ],
      "gaps": [
        {
          "en": "External transport, scoped credential issuance and client integration remain open.",
          "zh": "外部传输、范围限定的凭证签发及客户端接入仍待完成。"
        }
      ],
      "next_step": {
        "en": "Define a revocable grant for one explicitly selected library.",
        "zh": "定义仅用于一个明确选定相册库的可撤销授权。"
      },
      "delivery_note": {
        "en": "The internal reader passed generated source checks.",
        "zh": "内部读取接口已通过合成数据源码检查。"
      },
      "acceptance_note": {
        "en": "Verify revocation and isolation before connecting any external client.",
        "zh": "接入外部客户端前，须验证授权撤销与相册库隔离。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "EXTERNAL_SEARCH_INTERFACE.md",
            "zh": "EXTERNAL_SEARCH_INTERFACE.md"
          },
          "at": "2026-11-25",
          "state": "verified"
        }
      ]
    },
    {
      "id": "assistant-search",
      "area": "assistant",
      "stage": "delivered",
      "priority": "next",
      "title": {
        "en": "Jude: find & explain",
        "zh": "小贾：查找与解释"
      },
      "summary": {
        "en": "A private assistant translates a request into a bounded, authorized action.",
        "zh": "私密助手将请求转换为范围明确、符合权限的操作。"
      },
      "implementation": [
        {
          "en": "Request receipts, Search dispatch and visible result cards are implemented.",
          "zh": "已实现请求回执、搜索执行与可见结果卡片。"
        }
      ],
      "gaps": [
        {
          "en": "Unsupported requests must be explained without silently dropping constraints.",
          "zh": "不支持的请求必须明确解释，不能悄悄丢弃条件。"
        }
      ],
      "next_step": {
        "en": "Make visible evidence and the next useful action central to each answer.",
        "zh": "让每次回答围绕可见依据与下一步有用操作。"
      },
      "delivery_note": {
        "en": "Windows speech-to-Search returned 20 authorized cards in the October 29 exercise.",
        "zh": "10 月 29 日 Windows 语音到搜索流程返回了 20 张授权结果卡片。"
      },
      "acceptance_note": {
        "en": "That task does not prove a general autonomous agent.",
        "zh": "该任务结果不代表已具备通用自主智能体能力。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "RELEASE_2026-10-29.md · assistant contracts",
            "zh": "RELEASE_2026-10-29.md · 助手契约"
          },
          "at": "2026-10-29",
          "state": "verified"
        }
      ]
    },
    {
      "id": "assistant-followups",
      "area": "assistant",
      "stage": "in_progress",
      "priority": "next",
      "title": {
        "en": "Conversational Search refinement",
        "zh": "多轮对话细化搜索"
      },
      "summary": {
        "en": "Refine a search across turns instead of repeatedly starting over.",
        "zh": "跨轮次细化搜索，而不是每次从头开始。"
      },
      "implementation": [
        {
          "en": "Generated English, Chinese and mixed-language turns retain reviewed people while changing the month or media. The Web assistant can prepare Any date or Any person for review and Send.",
          "zh": "合成的中英文及混合语言流程可更改月份或媒体类型，同时保留已核对的人物条件。网页助手可填入「不限日期」或「不限人物」，供用户确认后发送。"
        },
        {
          "en": "Why this match? prepares a question about a visible result. The reply cites the available evidence and keeps the current filters and results.",
          "zh": "「为什么匹配？」可为当前可见结果准备提问。回复会说明已有的匹配依据，并保留现有筛选条件和结果。"
        }
      ],
      "gaps": [
        {
          "en": "Real household phrasing, ambiguous requests and exclusions still need native end-to-end evaluation.",
          "zh": "真实家庭用语、存在歧义的请求以及排除条件仍需本机端到端评估。"
        }
      ],
      "next_step": {
        "en": "Qualify the find, clarify, narrow and open journey on approved household devices with visible filters.",
        "zh": "在获准的家庭设备上验证查找、澄清、缩小范围和打开结果的完整流程，保持筛选条件可见。"
      },
      "delivery_note": {
        "en": "A live Windows search kept the date when media type changed and kept the media type when the month changed. Broader relevance and device acceptance remain open.",
        "zh": "Windows 真实搜索在更改媒体类型时保留了日期条件，在更改月份时保留了媒体类型。更全面的相关性与设备验收仍待完成。"
      },
      "acceptance_note": {
        "en": "Test with real user phrasing without hardcoding a demonstration.",
        "zh": "使用真实用户表达进行验证，不硬编码演示答案。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "Audit reconciliation · generated Search journeys",
            "zh": "审计对照记录 · 合成搜索流程"
          },
          "at": "2026-11-25",
          "state": "partial"
        },
        {
          "kind": "windows",
          "label": {
            "en": "Live Windows date search with two follow-ups",
            "zh": "Windows 真实日期搜索与两轮追问"
          },
          "at": "2026-11-25",
          "state": "verified"
        },
        {
          "kind": "local",
          "label": {
            "en": "Generated Web check · explain a result and continue to a story",
            "zh": "合成网页测试 · 解释匹配结果并继续创建故事"
          },
          "at": "2026-11-26",
          "state": "verified"
        }
      ]
    },
    {
      "id": "search-result-handoff",
      "area": "search",
      "stage": "in_progress",
      "priority": "next",
      "title": {
        "en": "Result selection & resumption",
        "zh": "结果选择与恢复"
      },
      "summary": {
        "en": "Carry selected, authorized results into a detail or story task.",
        "zh": "把已选且有权访问的结果带入详情或故事任务。"
      },
      "implementation": [
        {
          "en": "Choose story frames across result pages. After a reload in the same tab, reopening the conversation can recover the selection after checking the exact current result and selected pages.",
          "zh": "可跨结果页选择故事画面。同一标签页重新加载后，再打开对话并核实原结果与相关页，即可恢复选择。"
        }
      ],
      "gaps": [
        {
          "en": "Windows delivery and use on household devices remain open for this resumption path.",
          "zh": "恢复选择功能仍待 Windows 发布与家庭设备验证。"
        }
      ],
      "next_step": {
        "en": "Try selecting, reloading, reopening the conversation and starting an unsaved story on the installed Web client.",
        "zh": "在已安装网页客户端上试用选择画面、重新加载、打开原对话与创建未保存故事的完整流程。"
      },
      "delivery_note": {
        "en": "The same-tab Web journey passed with generated results and a fresh authorization check.",
        "zh": "使用合成数据通过了同一标签页的网页流程，并重新校验了访问权限。"
      },
      "acceptance_note": {
        "en": "The saved selection needs the same account, library, result and current source revisions.",
        "zh": "恢复选择须与账户、相册库、搜索结果及当前来源版本一致。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "ROADMAP.md · FEATURES.md",
            "zh": "ROADMAP.md · FEATURES.md"
          },
          "at": "2026-11-24",
          "state": "partial"
        },
        {
          "kind": "local",
          "label": {
            "en": "Generated Web check · select across pages and recover",
            "zh": "合成网页测试 · 跨页选择与恢复"
          },
          "at": "2026-11-26",
          "state": "verified"
        }
      ]
    },
    {
      "id": "page-local-photo-stacks",
      "area": "grouping",
      "stage": "delivered",
      "priority": "next",
      "title": {
        "en": "Similar-photo stacks",
        "zh": "相似照片堆叠"
      },
      "summary": {
        "en": "Reduce gallery clutter with visual groups while keeping originals intact.",
        "zh": "用视觉分组减少相册杂乱，同时保留原始媒体。"
      },
      "implementation": [
        {
          "en": "Page-local stacks and focused detail layout are implemented.",
          "zh": "已实现当前页堆叠与聚焦详情布局。"
        }
      ],
      "gaps": [
        {
          "en": "Similarity quality and phone/TV interaction need household acceptance.",
          "zh": "相似性质量及手机／电视交互仍需家庭验收。"
        }
      ],
      "next_step": {
        "en": "Explain why items were grouped and make opening the original straightforward.",
        "zh": "解释分组原因，让打开原始项目更直接。"
      },
      "delivery_note": {
        "en": "Focused phone details had recorded EN/中文 visual acceptance.",
        "zh": "聚焦手机详情已有英／中文视觉验收记录。"
      },
      "acceptance_note": {
        "en": "Page-local grouping is distinct from full-library or activity grouping.",
        "zh": "当前页分组与全库分组、活动分组是不同能力。"
      },
      "evidence": [
        {
          "kind": "local",
          "label": {
            "en": "LIBRARY_PHOTO_STACKS.md · FEATURES.md",
            "zh": "LIBRARY_PHOTO_STACKS.md · FEATURES.md"
          },
          "at": "2026-10-26",
          "state": "verified"
        }
      ]
    },
    {
      "id": "library-wide-photo-stacks",
      "area": "grouping",
      "stage": "in_progress",
      "priority": "now",
      "title": {
        "en": "Library-wide grouping refresh",
        "zh": "全库分组刷新"
      },
      "summary": {
        "en": "Refresh persistent visual grouping through the existing scheduled worker.",
        "zh": "通过现有定时工作进程刷新持久化视觉分组。"
      },
      "implementation": [
        {
          "en": "Windows grouping worker and recurring refresh have prior accepted runs.",
          "zh": "Windows 分组工作进程与定时刷新已有验收通过的运行记录。"
        },
        {
          "en": "The 24 November API/task binding passed a scheduled SYSTEM run with the native job drained and closed.",
          "zh": "11 月 24 日的 API／任务绑定通过了 SYSTEM 定时运行验证，原生作业已排空并关闭。"
        }
      ],
      "gaps": [
        {
          "en": "Household grouping quality and predictable refresh outcomes after library changes remain open.",
          "zh": "真实家庭分组质量，以及相册变更后的可预期刷新效果，仍待完善。"
        }
      ],
      "next_step": {
        "en": "Review actual groups and address concrete deferred or incomplete refresh cases within the existing resource budgets.",
        "zh": "检查实际分组，并在现有资源预算内解决具体的暂缓或未完成刷新情形。"
      },
      "delivery_note": {
        "en": "Existing groups were visible after the 25 November Search rollout. The scheduled worker returned REFRESH_DEFERRED with zero updates. A completed sweep on that build remains open.",
        "zh": "11 月 25 日搜索发布后，已有分组仍可查看。定时任务返回 REFRESH_DEFERRED，未更新分组。此版本的完整扫描仍待完成。"
      },
      "acceptance_note": {
        "en": "Task binding, completed cache refresh and household grouping quality are separate outcomes.",
        "zh": "任务版本绑定、缓存刷新完成与家庭分组质量是不同成果。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "LIBRARY_PHOTO_STACKS.md · Windows deployment reconciliation",
            "zh": "LIBRARY_PHOTO_STACKS.md · Windows 部署衔接记录"
          },
          "at": "2026-11-24",
          "state": "partial"
        },
        {
          "kind": "windows",
          "label": {
            "en": "Groups visible after Search rollout, sweep deferred",
            "zh": "搜索发布后分组仍可查看，完整扫描暂缓"
          },
          "at": "2026-11-25",
          "state": "partial"
        }
      ]
    },
    {
      "id": "activity-memory-grouping",
      "area": "grouping",
      "stage": "in_progress",
      "priority": "next",
      "title": {
        "en": "Activities & memory groups",
        "zh": "活动与记忆分组"
      },
      "summary": {
        "en": "Organize related moments into meaningful activities, not only look-alike images.",
        "zh": "将相关时刻整理成有意义的活动，而不仅是外观相似的图片。"
      },
      "implementation": [
        {
          "en": "The Web editor can add same-day media or split a group. Stories can load older saved groups, keep choices across pages, and start an unsaved story or review a combined group.",
          "zh": "网页编辑器可添加同日媒体或拆分回忆组。「故事」可查看较早保存的组，跨页保留选择，再开启未保存故事或审核合并组。"
        }
      ],
      "gaps": [
        {
          "en": "Automatic event discovery across devices and household review remain open.",
          "zh": "跨设备自动识别活动和家庭使用验收仍待完成。"
        }
      ],
      "next_step": {
        "en": "Try the editable groups with a small reviewed set of family events.",
        "zh": "用一小组可审阅的家庭活动试用可编辑的回忆组。"
      },
      "delivery_note": {
        "en": "Generated checks covered older pages, group order, revoked media and duplicate-free combine retries. The optional editor remains a separate Windows release.",
        "zh": "合成测试覆盖了旧组分页、分组顺序、已撤回媒体及合并重试去重。可选编辑器仍待单独发布到 Windows。"
      },
      "acceptance_note": {
        "en": "Family usefulness must be evaluated directly.",
        "zh": "家庭实用性必须直接评价。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "ROADMAP.md · FEATURES.md",
            "zh": "ROADMAP.md · FEATURES.md"
          },
          "at": "2026-11-24",
          "state": "partial"
        },
        {
          "kind": "source",
          "label": {
            "en": "AUDIT_RECONCILIATION_2026-11-24.md",
            "zh": "AUDIT_RECONCILIATION_2026-11-24.md"
          },
          "at": "2026-11-25",
          "state": "verified"
        },
        {
          "kind": "local",
          "label": {
            "en": "Generated API and Web checks · older private groups",
            "zh": "合成 API 与网页测试 · 较早的私密回忆组"
          },
          "at": "2026-11-26",
          "state": "verified"
        }
      ]
    },
    {
      "id": "story-editor-and-sources",
      "area": "stories",
      "stage": "delivered",
      "priority": "next",
      "title": {
        "en": "Stories & source attribution",
        "zh": "故事与来源标注"
      },
      "summary": {
        "en": "Keep original contributions separate from drafts and adopted stories.",
        "zh": "将原始贡献、草稿与已采纳故事明确区分。"
      },
      "implementation": [
        {
          "en": "Story editing and source links are available. Selected-source drafts show the original wording and let the author keep it for one chapter while reviewing the rest.",
          "zh": "已有故事编辑和来源关联。使用所选资料生成的草稿可与原文对照，可保留某一章原文并继续审核其余章节。"
        },
        {
          "en": "Find saved stories by title across the current library, with the same theme filters and pagination.",
          "zh": "可在当前相册库按标题查找已保存的故事，并结合现有主题筛选和分页。"
        }
      ],
      "gaps": [
        {
          "en": "Chapter review and title search need Windows rollout and family acceptance.",
          "zh": "逐章审阅和标题查找仍待 Windows 发布与家庭试用。"
        }
      ],
      "next_step": {
        "en": "Try keeping one original chapter, editing a second one and reopening the saved result.",
        "zh": "试用保留一章原文、编辑另一章，并再次打开已保存故事的流程。"
      },
      "delivery_note": {
        "en": "The underlying story editor has recorded delivery. The new chapter controls passed generated-data browser checks.",
        "zh": "基础故事编辑器已有交付记录。新的逐章操作通过了使用合成数据的浏览器测试。"
      },
      "acceptance_note": {
        "en": "AI edits remain proposals; originals and ownership are preserved.",
        "zh": "AI 修改始终是建议；原文与归属保持保留。"
      },
      "evidence": [
        {
          "kind": "family",
          "label": {
            "en": "FEATURES.md · FEATURES.md",
            "zh": "FEATURES.md · FEATURES.md"
          },
          "at": "2026-11-23",
          "state": "partial"
        },
        {
          "kind": "local",
          "label": {
            "en": "Generated API and Web checks · chapter review and saved title search",
            "zh": "合成 API 与网页测试 · 逐章审阅和已保存故事标题查找"
          },
          "at": "2026-11-26",
          "state": "verified"
        }
      ]
    },
    {
      "id": "saved-story-refinement",
      "area": "stories",
      "stage": "in_progress",
      "priority": "next",
      "title": {
        "en": "Automatic story refinement",
        "zh": "自动故事润色"
      },
      "summary": {
        "en": "Correct transcript errors and repetition, then propose readable prose.",
        "zh": "纠正转写错误与重复表达，再提出流畅可读的叙述。"
      },
      "implementation": [
        {
          "en": "Saved Stories can open a prepared AI draft directly and highlight wording changes next to the original. The author can choose which chapters enter the editor and explicitly save the review result.",
          "zh": "可从「已保存的故事」直接打开待核对的 AI 草稿，与原文对照查看标出的文字变化。作者可选择带入编辑的章节，并在核实后明确保存。"
        }
      ],
      "gaps": [
        {
          "en": "The reviewed draft missed name corrections and retained awkward repetition.",
          "zh": "已审阅草稿仍漏改姓名，并保留不自然重复。"
        }
      ],
      "next_step": {
        "en": "Combine local name grounding with factual, reviewable refinement and uncertainty.",
        "zh": "结合本地姓名依据，进行保留事实、可审阅且表达不确定性的润色。"
      },
      "delivery_note": {
        "en": "The new review controls passed generated browser checks. Local model quality and the new Windows build still need direct acceptance.",
        "zh": "新的审阅操作通过了合成浏览器测试。本地模型质量以及新的 Windows 版本仍待直接验收。"
      },
      "acceptance_note": {
        "en": "Do not invent facts or silently replace the original story.",
        "zh": "不编造事实，不悄悄替换原始故事。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "ROADMAP.md · local story role contracts",
            "zh": "ROADMAP.md · 本地故事角色契约"
          },
          "at": "2026-11-24",
          "state": "partial"
        },
        {
          "kind": "local",
          "label": {
            "en": "Generated API and Web checks · open and choose draft chapters",
            "zh": "合成 API 与网页测试 · 打开草稿并选择章节"
          },
          "at": "2026-11-26",
          "state": "verified"
        }
      ]
    },
    {
      "id": "name-grounded-story-roles",
      "area": "stories",
      "stage": "source_ready",
      "priority": "next",
      "title": {
        "en": "Local name grounding",
        "zh": "本地姓名依据"
      },
      "summary": {
        "en": "Use approved household context and role-specific local inference to resolve names.",
        "zh": "用获准家庭上下文与分角色本地推理辅助辨认姓名。"
      },
      "implementation": [
        {
          "en": "Grounding and separated story-role source work are prepared.",
          "zh": "姓名依据与独立故事角色源码已准备。"
        }
      ],
      "gaps": [
        {
          "en": "Exact runtime qualification and editorial acceptance remain open.",
          "zh": "精确运行环境验证与编辑质量验收仍未完成。"
        }
      ],
      "next_step": {
        "en": "Propose evidence-backed corrections; ask only when ambiguity cannot be resolved safely.",
        "zh": "提出有依据的纠错；仅在无法安全消除歧义时询问。"
      },
      "delivery_note": {
        "en": "Source-ready work is not an activated new story model or provider.",
        "zh": "源码就绪不等于新的故事模型或服务已启用。"
      },
      "acceptance_note": {
        "en": "Search and Jude must retain their qualified runtime behavior.",
        "zh": "搜索与小贾必须保持已验证运行行为。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "ROADMAP.md · story role implementation",
            "zh": "ROADMAP.md · 故事角色实现"
          },
          "at": "2026-11-24",
          "state": "partial"
        }
      ]
    },
    {
      "id": "cloud-proofreading",
      "area": "stories",
      "stage": "source_ready",
      "priority": "later",
      "title": {
        "en": "Optional cloud proofreading",
        "zh": "可选云端校对"
      },
      "summary": {
        "en": "Allow an author to preview exactly what would leave the local machine.",
        "zh": "让作者预览哪些内容将离开本地机器。"
      },
      "implementation": [
        {
          "en": "Opt-in preview and proofreading source boundaries are prepared.",
          "zh": "已准备主动选择、发送预览与校对源码边界。"
        }
      ],
      "gaps": [
        {
          "en": "Provider setup, privacy terms and exact-request qualification remain open.",
          "zh": "服务配置、隐私条款与精确请求验证仍未完成。"
        }
      ],
      "next_step": {
        "en": "Keep it off by default and require explicit consent for each send.",
        "zh": "默认关闭，每次发送都要求明确同意。"
      },
      "delivery_note": {
        "en": "No background cloud send or enabled cloud provider is claimed.",
        "zh": "不宣称已启用后台云端发送或云服务。"
      },
      "acceptance_note": {
        "en": "Only selected text may be sent; original media and private context stay local.",
        "zh": "只能发送选定文字；原始媒体与私密上下文保留本地。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "ROADMAP.md · cloud proofreading contracts",
            "zh": "ROADMAP.md · 云端校对契约"
          },
          "at": "2026-11-24",
          "state": "partial"
        }
      ]
    },
    {
      "id": "oral-history-intake-foundation",
      "area": "stories",
      "stage": "in_progress",
      "priority": "later",
      "title": {
        "en": "Oral history & memory hub",
        "zh": "口述历史与家庭记忆中心"
      },
      "summary": {
        "en": "Collect longer family accounts and connect them to people and moments.",
        "zh": "收集较长家庭叙述，并关联人物与时刻。"
      },
      "implementation": [
        {
          "en": "Authors can resume private recordings, play completed sections, and request local transcription with processing consent. They can edit and explicitly save reviewed wording while preserving the original audio.",
          "zh": "作者可以继续私密录音、回听已完成的段落，并在取得处理同意后发起本机转写。作者可以编辑并主动保存审阅文字，原始录音保持完整。"
        }
      ],
      "gaps": [
        {
          "en": "Physical capture, native transcription, source-linked story adoption and production storage qualification remain open.",
          "zh": "真机录音、本机转写效果、保留出处的故事采纳及生产存储验证仍待完成。"
        }
      ],
      "next_step": {
        "en": "Ship one resumable recording-to-reviewed-story journey before expanding automation.",
        "zh": "先交付一个可恢复的录音到已审阅故事流程，再扩展自动化。"
      },
      "delivery_note": {
        "en": "Generated checks covered exact retries, audio playback, transcript preview and reopening reviewed text. The recording and review features remain off in the deployed configuration.",
        "zh": "合成测试覆盖了无重复重试、回听、转写预览和重新打开审阅文字。已部署配置未启用录音与审阅功能。"
      },
      "acceptance_note": {
        "en": "Recording consent, attribution and author adoption remain explicit.",
        "zh": "录音同意、来源归属与作者采纳必须明确。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "ORAL_HISTORY_INTAKE_FOUNDATION.md",
            "zh": "ORAL_HISTORY_INTAKE_FOUNDATION.md"
          },
          "at": "2026-11-25",
          "state": "partial"
        }
      ]
    },
    {
      "id": "assistant-history-and-recovery",
      "area": "assistant",
      "stage": "in_progress",
      "priority": "next",
      "title": {
        "en": "Conversation context & recovery",
        "zh": "对话上下文与恢复"
      },
      "summary": {
        "en": "Continue useful work across turns, interruptions and reopened conversations.",
        "zh": "在多轮对话、中断与重新打开后继续有用任务。"
      },
      "implementation": [
        {
          "en": "Jude can open the latest conversation in one step, show an admitted pending request and check its result. An explicit discard prevents that reply from entering the conversation.",
          "zh": "小贾可一步打开上次对话，查看服务器已接收的待处理请求，并核实结果。明确丢弃可阻止该回复写入对话。"
        },
        {
          "en": "Manage conversations can page past the first 50 while keeping your current conversation open.",
          "zh": "「管理对话」可翻页查看超过前 50 条的较早对话，当前对话继续打开。"
        }
      ],
      "gaps": [
        {
          "en": "The new recovery interaction needs Windows and household acceptance, including a real interrupted session.",
          "zh": "新的恢复交互仍待 Windows 与家庭验收，包括实际中断后的继续使用。"
        }
      ],
      "next_step": {
        "en": "Try reopening an interrupted conversation, then recover its reply or discard it while keeping earlier messages.",
        "zh": "试用重新打开中断对话，恢复或丢弃待处理回复，并保留之前的消息。"
      },
      "delivery_note": {
        "en": "Generated API and browser checks covered a late completion and a reply that finished before discard.",
        "zh": "合成 API 与浏览器测试覆盖了迟到的回复，以及在丢弃操作之前已完成的回复。"
      },
      "acceptance_note": {
        "en": "The app checks the account, library, conversation and exact request before showing or discarding a pending reply.",
        "zh": "显示或丢弃待处理回复前，应用核实账户、相册库、对话和具体请求。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "ROADMAP.md · assistant lifecycle contracts",
            "zh": "ROADMAP.md · 助手生命周期契约"
          },
          "at": "2026-11-24",
          "state": "partial"
        },
        {
          "kind": "local",
          "label": {
            "en": "Generated API and Web checks · reopen, recover and discard",
            "zh": "合成 API 与网页测试 · 重开、恢复与丢弃请求"
          },
          "at": "2026-11-26",
          "state": "verified"
        }
      ]
    },
    {
      "id": "foreground-voice",
      "area": "assistant",
      "stage": "delivered",
      "priority": "next",
      "title": {
        "en": "Voice → Search → spoken reply",
        "zh": "语音 → 搜索 → 语音回复"
      },
      "summary": {
        "en": "Use an explicit foreground voice session with visible Pause and End controls.",
        "zh": "通过明确开启的前台语音会话交互，始终可见暂停与结束控制。"
      },
      "implementation": [
        {
          "en": "Windows HTTPS recognition, matching receipt, Search and reply audio passed together.",
          "zh": "Windows HTTPS 识别、匹配回执、搜索与回复音频已联合通过。"
        },
        {
          "en": "The local Web client lets each account choose normal or slightly slower spoken replies in Jude’s preferences.",
          "zh": "本地网页中，每个账户可在小贾的偏好设置选择正常或稍慢的语音回复速度。"
        }
      ],
      "gaps": [
        {
          "en": "Naturalness and physical browser microphone/speaker acceptance are still open.",
          "zh": "声音自然度及浏览器真实麦克风／扬声器验收仍待完成。"
        }
      ],
      "next_step": {
        "en": "Improve natural turn taking and voice choice without hidden recording or cloud fallback.",
        "zh": "改善自然轮次切换与声音选择，不隐藏录音，也不暗中切换云端。"
      },
      "delivery_note": {
        "en": "The October 29 Windows exercise completed in 28.688 seconds with 20 result cards.",
        "zh": "10 月 29 日 Windows 流程在 28.688 秒内完成，并返回 20 张结果卡片。"
      },
      "acceptance_note": {
        "en": "The owner deferred physical browser testing; do not count it as passed.",
        "zh": "所有者延后了浏览器物理测试，不能计为通过。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "RELEASE_2026-10-29.md · voice delivery",
            "zh": "RELEASE_2026-10-29.md · 语音交付"
          },
          "at": "2026-10-29",
          "state": "verified"
        }
      ]
    },
    {
      "id": "native-phone-and-tv-clients",
      "area": "clients",
      "stage": "in_progress",
      "priority": "later",
      "title": {
        "en": "Phone & TV clients",
        "zh": "手机与电视客户端"
      },
      "summary": {
        "en": "Bring protected browsing, playback and Search to household devices.",
        "zh": "让家庭设备使用受保护浏览、播放与搜索。"
      },
      "implementation": [
        {
          "en": "Android phone/TV source and local build evidence exist.",
          "zh": "已有 Android 手机／电视源码与本地构建证据。"
        },
        {
          "en": "The Android emulator verified confirmation before resuming on metered or unknown networks and reuse of the saved offset after a pause.",
          "zh": "Android 模拟器已验证计费或未知网络恢复上传前的确认，以及暂停后沿用已保存的传输进度。"
        }
      ],
      "gaps": [
        {
          "en": "Automatic mobile backup, iOS and private TV pairing are open. Installed artifacts, signing continuity and physical playback need current evidence.",
          "zh": "手机自动备份、iOS 原生端与私密电视配对仍待开发。已安装版本、签名连续性与真机播放仍需验证。"
        }
      ],
      "next_step": {
        "en": "Finish one installed-client journey before claiming cross-device parity.",
        "zh": "先完成一个已安装客户端流程，再宣称跨设备能力一致。"
      },
      "delivery_note": {
        "en": "A source build or old CI pass does not establish the installed version.",
        "zh": "源码构建或旧 CI 通过不能证明当前安装版本。"
      },
      "acceptance_note": {
        "en": "Phone, TV and Web acceptance stay separate.",
        "zh": "手机、电视与网页验收分别记录。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "FEATURES.md · FEATURES.md",
            "zh": "FEATURES.md · FEATURES.md"
          },
          "at": "2026-11-24",
          "state": "partial"
        },
        {
          "kind": "source",
          "label": {
            "en": "ANDROID_UPLOAD_RECOVERY.md",
            "zh": "ANDROID_UPLOAD_RECOVERY.md"
          },
          "at": "2026-11-25",
          "state": "verified"
        }
      ]
    },
    {
      "id": "web-assistant-redesign",
      "area": "clients",
      "stage": "delivered",
      "priority": "now",
      "title": {
        "en": "Modern bilingual Web UI",
        "zh": "现代双语网页界面"
      },
      "summary": {
        "en": "A consistent assistant, story workspace and responsive navigation.",
        "zh": "统一的助手、故事工作区与响应式导航。"
      },
      "implementation": [
        {
          "en": "The new UI passed responsive/large-text checks, actual Windows SYSTEM startup, trusted HTTPS checks and the repaired grouping binding.",
          "zh": "新版界面已通过响应式／大字检查、实际 Windows SYSTEM 启动、可信 HTTPS 检查及修复后的分组版本绑定。"
        }
      ],
      "gaps": [
        {
          "en": "Family feedback on the installed interface and real voice interactions is still pending.",
          "zh": "已部署界面的家庭反馈与真实语音交互体验仍待确认。"
        }
      ],
      "next_step": {
        "en": "Collect concrete phone/desktop feedback and improve the affected user journeys.",
        "zh": "收集手机／桌面端的具体反馈，改进对应使用流程。"
      },
      "delivery_note": {
        "en": "The reviewed UI component is served on Windows; the failed attempt and later recovery remain separate records.",
        "zh": "已审查的界面组件已由 Windows 提供；失败尝试与后续恢复分别保留记录。"
      },
      "acceptance_note": {
        "en": "Local rendering, HTTPS and family/device taste remain distinct.",
        "zh": "本地渲染、HTTPS 与家庭／设备审美体验分别记录。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "ROADMAP.md · Windows UI recovery and current grouping binding",
            "zh": "ROADMAP.md · Windows 界面恢复与当前分组版本绑定"
          },
          "at": "2026-11-24",
          "state": "verified"
        }
      ]
    },
    {
      "id": "rust-production-kernels",
      "area": "performance",
      "stage": "delivered",
      "priority": "later",
      "title": {
        "en": "Targeted Rust kernels",
        "zh": "针对性 Rust 内核"
      },
      "summary": {
        "en": "Move measured hot loops to Rust while preserving the Python application contracts.",
        "zh": "将有测量依据的热点循环迁移到 Rust，保持 Python 应用契约。"
      },
      "implementation": [
        {
          "en": "Qualified vector/visual and photo-stack components have Windows delivery records.",
          "zh": "已验证的向量／视觉与照片分组组件已有 Windows 交付记录。"
        }
      ],
      "gaps": [
        {
          "en": "Component speedup is not whole-request or whole-library speedup.",
          "zh": "组件提速不等于完整请求或全库提速。"
        }
      ],
      "next_step": {
        "en": "Profile the next real bottleneck; avoid rebuilding components that already passed.",
        "zh": "分析下一个真实瓶颈，避免重建已通过的组件。"
      },
      "delivery_note": {
        "en": "November 21 rollout accepted Rust components; the application remains Python with Rust kernels.",
        "zh": "11 月 21 日部署验收了 Rust 组件；应用仍是 Python 加 Rust 内核。"
      },
      "acceptance_note": {
        "en": "Search relevance, grouping quality and operational reliability are independent outcomes.",
        "zh": "搜索相关性、分组质量与运行可靠性是独立结果。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "Rust rollout delivery · component qualification",
            "zh": "Rust 部署交付 · 组件验证"
          },
          "at": "2026-11-21",
          "state": "verified"
        }
      ]
    },
    {
      "id": "semantic-rust-reuse",
      "area": "performance",
      "stage": "source_ready",
      "priority": "later",
      "title": {
        "en": "Semantic query reuse optimization",
        "zh": "语义查询复用优化"
      },
      "summary": {
        "en": "Reuse prepared native work when parity and measured benefit justify it.",
        "zh": "在行为一致且测量有收益时复用已准备的原生工作。"
      },
      "implementation": [
        {
          "en": "A Windows component qualification measured approximately 1.19× speedup.",
          "zh": "Windows 组件验证测得约 1.19 倍提速。"
        }
      ],
      "gaps": [
        {
          "en": "The new reuse path has not been activated in the live API.",
          "zh": "新的复用路径尚未在在线 API 启用。"
        }
      ],
      "next_step": {
        "en": "Integrate once the live delivery handoff is stable; measure full-request benefit.",
        "zh": "待在线部署衔接稳定后集成，并测量完整请求收益。"
      },
      "delivery_note": {
        "en": "Qualified component, not an enabled production optimization.",
        "zh": "这是已验证组件，不是已启用生产优化。"
      },
      "acceptance_note": {
        "en": "Keep existing search behavior and rollback intact.",
        "zh": "保持现有搜索行为与回退能力。"
      },
      "evidence": [
        {
          "kind": "windows",
          "label": {
            "en": "WINDOWS_PLAYBACK_QUERY_BUDGET.md · Rust qualification",
            "zh": "WINDOWS_PLAYBACK_QUERY_BUDGET.md · Rust 验证"
          },
          "at": "2026-11-24",
          "state": "verified"
        }
      ]
    },
    {
      "id": "installation-and-recovery",
      "area": "operations",
      "stage": "in_progress",
      "priority": "next",
      "title": {
        "en": "Installation and recovery",
        "zh": "安装与恢复"
      },
      "summary": {
        "en": "Make new installations and backup restores repeatable.",
        "zh": "让新安装和备份恢复可以可靠复现。"
      },
      "implementation": [
        {
          "en": "An extracted source package can provision a synthetic owner, import a photo and recover without restoring withdrawn access.",
          "zh": "解包后的源码可创建合成测试所有者、导入照片，并在恢复时保留已撤销的访问限制。"
        },
        {
          "en": "Native Windows Android checks now select a reusable Gradle cache and temporary files on a fixed data volume. Local tests cover the storage selection.",
          "zh": "Windows 本机 Android 检查会在本地固定数据盘复用 Gradle 缓存并放置临时文件。存储位置的选择已通过本地测试。"
        }
      ],
      "gaps": [
        {
          "en": "Supported installers, service lifecycle and household recovery drills still need qualification.",
          "zh": "受支持的安装程序、服务生命周期与家庭恢复演练仍待验证。"
        }
      ],
      "next_step": {
        "en": "Rehearse the documented recovery flow with generated data for each supported platform.",
        "zh": "为各受支持平台用合成数据演练文档中的恢复流程。"
      },
      "delivery_note": {
        "en": "Current evidence is a local package and synthetic restore drill.",
        "zh": "当前证据来自本地打包与合成数据恢复演练。"
      },
      "acceptance_note": {
        "en": "Record runtime, storage, rollback and restored permissions for each platform.",
        "zh": "按平台记录运行环境、存储、回滚与恢复后的权限。"
      },
      "evidence": [
        {
          "kind": "source",
          "label": {
            "en": "AUDIT_RECONCILIATION_2026-11-24.md",
            "zh": "AUDIT_RECONCILIATION_2026-11-24.md"
          },
          "at": "2026-11-25",
          "state": "verified"
        }
      ]
    }
  ],
  "reference_links": []
};
