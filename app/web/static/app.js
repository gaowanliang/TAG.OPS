// ============================================================
//  Anime Image Classifier — frontend logic
// ============================================================

// ---- tiny helpers ----
const $ = (id) => document.getElementById(id);
const h = (tag, attrs = {}, ...children) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (k === 'class') el.className = v;
        else if (k === 'text') el.textContent = v;
        else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
        else if (v !== false && v != null) el.setAttribute(k, v);
    }
    for (const c of children.flat()) {
        if (c == null || c === false) continue;
        el.append(c.nodeType ? c : document.createTextNode(c));
    }
    return el;
};
const esc = (s) => String(s).replace(/[&<>"]/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]
));

// ---- icons (Font Awesome 7) ----
// FA 通过 CSS class 渲染图标字形，不需要 JS 初始化。保留 refreshIcons 作为
// 向后兼容的 no-op，避免调用点抛错。
function refreshIcons(_root) { /* FA is pure CSS; nothing to do */ }

// 构建一个 FA 图标 span：name 不含 "fa-" 前缀，variant 可选 "solid" | "brands" | "regular"。
function icon(name, extraClass = '', variant = 'solid') {
    return h('span', {
        class: `fa-${variant} fa-${name} ${extraClass}`.trim(),
    });
}

// ---- state ----
const state = {
    folder: null,
    files: [],
    jobId: null,
    results: [],
    byKey: {},          // key = path for folder jobs, filename for upload
    view: 'grid',       // 'grid' | 'category' | 'history' | 'detail'
    source: 'none',     // 'none' | 'scan' | 'upload' | 'history'
    page: 1,
    pageSize: 20,
    categories: {},
    categoryName: null,
    currentDetail: null,
    lang: 'zh',
};

// ---- tag translations (from /api/tag-i18n) ----
let TAG_I18N = {};
function tagKey(name) {
    return String(name || '').trim().toLowerCase().replace(/\s+/g, '_');
}
function tagZh(name) {
    const e = TAG_I18N[tagKey(name)];
    return e && e.zh ? e.zh : '';
}

/**
 * 渲染一个 tag 名：中文模式下显示「中文 <small>英文</small>」。
 * 返回 DOM 节点片段（document fragment）。
 */
function renderTagName(rawName) {
    const frag = document.createDocumentFragment();
    const zh = tagZh(rawName);
    if (state.lang === 'zh' && zh) {
        frag.append(document.createTextNode(zh));
        frag.append(h('span', { class: 'bar-label-en mono' }, rawName));
    } else {
        frag.append(document.createTextNode(rawName));
    }
    return frag;
}

async function loadTagI18n() {
    try {
        const r = await fetch('/api/tag-i18n');
        TAG_I18N = await r.json();
    } catch { TAG_I18N = {}; }
}

// ---- UI i18n ----
const STRINGS = {
    'card.hw':           { zh: '硬件状态',            en: 'Hardware' },
    'card.src':          { zh: '图片来源',            en: 'Source' },
    'card.settings':     { zh: '识别设置',            en: 'Settings' },
    'card.about':        { zh: '关于',                en: 'About' },
    'about.qq':          { zh: 'QQ 群 · 哔哩哔哩科技宅',
                           en: 'QQ group · bilibili techie' },
    'label.folder':      { zh: '文件夹路径',          en: 'Folder path' },
    'label.recursive':   { zh: '递归子目录',          en: 'Recursive' },
    'label.save_fmt':    { zh: '保存格式',            en: 'Save format' },
    'label.model':       { zh: '模型',                en: 'Model' },
    'label.gpu':         { zh: '加速显卡',            en: 'GPU device' },
    'label.threshold':   { zh: '阈值',                en: 'Threshold' },
    'label.max_tags':    { zh: '最大标签数',          en: 'Max tags' },
    'label.repl_us':     { zh: '替换下划线',          en: 'Replace underscore' },
    'label.sort_alpha':  { zh: '按字母排序',          en: 'Sort alphabetically' },
    'label.page_size':   { zh: '每页',                en: 'Per page' },
    'label.top_n':       { zh: '前 N 个标签',         en: 'Top-N tags' },
    'label.min_images':  { zh: '最小图片数',          en: 'Min images' },
    'label.search':      { zh: '搜索',                en: 'Search' },
    'label.sort':        { zh: '排序',                en: 'Sort' },
    'label.or_drop':     { zh: 'OR · 拖放图片到页面任意位置',
                           en: 'OR · drop images anywhere on the page' },
    'opt.yes':           { zh: '是',                  en: 'Yes' },
    'opt.no':            { zh: '否',                  en: 'No' },
    'opt.save_none':     { zh: '不保存',              en: "Don't save" },
    'opt.sort_count':    { zh: '图片数量',            en: 'Image count' },
    'opt.sort_name':     { zh: '标签名称',            en: 'Tag name' },
    'btn.browse':        { zh: '浏览…',              en: 'Browse…' },
    'btn.pick':          { zh: '选择文件…',           en: 'Pick files…' },
    'btn.run':           { zh: '识别',                en: 'Recognize' },
    'btn.refresh_cat':   { zh: '刷新分类',            en: 'Refresh' },
    'btn.back':          { zh: '← 返回',             en: '← Back' },
    'btn.dl_all':        { zh: '下载全部标签',        en: 'Download all tags' },
    'btn.dl_high':       { zh: '下载高置信度 (≥0.7)', en: 'Download high-conf (≥0.7)' },
    'btn.up':            { zh: '↑ 上级',             en: '↑ Up' },
    'btn.go':            { zh: '前往',                en: 'Go' },
    'btn.cancel':        { zh: '取消',                en: 'Cancel' },
    'btn.pick_this':     { zh: '选择此文件夹',        en: 'Pick this folder' },
    'btn.ok':            { zh: '确定',                en: 'OK' },
    'tab.grid':          { zh: '图片网格',            en: 'Grid' },
    'tab.cat':           { zh: '标签分类',            en: 'Categories' },
    'tab.hist':          { zh: '历史',                en: 'History' },
    'label.save_as':     { zh: '保存：',              en: 'Save:' },
    'h.history':         { zh: '识别历史',            en: 'Recognition history' },
    'btn.refresh':       { zh: '刷新',                en: 'Refresh' },
    'btn.load':          { zh: '加载',                en: 'Load' },
    'btn.delete':        { zh: '删除',                en: 'Delete' },
    'info.hist_hint':    { zh: '所有已完成的文件夹识别都会记录在此，点击任意条目即可回看。',
                           en: 'Every finished folder run is recorded here — click an entry to open it.' },
    'info.hist_empty':   { zh: '暂无历史记录，跑完一个文件夹后这里会出现条目。',
                           en: 'No history yet. Finish a folder run and it will appear here.' },
    'info.hist_loaded':  { zh: '✓ 已加载「{p}」的历史结果（{n} 张）',
                           en: '✓ Loaded history: {p} ({n} images)' },
    'info.save_ok':      { zh: '✓ 已保存 {n} 个文件到 {p}',
                           en: '✓ Saved {n} files to {p}' },
    'info.save_ok2':     { zh: '✓ 已保存 {n} 个文件（清理旧记录 {r} 个）到 {p}',
                           en: '✓ Saved {n} files (removed {r} old) to {p}' },
    'dlg.skip_cached':   { zh: '跳过已识别？',        en: 'Skip cached?' },
    'msg.skip_cached':   { zh: '检测到该目录已有 {n} 条历史结果（含 xxhash）。是否跳过它们？\n• 选“是”：仅处理新图片，旧图片直接读回原结果\n• 选“否”：全部重新识别',
                           en: 'Found {n} cached results (with xxhash). Skip them?\n• Yes: only process new images, reuse cached ones\n• No: re-run everything' },
    'msg.confirm_del':   { zh: '删除该历史记录？',    en: 'Delete this history record?' },
    'meta.images':       { zh: '{n} 张',              en: '{n} imgs' },
    'info.rec_on':       { zh: '递归',                en: 'Recursive' },
    'info.rec_off':      { zh: '不递归',              en: 'Flat' },
    'info.rec_on_tip':   { zh: '扫描时包含子目录',    en: 'Scanned subfolders' },
    'info.rec_off_tip':  { zh: '仅扫描顶层目录',      en: 'Top folder only' },
    'info.skip_on':      { zh: '命中缓存',            en: 'Cached' },
    'info.hist_missing': { zh: '缺失 {n} 张',          en: '{n} missing' },
    'msg.folder_gone':   { zh: '目录已不存在：{p}',    en: 'Folder no longer exists: {p}' },
    'msg.hist_empty_disk': { zh: '历史记录里的文件已全部缺失',
                             en: 'All files referenced by this record are missing.' },
    'btn.select':        { zh: '选中',                en: 'Select' },
    'btn.select_all':    { zh: '全选',                en: 'Select all' },
    'btn.select_none':   { zh: '清空',                en: 'Clear' },
    'btn.copy_to':       { zh: '复制到…',            en: 'Copy to…' },
    'btn.move_to':       { zh: '剪切到…',            en: 'Move to…' },
    'info.selected':     { zh: '已选 {n} 张',         en: '{n} selected' },
    'info.copied_ok':    { zh: '✓ 已复制 {n} 张到 {p}', en: '✓ Copied {n} to {p}' },
    'info.moved_ok':     { zh: '✓ 已移动 {n} 张到 {p}', en: '✓ Moved {n} to {p}' },
    'info.transfer_err': { zh: '{n} 张失败，请查看控制台', en: '{n} failed, see console' },
    'h.img_info':        { zh: '图片信息',            en: 'Image info' },
    'h.ratings':         { zh: '评级',                en: 'Rating' },
    'h.tags':            { zh: '标签',                en: 'Tags' },
    'h.pick_folder':     { zh: '选择文件夹',          en: 'Pick folder' },
    'ph.folder':         { zh: '例如 D:\\images\\anime', en: 'e.g. D:\\images\\anime' },
    'ph.tag':            { zh: '标签名',              en: 'Tag name' },
    'ph.cur_path':       { zh: '当前路径',            en: 'Current path' },
    'drop.title':        { zh: '拖放图片到此处',      en: 'Drop images here' },
    'drop.sub':          { zh: '松开即可添加',        en: 'Release to add' },
    'dlg.start':         { zh: '开始识别',            en: 'Start recognition' },
    'dlg.tip':           { zh: '提示',                en: 'Notice' },
    'msg.no_source':     { zh: '请先填写文件夹路径或拖放图片到页面',
                           en: 'Please enter a folder path or drop images.' },
    'msg.no_files':      { zh: '请选择或拖放图片',    en: 'Please pick or drop images.' },
    'msg.need_path':     { zh: '请输入文件夹路径',    en: 'Please enter a folder path.' },
    'msg.need_job':      { zh: '请先运行识别',        en: 'Run recognition first.' },
    'msg.pick_folder':   { zh: '请选择一个文件夹',    en: 'Please pick a folder.' },
    'msg.confirm_up':    { zh: '已准备 {n} 张上传图片，是否开始识别？',
                           en: 'Ready: {n} uploaded images. Start recognition?' },
    'msg.confirm_folder':{ zh: '扫描到 {n} 张图片，是否开始识别？\n\n路径：{p}',
                           en: 'Scanned {n} images. Start recognition?\n\nPath: {p}' },
    'msg.added':         { zh: '已添加 {n} 张图片，是否现在开始识别？',
                           en: 'Added {n} images. Start recognition now?' },
    'info.scanned':      { zh: '✓ 扫描到 {n} 张图片于 {p}',
                           en: '✓ Scanned {n} images at {p}' },
    'info.picked':       { zh: '✓ 已选择 {n} 个文件',
                           en: '✓ Selected {n} file(s)' },
    'info.total':        { zh: '共 {n} 张图片',       en: '{n} images total' },
    'info.empty_grid':   { zh: '扫描一个文件夹或上传图片开始 SYS_READY_.',
                           en: 'Scan a folder or drop images to start. SYS_READY_.' },
    'info.empty_cat':    { zh: '没有符合条件的分类', en: 'No matching categories' },
    'info.total_tags':   { zh: '共 {n} 个标签',       en: '{n} tags total' },
    'info.auto_select':  { zh: '自动选择',            en: 'Auto-select' },
    'info.auto_ort':     { zh: '自动 (由 ORT 选择)', en: 'Auto (pick by ORT)' },
    'info.no_gpu':       { zh: '无显卡',              en: 'No GPU' },
    'info.available':    { zh: '{n} 可用',            en: '{n} available' },
    'info.none':         { zh: '无',                  en: 'None' },
    'info.ok_tags':      { zh: '✓ {n} 个标签',        en: '✓ {n} tags' },
    'info.err':          { zh: '✗ 处理失败',          en: '✗ Failed' },
    'info.pending':      { zh: '· 待识别',            en: '· Pending' },
    'info.no_result':    { zh: '无结果',              en: 'No result' },
    'info.analyzing':    { zh: '正在分析...',         en: 'Analyzing...' },
    'info.no_src':       { zh: '(原图不可用)',        en: '(original unavailable)' },
    'info.back_cat':     { zh: '← 返回分类',         en: '← Back to categories' },
    'info.empty_dir':    { zh: '（空）',             en: '(empty)' },
    'info.n_images':     { zh: '📸 {n} 张 · ⭐ {c}',  en: '📸 {n} · ⭐ {c}' },
    'info.kv.size':      { zh: '尺寸',                en: 'Size' },
    'info.kv.format':    { zh: '格式',                en: 'Format' },
    'info.kv.mode':      { zh: '模式',                en: 'Mode' },
    'info.kv.filesize':  { zh: '文件大小',            en: 'File size' },
    'cat.count':         { zh: '个类别',              en: 'categories' },
    'cat.images':        { zh: '张图片',              en: 'images' },
    'cat.avg':           { zh: '平均每类',            en: 'avg/category' },
    'model.downloaded':  { zh: '✓ 已下载',            en: '✓ Downloaded' },
    'model.warn':        { zh: '⬇ 首次使用将自动下载', en: '⬇ Auto-download on first use' },
    'model.group_dl':    { zh: '✅ 已下载',            en: '✅ Downloaded' },
    'model.group_nd':    { zh: '⬇ 未下载',            en: '⬇ Not downloaded' },
};

function t(key, vars) {
    const row = STRINGS[key];
    let s = row ? (row[state.lang] || row.zh || key) : key;
    if (vars) {
        for (const [k, v] of Object.entries(vars)) {
            s = s.replaceAll('{' + k + '}', v);
        }
    }
    return s;
}

function applyI18n() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (STRINGS[key]) el.textContent = t(key);
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => {
        const key = el.getAttribute('data-i18n-ph');
        if (STRINGS[key]) el.placeholder = t(key);
    });
    document.documentElement.lang = state.lang;
    // 更新 lang slider 视觉状态（滑块位置 + active 文字）
    const slider = $('btn-lang');
    if (slider) {
        slider.classList.toggle('lang-zh', state.lang === 'zh');
        slider.classList.toggle('lang-en', state.lang === 'en');
        slider.querySelectorAll('.lang-slot').forEach(el => {
            el.classList.toggle('active',
                el.getAttribute('data-lang') === state.lang);
        });
    }
}

function setLang(lang) {
    state.lang = lang;
    localStorage.setItem('aict_lang', lang);
    applyI18n();
    // 重新渲染动态内容
    if (HW_CACHE) renderHardware(HW_CACHE);
    renderModelHint();
    renderGrid();
    // 重新分组模型 select（分组标签跟随语言）
    loadModels();
    if (state.view === 'detail' && state.currentDetail) {
        const r = state.byKey[state.currentDetail];
        if (r) renderDetail(r);
    }
    if (state.view === 'category') renderCategoryGrid();
}

// ---- upload staging (drag & drop) ----
let uploadFiles = [];   // File[] staged for upload

// ---- recent paths (localStorage) ----
const RECENT_KEY = 'aict_recent_paths';

function loadRecentPaths() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); }
    catch { return []; }
}

function pushRecentPath(p) {
    if (!p) return;
    let list = loadRecentPaths().filter(x => x !== p);
    list.unshift(p);
    list = list.slice(0, 5);
    localStorage.setItem(RECENT_KEY, JSON.stringify(list));
    renderRecentPaths();
}

function renderRecentPaths() {
    const dl = $('recent-paths');
    dl.innerHTML = '';
    for (const p of loadRecentPaths()) {
        dl.append(h('option', { value: p }));
    }
}

// ---- hardware / models bootstrap ----
let HW_CACHE = null;

async function loadHardware() {
    const r = await fetch('/api/hardware');
    const d = await r.json();
    HW_CACHE = d;
    renderHardware(d);
    populateGpuSelect(d);
}

function renderHardware(d) {
    const box = $('hw');
    box.innerHTML = '';
    const net = d.network || {};
    const accelOk = d.selected && d.selected !== 'CPUExecutionProvider';
    const gpus = d.gpus_indexed || [];
    const selectedId = parseInt(localStorage.getItem('aict_device_id') ?? '');
    const hasSel = Number.isFinite(selectedId);

    // ① 加速器
    box.append(stat({
        label: 'ACCELERATOR',
        value: d.accelerator || 'CPU',
        sub: d.selected || '—',
        badge: accelOk ? '⚡' : '·',
        badgeCls: accelOk ? 'accel' : 'warn',
    }));

    // ② 下载通道
    const channel = (state.lang === 'en' && d.download_channel_en)
        ? d.download_channel_en
        : d.download_channel;
    box.append(stat({
        label: 'CHANNEL',
        value: channel || '—',
        sub: `${net.region || '—'} · ${net.endpoint || '—'}`,
        badge: '◎',
        badgeCls: 'net',
    }));

    // ③ Providers（全宽）
    box.append(stat({
        label: 'PROVIDERS',
        value: (d.providers || []).length
            ? t('info.available', { n: (d.providers || []).length })
            : t('info.none'),
        sub: (d.providers || []).join(' · ') || '—',
        badge: 'Σ',
        badgeCls: 'prov',
        full: true,
    }));

    // ④ GPUs（全宽，列表）
    const gpuStat = stat({
        label: `GPU × ${gpus.length}`,
        value: hasSel && gpus.length
            ? (gpus.find(g => g.id === selectedId)?.name || `GPU ${selectedId}`)
            : (gpus.length ? t('info.auto_select') : t('info.no_gpu')),
        sub: null,
        badge: gpus.length ? String(gpus.length) : '0',
        badgeCls: 'gpu',
        full: true,
    });
    if (gpus.length) {
        const list = h('div', { class: 'hw-gpu-list' });
        for (const g of gpus) {
            list.append(h('div', {
                class: 'hw-gpu-item' + (hasSel && selectedId === g.id ? ' selected' : ''),
            },
                h('span', { class: 'hw-gpu-index' }, String(g.id)),
                h('span', { class: 'hw-gpu-name', title: g.name }, g.name),
            ));
        }
        gpuStat.append(list);
    }
    box.append(gpuStat);

    if (d.error) box.append(h('div', { class: 'err' }, d.error));
}

function stat({ label, value, sub, badge, badgeCls = '', full = false }) {
    const el = h('div', { class: 'hw-stat' + (full ? ' full hw-full' : '') },
        h('div', { class: 'hw-stat-label' }, label),
        h('div', { class: 'hw-stat-value' }, value),
        sub ? h('div', { class: 'hw-stat-sub' }, sub) : null,
    );
    if (badge) {
        el.append(h('span', { class: 'hw-stat-badge ' + badgeCls }, badge));
    }
    return el;
}

function populateGpuSelect(d) {
    const sel = $('gpu-device');
    if (!sel) return;
    const gpus = d.gpus_indexed || [];
    sel.innerHTML = `<option value="">${t('info.auto_ort')}</option>`
        + gpus.map(g => `<option value="${g.id}">[${g.id}] ${esc(g.name)}</option>`).join('');
    const saved = localStorage.getItem('aict_device_id');
    if (saved !== null) sel.value = saved;
    sel.onchange = () => {
        if (sel.value === '') localStorage.removeItem('aict_device_id');
        else localStorage.setItem('aict_device_id', sel.value);
        if (HW_CACHE) renderHardware(HW_CACHE);
    };
}

function updateTopbarStatus() { /* no-op: chips removed */ }

const MODEL_KEY = 'aict_model';
let MODEL_INFO = [];

async function loadModels() {
    const r = await fetch('/api/models');
    const d = await r.json();
    const info = d.info || (d.models || []).map(n => (
        { name: n, tier: '', hint: '', downloaded: false }
    ));
    MODEL_INFO = info;

    const sel = $('model');
    sel.innerHTML = '';
    const mk = (label, items) => {
        if (!items.length) return;
        const og = document.createElement('optgroup');
        og.label = label;
        for (const m of items) {
            const opt = document.createElement('option');
            opt.value = m.name;
            const tierTag = m.tier ? `[${m.tier}] ` : '';
            opt.textContent = `${tierTag}${m.name}`;
            og.append(opt);
        }
        sel.append(og);
    };
    mk(t('model.group_dl'), info.filter(m => m.downloaded));
    mk(t('model.group_nd'), info.filter(m => !m.downloaded));

    const saved = localStorage.getItem(MODEL_KEY);
    const valid = info.some(m => m.name === saved);
    // 选择优先级：已保存 > 已下载首个 > 推荐首个
    const firstDownloaded = info.find(m => m.downloaded);
    sel.value = valid ? saved
        : (firstDownloaded ? firstDownloaded.name
            : (info[0] ? info[0].name : ''));
    renderModelHint();

    sel.addEventListener('change', () => {
        localStorage.setItem(MODEL_KEY, sel.value);
        renderModelHint();
    });
}

function renderModelHint() {
    const box = $('model-hint');
    if (!box) return;
    const name = $('model').value;
    const m = MODEL_INFO.find(x => x.name === name);
    if (!m) { box.innerHTML = ''; return; }
    const tierCls = m.tier
        ? 'tier-' + m.tier.toLowerCase().replace(/[^a-z0-9]/g, '')
        : '';
    const status = m.downloaded
        ? `<span class="model-hint-dl ok">${t('model.downloaded')}</span>`
        : `<span class="model-hint-dl warn">${t('model.warn')}</span>`;
    const hint = (state.lang === 'en' && m.hint_en) ? m.hint_en : m.hint;
    box.innerHTML =
        (m.tier ? `<span class="model-tier ${tierCls}">${m.tier}</span>` : '')
        + (hint ? `<span class="model-hint-text">${esc(hint)}</span>` : '')
        + status;
}

// ---- settings builder ----
function currentOptions() {
    const devStr = $('gpu-device')?.value ?? '';
    return {
        model:                $('model').value,
        threshold:            parseFloat($('threshold').value),
        max_tags:             parseInt($('max-tags').value) || null,
        replace_underscore:   $('replace-underscore').value === '1',
        sort_alphabetical:    $('sort-alphabetical').value === '1',
        save_format:          'none',  // 保存由事后按钮触发
        device_id:            devStr === '' ? null : parseInt(devStr),
    };
}

// ---- scan ----
async function scanFolder(silent = false) {
    const path = $('folder-path').value.trim();
    if (!path) {
        if (!silent) await showAlert(t('msg.need_path'));
        return null;
    }
    const recursive = $('recursive').value === '1';
    const r = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, recursive }),
    });
    const d = await r.json();
    if (d.error) { await showAlert(d.error); return null; }
    state.folder = d.path;
    state.files = d.files;
    state.source = 'scan';
    state.historyId = null;
    state.page = 1;
    for (const f of state.files) if (f.blobUrl) URL.revokeObjectURL(f.blobUrl);
    uploadFiles = [];
    $('dropzone-count').textContent = '';
    pushRecentPath(d.path);
    $('scan-info').textContent = t('info.scanned', { n: d.count, p: d.path });
    _jobStatus = '';
    switchView('grid');
    renderGrid();
    return d;
}

// ---- save-as (TXT / JSON) ----
async function runSave(fmt) {
    const body = {};
    if (state.source === 'scan' && state.jobId) {
        body.job_id = state.jobId;
    } else if (state.source === 'history' && state.historyId) {
        body.history_id = state.historyId;
    } else {
        await showAlert(t('msg.need_job'));
        return;
    }
    body.format = fmt;
    const r = await fetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const d = await r.json();
    if (d.error) { await showAlert(d.error); return; }
    const msg = (d.removed > 0)
        ? t('info.save_ok2', { n: d.saved, r: d.removed, p: d.save_dir })
        : t('info.save_ok',  { n: d.saved, p: d.save_dir });
    await showAlert(msg);
}

function updateSaveButtons() {
    const canScanSave = state.source === 'scan'
        && state.jobId && _jobStatus === 'finished';
    const canHistSave = state.source === 'history' && state.historyId;
    const enable = canScanSave || canHistSave;
    for (const id of ['btn-save-txt', 'btn-save-json']) {
        const el = $(id);
        if (el) el.disabled = !enable;
    }
    const box = $('save-settings');
    if (box) box.hidden = !(state.source === 'scan' || state.source === 'history');
}

let _jobStatus = '';
async function refreshHistory() {
    const list = $('history-list');
    if (!list) return;
    list.innerHTML = '';
    let d;
    try {
        const r = await fetch('/api/history/list');
        d = await r.json();
    } catch { d = { runs: [] }; }
    const runs = d.runs || [];
    if (!runs.length) {
        list.append(h('div', { class: 'history-empty mono' },
            t('info.hist_empty')));
        return;
    }
    for (const r of runs) list.append(historyRow(r));
    refreshIcons();
}

function historyRow(r) {
    const meta = h('div', { class: 'hrow-meta mono' });
    meta.append(h('span', {}, r.created_at || ''));
    if (r.model) meta.append(h('span', {}, '· ' + r.model));
    if (r.status && r.status !== 'finished') {
        meta.append(h('span', {}, '· ' + r.status));
    }
    const settings = r.settings || {};
    const recBadge = h('span', {
        class: 'hrow-rec ' + (settings.recursive ? 'on' : 'off'),
        title: settings.recursive
            ? t('info.rec_on_tip') : t('info.rec_off_tip'),
    }, settings.recursive ? t('info.rec_on') : t('info.rec_off'));
    meta.append(recBadge);
    if (settings.skip_existing) {
        meta.append(h('span', { class: 'hrow-rec on' }, t('info.skip_on')));
    }

    const row = h('div', { class: 'history-row' },
        h('span', { class: 'hrow-id' }, '#' + r.id),
        h('div', { class: 'hrow-body' },
            h('div', { class: 'hrow-path', title: r.path }, r.path),
            meta,
        ),
        h('span', { class: 'hrow-count mono' },
            t('meta.images', { n: r.total || 0 })),
        h('button', {
            class: 'hrow-del icon-btn',
            type: 'button',
            title: t('btn.delete'),
            onclick: async (ev) => {
                ev.stopPropagation();
                const ok = await showConfirm(t('btn.delete'),
                    t('msg.confirm_del'));
                if (!ok) return;
                await fetch('/api/history/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: r.id }),
                });
                refreshHistory();
            },
        }, icon('trash-can')),
    );
    row.addEventListener('click', () => loadHistoryRun(r.id));
    return row;
}

async function loadHistoryRun(id) {
    const resp = await fetch('/api/history/get?id=' + id + '&rescan=1');
    const d = await resp.json();
    if (d.error) { await showAlert(d.error); return; }
    if (!d.folder_exists) {
        await showAlert(t('msg.folder_gone', { p: d.path || '' }));
        return;
    }
    const results = d.results || [];
    if (!results.length) {
        await showAlert(t('msg.hist_empty_disk'));
        return;
    }

    // 释放旧 blob
    for (const f of state.files) if (f.blobUrl) URL.revokeObjectURL(f.blobUrl);
    uploadFiles = [];
    $('folder-path').value = '';
    $('scan-info').textContent = '';

    state.folder = d.path || '';
    state.source = 'history';
    state.historyId = id;
    state.files = results.map(r => ({
        path: r.path || r.file,
        name: r.file || (r.path ? r.path.split(/[\\/]/).pop() : 'result'),
        realPath: r.path || '',
    }));
    state.byKey = {};
    for (const r of results) {
        const key = r.path || r.file;
        if (key) state.byKey[key] = r;
    }
    state.results = results;
    state.jobId = null;
    state.categories = {};
    state.categoryName = null;
    state.page = 1;

    const missTxt = d.missing
        ? ' · ' + t('info.hist_missing', { n: d.missing })
        : '';
    $('grid-count').textContent =
        t('info.hist_loaded', { n: results.length, p: d.path || '' }) + missTxt;
    switchView('grid');
    renderGrid();
}

async function runRecognize() {
    // 优先级：文件夹路径 > 已上传图片
    const path = $('folder-path').value.trim();
    if (path) {
        const d = await scanFolder();
        if (!d) return;
        // 若目录里有 tagging_results/*.json（带 xxhash），询问是否跳过已识别
        let skipExisting = false;
        if (d.has_tagging_results && d.cached_hashes > 0) {
            skipExisting = await showConfirm(
                t('dlg.skip_cached'),
                t('msg.skip_cached', { n: d.cached_hashes }),
            );
        }
        const ok = await showConfirm(t('dlg.start'),
            t('msg.confirm_folder', { n: d.count, p: d.path }));
        if (ok) runFolderBatch({ skip_existing: skipExisting });
        return;
    }
    if (uploadFiles.length) {
        const ok = await showConfirm(t('dlg.start'),
            t('msg.confirm_up', { n: uploadFiles.length }));
        if (ok) runUpload();
        return;
    }
    await showAlert(t('msg.no_source'));
}

// ---- batch (folder) ----
async function runFolderBatch(extra = {}) {
    if (!state.folder) return;
    const opts = currentOptions();
    const body = {
        ...opts,
        path: state.folder,
        recursive: $('recursive').value === '1',
        ...extra,
    };
    const r = await fetch('/api/batch/folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const d = await r.json();
    if (d.error) { await showAlert(d.error); return; }
    state.jobId = d.job_id;
    pollJob();
}

// ---- batch (upload) ----
async function runUpload() {
    const files = uploadFiles.length ? uploadFiles : Array.from($('files').files || []);
    if (!files.length) { await showAlert(t('msg.no_files')); return; }
    const fd = new FormData();
    for (const f of files) fd.append('files', f);
    const opts = currentOptions();
    for (const [k, v] of Object.entries(opts)) {
        if (typeof v === 'boolean') fd.append(k, v ? '1' : '0');
        else if (v != null) fd.append(k, v);
    }
    const r = await fetch('/api/batch', { method: 'POST', body: fd });
    const d = await r.json();
    if (d.error) { await showAlert(d.error); return; }
    state.jobId = d.job_id;
    switchView('grid');
    renderGrid();
    pollJob();
}

// ---- poll ----
async function pollJob() {
    if (!state.jobId) return;
    const r = await fetch('/api/status?id=' + state.jobId);
    const d = await r.json();
    const prog = $('progress');
    prog.max = d.total; prog.value = d.done;
    $('pmsg').textContent = `${d.status} — ${d.done}/${d.total} · ${d.message || ''}`;

    if (d.results) {
        state.results = d.results;
        state.byKey = {};
        for (const it of d.results) {
            const key = it.path || it.file;
            if (key) state.byKey[key] = it;
        }
        // 刷新网格状态徽标
        renderGrid();
    }

    _jobStatus = d.status;
    updateSaveButtons();

    if (d.status === 'running' || d.status === 'pending') {
        setTimeout(pollJob, 600);
    }
}

// ---- grid ----
function renderGrid() {
    const grid = $('grid');
    grid.innerHTML = '';
    const total = state.files.length;
    $('grid-count').textContent = total ? t('info.total', { n: total }) : '';

    if (!total) {
        grid.append(h('div', { class: 'empty mono' }, t('info.empty_grid')));
        renderPager(0);
        return;
    }

    const pageSize = parseInt($('page-size').value) || 20;
    state.pageSize = pageSize;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    if (state.page > pages) state.page = pages;
    const start = (state.page - 1) * pageSize;
    const slice = state.files.slice(start, start + pageSize);

    for (const f of slice) {
        grid.append(buildCard(f));
    }
    renderPager(pages);
}

function buildCard(f) {
    const key = f.path;
    const r = state.byKey[key];
    const isUpload = state.folder == null;
    // history 模式可能没有源文件：用 realPath 判定是否能取缩略
    const diskPath = (f.realPath != null) ? f.realPath : key;
    const canThumb = isUpload ? !!f.blobUrl : !!diskPath;
    const thumbSrc = canThumb
        ? (isUpload
            ? f.blobUrl
            : `/api/thumb?path=${encodeURIComponent(diskPath)}&size=240`)
        : '';
    const status = r
        ? (r.error
            ? h('div', { class: 'card-status err', text: t('info.err') })
            : h('div', { class: 'card-status ok' },
                t('info.ok_tags', { n: Object.keys(r.tags || {}).length })))
        : h('div', { class: 'card-status mono', text: t('info.pending') });

    const thumb = thumbSrc
        ? h('img', { src: thumbSrc, loading: 'lazy', alt: f.name })
        : h('div', { class: 'thumb-placeholder mono' }, f.name);

    return h('div', {
        class: 'card-img',
        onclick: () => openDetail(key),
    },
        h('div', { class: 'thumb' }, thumb),
        h('div', { class: 'card-name mono', title: f.path, text: f.name }),
        status,
    );
}

function renderPager(pages) {
    const box = $('pager'); box.innerHTML = '';
    if (pages < 2) return;
    const mk = (label, page, disabled = false, active = false) =>
        h('button', {
            class: 'pager-btn' + (active ? ' active' : ''),
            type: 'button',
            disabled,
            onclick: () => { state.page = page; renderGrid(); },
        }, label);
    box.append(mk('‹', state.page - 1, state.page <= 1));
    const maxShow = 7;
    let from = Math.max(1, state.page - 3);
    let to = Math.min(pages, from + maxShow - 1);
    from = Math.max(1, to - maxShow + 1);
    for (let p = from; p <= to; p++) {
        box.append(mk(String(p), p, false, p === state.page));
    }
    box.append(mk('›', state.page + 1, state.page >= pages));
}

// ---- detail ----
async function openDetail(key) {
    state.currentDetail = key;
    switchView('detail');
    $('detail-title').textContent = state.byKey[key]?.file || key.split(/[\\/]/).pop();

    const imgBox = $('detail-image');
    imgBox.innerHTML = '';
    const isLocal = state.folder != null;
    const fileEntry = state.files.find(x => x.path === key);
    if (isLocal) {
        // history 模式下用 realPath；文件夹扫描下 key 就是实际路径
        const diskPath = (fileEntry && fileEntry.realPath != null)
            ? fileEntry.realPath
            : key;
        if (diskPath) {
            imgBox.append(h('img', {
                src: `/api/image?path=${encodeURIComponent(diskPath)}`,
            }));
        } else {
            imgBox.append(h('div', { class: 'mono' }, t('info.no_src')));
        }
    } else {
        if (fileEntry && fileEntry.blobUrl) {
            imgBox.append(h('img', { src: fileEntry.blobUrl }));
        } else {
            imgBox.append(h('div', { class: 'mono' }, t('info.no_src')));
        }
    }

    let r = state.byKey[key];
    if (!r || r.error) {
        // history 模式已带 tags，直接渲染
        if (state.source === 'history') { renderDetail(r); return; }
        // lazy compute
        if (!isLocal) { renderDetail(r); return; }
        $('detail-tags').innerHTML = `<div class="mono">${t('info.analyzing')}</div>`;
        const opts = currentOptions();
        const body = { ...opts, path: key };
        const resp = await fetch('/api/interrogate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        r = await resp.json();
        if (r.error) {
            $('detail-tags').innerHTML = `<div class="err">${esc(r.error)}</div>`;
            return;
        }
        state.byKey[key] = r;
    }
    renderDetail(r);
}

function renderDetail(r) {
    if (!r) {
        $('detail-tags').innerHTML = `<div class="err">${t('info.no_result')}</div>`;
        return;
    }
    const info = $('detail-info');
    const im = r.image_info || {};
    info.innerHTML = '';
    const rows = [
        [t('info.kv.size'), im.width && im.height ? `${im.width} × ${im.height}` : '—'],
        [t('info.kv.format'), im.format || '—'],
        [t('info.kv.mode'), im.mode || '—'],
        [t('info.kv.filesize'),
            im.file_size ? (im.file_size / 1024).toFixed(1) + ' KB' : '—'],
    ];
    for (const [k, v] of rows) {
        info.append(h('div', { class: 'kv' },
            h('span', { class: 'k' }, k),
            h('span', { class: 'v' }, v)));
    }

    // 评级：紧凑 chip
    const ratingsBox = $('detail-ratings');
    ratingsBox.innerHTML = '';
    const ratings = r.ratings || {};
    const entries = Object.entries(ratings);
    let topName = null, topConf = -1;
    for (const [n, c] of entries) if (c > topConf) { topConf = c; topName = n; }
    for (const [name, conf] of entries) {
        ratingsBox.append(ratingChip(name, conf, name === topName));
    }

    const tagsBox = $('detail-tags');
    tagsBox.innerHTML = '';
    const tags = r.tags || {};
    const count = Object.keys(tags).length;
    const badge = $('detail-tag-count');
    if (badge) badge.textContent = t('info.total_tags', { n: count });
    for (const [name, conf] of Object.entries(tags)) {
        tagsBox.append(bar(name, conf, emojiOf(conf)));
    }

    $('btn-dl-all').onclick = () => downloadText(
        `${stemOf(r.file)}_all_tags.txt`,
        Object.keys(tags).join(', '),
    );
    $('btn-dl-high').onclick = () => downloadText(
        `${stemOf(r.file)}_high_conf_tags.txt`,
        Object.entries(tags).filter(([, c]) => c >= 0.7).map(([t]) => t).join(', '),
    );
}

function ratingChip(name, conf, isTop) {
    const zh = tagZh(name);
    const showZh = state.lang === 'zh' && zh;
    const nameSpan = h('span', { class: 'rc-name' },
        showZh ? zh : name,
        showZh ? h('span', { class: 'rc-en' }, name) : null,
    );
    return h('div', { class: 'rating-chip' + (isTop ? ' top' : '') },
        h('span', { class: 'rc-dot' }),
        nameSpan,
        h('span', { class: 'rc-val' }, conf.toFixed(3)),
    );
}

function emojiOf(c) {
    if (c >= 0.8) return '🔥';
    if (c >= 0.6) return '⭐';
    if (c >= 0.4) return '✨';
    return '💫';
}

function stemOf(name) { return (name || 'result').replace(/\.[^.]+$/, ''); }

function bar(name, conf, prefix = '') {
    const pct = Math.max(0, Math.min(1, conf)) * 100;
    const labelEl = h('div', { class: 'bar-label', title: name });
    if (prefix) labelEl.append(document.createTextNode(prefix + ' '));
    labelEl.append(renderTagName(name));
    return h('div', { class: 'bar-row' },
        labelEl,
        h('div', { class: 'bar-track' },
            h('div', { class: 'bar-fill', style: `width:${pct.toFixed(1)}%` })),
        h('div', { class: 'bar-value mono' }, conf.toFixed(3)),
    );
}

function downloadText(filename, content) {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = h('a', { href: url, download: filename });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---- view switching ----
function switchView(view) {
    if (view !== 'detail') state.lastView = view;
    state.view = view;
    for (const id of ['view-grid', 'view-category', 'view-history', 'view-detail']) {
        const el = $(id);
        if (el) el.hidden = (id !== 'view-' + view);
    }
    $('tab-grid').classList.toggle('active', view === 'grid');
    $('tab-category').classList.toggle('active', view === 'category');
    $('tab-history').classList.toggle('active', view === 'history');

    const tabsVisible = view !== 'detail';
    const tabsEl = document.querySelector('.topbar-tabs');
    if (tabsEl) tabsEl.style.visibility = tabsVisible ? '' : 'hidden';

    updateSaveButtons();
}

// ---- category view ----
async function refreshCategories() {
    let url;
    if (state.source === 'history' && state.historyId) {
        url = `/api/categorize?history_id=${state.historyId}`;
    } else if (state.jobId) {
        url = `/api/categorize?job_id=${state.jobId}`;
    } else {
        await showAlert(t('msg.need_job'));
        return;
    }
    const topN = parseInt($('top-n').value) || 3;
    const minImages = parseInt($('min-images').value) || 2;
    const r = await fetch(`${url}&top_n=${topN}&min_images=${minImages}`);
    const d = await r.json();
    if (d.error) { await showAlert(d.error); return; }
    state.categories = d.categories || {};
    state.categoryName = null;
    renderCategoryStats(d);
    renderCategoryGrid();
}

function renderCategoryStats(d) {
    const avg = d.total_categories
        ? (d.total_images / d.total_categories).toFixed(1) : '0';
    $('cat-stats').innerHTML = `
        <div class="cat-stat"><h2>${d.total_categories}</h2><span>${t('cat.count')}</span></div>
        <div class="cat-stat"><h2>${d.total_images}</h2><span>${t('cat.images')}</span></div>
        <div class="cat-stat"><h2>${avg}</h2><span>${t('cat.avg')}</span></div>`;
}

// ---- category detail selection ----
const catSelect = new Set();  // 存当前分类详情中已选 paths

function updateCatToolbar() {
    // toolbar 内嵌在 cat-header 里；选择数与复制/剪切按钮由 DOM 按 id 查找
    const countEl = $('cat-sel-count');
    if (countEl) {
        countEl.textContent = t('info.selected', { n: catSelect.size });
    }
    const disabled = catSelect.size === 0;
    for (const id of ['btn-cat-copy', 'btn-cat-move']) {
        const el = $(id);
        if (el) el.disabled = disabled;
    }
}

function buildCatHeader(categoryName, imgs) {
    const back = h('button', {
        class: 'secondary hrow-back btn-with-icon',
        type: 'button',
        onclick: () => {
            state.categoryName = null;
            catSelect.clear();
            renderCategoryGrid();
        },
    }, icon('arrow-left'), h('span', { text: t('info.back_cat') }));

    const title = h('h3', {});
    title.append(renderTagName(categoryName));
    title.append(document.createTextNode(` (${imgs.length})`));

    // 右侧：选中徽章 + 多选操作按钮
    const actions = h('div', { class: 'cat-header-actions' },
        h('span', { id: 'cat-sel-count', class: 'mono' }, ''),
        h('button', {
            id: 'btn-cat-select-all',
            type: 'button', class: 'secondary',
            onclick: () => {
                catSelect.clear();
                for (const it of imgs) if (it.path) catSelect.add(it.path);
                renderCategoryGrid();
            },
        }, t('btn.select_all')),
        h('button', {
            id: 'btn-cat-select-none',
            type: 'button', class: 'secondary',
            onclick: () => { catSelect.clear(); renderCategoryGrid(); },
        }, t('btn.select_none')),
        h('button', {
            id: 'btn-cat-copy', type: 'button', class: 'secondary',
            onclick: () => transferSelected('copy'),
        }, t('btn.copy_to')),
        h('button', {
            id: 'btn-cat-move', type: 'button',
            onclick: () => transferSelected('move'),
        }, t('btn.move_to')),
    );

    return h('div', { class: 'cat-header' }, back, title, actions);
}

function renderCategoryGrid() {
    const grid = $('cat-grid');
    grid.innerHTML = '';
    const inDetail = !!state.categoryName;
    const ctl = $('cat-controls');
    if (ctl) ctl.hidden = inDetail;
    const stats = $('cat-stats');
    if (stats) stats.hidden = inDetail;

    if (inDetail) {
        const imgs = state.categories[state.categoryName] || [];
        grid.append(buildCatHeader(state.categoryName, imgs));

        for (const it of imgs) {
            const selected = catSelect.has(it.path);
            const card = h('div', {
                class: 'card-img cat-detail-card' + (selected ? ' selected' : ''),
                'data-path': it.path,
            },
                h('span', {
                    class: 'card-check' + (selected ? ' on' : ''),
                    title: t('btn.select'),
                    onclick: (ev) => {
                        ev.stopPropagation();
                        toggleCatSelect(it.path);
                    },
                }, selected ? '✓' : ''),
                h('div', { class: 'thumb' },
                    h('img', {
                        src: `/api/thumb?path=${encodeURIComponent(it.path)}&size=240`,
                        loading: 'lazy',
                    })),
                h('div', { class: 'card-name mono', text: it.path.split(/[\\/]/).pop() }),
                h('div', { class: 'card-status mono' }, `⭐ ${it.confidence.toFixed(3)}`),
            );
            card.addEventListener('click', () => openDetail(it.path));
            grid.append(card);
        }
        updateCatToolbar();
        refreshIcons();
        return;
    }

    const search = ($('cat-search').value || '').toLowerCase();
    const sort = $('cat-sort').value;
    let entries = Object.entries(state.categories);
    if (search) {
        entries = entries.filter(([n]) =>
            n.toLowerCase().includes(search) ||
            (tagZh(n) || '').toLowerCase().includes(search));
    }
    if (sort === 'name') entries.sort((a, b) => a[0].localeCompare(b[0]));
    else entries.sort((a, b) => b[1].length - a[1].length);

    if (!entries.length) {
        grid.append(h('div', { class: 'empty mono' }, t('info.empty_cat')));
        return;
    }

    for (const [name, items] of entries) {
        const first = items[0];
        const title = h('h4', { class: 'cat-card-title' });
        title.append(icon('tag', 'cat-card-tag-ico'));
        title.append(renderTagName(name));
        grid.append(h('div', {
            class: 'cat-card',
            onclick: () => { state.categoryName = name; catSelect.clear(); renderCategoryGrid(); },
        },
            h('div', { class: 'thumb' },
                h('img', {
                    src: `/api/thumb?path=${encodeURIComponent(first.path)}&size=240`,
                    loading: 'lazy',
                })),
            h('div', { class: 'cat-card-body' },
                title,
                h('div', { class: 'cat-card-meta mono' },
                    t('info.n_images', {
                        n: items.length, c: first.confidence.toFixed(2),
                    }))),
        ));
    }
    refreshIcons();
}

function toggleCatSelect(path) {
    if (catSelect.has(path)) catSelect.delete(path);
    else catSelect.add(path);
    // 只刷这张卡的 class 比整格重建更省事
    const card = document.querySelector(
        `.cat-detail-card[data-path="${CSS.escape(path)}"]`);
    if (card) {
        const on = catSelect.has(path);
        card.classList.toggle('selected', on);
        const chk = card.querySelector('.card-check');
        if (chk) {
            chk.classList.toggle('on', on);
            chk.textContent = on ? '✓' : '';
        }
    }
    updateCatToolbar();
}

async function transferSelected(mode) {
    if (!catSelect.size) return;
    const paths = [...catSelect].filter(p => p);
    openBrowser({
        onPick: async (dest) => {
            const r = await fetch('/api/files/transfer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paths, dest, mode }),
            });
            const d = await r.json();
            if (d.error) { await showAlert(d.error); return; }
            const errN = (d.errors || []).length;
            const key = mode === 'copy' ? 'info.copied_ok' : 'info.moved_ok';
            let msg = t(key, { n: d.done, p: d.dest });
            if (errN) msg += '\n' + t('info.transfer_err', { n: errN });
            await showAlert(msg);
            // 剪切成功后：从 state 中移除这些 path 的对应项
            if (mode === 'move' && d.done > 0) {
                const moved = new Set(paths);
                // 从 categories / files 中移除
                for (const name of Object.keys(state.categories)) {
                    state.categories[name] = state.categories[name]
                        .filter(it => !moved.has(it.path));
                }
                state.files = state.files.filter(f => !moved.has(f.path));
                for (const p of moved) delete state.byKey[p];
                catSelect.clear();
                renderCategoryGrid();
            }
        },
    });
}

// ---- boot ----
document.addEventListener('DOMContentLoaded', async () => {
    // 先恢复语言（无保存时按浏览器语言：zh* → 中文，其他 → 英文），再 applyI18n
    const saved = localStorage.getItem('aict_lang');
    if (saved === 'zh' || saved === 'en') {
        state.lang = saved;
    } else {
        const navLang = (navigator.languages && navigator.languages[0])
            || navigator.language || '';
        state.lang = /^zh\b/i.test(navLang) ? 'zh' : 'en';
    }
    applyI18n();

    await loadTagI18n();
    loadHardware();
    loadModels();
    renderRecentPaths();
    renderGrid();

    $('btn-run').addEventListener('click', runRecognize);
    $('page-size').addEventListener('change', () => { state.page = 1; renderGrid(); });

    $('tab-grid').addEventListener('click', () => switchView('grid'));
    $('tab-category').addEventListener('click', () => {
        switchView('category');
        if (!Object.keys(state.categories).length) refreshCategories();
    });
    $('tab-history').addEventListener('click', () => {
        switchView('history');
        refreshHistory();
    });
    const btnHRefresh = $('btn-history-refresh');
    if (btnHRefresh) btnHRefresh.addEventListener('click', refreshHistory);

    $('btn-save-txt').addEventListener('click', () => runSave('txt'));
    $('btn-save-json').addEventListener('click', () => runSave('json'));
    $('btn-back').addEventListener('click', () => {
        if (state.categoryName) { switchView('category'); return; }
        switchView(state.lastView || 'grid');
    });

    $('btn-categorize').addEventListener('click', refreshCategories);
    $('cat-search').addEventListener('input', renderCategoryGrid);
    $('cat-sort').addEventListener('change', renderCategoryGrid);

    $('btn-lang').addEventListener('click', () => {
        setLang(state.lang === 'zh' ? 'en' : 'zh');
    });
    $('btn-lang').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setLang(state.lang === 'zh' ? 'en' : 'zh');
        }
    });

    initFolderBrowser();
    initDropzone();
    initDialog();
    initAbout();
    refreshIcons();  // 首屏静态 DOM 的图标
});

function initAbout() {
    document.querySelectorAll('.about-row[data-href]').forEach(row => {
        row.addEventListener('click', () => {
            const url = row.getAttribute('data-href');
            if (url) window.open(url, '_blank', 'noopener');
        });
    });
}

// ---- dropzone (page-wide) ----
// 返回 {added, total}：本次新增 / 累计图片数。多次拖放会累加，去重按 (name,size)。
function stageUploadFiles(fileList) {
    const incoming = Array.from(fileList || []).filter(f =>
        f.type.startsWith('image/') ||
        /\.(png|jpe?g|webp|bmp|gif)$/i.test(f.name));
    if (!incoming.length) return { added: 0, total: uploadFiles.length };

    // 切入上传模式：清掉文件夹路径（优先级：文件夹 > 上传）
    $('folder-path').value = '';
    $('scan-info').textContent = '';

    // 如果上一次 state 是文件夹扫描，先清理它的预览，换成上传模式
    if (state.source === 'scan' || state.source === 'history') {
        state.folder = null;
        state.files = [];
        state.byKey = {};
        state.jobId = null;
        uploadFiles = [];
    }
    state.source = 'upload';
    state.historyId = null;

    // 去重追加
    const key = (f) => `${f.name}::${f.size}`;
    const existing = new Set(uploadFiles.map(key));
    let added = 0;
    for (const f of incoming) {
        if (existing.has(key(f))) continue;
        existing.add(key(f));
        uploadFiles.push(f);
        state.files.push({
            path: f.name, name: f.name, size: f.size,
            blobUrl: URL.createObjectURL(f),
        });
        added++;
    }

    state.byKey = {};  // 新增后历史结果失效
    state.jobId = null;
    state.page = 1;
    $('dropzone-count').textContent = t('info.picked', { n: uploadFiles.length });
    switchView('grid');
    renderGrid();
    return { added, total: uploadFiles.length };
}

function initDropzone() {
    const input = $('files');
    const pick = $('btn-pick-files');
    if (pick && input) {
        pick.addEventListener('click', () => input.click());
        input.addEventListener('change', () => {
            const r = stageUploadFiles(input.files);
            if (r.added) askStartRecognize(r.total);
            // 允许再次选择相同文件触发 change
            input.value = '';
        });
    }

    // 全页拖放
    const overlay = $('drop-overlay');
    let dragDepth = 0;
    const hasFiles = (e) =>
        Array.from(e.dataTransfer?.types || []).includes('Files');

    window.addEventListener('dragenter', (e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        dragDepth++;
        overlay.hidden = false;
    });
    window.addEventListener('dragover', (e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    });
    window.addEventListener('dragleave', (e) => {
        if (!hasFiles(e)) return;
        dragDepth = Math.max(0, dragDepth - 1);
        if (dragDepth === 0) overlay.hidden = true;
    });
    window.addEventListener('drop', (e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        dragDepth = 0;
        overlay.hidden = true;
        const files = e.dataTransfer?.files;
        if (!files || !files.length) return;
        const r = stageUploadFiles(files);
        if (r.added) askStartRecognize(r.total);
    });
}

async function askStartRecognize(n) {
    const ok = await showConfirm(t('dlg.start'), t('msg.added', { n }));
    if (ok) runUpload();
}

// ---- dialog (modal alert / confirm) ----
let dialogResolve = null;

function initDialog() {
    const modal = $('dialog-modal');
    modal.addEventListener('click', (e) => {
        if (e.target.id === 'dialog-modal') closeDialog(false);
    });
    document.addEventListener('keydown', (e) => {
        if (modal.hidden) return;
        if (e.key === 'Escape') closeDialog(false);
        else if (e.key === 'Enter') closeDialog(true);
    });
}

function closeDialog(result) {
    const modal = $('dialog-modal');
    modal.hidden = true;
    const r = dialogResolve;
    dialogResolve = null;
    if (r) r(result);
}

function openDialog({ title, body, buttons }) {
    return new Promise((resolve) => {
        dialogResolve = resolve;
        $('dialog-title').textContent = title;
        const b = $('dialog-body');
        b.innerHTML = '';
        // 保留换行
        for (const line of String(body).split('\n')) {
            const div = h('div', {}, line || '\u00a0');
            b.append(div);
        }
        const foot = $('dialog-footer');
        foot.innerHTML = '';
        for (const btn of buttons) {
            foot.append(h('button', {
                class: btn.secondary ? 'secondary' : '',
                type: 'button',
                onclick: () => closeDialog(btn.value),
            }, btn.label));
        }
        $('dialog-modal').hidden = false;
    });
}

function showAlert(message, title) {
    return openDialog({
        title: title || t('dlg.tip'),
        body: message,
        buttons: [{ label: t('btn.ok'), value: true }],
    });
}

function showConfirm(title, message) {
    return openDialog({
        title,
        body: message,
        buttons: [
            { label: t('btn.cancel'), value: false, secondary: true },
            { label: t('btn.ok'), value: true },
        ],
    });
}

// ---- folder browser ----
const browser = {
    current: '', parent: null,
    targetId: null,       // 直接写入某个输入框
    onPick: null,         // 或者回调 (path) => void
};

function openBrowser(opts = {}) {
    // 兼容：传字符串等价于 { targetId: string }
    if (typeof opts === 'string') opts = { targetId: opts };
    browser.targetId = opts.targetId || null;
    browser.onPick = opts.onPick || null;
    const seedId = browser.targetId || 'folder-path';
    const seedEl = $(seedId);
    const cur = seedEl ? seedEl.value.trim() : '';
    $('browser-modal').hidden = false;
    browserLoad(cur || '');
}

function closeBrowser() { $('browser-modal').hidden = true; }

function initFolderBrowser() {
    $('btn-browse').addEventListener('click', () => openBrowser('folder-path'));
    $('browser-close').addEventListener('click', closeBrowser);
    $('browser-cancel').addEventListener('click', closeBrowser);
    $('browser-pick').addEventListener('click', async () => {
        if (!browser.current) { await showAlert(t('msg.pick_folder')); return; }
        if (browser.onPick) {
            const cb = browser.onPick;
            closeBrowser();
            cb(browser.current);
        } else {
            const id = browser.targetId || 'folder-path';
            const el = $(id);
            if (el) el.value = browser.current;
            closeBrowser();
        }
    });
    $('browser-up').addEventListener('click', () => {
        if (browser.parent !== null) browserLoad(browser.parent);
    });
    $('browser-go').addEventListener('click', () => {
        browserLoad($('browser-path').value.trim());
    });
    $('browser-path').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') browserLoad(e.target.value.trim());
    });
    $('browser-modal').addEventListener('click', (e) => {
        if (e.target.id === 'browser-modal') closeBrowser();
    });
}

async function browserLoad(path) {
    const r = await fetch(`/api/browse?path=${encodeURIComponent(path || '')}`);
    const d = await r.json();
    if (!r.ok) { await showAlert(d.error || '无法打开'); return; }
    browser.current = d.path || '';
    browser.parent = d.parent;
    $('browser-path').value = browser.current;
    const list = $('browser-list');
    list.innerHTML = '';
    if (!d.entries.length) {
        list.append(h('div', { class: 'browser-empty mono', text: t('info.empty_dir') }));
    }
    for (const e of d.entries) {
        const row = h('div', {
            class: 'browser-item',
            onclick: () => browserLoad(e.path),
            ondblclick: () => browserLoad(e.path),
        },
            icon('folder', 'browser-icon'),
            h('span', { class: 'browser-name', text: e.name }),
        );
        list.append(row);
    }
    refreshIcons();
}
