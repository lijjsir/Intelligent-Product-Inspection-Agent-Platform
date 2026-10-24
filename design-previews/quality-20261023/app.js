/* Standalone interface preview. No application APIs, credentials or database writes. */
const paths = {
  logo: '<path d="m5 12 7-7 7 7-7 7-7-7Z"/><path d="m12 2 10 10-10 10M2 12h20"/><circle cx="5" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="5" r="2" fill="currentColor"/><circle cx="19" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="19" r="2" fill="currentColor"/>',
  chat: '<path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H6l-4 3v-7.5A7.5 7.5 0 0 1 9.5 7H16a4 4 0 0 1 4 4.5Z"/><path d="M7 12h8M7 15h5M8 3h8a6 6 0 0 1 6 6"/>',
  meeting: '<path d="M3 10h18v11H3zM7 10V5h10v5M7 15h2m6 0h2M9 21v-3h6v3"/><path d="M11 2h2"/>',
  shield: '<path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6l-9-4Z"/><path d="m8 12 3 3 5-6"/>',
  task: '<rect x="5" y="4" width="15" height="18" rx="2"/><path d="M9 4V2h7v2M8 10h8M8 14h8M8 18h5"/>',
  results: '<path d="M4 3h16v18H4zM8 8h8M8 12h3m-3 4h3m3-3 2 2 4-5"/>',
  report: '<path d="M5 3h10l5 5v13H5V3Z"/><path d="M15 3v6h5M9 13h7M9 17h7"/>',
  standard: '<path d="M4 3h15v18H4zM8 8h7M8 12h7M8 16h4"/><path d="m14 18 2 2 5-5"/>',
  book: '<path d="M12 5v16M12 5C9 3 5 3 2 4v15c4-1 7-1 10 2 3-3 6-3 10-2V4c-3-1-7-1-10 1Z"/>',
  settings: '<path d="m9 3-1 3-3 1-2 5 2 5 3 1 1 3h6l1-3 3-1 2-5-2-5-3-1-1-3H9Z"/><circle cx="12" cy="12" r="3"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M4 16v5h16v-5M12 16V3m-5 5 5-5 5 5"/>',
  external: '<path d="M14 3h7v7M21 3 11 13M10 4H4v16h16v-6"/>',
  refresh: '<path d="M20 7a9 9 0 1 0 1 9M20 2v6h-6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  filter: '<path d="M3 6h18M6 12h12M9 18h6"/><circle cx="8" cy="6" r="2" fill="white"/><circle cx="16" cy="12" r="2" fill="white"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  back: '<path d="M20 12H4m6-6-6 6 6 6"/>',
  file: '<path d="M5 2h9l5 5v15H5V2Z"/><path d="M14 2v6h5M8 13h8M8 17h5"/>',
  expand: '<path d="M9 3H3v6m12-6h6v6M3 15v6h6m6 0h6v-6"/>',
  link: '<path d="m10 7 3-3a5 5 0 0 1 7 7l-3 3M14 17l-3 3a5 5 0 0 1-7-7l3-3M8 16l8-8"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  evidence: '<path d="M5 3h14v18H5zM9 8h6M9 12h6M9 16h4"/><circle cx="18" cy="18" r="4" fill="white"/><path d="m21 21 2 2"/>',
  warning: '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3h.01"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
const facts = window.PUBLIC_FACTS;
const fact = key => facts.find(f => f.key === key);
const originalUrl = fact('report').provenance.source_url;
const records = [
  { key: 'samr_charger', suffix: '00000005', title: '电动自行车充电器国家监督抽查通报', subtitle: '80批次中发现4批次不合格，涉及过充切断与超温保护。', type: '监督抽查', group: 'other', publisher: '国家市场监督管理总局', domain: 'samr.gov.cn', date: '2025-04-07', dateLabel: '通报发布', object: '电动自行车充电器', binding: '类别资料 · 产品及企业未确认', tone: 'amber', state: '对象待确认', detail: false },
  { key: 'cq_enforcement', suffix: '00000004', title: '万州电动自行车鞍座超长执法案例', subtitle: '公告披露10个型号、28辆涉案车辆，具体品牌与型号未公开。', type: '执法案例', group: 'other', publisher: '重庆市市场监督管理局', domain: 'scjgj.cq.gov.cn', date: '2025-12-19', dateLabel: '案例发布', object: '电动自行车', binding: '类别资料 · 产品及企业未确认', tone: 'amber', state: '对象待确认', detail: false },
  { key: 'report', suffix: '00000003', title: '速珂 TDR009Z-2Z 检验报告', subtitle: 'JG2128520085 · 整理车速限值、整车质量与鸣号装置的原报告结果。', type: '检测报告', group: 'report', publisher: '泉州市鲤城区政府网站', domain: 'qzlc.gov.cn', date: '2021-09-03', dateLabel: '报告签发', object: '速珂 TDR009Z-2Z', binding: '已关联产品 · 历史报告样品', tone: 'teal', state: '已关联产品', detail: true },
  { key: 'news', suffix: '00000002', title: '道路交通产品国家监督抽查报道', subtitle: '同一公开抽查事件的报道，用于补充来源背景，不计为新增检测。', type: '舆情资料', group: 'news', publisher: '中国质量新闻网', domain: 'cqn.com.cn', date: '2022-04-24', dateLabel: '报道发布', object: '速珂 TDR009Z-2Z', binding: '已关联产品 · 同一历史事件', tone: 'teal', state: '已关联产品', detail: false },
  { key: 'sampling', suffix: '00000001', title: '速珂 TDR009Z-2Z 抽样事实摘录', subtitle: '抽样2辆，含1辆检测与1辆备样；摘录自同一份历史检验报告。', type: '监督抽查', group: 'other', publisher: '泉州市鲤城区政府网站', domain: 'qzlc.gov.cn', date: '2021-07-30', dateLabel: '抽样日期', object: '速珂 TDR009Z-2Z', binding: '已关联产品 · 历史报告样品', tone: 'teal', state: '已关联产品', detail: false }
];
// Resolve the actual package key without synthesizing a source.
records[0].key = facts.find(f => f.key !== 'sampling' && f.key !== 'news' && f.key !== 'report' && f.key !== 'cq_enforcement').key;
const cases = [
  { key: 'main', title: '真实历史资料复盘｜速珂 TDR009Z-2Z 国家监督抽查与报告核对', code: 'RISK-7A5605B00C57', scope: '具体产品', evidence: 5, sources: 3, version: 6, status: '待独立复核', tone: 'blue', description: '原报告结果已整理 · 仅适用于历史样品与所检范围', action: '查看研判' },
  { key: 'charger', title: '真实公开抽查复盘｜电动自行车充电器安全项目', code: 'RISK-696B86A754EE', scope: '产品类别', evidence: 2, sources: null, version: 5, status: '待补充证据', tone: 'amber', description: '类别抽查信息 · 具体样品、产品及企业信息不足', action: '补充资料' },
  { key: 'cq', title: '真实公开执法复盘｜万州电动自行车鞍座超长案', code: 'RISK-91C9D96E8B3C', scope: '产品类别', evidence: 2, sources: null, version: 5, status: '待补充证据', tone: 'amber', description: '公开案例信息 · 具体品牌型号及原始报告未公开', action: '补充资料' }
];
let currentView = 'intake';
let activeTab = 'all';
let activeRiskTab = 'all';
let selectedCase = 'main';
let activeDetailTab = 'assessment';
let query = '';
let objectFilter = '';
let typeFilter = '';

function shell(view, body) {
  const detail = view === 'detail';
  const isRisk = view === 'risk';
  const nav = (label, ico, target, child = false, active = false) => `<a class="nav-item${child ? ' nav-child' : ''}${active ? ' active' : ''}" ${target ? `href="#${target}"` : 'href="#" data-info="nav"'}>${ico ? icon(ico) : ''}<span>${label}</span></a>`;
  return `<div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="brand"><div class="brand-mark">${icon('logo')}</div><div><div class="brand-word">PIAP</div><div class="brand-sub">智能检测平台</div></div></div>
      <nav>
        ${nav('AI 对话','chat')}${nav('会议室','meeting')}
        <div class="nav-group">${icon('shield')}<span>质量监督</span>${icon('down').replace('<svg','<svg class="chevron"')}</div>
        ${nav('数据采集',null,'intake',true,!isRisk)}
        ${nav('市场监控',null,null,true)}
        ${nav('风险研判',null,'risk',true,isRisk)}
        ${nav('监督抽查',null,null,true)}
        ${nav('实验室检测',null,null,true)}
        <div class="nav-separator"></div>
        ${nav('检测任务','task')}${nav('检测结果','results')}${nav('报告中心','report')}
        ${nav('标准审核','standard')}${nav('知识资料','book')}
        <div class="nav-separator"></div>${nav('个人设置','settings')}
      </nav>
      <div class="sidebar-foot"><span></span><span>界面预览 · 不写入业务数据</span></div>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div class="breadcrumbs"><button class="icon-btn mobile-menu" aria-label="展开导航">${icon('menu')}</button><span>PIAP 控制台</span><span class="slash">/</span><span>质量监督</span><span class="slash">/</span><b>${isRisk ? '风险研判' : detail ? '资料详情' : '数据采集'}</b></div>
        <div class="top-right"><div class="preview-tabs" aria-label="预览切换"><a href="#intake" class="${view === 'intake' ? 'active' : ''}">01 资料列表</a><a href="#detail" class="${detail ? 'active' : ''}">02 资料详情</a><a href="#risk" class="${isRisk ? 'active' : ''}">03 风险研判</a></div><span class="preview-label">交互预览</span><span class="vline"></span><div class="user"><span class="avatar">专</span><div class="user-text"><b>expert</b><small>专家</small></div></div></div>
      </header>
      <main id="main">${body}</main>
    </div>
  </div>`;
}
function footer(index) {
  return `<footer class="page-footer"><span>使用项目现有公开历史材料预览 · 展示标题与短摘录为本次整理 · 未产生新检测或专业审批</span><span class="version">PIAP / QUALITY SUPERVISION &nbsp; ${index} / 03</span></footer>`;
}
function tab(key, label, count, active, attr = 'data-tab') {
  return `<button class="tab ${key === active ? 'active' : ''}" ${attr}="${key}" role="tab" aria-selected="${key === active}">${label}<span>${count}</span></button>`;
}
function intake() {
  return shell('intake', `
    <div class="page-heading"><div><div class="eyebrow">QUALITY SUPERVISION / INTAKE</div><h1>数据采集</h1><p class="description">接入原始资料，确认来源与对象，让每一条研判都有据可查。</p></div><div class="actions"><button class="btn" data-info="references">${icon('book')}参考资料</button><button class="btn" data-info="import">${icon('upload')}文件导入</button><button class="btn primary" data-info="submit">${icon('plus')}提交资料</button></div></div>
    <div class="context-strip">${icon('info')}<span>原始资料保留完整内容与出处；公开历史材料的时间和适用范围单独标明。</span><a href="#detail">查看原文示例 ${icon('arrow')}</a></div>
    <section class="panel" aria-label="资料记录">
      <div class="tabs-row"><div class="tabs" role="tablist" aria-label="资料类型">${tab('all','全部资料',5,activeTab)}${tab('complaint','投诉',0,activeTab)}${tab('news','舆情',1,activeTab)}${tab('report','检测报告',1,activeTab)}${tab('other','其他资料',3,activeTab)}</div><span class="caption">当前预览材料</span></div>
      <form class="filters" id="intake-filter"><div class="field search"><label for="record-search">搜索资料</label><div class="input-wrap">${icon('search')}<input id="record-search" placeholder="标题、原文关键词或受理编号" value="${esc(query)}" autocomplete="off"></div></div><div class="field select-field"><label for="record-object">关联对象</label><select id="record-object"><option value="">全部对象</option value="linked" ${objectFilter === 'linked' ? 'selected' : ''}>已关联产品</option><option value="unlinked" ${objectFilter === 'unlinked' ? 'selected' : ''}>产品及企业未确认</option></select></div><div class="field select-field"><label for="record-type">资料类型</label><select id="record-type"><option value="">全部类型</option> ${['监督抽查','执法案例','检测报告','舆情资料'].map(t => `<option ${typeFilter === t ? 'selected' : ''}>${t}</option>`).join('')}</select></div><button class="btn filter-button" type="submit">查询</button><button class="more-filter" type="button" data-info="filter">${icon('filter')}更多筛选</button></form>
      <div class="table-meta"><span>显示 <strong id="record-count">5</strong> 份材料 <span id="filter-note"></span></span><span>原文摘录 · 点击标题查看详情</span></div>
      <table class="data-table"><colgroup><col style="width:39%"><col style="width:17%"><col style="width:19%"><col style="width:13%"><col style="width:12%"></colgroup><thead><tr><th>资料 / 受理编号</th><th>原始出处</th><th>关联对象</th><th>资料日期</th><th style="text-align:right">对象关联</th></tr></thead><tbody id="record-rows">${intakeRows(records)}</tbody></table>
      <div class="empty" id="record-empty" hidden>未找到匹配的资料。可调整关键词或资料类型。</div>
      <div class="pagination"><span>每页 20 条 · 当前预览共 5 份</span><div class="page-buttons"><button disabled aria-label="上一页">‹</button><button class="current" aria-current="page">1</button><button disabled aria-label="下一页">›</button></div></div>
    </section>${footer('01')}`);
}
function intakeRows(items) {
  return items.map(r => {
    const f = fact(r.key);
    return `<tr><td><button class="record-title" data-record="${r.key}">${r.title}</button><div class="excerpt" title="${esc(r.subtitle)}">${r.subtitle}</div><div class="meta-line"><span class="tag ${r.group === 'report' ? 'blue' : ''}">${r.type}</span><span class="mono">ZL-20261023-${r.suffix}</span><span>历史资料</span></div></td>
    <td><span class="source-name">${r.publisher}</span><a class="source-domain" href="${esc(f.provenance.source_url)}" target="_blank" rel="noreferrer">${r.domain} ${icon('external')}</a></td>
    <td><div class="objects">${r.object}<small>${r.binding}</small></div></td>
    <td><div class="date">${r.date}<small>${r.dateLabel}</small></div></td>
    <td><div class="row-actions"><span class="tag ${r.tone}">${r.state}</span><button class="text-btn" data-record="${r.key}">查看详情 →</button></div></td></tr>`;
  }).join('');
}
function detail() {
  return shell('detail', `
    <a class="back-link" href="#intake">${icon('back')}返回资料列表</a>
    <div class="page-heading"><div><div class="eyebrow">SOURCE RECORD / HISTORICAL REPORT</div><h1>速珂 TDR009Z-2Z 检验报告</h1><div class="heading-meta"><span class="mono">JG2128520085</span><span class="dot"></span><span>签发于 2021-09-03</span><span class="tag blue">历史资料</span><span class="tag amber">整理摘录待核对</span></div></div><div class="actions"><a class="btn" href="assets/JG2128520085.pdf" target="_blank">${icon('file')}打开原始 PDF</a><a class="btn primary" href="#risk">查看关联研判 ${icon('arrow')}</a></div></div>
    <div class="detail-grid">
      <div class="source-side">
        <section class="panel viewer-panel" aria-label="原始报告预览"><div class="viewer-toolbar"><div class="file-name">${icon('file')}JG2128520085.pdf</div><div class="page-picker"><select id="pdf-page" aria-label="原始PDF页码"><option value="3">PDF 第3页</option><option value="5">PDF 第5页</option></select><span class="caption">/ 8</span><button class="icon-btn expand-original" aria-label="放大原报告页面">${icon('expand')}</button></div></div><div class="pdf-canvas"><img id="original-page" src="assets/report-page-3.png" alt="JG2128520085 原始 PDF 第3页，车速限值与整车质量结果表"></div><div class="pdf-caption">${icon('info')}原件扫描页，点击放大查看；页码按 PDF 顺序标注。</div></section>
        <section class="panel source-card">${icon('link')}<div><h3>公开原件来源</h3><p>泉州市鲤城区政府网站 · qzlc.gov.cn</p><p>采集整理于 2026-10-23 · 保留原件与完整来源链接</p><p class="mono">SHA-256: 94ee5414…34df0e2</p><a href="${originalUrl}" target="_blank" rel="noreferrer">访问来源页面 ${icon('external')}</a></div></section>
      </div>
      <div class="detail-side">
        <section class="panel detail-summary"><div class="panel-header"><h2>报告事实摘录</h2><span class="tag">待独立核对</span></div><div class="detail-body">
          <div class="section-label">原报告所检项目结论</div><div class="report-verdict"><strong>不合格</strong><span class="tag red">原报告记载</span></div><p class="summary-note">仅针对该历史样品及所检范围，不代表当前在售产品状态。</p>
          <dl class="facts"><dt>样品对象</dt><dd>速珂 TDR009Z-2Z · 生产于 2019-08-01</dd><dt>标称生产单位</dt><dd>江苏速珂智能科技有限公司</dd><dt>检验依据</dt><dd>GB 17761-2018 <span class="caption">（原报告采用）</span></dd><dt>承检机构</dt><dd>上海市质量监督检验技术研究院</dd></dl>
          <div class="metrics-header"><h3>已整理的 3 项结果</h3><span>结果均为报告汇总值</span></div>
          <div class="measurement"><div><h3>车速限值</h3><p>设计车速 24，要求不超过 25 km/h</p></div><div class="value">30.8<small>km/h</small></div><span class="tag red">原判不合格</span></div>
          <div class="measurement"><div><h3>整车质量</h3><p>原要求 ≤ 55 kg · PDF 第3页</p></div><div class="value">51.4<small>kg</small></div><span class="tag teal">原判合格</span></div>
          <div class="measurement"><div><h3>鸣号声压级</h3><p>原要求 75–100 dB(A) · PDF 第5页</p></div><div class="value">73<small>dB(A)</small></div><span class="tag red">原判不合格</span></div>
          <div class="limits-note">车速原要求同时不超过最高设计车速。缺少仪器校准档案与重复原始读数；本次整理未补造检测数据。</div>
        </div></section>
        <section class="panel related-box"><div class="panel-header"><h2>关联业务</h2><span class="caption">沿用原事项</span></div><div class="related-content"><div><h3>速珂 TDR009Z-2Z 历史资料复盘</h3><div class="caption">第6版 · 待独立复核 · 5条证据</div></div><a href="#risk" class="text-btn">进入研判 →</a></div></section>
      </div>
    </div>
    <details class="panel under-detail"><summary>查看完整资料内容与来源说明</summary><div class="raw-text">${esc(fact('report').content.text)}\n\n适用范围：${esc(fact('report').content.limitations.join('；'))}。</div></details>
    ${footer('02')}`);
}
function risk() {
  return shell('risk', `
    <div class="page-heading"><div><div class="eyebrow">QUALITY SUPERVISION / RISK ASSESSMENT</div><h1>风险研判</h1><p class="description">围绕同一事项组织证据、研判与复核，保留每次判断的依据。</p></div><div class="actions"><button class="btn" data-info="history">${icon('clock')}历史记录</button><button class="btn" data-info="rules">风险等级规则</button><button class="btn primary" data-info="newcase">${icon('plus')}新建研判事项</button></div></div>
    <div class="count-line" aria-label="当前预览事项分布"><span class="count-label">当前预览</span><span><b>3</b><span class="count-label">个事项</span></span><span class="divider"></span><span><i class="status-dot amber"></i><span class="count-label">待补充证据</span><b>2</b></span><span><i class="status-dot blue"></i><span class="count-label">待独立复核</span><b>1</b></span><span class="tail">状态保留在业务记录中</span></div>
    <section class="panel" aria-label="研判事项台账"><div class="tabs-row"><div class="tabs" role="tablist" aria-label="事项状态">${tab('all','全部事项',3,activeRiskTab,'data-risk-tab')}${tab('evidence','待补充证据',2,activeRiskTab,'data-risk-tab')}${tab('review','待独立复核',1,activeRiskTab,'data-risk-tab')}</div><button class="text-btn" id="refresh-preview">${icon('refresh')} 刷新</button></div>
      <form class="filters" id="risk-filter"><div class="field search"><label for="risk-search">搜索事项</label><div class="input-wrap">${icon('search')}<input id="risk-search" placeholder="风险事项标题或编号" autocomplete="off"></div></div><div class="field select-field"><label for="risk-scope">研判范围</label><select id="risk-scope"><option value="">全部范围</option><option>具体产品</option><option>产品类别</option></select></div><button type="submit" class="btn filter-button">查询</button></form>
      <table class="risk-table"><colgroup><col><col style="width:110px"><col style="width:90px"><col style="width:110px"><col style="width:145px"><col style="width:115px"></colgroup><thead><tr><th>风险事项</th><th>研判范围</th><th>证据</th><th>当前版本</th><th>业务状态</th><th style="text-align:right">操作</th></tr></thead><tbody id="case-rows">${riskRows(cases)}</tbody></table><div class="empty" id="risk-empty" hidden>未找到匹配的事项。</div>
      <div class="pagination"><span>共 3 个预览事项 · 列表与详情使用同一条业务记录</span><div class="page-buttons"><button disabled aria-label="上一页">‹</button><button class="current" aria-current="page">1</button><button disabled aria-label="下一页">›</button></div></div>
    </section>
    <section class="panel selected-detail" id="selected-risk" tabindex="-1" aria-label="选中事项的研判详情">${riskDetail(selectedCase)}</section>
    ${footer('03')}`);
}
function riskRows(items) {
  return items.map(c => `<tr class="${c.key === selectedCase ? 'selected' : ''}"><td><button class="record-title" data-case="${c.key}">${c.title}</button><div class="mono">${c.code}</div><div class="risk-description">${c.description}</div></td><td>${c.scope}</td><td><span class="num-link">${c.evidence}<small>条</small></span></td><td><span class="tag">第${c.version}版</span></td><td><span class="tag ${c.tone}">${c.status}</span></td><td style="text-align:right"><button class="text-btn" data-case="${c.key}">${c.action}</button></td></tr>`).join('');
}
function riskDetail(key) {
  const c = cases.find(c => c.key === key);
  const main = key === 'main';
  const title = main ? '速珂 TDR009Z-2Z · 历史资料复盘' : key === 'charger' ? '电动自行车充电器 · 公开抽查复盘' : '万州电动自行车 · 公开执法复盘';
  const text = main ? '原报告记载车速限值、鸣号装置项目不合格，整车质量项目合格。本次研判限定于历史样品与原报告所检范围；摘录与引用关系仍需独立复核。' : key === 'charger' ? '公开通报提供类别层面的抽查结果，尚不足以定位具体产品、企业和样品。当前保留证据缺口，补充原始报告后再形成更具体的判断。' : '公开公告提供涉案车辆数量和鞍座不合格事实，未公开完整品牌型号、具体测量值及原始检验报告。当前保留证据缺口，不扩展为未披露的事实。';
  return `<div class="detail-heading"><div><div class="inline"><h2>${title}</h2><span class="tag ${c.tone}">${c.status}</span></div><div class="caption"><span class="mono">${c.code}</span> &nbsp; · &nbsp; 第${c.version}版</div></div><div class="actions"><button class="btn small" data-info="version">查看版本记录</button><button class="icon-btn" data-info="case-more" aria-label="更多事项操作">${icon('more')}</button></div></div>
    <div class="current-scope"><span class="tag teal">历史资料复盘</span><strong>${main ? '速珂 TDR009Z-2Z' : key === 'charger' ? '电动自行车充电器' : '电动自行车'}</strong><span>资料时期：${main ? '2021—2022' : key === 'charger' ? '2024' : '2024-07'}</span><span>来源 ${main ? 3 : 1} 条 · 证据 ${c.evidence} 项</span><button class="btn small" data-info="evidence">关联补充资料</button></div>
    <p class="report-condition">${icon('info')}复盘报告须在本版完成独立复核后生成；当前保留原状态。</p>
    <div class="tabs-row detail-workflow-tabs"><div class="tabs" role="tablist" aria-label="研判事项详情功能">${[['assessment','研判结论'],['sources',`原始资料（${main ? 3 : 1}）`],['laboratory','可选验证'],['reports','复盘报告'],['versions',`版本与复核（${c.version}）`]].map(([value,label])=>`<button class="tab ${activeDetailTab===value?'active':''}" role="tab" aria-selected="${activeDetailTab===value}" data-detail-tab="${value}">${label}</button>`).join('')}</div></div>
    <div id="detail-workflow-content">${activeDetailTab === 'assessment' ? `<div class="analysis-controls"><label>已发布风险等级规则（可选）<select aria-label="预览风险等级规则"><option>未指定</option></select></label><button class="btn primary" data-info="analysis">${icon('plus')}生成风险研判草稿</button><span class="tag ${c.tone}">第${c.version}版 · ${c.status}</span></div>
    <div class="assessment-body"><div class="assessment-main"><div class="minor-label">平台复盘分析 · 待独立核对</div><p class="analysis-text">${text}</p><div class="evidence-chips"><a class="evidence-chip" href="${main ? '#detail' : '#intake'}">${icon('evidence')}${main ? 'JG2128520085 · 原报告' : '公开通报与来源说明'}</a><a class="evidence-chip" href="#intake">${icon('link')}${main ? '3份关联资料' : '查看关联资料'}</a><span class="evidence-chip">${icon('clock')}历史复盘范围</span></div></div>
    <div class="assessment-side"><div class="next-step"><h3>${main ? '下一步：独立核对原件与摘录' : '下一步：补充可核验的原始资料'}</h3><p>${main ? '核对对象、历史标准、数值与引用页码，再由具备权限的独立复核人确认。' : '补充具体产品与企业、原始检验报告或测量记录，并说明资料来源。'}</p><button class="btn primary" data-info="${main ? 'review' : 'evidence'}">${main ? '进入复核' : '补充资料'} ${icon('arrow')}</button></div></div></div>
    <div class="current-review-facts"><span>历史风险信号等级：${main ? '中（模型建议，待复核）' : '待确认'}</span><span>风险概率：未校准，不展示概率</span></div>` : riskWorkflowContent(c, activeDetailTab)}</div>
    <div class="risk-footer">${icon('info')}<span>${main ? '第6版引用已保存的第4版模型分析；本版未重新调用模型。' : '公开资料不足；系统未代填测量值或人工审批结论。'}</span><a href="${main ? '#detail' : '#intake'}">${main ? '查看原报告' : '查看关联资料'}</a></div>`;
}
function riskWorkflowContent(c, tab) {
  const main = c.key === 'main';
  const items = main ? [fact('sampling'),fact('news'),fact('report')] : [c.key === 'charger' ? fact(records[0].key) : fact('cq_enforcement')];
  if (tab === 'sources') return `<div class="workflow-tab-body">${items.map(item=>`<article class="workflow-source"><div><span class="tag">${item.record_type==='inspection_report'?'检测报告':item.record_type==='public_opinion'?'舆情资料':'公开来源'}</span><a class="text-btn" href="${item.key==='report'?'#detail':'#intake'}">查看资料与原件 →</a></div><p>${esc(item.content.text)}</p><a href="${esc(item.provenance.source_url)}" target="_blank" rel="noreferrer">打开原始出处 ↗</a></article>`).join('')}</div>`;
  if (tab === 'laboratory') return `<div class="workflow-tab-body"><h3>已有报告引用与资料回流</h3><p>历史资料复盘可核对已有报告。需要新的实物检测时，应明确当前监管对象，另行创建对应业务事项。</p><p>${main?'已存在历史报告引用，原件与摘录仍需独立核对。':'当前来源为公开网页通报，没有具体样品的原始检验报告。'}</p><a class="btn" href="${main?'#detail':'#intake'}">${main?'核对已有报告':'查看现有来源资料'}</a></div>`;
  if (tab === 'reports') return `<div class="workflow-tab-body"><h3>复盘报告</h3><p>本版尚未完成独立复核，当前不能生成正式复盘报告。</p><p>报告将分别保存原资料记载、平台分析和结论限制，保留历史资料适用范围。</p><button class="btn" data-detail-tab="versions">查看版本与复核条件</button></div>`;
  return `<div class="workflow-tab-body"><h3>版本与复核</h3><p>当前第${c.version}版 · ${c.status}。${main?'本版沿用已保存的第4版模型分析。':'本版沿用已保存的第3版模型分析。'}</p><p>正式系统中的完整版本列表、原意见与独立复核操作继续保留。本预览不构造新的审批记录。</p><button class="btn" data-info="review">查看独立复核条件</button></div>`;
}
function render() {
  currentView = ['intake','detail','risk'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'intake';
  document.getElementById('app').innerHTML = currentView === 'intake' ? intake() : currentView === 'detail' ? detail() : risk();
  document.title = `PIAP · ${currentView === 'intake' ? '资料列表' : currentView === 'detail' ? '资料详情' : '风险研判'}界面预览`;
  if (currentView === 'intake') applyIntakeFilter();
}
function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message; el.classList.add('show');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove('show'), 3500);
}
function showInfo(title, body) {
  document.getElementById('dialog-title').textContent = title;
  document.getElementById('dialog-body').innerHTML = body;
  document.getElementById('info-dialog').showModal();
}
const info = {
  analysis: ['生成风险研判草稿', '<p>正式系统沿用现有后台研判任务、排队进度、版本校验与失败重试逻辑。</p><p>本预览只展示入口，不调用模型或修改事项。</p>'],
  nav: ['导航位置预览', '<p>会议室保留在 AI 对话下方，实验室检测归入质量监督，标准审核与知识资料各自独立。</p><p>这个预览只展开本次设计的三个视图，其余业务继续使用正式系统。</p>'],
  references: ['参考资料', '<p>两个独立入口，保持原有业务边界。</p><div class="actions"><button class="btn" data-info="standards">标准审核</button><button class="btn" data-info="knowledge">知识资料</button></div>'],
  standards: ['标准审核', '<p>保留标准导入、原件核对、条款审核与发布。当前为界面预览，未跳转正式系统。</p>'],
  knowledge: ['知识资料', '<p>保留资料整理与知识管理。当前为界面预览，未跳转正式系统。</p>'],
  import: ['文件导入', '<p>正式系统已有 CSV、XLSX、JSON 导入预览、字段映射、重复识别与确认导入接口。</p><p>本次只调整入口和信息层级，不触发导入。</p>'],
  submit: ['提交资料', '<p>沿用正式系统的资料提交表单：原始内容、资料类型、出处、发生时间、附件与对象关联。</p><p>本预览不提交资料，也不写入数据库。</p>'],
  filter: ['更多筛选', '<p>可展开已有产品、企业筛选。跨全部记录的“待确认数量”或新的状态组合筛选，需要先补齐后端查询支持。</p>'],
  history: ['历史记录', '<p>研判版本与审批记录仍保存在各个业务事项中，不额外增加独立待办面板。</p>'],
  rules: ['风险等级规则', '<p>沿用现有等级规则管理。样式调整不会改变正式判定规则。</p>'],
  newcase: ['新建研判事项', '<p>保留正式系统的新建表单，选择来源资料、研判范围与用途。</p><p>本预览没有创建新事项。</p>'],
  version: ['当前事项的版本记录', '<p>主案例当前为第6版、待独立复核。第6版沿用已保存的第4版模型分析，不是一次新的模型推理。</p><p>正式版本列表继续使用现有接口；本预览没有构造不存在的审批历史。</p>'],
  'case-more': ['事项操作', '<p>可集中收纳低频操作，例如查看来源、历史版本、补充资料。具体显示由角色权限与当前状态决定。</p>'],
  review: ['独立复核入口', '<p>可在正式系统打开已有复核表单，展示原件、摘录、适用范围和版本，再由具备权限的独立复核人作出决定。</p><p>本预览没有提交复核意见。</p>'],
  evidence: ['补充资料入口', '<p>将已有资料关联到当前事项，或提交带原始出处的新资料；保留版本检查与权限控制。</p><p>本预览没有生成或补造证据。</p>']
};
function applyIntakeFilter() {
  const items = records.filter(r => (activeTab === 'all' || activeTab === r.group) && (!query || `${r.title} ${fact(r.key).content.text} ZL-20261023-${r.suffix}`.toLowerCase().includes(query.toLowerCase())) && (!typeFilter || typeFilter === r.type) && (!objectFilter || (objectFilter === 'linked' ? r.tone === 'teal' : r.tone === 'amber')));
  document.getElementById('record-rows').innerHTML = intakeRows(items);
  document.getElementById('record-count').textContent = items.length;
  document.getElementById('record-empty').hidden = items.length > 0;
  document.getElementById('filter-note').textContent = items.length !== 5 ? '· 已筛选' : '';
}
function applyRiskFilter() {
  const keyword = document.getElementById('risk-search').value.trim().toLowerCase();
  const scope = document.getElementById('risk-scope').value;
  const items = cases.filter(c => (!keyword || `${c.title} ${c.code}`.toLowerCase().includes(keyword)) && (!scope || c.scope === scope) && (activeRiskTab === 'all' || (activeRiskTab === 'review' ? c.key === 'main' : c.key !== 'main')));
  document.getElementById('case-rows').innerHTML = riskRows(items);
  document.getElementById('risk-empty').hidden = items.length > 0;
}
document.addEventListener('click', e => {
  const detailTab = e.target.closest('[data-detail-tab]');
  if (detailTab) {
    activeDetailTab = detailTab.dataset.detailTab;
    document.getElementById('selected-risk').innerHTML = riskDetail(selectedCase);
    document.querySelector(`[data-detail-tab="${activeDetailTab}"]`).focus({preventScroll:true});
    return;
  }
  const tabBtn = e.target.closest('[data-tab]');
  if (tabBtn) {
    activeTab = tabBtn.dataset.tab;
    document.querySelectorAll('[data-tab]').forEach(b => { b.classList.toggle('active', b === tabBtn); b.setAttribute('aria-selected', String(b === tabBtn)); });
    applyIntakeFilter(); return;
  }
  const riskTab = e.target.closest('[data-risk-tab]');
  if (riskTab) {
    activeRiskTab = riskTab.dataset.riskTab;
    document.querySelectorAll('[data-risk-tab]').forEach(b => { b.classList.toggle('active', b === riskTab); b.setAttribute('aria-selected', String(b === riskTab)); });
    applyRiskFilter(); return;
  }
  const record = e.target.closest('[data-record]');
  if (record) {
    if (record.dataset.record === 'report') { location.hash = 'detail'; return; }
    const r = records.find(r => r.key === record.dataset.record);
    const f = fact(r.key);
    showInfo(r.title, `<p>${esc(f.content.text)}</p><p><a href="${esc(f.provenance.source_url)}" target="_blank" rel="noreferrer">访问原始出处 ${icon('external')}</a></p>`); return;
  }
  const caseBtn = e.target.closest('[data-case]');
  if (caseBtn) {
    selectedCase = caseBtn.dataset.case;
    activeDetailTab = 'assessment';
    document.getElementById('selected-risk').innerHTML = riskDetail(selectedCase);
    applyRiskFilter();
    const el = document.getElementById('selected-risk'); el.scrollIntoView({block:'start',behavior:'smooth'}); el.focus({preventScroll:true}); return;
  }
  const infoBtn = e.target.closest('[data-info]');
  if (infoBtn) {
    e.preventDefault();
    const item = info[infoBtn.dataset.info];
    if (document.getElementById('info-dialog').open) document.getElementById('info-dialog').close();
    if (item) showInfo(...item); return;
  }
  if (e.target.closest('.expand-original') || e.target.id === 'original-page') {
    document.getElementById('large-original').src = document.getElementById('original-page').src;
    document.getElementById('image-dialog').showModal(); return;
  }
  if (e.target.closest('.mobile-menu')) document.querySelector('.sidebar').classList.toggle('open');
  if (e.target.id === 'close-image') document.getElementById('image-dialog').close();
  if (e.target.id === 'close-info') document.getElementById('info-dialog').close();
  if (e.target.closest('#refresh-preview')) toast('当前为本地预览，未调用正式系统接口。');
});
document.addEventListener('submit', e => {
  if (e.target.id === 'intake-filter') {
    e.preventDefault(); query = document.getElementById('record-search').value.trim(); objectFilter = document.getElementById('record-object').value; typeFilter = document.getElementById('record-type').value; applyIntakeFilter();
  }
  if (e.target.id === 'risk-filter') { e.preventDefault(); applyRiskFilter(); }
});
document.addEventListener('change', e => {
  if (e.target.id === 'pdf-page') {
    const page = e.target.value;
    const img = document.getElementById('original-page'); img.src = `assets/report-page-${page}.png`;
    img.alt = `JG2128520085 原始 PDF 第${page}页`;
    document.querySelector('.pdf-canvas').scrollTop = 0;
  }
});
window.addEventListener('hashchange', () => { render(); window.scrollTo(0,0); });
render();
