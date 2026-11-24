(() => {
  "use strict";

  const copy = {
    en: {
      documentTitle: "PhotoHouse roadmap", skip: "Skip to roadmap", home: "PhotoHouse roadmap home", languageLabel: "Language", navigation: "Roadmap navigation", areasLabel: "Product areas", browseLabel: "Browse product area", localRoadmap: "Product roadmap", eyebrow: "A clearer view of what’s here and what’s next", roadmapWord: "roadmap",
      introCopy: "A practical map of product work, evidence, and the gaps still to close.", reviewed: "Reviewed",
      overviewKicker: "AT A GLANCE", overviewTitle: "Recorded delivery", countNote: "Counts describe dated roadmap records, not current service health.",
      explore: "EXPLORE", browseArea: "Browse area", allAreas: "All product areas", sidebarNote: "Plans and evidence are reviewed separately from live service status.",
      directionKicker: "THE DIRECTION", prioritiesTitle: "What we’re working toward", prioritiesIntro: "A small set of outcomes guides the next steps.",
      detailKicker: "THE DETAIL", featuresTitle: "Capabilities & gaps", searchLabel: "Search roadmap", searchPlaceholder: "Search features, gaps, evidence…",
      stageFilter: "Filter by stage", priorityFilter: "Filter by priority", allStages: "All stages", allPriorities: "All priorities", clearFilters: "Clear filters",
      emptyTitle: "No roadmap items match", emptyBody: "Try another search or clear the filters.", footerNote: "PhotoHouse · A product plan grounded in recorded evidence", sourceLink: "Read the roadmap notes",
      delivered: "Recorded delivery", source_ready: "Source ready", in_progress: "In progress", planned: "Planned",
      now: "Now", next: "Next", later: "Later", why: "Why it matters", doneWhen: "Done when",
      implementation: "Implemented", gaps: "Still missing", nextStep: "Next step", deliveryNote: "Delivery context", acceptanceNote: "Acceptance context",
      details: "Implementation, gaps & evidence", closeDetails: "Close details", evidence: "Evidence", source: "Source", local: "Local", windows: "Windows", family: "Family",
      verified: "Verified", partial: "Partial", pending: "Pending", featureCount: n => `${n} ${n === 1 ? "roadmap item" : "roadmap items"}`,
      noDescription: "No description provided.", notRecorded: "Not recorded in this roadmap.", noNotice: "This roadmap has no runtime-status notice.",
      noticeWarning: "Planning note", noticeInfo: "Status note", noTitle: "Roadmap data unavailable", noBody: "The data.js companion file has not loaded. Open this page alongside its data file.",
      related: "Related notes", areaCount: n => `${n} items`, shippedWarning: "Dated delivery record · not a live-status claim",
    },
    zh: {
      documentTitle: "PhotoHouse 产品路线图", skip: "跳到路线图", home: "PhotoHouse 路线图首页", languageLabel: "语言", navigation: "路线图导航", areasLabel: "产品区域", browseLabel: "选择产品区域", localRoadmap: "产品路线图", eyebrow: "看清已有进展，也看清下一步", roadmapWord: "路线图",
      introCopy: "以实际工作、证据和待补齐的差距为基础，梳理产品方向。", reviewed: "回顾日期",
      overviewKicker: "进度概览", overviewTitle: "路线图记录", countNote: "统计的是有日期的路线图记录，不代表服务当前状态。",
      explore: "浏览区域", browseArea: "选择产品区域", allAreas: "所有产品区域", sidebarNote: "产品计划与证据回顾不等于实时服务状态。",
      directionKicker: "产品方向", prioritiesTitle: "我们正在推进的目标", prioritiesIntro: "用少量清晰成果指引后续工作。",
      detailKicker: "具体进展", featuresTitle: "能力与差距", searchLabel: "搜索路线图", searchPlaceholder: "搜索功能、差距或证据…",
      stageFilter: "按阶段筛选", priorityFilter: "按优先级筛选", allStages: "所有阶段", allPriorities: "所有优先级", clearFilters: "清除筛选",
      emptyTitle: "没有匹配的路线图项目", emptyBody: "试试其他关键词，或清除筛选条件。", footerNote: "PhotoHouse · 以已记录证据为基础的产品计划", sourceLink: "阅读路线图说明",
      delivered: "已交付记录", source_ready: "源码已就绪", in_progress: "进行中", planned: "计划中",
      now: "当前重点", next: "下一步", later: "后续", why: "目标价值", doneWhen: "完成标准",
      implementation: "已实现", gaps: "仍有差距", nextStep: "下一步", deliveryNote: "交付背景", acceptanceNote: "验收背景",
      details: "实现情况、差距与证据", closeDetails: "收起详情", evidence: "证据", source: "源码", local: "本地", windows: "Windows", family: "家庭验收",
      verified: "已核实", partial: "部分完成", pending: "待核实", featureCount: n => `${n} 项路线图记录`,
      noDescription: "暂无说明。", notRecorded: "路线图中没有记录。", noNotice: "路线图未提供运行状态说明。",
      noticeWarning: "规划提示", noticeInfo: "状态说明", noTitle: "路线图数据不可用", noBody: "data.js 配套文件未加载。请将此页面与数据文件放在一起打开。",
      related: "相关说明", areaCount: n => `${n} 项`, shippedWarning: "有日期的交付记录 · 不代表实时状态",
    }
  };
  const stages = ["delivered", "source_ready", "in_progress", "planned"];
  const priorities = ["now", "next", "later"];
  const data = window.PHOTOHOUSE_ROADMAP;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  let language = "en";
  let activeArea = "all";

  try {
    const saved = localStorage.getItem("photohouse-roadmap-language");
    if (saved === "en" || saved === "zh") language = saved;
  } catch (_) { /* local file storage can be unavailable in some browsers */ }
  const requestedLanguage = new URLSearchParams(location.search).get("lang");
  if (requestedLanguage === "en" || requestedLanguage === "zh") language = requestedLanguage;

  const text = value => {
    if (value && typeof value === "object") return String(value[language] ?? value.en ?? "");
    return value == null ? "" : String(value);
  };
  const tr = key => copy[language][key];
  const node = (tag, className, content) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined) element.textContent = String(content);
    return element;
  };
  const safeHref = raw => {
    if (typeof raw !== "string" || !raw.trim()) return null;
    const href = raw.trim();
    if (/^https?:\/\//i.test(href)) return href;
    if (href.startsWith("//") || href.startsWith("/") || href.includes("\\") || /^[a-z][a-z\d+.-]*:/i.test(href)) return null;
    return href;
  };
  const link = (label, href, className) => {
    const safe = safeHref(href);
    if (!safe) return node("span", className, label);
    const a = node("a", className, label);
    a.href = safe;
    if (/^https?:\/\//i.test(safe)) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
    return a;
  };
  const array = value => Array.isArray(value) ? value : [];
  const languageData = window.PHOTOHOUSE_ROADMAP;

  function setStaticLanguage() {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    document.title = tr("documentTitle");
    $$('[data-i18n]').forEach(el => {
      const value = tr(el.dataset.i18n);
      if (typeof value === "string") el.textContent = value;
    });
    $$('[data-i18n-aria]').forEach(el => el.setAttribute("aria-label", tr(el.dataset.i18nAria)));
    $("#search-input").placeholder = tr("searchPlaceholder");
    $$('[data-language]').forEach(button => button.setAttribute("aria-pressed", String(button.dataset.language === language)));
    const source = $("#source-link");
    source.replaceChildren(document.createTextNode(tr("sourceLink") + " "));
    const arrow = node("span", "", "↗"); arrow.setAttribute("aria-hidden", "true"); source.append(arrow);
  }

  function renderUnavailable() {
    const banner = $("#runtime-notice");
    banner.className = "runtime-notice info";
    const icon = node("span", "notice-symbol", "i"); icon.setAttribute("aria-hidden", "true");
    const body = node("div"); body.append(node("strong", "notice-title", tr("noTitle")), node("p", "notice-body", tr("noBody")));
    banner.replaceChildren(icon, body);
    $("#feature-list").replaceChildren();
    $("#empty-state").hidden = false;
    $("#empty-state h3").textContent = tr("noTitle");
    $("#empty-state p").textContent = tr("noBody");
  }

  function renderNotice() {
    const notice = languageData.runtime_notice || {};
    const severity = notice.severity === "info" ? "info" : "warning";
    const banner = $("#runtime-notice");
    banner.className = `runtime-notice ${severity}`;
    const icon = node("span", "notice-symbol", severity === "info" ? "i" : "!"); icon.setAttribute("aria-hidden", "true");
    const body = node("div");
    body.append(node("strong", "notice-title", text(notice.title) || tr(severity === "info" ? "noticeInfo" : "noticeWarning")));
    body.append(node("p", "notice-body", text(notice.body) || tr("noNotice")));
    banner.replaceChildren(icon, body);
  }

  function renderSummary() {
    const counts = Object.fromEntries(stages.map(stage => [stage, array(languageData.features).filter(feature => feature.stage === stage).length]));
    $("#summary-counts").replaceChildren(...stages.map(stage => {
      const card = node("div", "summary-card"); card.dataset.stage = stage;
      const top = node("div", "summary-top", tr(stage));
      const dot = node("span", "summary-indicator"); dot.setAttribute("aria-hidden", "true"); top.append(dot);
      card.append(top, node("div", "summary-number", counts[stage]));
      return card;
    }));
  }

  function renderAreas() {
    const areas = array(languageData.areas);
    const features = array(languageData.features);
    const nav = $("#area-nav"), select = $("#area-select");
    nav.replaceChildren(); select.replaceChildren();
    const allOption = node("option", "", tr("allAreas")); allOption.value = "all"; select.append(allOption);
    const allButton = node("button", "area-link"); allButton.type = "button"; allButton.dataset.area = "all"; allButton.setAttribute("aria-current", String(activeArea === "all"));
    const allLabel = node("span", "", tr("allAreas")); const allCount = node("span", "area-count", features.length); allButton.append(allLabel, allCount); nav.append(allButton);
    areas.forEach(area => {
      const count = features.filter(feature => feature.area === area.id).length;
      const button = node("button", "area-link"); button.type = "button"; button.dataset.area = area.id; button.setAttribute("aria-current", String(activeArea === area.id));
      button.append(node("span", "", text(area.title) || tr("noDescription")), node("span", "area-count", count)); nav.append(button);
      const option = node("option", "", text(area.title)); option.value = area.id; select.append(option);
    });
    select.value = activeArea;
  }

  function renderPriorities() {
    const container = $("#priorities");
    const items = array(languageData.priorities);
    container.replaceChildren(...items.map((item, index) => {
      const card = node("article", "priority-card"); card.dataset.priority = item.id || priorities[index] || "later";
      const top = node("div", "priority-top"); top.append(node("span", "priority-tag", tr(item.id) || tr(priorities[index]) || ""), node("span", "priority-index", String(index + 1).padStart(2, "0")));
      card.append(top, node("h3", "", text(item.title) || tr("noDescription")), node("p", "", text(item.why) || tr("notRecorded")));
      const done = node("div", "priority-done"); done.append(node("strong", "", `${tr("doneWhen")}: `), document.createTextNode(text(item.done_when) || tr("notRecorded")));
      card.append(done);
      return card;
    }));
  }

  function normalized(value) { return String(value || "").toLocaleLowerCase(language === "zh" ? "zh-CN" : "en").normalize("NFKD"); }
  function featureSearchText(feature) {
    // Search both translations so changing language never loses a matching item.
    return JSON.stringify(feature);
  }

  function makeNote(label, value, className = "") {
    const block = node("div", `note-block ${className}`.trim()); block.append(node("strong", "", label), document.createTextNode(value || tr("notRecorded"))); return block;
  }
  function listColumn(title, items, extraClass = "") {
    const section = node("section", `detail-column ${extraClass}`.trim()); section.append(node("h4", "", title));
    const list = node("ul");
    const values = array(items).map(text).filter(Boolean);
    if (!values.length) list.append(node("li", "", tr("notRecorded")));
    else values.forEach(value => list.append(node("li", "", value)));
    section.append(list); return section;
  }
  function renderFeature(feature) {
    const card = node("article", "feature-card"); card.id = feature.id; card.dataset.area = feature.area || ""; card.dataset.stage = feature.stage || ""; card.dataset.priority = feature.priority || "";
    const main = node("div", "feature-main");
    const topline = node("div", "feature-topline"); const tags = node("div", "feature-tags");
    const stageTag = node("span", `tag stage-${feature.stage || "planned"}`, tr(feature.stage) || tr("planned"));
    if (feature.stage === "delivered") stageTag.title = tr("shippedWarning");
    tags.append(stageTag, node("span", `tag priority-${feature.priority || "later"}`, tr(feature.priority) || tr("later")));
    const area = array(languageData.areas).find(item => item.id === feature.area);
    if (area) tags.append(node("span", "tag", text(area.title)));
    topline.append(tags);
    const date = (array(feature.evidence).map(e => e.at).filter(Boolean).sort().slice(-1)[0]);
    if (date) topline.append(node("time", "feature-time", date));
    const heading = node("h3");
    const titleLink = node("a", "feature-title-link", text(feature.title) || tr("noDescription")); titleLink.href = `#${encodeURIComponent(feature.id)}`;
    heading.append(titleLink);
    main.append(topline, heading, node("p", "feature-summary", text(feature.summary) || tr("noDescription")));
    card.append(main);
    const notes = node("div", "feature-notes");
    notes.append(makeNote(tr("deliveryNote"), text(feature.delivery_note)), makeNote(tr("acceptanceNote"), text(feature.acceptance_note), "gap")); card.append(notes);
    const details = document.createElement("details"); details.className = "feature-details";
    if (location.hash === `#${feature.id}`) details.open = true;
    const summary = document.createElement("summary"); summary.textContent = tr("details"); details.append(summary);
    const body = node("div", "detail-content");
    const columns = node("div", "detail-columns");
    columns.append(listColumn(tr("implementation"), feature.implementation), listColumn(tr("gaps"), feature.gaps, "gaps"));
    const next = node("section", "detail-column"); next.append(node("h4", "", tr("nextStep")), node("p", "", text(feature.next_step) || tr("notRecorded"))); columns.append(next);
    body.append(columns);
    const evidence = array(feature.evidence);
    if (evidence.length) {
      body.append(node("h4", "", tr("evidence")));
      const list = node("div", "evidence-list");
      evidence.forEach(item => {
        const label = `${tr(item.kind) || item.kind || tr("evidence")}: ${text(item.label)}${item.at ? ` · ${item.at}` : ""}`;
        const pill = link(label, item.href, safeHref(item.href) ? "evidence-link" : "evidence-label");
        const dot = node("span", `evidence-state ${item.state || "pending"}`); dot.setAttribute("aria-hidden", "true"); pill.prepend(dot);
        const state = node("span", "visually-hidden", ` · ${tr(item.state) || tr("pending")}`); pill.append(state); list.append(pill);
      }); body.append(list);
    }
    details.append(body); card.append(details); return card;
  }

  function filteredFeatures() {
    const query = normalized($("#search-input").value.trim());
    const stage = $("#stage-filter").value;
    const priority = $("#priority-filter").value;
    return array(languageData.features).filter(feature =>
      (activeArea === "all" || feature.area === activeArea) &&
      (stage === "all" || feature.stage === stage) &&
      (priority === "all" || feature.priority === priority) &&
      (!query || normalized(featureSearchText(feature)).includes(query))
    );
  }
  function renderFeatures() {
    const filtered = filteredFeatures();
    const container = $("#feature-list"); container.replaceChildren(...filtered.map(renderFeature));
    $("#empty-state").hidden = filtered.length > 0;
    $("#result-count").textContent = tr("featureCount")(filtered.length);
    const hasFilters = activeArea !== "all" || $("#stage-filter").value !== "all" || $("#priority-filter").value !== "all" || $("#search-input").value.trim() !== "";
    $("#clear-filters").hidden = !hasFilters;
    renderAreas();
  }

  function renderFilters() {
    const stageSelect = $("#stage-filter"), prioritySelect = $("#priority-filter");
    const currentStage = stageSelect.value || "all", currentPriority = prioritySelect.value || "all";
    stageSelect.replaceChildren(stageSelect.options[0]);
    prioritySelect.replaceChildren(prioritySelect.options[0]);
    stages.forEach(stage => { const option = node("option", "", tr(stage)); option.value = stage; stageSelect.append(option); });
    priorities.forEach(priority => { const option = node("option", "", tr(priority)); option.value = priority; prioritySelect.append(option); });
    stageSelect.value = currentStage; prioritySelect.value = currentPriority;
  }
  function renderRelated() {
    const links = array(languageData.reference_links);
    if (!links.length) return;
    const footer = $(".page-footer");
    const old = $(".related-links"); if (old) old.remove();
    const related = node("div", "related-links"); related.append(node("span", "related-label", `${tr("related")}: `));
    links.forEach(item => related.append(link(text(item.label), item.href, "related-link")));
    footer.before(related);
  }
  function resetFilters() {
    activeArea = "all"; $("#search-input").value = ""; $("#stage-filter").value = "all"; $("#priority-filter").value = "all"; renderFeatures();
  }
  function applyHash() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; }
    if (!id) return;
    const feature = array(languageData.features).find(item => item.id === id);
    if (!feature) return;
    activeArea = "all"; $("#search-input").value = ""; $("#stage-filter").value = "all"; $("#priority-filter").value = "all";
    renderFeatures();
    requestAnimationFrame(() => {
      const card = document.getElementById(id);
      if (card) { card.querySelector("details").open = true; card.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }
    });
  }
  function renderAll(savedView = null) {
    setStaticLanguage();
    if (!languageData || languageData.schema_version !== 1) { renderUnavailable(); return; }
    if (savedView) {
      activeArea = savedView.area;
      $("#search-input").value = savedView.search;
      $("#stage-filter").value = savedView.stage;
      $("#priority-filter").value = savedView.priority;
    }
    const snapshot = languageData.snapshot_label;
    $("#review-date").textContent = text(snapshot) || (languageData.updated_at || "—");
    renderNotice(); renderSummary(); renderAreas(); renderPriorities(); renderFilters(); renderRelated(); renderFeatures();
    if (savedView) savedView.openDetails.forEach(id => {
      const details = document.getElementById(id)?.querySelector("details");
      if (details) details.open = true;
    });
  }

  $$('.language-switch button').forEach(button => button.addEventListener("click", () => {
    const savedView = {
      area: activeArea,
      search: $("#search-input").value,
      stage: $("#stage-filter").value,
      priority: $("#priority-filter").value,
      openDetails: $$("#feature-list .feature-card").filter(card => card.querySelector("details")?.open).map(card => card.id),
    };
    language = button.dataset.language;
    try { localStorage.setItem("photohouse-roadmap-language", language); } catch (_) { /* preference remains in memory */ }
    try {
      const url = new URL(location.href); url.searchParams.set("lang", language);
      history.replaceState(null, "", url);
    } catch (_) { /* file previews may restrict history */ }
    renderAll(savedView);
  }));
  $("#area-nav").addEventListener("click", event => {
    const button = event.target.closest("button[data-area]"); if (!button) return;
    activeArea = button.dataset.area; renderFeatures();
  });
  $("#area-select").addEventListener("change", event => { activeArea = event.target.value; renderFeatures(); });
  $("#search-input").addEventListener("input", renderFeatures);
  $("#stage-filter").addEventListener("change", renderFeatures);
  $("#priority-filter").addEventListener("change", renderFeatures);
  $("#clear-filters").addEventListener("click", resetFilters);
  $("#empty-state").addEventListener("click", event => { if (event.target.closest('[data-action="clear"]')) resetFilters(); });
  window.addEventListener("hashchange", applyHash);
  renderAll();
  applyHash();
})();
