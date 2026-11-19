/** Dynamic filter panel: sessions, subjects, units, search, year, status, dedup, random quiz. */

import { escapeHtml } from '../markdown.js';
import { notify, state, toggleAllExplanations } from '../store.js';
import { showToast } from './toast.js';

function getDefaultUnitTabClass(unitCode, examDetail) {
  if (unitCode === 'ALL' || unitCode.startsWith('SESSION_')) {
    return 'unit-tab px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition';
  }
  if (unitCode.startsWith('SUBJ_')) {
    return 'unit-tab px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition';
  }
  if (unitCode === 'OUT_OF_SCOPE') {
    return 'unit-tab px-2 py-1 rounded-md text-[11px] font-semibold bg-amber-100 border border-amber-300 text-amber-900 hover:bg-amber-200 transition';
  }
  const unitMeta = (examDetail?.units || []).find((u) => u.unitCode === unitCode);
  if (unitMeta?.highlight) {
    return 'unit-tab px-2.5 py-1 rounded-md text-[11px] font-bold bg-indigo-50 border border-indigo-300 text-indigo-800 hover:bg-indigo-100 transition';
  }
  if (unitMeta?.isOutOfScope) {
    return 'unit-tab px-2 py-1 rounded-md text-[11px] font-medium bg-amber-50 border border-amber-200 text-amber-800 hover:bg-amber-100 transition';
  }
  return 'unit-tab px-2 py-1 rounded-md text-[11px] font-medium bg-slate-50 border border-slate-200 text-slate-700 hover:bg-slate-100 transition';
}

export function renderFilterMetadata() {
  const exam = state.examDetail;
  if (!exam) return;

  const macroRow = document.getElementById('macroTabsRow');
  const sessionBtns = exam.sessions.map(
    (s) =>
      `<button type="button" data-unit="SESSION_${escapeHtml(s.code)}" class="${getDefaultUnitTabClass(`SESSION_${s.code}`, exam)}">${escapeHtml(s.emoji)} ${escapeHtml(s.label)}全 (${s.questionCount})</button>`
  );
  const subjectBtns = exam.subjects.map(
    (sub) =>
      `<button type="button" data-unit="SUBJ_${escapeHtml(sub.code)}" class="${getDefaultUnitTabClass(`SUBJ_${sub.code}`, exam)}">${escapeHtml(sub.emoji)} ${escapeHtml(sub.label)} (${sub.questionCount})</button>`
  );

  macroRow.innerHTML = [
    `<button type="button" data-unit="ALL" class="${getDefaultUnitTabClass('ALL', exam)}">全部題庫 (${exam.totalQuestions})</button>`,
    ...sessionBtns,
    `<span class="text-slate-300 mx-0.5 hidden sm:inline">|</span>`,
    ...subjectBtns,
  ].join('');

  const unitRow = document.getElementById('unitTabsRow');
  const regularUnits = exam.units.filter((u) => !u.isOutOfScope);
  const outUnits = exam.units.filter((u) => u.isOutOfScope);

  const regularHtml = regularUnits.map(
    (u) =>
      `<button type="button" data-unit="${escapeHtml(u.unitCode)}" class="${getDefaultUnitTabClass(u.unitCode, exam)}">${escapeHtml(u.shortLabel)} (${u.questionCount})</button>`
  );

  const outHtml = outUnits.length
    ? [
        `<button type="button" data-unit="OUT_OF_SCOPE" class="${getDefaultUnitTabClass('OUT_OF_SCOPE', exam)}">📚 非本屆範圍／歷屆補充全 (${exam.outOfScopeCount})</button>`,
        ...outUnits.map(
          (u) =>
            `<button type="button" data-unit="${escapeHtml(u.unitCode)}" class="${getDefaultUnitTabClass(u.unitCode, exam)}">${escapeHtml(u.shortLabel)} (${u.questionCount})</button>`
        ),
      ]
    : [];

  unitRow.innerHTML = [
    `<span class="text-[11px] font-semibold text-slate-400 mr-1">共筆單元：</span>`,
    ...regularHtml,
    ...outHtml,
  ].join('');

  const yearSel = document.getElementById('yearFilter');
  yearSel.innerHTML = [
    `<option value="ALL">📅 全部年份</option>`,
    ...exam.yearGroups.map(
      (y) => `<option value="${escapeHtml(y.code)}">${escapeHtml(y.label)}</option>`
    ),
  ].join('');

  const errataOpt = document.getElementById('statusErrataOption');
  if (errataOpt) {
    errataOpt.textContent = `⚠️ 申覆多解／送分／爭議題 (${exam.errataCount} 題)`;
  }

  document.getElementById('searchInput').value = '';
  document.getElementById('clearSearchBtn').classList.add('hidden');
  document.getElementById('statusFilter').value = 'ALL';

  renderFilterState();
}

export function renderFilterState() {
  const exam = state.examDetail;
  if (!exam) return;

  document.querySelectorAll('.unit-tab').forEach((btn) => {
    const u = btn.getAttribute('data-unit');
    if (u === state.unitFilter && !state.randomIds) {
      btn.className =
        'unit-tab px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow-sm transition';
    } else {
      btn.className = getDefaultUnitTabClass(u, exam);
    }
  });

  const yearSel = document.getElementById('yearFilter');
  if (yearSel.value !== state.yearFilter) yearSel.value = state.yearFilter;

  const statusSel = document.getElementById('statusFilter');
  if (statusSel.value !== state.statusFilter) statusSel.value = state.statusFilter;

  const searchInput = document.getElementById('searchInput');
  const clearSearchBtn = document.getElementById('clearSearchBtn');
  if (searchInput.value !== state.searchQuery) searchInput.value = state.searchQuery;
  clearSearchBtn.classList.toggle('hidden', !state.searchQuery);

  const toggleDedupBtn = document.getElementById('toggleDedupBtn');
  if (state.hideCrossDup) {
    toggleDedupBtn.className =
      'px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow-sm transition';
    toggleDedupBtn.textContent = `✓ 已隱藏重複 (${exam.uniqueQuestions}題)`;
  } else {
    toggleDedupBtn.className =
      'px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition';
    toggleDedupBtn.textContent = '隱藏跨共筆重複';
  }

  const toggleAllExplBtn = document.getElementById('toggleAllExplBtn');
  toggleAllExplBtn.textContent = state.isAllExplExpanded ? '收合全部詳解' : '展開全部詳解';

  const dedupBadge = document.getElementById('dedupBadge');
  dedupBadge.textContent = `已隱藏跨共筆重複題（精簡 ${exam.uniqueQuestions} 題）`;
  dedupBadge.classList.toggle('hidden', !state.hideCrossDup);

  const randomBadge = document.getElementById('randomFilterBadge');
  randomBadge.classList.toggle('hidden', !state.randomIds);
}

export function initFilters() {
  document.getElementById('unitTabsContainer').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-unit]');
    if (!btn) return;
    state.unitFilter = btn.getAttribute('data-unit');
    state.randomIds = null;
    notify();
  });

  const searchInput = document.getElementById('searchInput');
  const clearSearchBtn = document.getElementById('clearSearchBtn');
  searchInput.addEventListener('input', () => {
    state.searchQuery = searchInput.value;
    notify();
  });
  clearSearchBtn.addEventListener('click', () => {
    state.searchQuery = '';
    searchInput.value = '';
    notify();
  });

  document.getElementById('yearFilter').addEventListener('change', (e) => {
    state.yearFilter = e.target.value;
    notify();
  });

  document.getElementById('statusFilter').addEventListener('change', (e) => {
    state.statusFilter = e.target.value;
    notify();
  });

  document.getElementById('toggleDedupBtn').addEventListener('click', () => {
    const exam = state.examDetail;
    state.hideCrossDup = !state.hideCrossDup;
    if (exam) {
      if (state.hideCrossDup) {
        const dupCount = exam.totalQuestions - exam.uniqueQuestions;
        showToast(
          `已隱藏跨共筆重複收錄的 ${dupCount} 題，目前顯示 ${exam.uniqueQuestions} 道獨立考題！`
        );
      } else {
        showToast(`已顯示全部 ${exam.totalQuestions} 道考題！`);
      }
    }
    notify();
  });

  document.getElementById('toggleAllExplBtn').addEventListener('click', () => {
    toggleAllExplanations();
  });

  document.getElementById('randomQuizBtn').addEventListener('click', () => {
    const pool = state.questions.filter((q) => !q.isCrossDup);
    for (let i = pool.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    const count = Math.min(25, pool.length);
    state.randomIds = new Set(pool.slice(0, count).map((q) => q.id));
    state.unitFilter = 'ALL';
    state.yearFilter = 'ALL';
    state.statusFilter = 'ALL';
    showToast(`🎲 已隨機抽出 ${count} 道不重複整合考考古題！`);
    notify();
  });

  document.getElementById('exitRandomBtn').addEventListener('click', () => {
    state.randomIds = null;
    notify();
  });
}
