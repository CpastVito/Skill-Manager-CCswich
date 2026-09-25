// Skill 分类管理器 — 前端逻辑
let state = null;
let selected = null;

const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function api(path, body) {
  try {
    const res = await fetch(path, body !== undefined
      ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      : undefined);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return await res.json();
  } catch (e) {
    return { error: '无法连接服务端，请确认程序已启动（' + (e.message || e) + '）' };
  }
}

let toastTimer = null;
function toast(msg, type = 'info') {
  const el = $('toast');
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  el.className = 'toast show toast-' + type;
  el.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span>${esc(msg)}</span>`;
  clearTimeout(toastTimer);
  const dur = type === 'error' ? 5000 : 3200;
  toastTimer = setTimeout(() => el.classList.remove('show'), dur);
}

function catSkills(catKey) {
  if (catKey === '◆ 未分类') return state.skills.filter((s) => !s.cat);
  return state.skills.filter((s) => s.cat === catKey);
}

function catAllOn(catKey, agent) {
  const list = catSkills(catKey);
  return list.length > 0 && list.every((s) => s.pending[agent]);
}

// ---------- 渲染 ----------

function render() {
  renderSidebar();
  renderContent();
  $('dirty-badge').classList.toggle('hidden', !state.dirty);
  $('btn-apply').disabled = !state.dirty;
}

function renderSidebar() {
  const list = $('cat-list');
  list.innerHTML = '';
  const cats = [...state.categories];
  if (state.uncategorized.length) cats.push('◆ 未分类');

  for (const c of cats) {
    const item = document.createElement('div');
    item.className = 'cat-item' + (c === selected ? ' active' : '') + (c === '◆ 未分类' ? ' special' : '');
    const list0 = catSkills(c);
    const onN = list0.filter((s) => Object.values(s.pending).every(Boolean)).length;
    const delBtn = c === '◆ 未分类'
      ? ''
      : `<button class="cat-del" data-cat="${esc(c)}" title="删除分类">✕</button>`;
    item.innerHTML =
      `<div class="cat-info">
         <div class="cat-name">${esc(c)}</div>
         <div class="cat-meta">${list0.length} 个 skill · 全开 ${onN}</div>
       </div>
       ${delBtn}
       <div class="cat-agent-dots">
         ${state.agents.map((a) =>
           `<span class="cat-dot ${catAllOn(c, a.key) ? 'on' : ''}" data-agent="${a.key}" title="${esc(a.label)}"></span>`
         ).join('')}
       </div>`;
    item.addEventListener('click', (e) => {
      if (e.target.classList.contains('cat-dot')) {
        const agent = e.target.dataset.agent;
        toggleCategory(c, agent, !catAllOn(c, agent));
        return;
      }
      if (e.target.classList.contains('cat-del')) {
        delCat(e.target.dataset.cat);
        return;
      }
      selected = c;
      render();
    });
    list.appendChild(item);
  }
}

function renderContent() {
  $('cat-title').textContent = selected || 'Skill 分类管理器';
  const list0 = selected ? catSkills(selected) : [];
  $('cat-sub').textContent = selected
    ? (selected === '◆ 未分类'
        ? '以下 skill 尚未归类，请为它们选择类别'
        : `共 ${list0.length} 个 skill · 开关控制各 Agent 启用 · 下拉框调整分类`)
    : '在左侧选择分类，查看并管理其中的 skill';

  // 分类头部：每个 Agent 一个整类一键开关
  $('cat-toggles').innerHTML = selected
    ? state.agents.map((a) =>
        `<div class="agent-toggle">
           <span class="agent-label">${esc(a.short)}</span>
           <label class="switch">
             <input type="checkbox" data-cat-agent="${a.key}" ${catAllOn(selected, a.key) ? 'checked' : ''}>
             <span class="slider"></span>
           </label>
         </div>`).join('')
    : '';
  $('cat-toggles').querySelectorAll('input[data-cat-agent]').forEach((inp) => {
    inp.addEventListener('change', () =>
      toggleCategory(selected, inp.dataset.catAgent, inp.checked));
  });

  const listEl = $('skill-list');
  listEl.innerHTML = '';
  if (!selected) {
    listEl.innerHTML = '<div class="empty">← 在左侧选择一个分类</div>';
    return;
  }
  if (!list0.length) {
    listEl.innerHTML = '<div class="empty">该分类暂无 skill</div>';
    return;
  }
  for (const s of list0) listEl.appendChild(renderSkill(s));
}

function renderSkill(s) {
  const card = document.createElement('div');
  card.className = 'skill-card';
  const isUncat = !s.cat;
  // 已分类：把「当前类别」放在首位并选中，其余类别依次排列，最后提供「设为未分类」与「新建类别」
  const catOptions = isUncat
    ? ['（选择分类）', ...state.categories, '＋ 新建类别…']
    : [s.cat, ...state.categories.filter((c) => c !== s.cat), '设为未分类', '＋ 新建类别…'];
  const curCat = s.cat || '（选择分类）';
  card.innerHTML =
    `<div class="skill-top">
       <div class="skill-info">
         <div class="skill-name">${esc(s.name)}</div>
         <div class="skill-dir">${esc(s.dir)}</div>
         ${s.desc ? `<div class="skill-desc">${esc(s.desc)}</div>` : ''}
       </div>
       <select class="skill-cat-select">
         ${catOptions.map((o) => `<option ${o === curCat ? 'selected' : ''}>${esc(o)}</option>`).join('')}
       </select>
     </div>
     <div class="skill-agents">
       ${state.agents.map((a) =>
         `<div class="agent-toggle">
            <span class="agent-label">${esc(a.short)}</span>
            <label class="switch">
              <input type="checkbox" data-skill="${esc(s.dir)}" data-agent="${a.key}" ${s.pending[a.key] ? 'checked' : ''}>
              <span class="slider"></span>
            </label>
          </div>`).join('')}
     </div>`;

  card.querySelectorAll('input[data-skill]').forEach((inp) => {
    inp.addEventListener('change', () =>
      toggleSkill(s.dir, inp.dataset.agent, inp.checked));
  });
  card.querySelector('.skill-cat-select').addEventListener('change', (e) => {
    const v = e.target.value;
    if (v === '＋ 新建类别…') {
      const name = prompt('请输入新类别名称：');
      if (!name || !name.trim()) return;
      newCat(name.trim()).then(() => assign(s.dir, name.trim()));
      return;
    }
    if (v === '设为未分类') { assign(s.dir, ''); return; }
    if (v === '（选择分类）') return;
    assign(s.dir, v);
  });
  return card;
}

// ---------- 操作 ----------

async function refresh(data) {
  state = data;
  render();
}

async function toggleSkill(dir, agent, on) {
  const r = await api('/api/toggle_skill', { dir, agent, on });
  if (r.error) { toast(r.error, 'error'); return; }
  refresh(r);
}

async function toggleCategory(cat, agent, on) {
  const r = await api('/api/toggle_category', { category: cat, agent, on });
  if (r.error) { toast(r.error, 'error'); return; }
  refresh(r);
}

async function assign(dir, category) {
  const r = await api('/api/assign', { dir, category: category || '' });
  if (r.error) { toast(r.error, 'error'); return; }
  refresh(r);
  toast(category ? `已把 ${dir} 归入「${category}」` : `已将 ${dir} 移出分类`, 'success');
}

async function newCat(name) {
  const r = await api('/api/newcat', { name });
  if (r.error) { toast(r.error, 'error'); return false; }
  refresh(r);
  selected = name;
  render();
  toast(`已新建分类「${name}」`, 'success');
  return true;
}

async function delCat(category) {
  if (!confirm(`确定删除分类「${category}」？\n其中的 skill 将移回「未分类」，不会被删除。`)) return;
  const r = await api('/api/delcat', { category });
  if (r.error) { toast(r.error, 'error'); return; }
  if (selected === category) selected = null;
  refresh(r);
  toast(`已删除分类「${category}」`, 'success');
}

async function apply() {
  const btn = $('btn-apply');
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = '准备中…';
  const r = await api('/api/apply', {});
  if (r.error) { toast(r.error, 'error'); btn.textContent = '应用修改'; btn.disabled = false; return; }
  if (r.started === false) { toast(r.message || '没有需要修改的项', 'info'); btn.textContent = '应用修改'; btn.disabled = false; return; }
  await pollApply(r.total);
  btn.textContent = '应用修改';
  btn.disabled = false;
}

function sleep(ms) { return new Promise((res) => setTimeout(res, ms)); }

async function pollApply(total) {
  const btn = $('btn-apply');
  for (;;) {
    await sleep(600);
    const st = await api('/api/apply_status');
    if (st.error) { toast(st.error, 'error'); return; }
    if (st.running) {
      btn.textContent = `应用中 ${st.done}/${st.total}`;
      continue;
    }
    if (st.finished) {
      const fresh = await api('/api/state');
      if (!fresh.error) refresh(fresh);
      if (st.errors && st.errors.length) {
        toast(`应用完成：启用 ${st.on}、禁用 ${st.off}，${st.errors.length} 个失败`, 'error');
        alert('部分失败（共 ' + st.errors.length + ' 个）：\n' + st.errors.join('\n'));
      } else {
        toast(`应用完成：已启用 ${st.on} 项、禁用 ${st.off} 项，请重新打开 cc-switch 查看`, 'success');
      }
      return;
    }
  }
}

// ---------- 弹窗 ----------

function showModal(title, bodyText) {
  $('modal-title').textContent = title;
  $('modal-body').textContent = bodyText;
  $('modal').classList.remove('hidden');
  $('modal-refresh').style.display = title === '路径诊断' ? '' : 'none';
}

function closeModal() { $('modal').classList.add('hidden'); }

// ---------- 初始化 ----------

function safeRefresh(r) {
  if (r.error) { toast(r.error, 'error'); return false; }
  refresh(r);
  return true;
}

function bindToolbar() {
  $('btn-scan').onclick = async () => {
    const r = await api('/api/scan', {});
    if (safeRefresh(r)) toast('已重新扫描数据库', 'success');
  };
  $('btn-newcat').onclick = $('btn-newcat2').onclick = () => {
    const name = prompt('请输入新类别名称：');
    if (name && name.trim()) newCat(name.trim());
  };
  $('btn-paths').onclick = async () => {
    const r = await api('/api/paths');
    if (r.error) { toast(r.error, 'error'); return; }
    showModal('路径诊断', r.report);
  };
  $('btn-all-on').onclick = async () => { safeRefresh(await api('/api/set_all', { on: true })); };
  $('btn-all-off').onclick = async () => { safeRefresh(await api('/api/set_all', { on: false })); };
  $('btn-reset').onclick = async () => {
    if (safeRefresh(await api('/api/reset', {}))) toast('已放弃修改', 'info');
  };
  $('btn-apply').onclick = apply;

  // AI 智能分类
  $('btn-ai').onclick = openAiModal;
  $('ai-close').onclick = closeAiModal;
  $('ai-cancel').onclick = closeAiModal;
  $('ai-run').onclick = runAiClassify;
  $('ai-apply').onclick = applyAiResult;
  $('ai-modal').addEventListener('click', (e) => { if (e.target === $('ai-modal')) closeAiModal(); });
  document.querySelectorAll('input[name="ai-scope"]').forEach((inp) => {
    inp.addEventListener('change', updateAiScope);
  });

  $('modal-close').onclick = closeModal;
  $('modal-ok').onclick = closeModal;
  $('modal-refresh').onclick = async () => {
    const r = await api('/api/paths');
    if (r.error) { toast(r.error, 'error'); return; }
    $('modal-body').textContent = r.report;
    toast('已重新探测路径', 'success');
  };
  $('modal').addEventListener('click', (e) => { if (e.target === $('modal')) closeModal(); });
}

// ---------- AI 智能分类 ----------

let aiResultPayload = null;

async function openAiModal() {
  $('ai-modal').classList.remove('hidden');
  $('ai-result').classList.add('hidden');
  $('ai-apply').classList.add('hidden');
  $('ai-instruction').value = '';
  aiResultPayload = null;

  // 显示当前可用的 AI 接口信息，并填充模型下拉
  const cfg = await api('/api/ai_config');
  const box = $('ai-config');
  const modelSel = $('ai-model');
  modelSel.innerHTML = '';
  if (cfg.available) {
    box.innerHTML = `<div class="ai-config-ok">已检测到 AI 接口：<b>${esc(cfg.model)}</b>（${esc(cfg.auth_style)} · ${esc(cfg.base_url)}）</div>`;
    const models = cfg.models || [cfg.model];
    for (const m of models) {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      if (m === cfg.model) opt.selected = true;
      modelSel.appendChild(opt);
    }
  } else {
    box.innerHTML = `<div class="ai-config-err">⚠️ 未在 cc-switch 中找到可用的 AI 接口。请先在 cc-switch 配置一个 OpenAI/Anthropic 兼容的 Provider（如 DeepSeek）。</div>`;
  }

  // 填充分类多选框（用于「指定分类」）
  const picker = $('ai-cat-picker');
  picker.innerHTML = '';
  for (const c of (state.categories || [])) {
    const lab = document.createElement('label');
    lab.className = 'radio';
    lab.innerHTML = `<input type="checkbox" name="ai-cat" value="${esc(c)}"> ${esc(c)}`;
    picker.appendChild(lab);
  }

  // 重置范围为默认
  document.querySelector('input[name="ai-scope"][value="uncategorized"]').checked = true;
  updateAiScope();
}

function updateAiScope() {
  const scope = aiScopeValue();
  $('ai-cat-picker').classList.toggle('hidden', scope !== 'selected');
}

function closeAiModal() { $('ai-modal').classList.add('hidden'); }

function aiScopeValue() {
  const sel = document.querySelector('input[name="ai-scope"]:checked');
  return sel ? sel.value : 'uncategorized';
}

function aiSelectedCats() {
  return [...document.querySelectorAll('input[name="ai-cat"]:checked')].map((c) => c.value);
}

async function runAiClassify() {
  const btn = $('ai-run');
  const resultBox = $('ai-result');
  const scope = aiScopeValue();
  const instruction = $('ai-instruction').value.trim();
  const model = $('ai-model').value;

  btn.disabled = true;
  btn.textContent = 'AI 分类中…';
  resultBox.classList.remove('hidden');
  resultBox.innerHTML = '<div class="ai-loading">正在调用大模型分析 skill…</div>';
  $('ai-apply').classList.add('hidden');

  const body = { scope, instruction, model };
  if (scope === 'current') body.category = selected;
  if (scope === 'selected') {
    const cats = aiSelectedCats();
    if (!cats.length) {
      resultBox.innerHTML = '<div class="ai-error">请至少勾选一个分类</div>';
      btn.disabled = false;
      btn.textContent = '开始分类';
      return;
    }
    body.categories = cats;
  }

  const r = await api('/api/ai_classify', body);
  btn.disabled = false;
  btn.textContent = '开始分类';

  if (r.error) {
    resultBox.innerHTML = `<div class="ai-error">${esc(r.error)}</div>`;
    return;
  }

  aiResultPayload = r;
  // 展示分类方案预览（不写数据，等用户确认）
  const preview = r.preview || [];
  const created = r.created_categories || [];
  let html = `<div class="ai-ok">✓ AI 已生成分类方案，共 <b>${r.applied || preview.length}</b> 个 skill`;
  if (created.length) {
    html += `，将新建 ${created.length} 个类别：${created.map(esc).join('、')}`;
  }
  html += `。</div>`;
  html += `<div class="ai-note">以下为预览，尚未修改任何数据。请核对后点「确认应用」。</div>`;
  // 预览表格
  html += '<table class="ai-table"><thead><tr><th>Skill</th><th>原分类</th><th>→ 新分类</th></tr></thead><tbody>';
  for (const p of preview) {
    html += `<tr><td class="ai-dir">${esc(p.name)}<span class="ai-dir-sub">${esc(p.dir)}</span></td>`
      + `<td>${esc(p.from || '未分类')}</td>`
      + `<td class="ai-to">${esc(p.to)}</td></tr>`;
  }
  html += '</tbody></table>';
  resultBox.innerHTML = html;
  $('ai-apply').classList.remove('hidden');
}

async function applyAiResult() {
  if (!aiResultPayload) return;
  const btn = $('ai-apply');
  btn.disabled = true;
  btn.textContent = '应用中…';
  const r = await api('/api/ai_apply', {});
  if (r.error) {
    toast(r.error, 'error');
    btn.disabled = false;
    btn.textContent = '确认应用';
    return;
  }
  refresh(r);
  closeAiModal();
  toast(`已应用 AI 分类：归类 ${r.ai ? r.ai.applied : 0} 个 skill`, 'success');
}

(async function init() {
  state = await api('/api/state');
  if (state.error) {
    document.body.innerHTML = '<div class="empty">无法连接服务端，请确认已运行「技能分类管理器.bat」。</div>';
    return;
  }
  // 默认选中第一个真实分类（而非「◆ 未分类」），让用户一进来就看到原本的类别
  if (state.categories.length) selected = state.categories[0];
  else if (state.uncategorized && state.uncategorized.length) selected = '◆ 未分类';
  bindToolbar();
  render();
})();
