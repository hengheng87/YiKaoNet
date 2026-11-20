/** Score accuracy analytics, multi-dimensional breakdown bars, and weak-unit diagnosis view. */

import { isSingleExamOfflineMode } from '../api.js';
import { escapeHtml } from '../markdown.js';
import { isAnswerCorrect, notify, state } from '../store.js';
import { showToast } from './toast.js';

const ANALYTICS_TIER_META = {
  critical: {
    label: '🔴 急需加強',
    badgeClass: 'analytics-tier-critical',
    cardClass: 'analytics-weak-critical',
    rank: 0,
  },
  warn: {
    label: '🟠 建議加強',
    badgeClass: 'analytics-tier-warn',
    cardClass: 'analytics-weak-warn',
    rank: 1,
  },
  unstarted: {
    label: '🔵 尚未作答',
    badgeClass: 'analytics-tier-unstarted',
    cardClass: '',
    rank: 2,
  },
  lowcov: {
    label: '🟡 進度偏低',
    badgeClass: 'analytics-tier-lowcov',
    cardClass: '',
    rank: 3,
  },
  good: {
    label: '🟢 掌握良好',
    badgeClass: 'analytics-tier-good',
    cardClass: '',
    rank: 4,
  },
};

let analyticsCallbacks = {
  onBackToExam: null,
  onBackToPortal: null,
  onSwitchExam: null,
  onJumpToQuiz: null,
};

function analyticsCalcRates(total, correct, wrong) {
  const answered = correct + wrong;
  const unanswered = Math.max(0, total - answered);
  const accuracy = answered > 0 ? Math.round((correct / answered) * 100) : null;
  const coverage = total > 0 ? Math.round((answered / total) * 100) : 0;
  const correctBarPct = total > 0 ? (correct / total) * 100 : 0;
  const wrongBarPct = total > 0 ? (wrong / total) * 100 : 0;
  return {
    total,
    answered,
    correct,
    wrong,
    unanswered,
    accuracy,
    coverage,
    correctBarPct,
    wrongBarPct,
  };
}

function analyticsClassifyUnit(unitStat) {
  const { total, answered, wrong, accuracy, coverage } = unitStat;
  if (total === 0) {
    return {
      tier: 'unstarted',
      reasonText: '目前篩選條件下無題目',
      priorityScore: 9999,
    };
  }
  if (answered === 0) {
    return {
      tier: 'unstarted',
      reasonText: `尚未開始練習（共 ${total} 題）`,
      priorityScore: 2000 + Math.max(0, 500 - total),
    };
  }
  if (accuracy < 60 || (wrong >= 3 && accuracy < 70)) {
    return {
      tier: 'critical',
      reasonText: `正確率僅 ${accuracy}%（已答 ${answered}/${total} 題，錯 ${wrong} 題）`,
      priorityScore: accuracy * 10 - wrong,
    };
  }
  if (accuracy < 80) {
    return {
      tier: 'warn',
      reasonText: `正確率 ${accuracy}%（已答 ${answered}/${total} 題，錯 ${wrong} 題）`,
      priorityScore: 1000 + accuracy * 10 - wrong,
    };
  }
  if (coverage < 30) {
    return {
      tier: 'lowcov',
      reasonText: `正確率 ${accuracy}%，但僅練習 ${answered}/${total} 題（覆蓋率 ${coverage}%）`,
      priorityScore: 3000 + coverage * 10,
    };
  }
  return {
    tier: 'good',
    reasonText: `正確率 ${accuracy}%，已完成 ${answered}/${total} 題（錯 ${wrong} 題）`,
    priorityScore: 4000 + (100 - accuracy),
  };
}

function analyticsComputeReport() {
  const exam = state.examDetail;
  if (!exam) return null;

  const unitMetaByCode = new Map();
  (exam.units || []).forEach((u, idx) => {
    unitMetaByCode.set(u.unitCode, { ...u, sortOrder: idx });
  });

  const poolQuestions = [];
  let totalStarred = 0;
  let totalCorrect = 0;
  let totalWrong = 0;

  const sessionAgg = new Map();
  (exam.sessions || []).forEach((s) => {
    sessionAgg.set(s.code, {
      code: s.code,
      label: s.label,
      emoji: s.emoji || '',
      description: s.description || '',
      total: 0,
      correct: 0,
      wrong: 0,
    });
  });

  const subjectAgg = new Map();
  (exam.subjects || []).forEach((sub) => {
    subjectAgg.set(sub.code, {
      code: sub.code,
      label: sub.label,
      emoji: sub.emoji || '',
      profs: sub.profs || '',
      total: 0,
      correct: 0,
      wrong: 0,
    });
  });

  const yearAgg = new Map();
  (exam.yearGroups || []).forEach((y) => {
    yearAgg.set(y.code, {
      code: y.code,
      label: y.label,
      total: 0,
      correct: 0,
      wrong: 0,
    });
  });

  const unitAgg = new Map();
  (exam.units || []).forEach((u, idx) => {
    if (state.analyticsHideOutOfScope && u.isOutOfScope) return;
    unitAgg.set(u.unitCode, {
      unitCode: u.unitCode,
      shortLabel: u.shortLabel || u.unitTitle,
      unitTitle: u.unitTitle || u.shortLabel,
      session: u.session,
      subject: u.subject,
      subjectTitle: u.subjectTitle,
      prof: u.prof,
      isOutOfScope: !!u.isOutOfScope,
      highlight: !!u.highlight,
      sortOrder: idx,
      total: 0,
      correct: 0,
      wrong: 0,
      starred: 0,
    });
  });

  state.questions.forEach((q) => {
    if (state.analyticsHideOutOfScope && state.outOfScopeUnits.has(q.unitCode)) {
      return;
    }
    if (state.analyticsHideCrossDup && q.isCrossDup) {
      return;
    }
    poolQuestions.push(q);

    const chosen = state.userAnswers[q.id];
    const isStarred = !!state.starred[q.id];
    if (isStarred) totalStarred += 1;

    const ok = chosen ? isAnswerCorrect(q, chosen) : false;
    const err = Boolean(chosen && !ok);
    if (ok) totalCorrect += 1;
    if (err) totalWrong += 1;

    const sItem = sessionAgg.get(q.session);
    if (sItem) {
      sItem.total += 1;
      if (ok) sItem.correct += 1;
      if (err) sItem.wrong += 1;
    }

    const subItem = subjectAgg.get(q.subject);
    if (subItem) {
      subItem.total += 1;
      if (ok) subItem.correct += 1;
      if (err) subItem.wrong += 1;
    }

    const yItem = yearAgg.get(q.yearGroup);
    if (yItem) {
      yItem.total += 1;
      if (ok) yItem.correct += 1;
      if (err) yItem.wrong += 1;
    }

    const uItem = unitAgg.get(q.unitCode);
    if (uItem) {
      uItem.total += 1;
      if (ok) uItem.correct += 1;
      if (err) uItem.wrong += 1;
      if (isStarred) uItem.starred += 1;
    }
  });

  const overall = {
    ...analyticsCalcRates(poolQuestions.length, totalCorrect, totalWrong),
    starred: totalStarred,
  };

  const sessions = Array.from(sessionAgg.values()).map((s) => ({
    ...s,
    ...analyticsCalcRates(s.total, s.correct, s.wrong),
  }));
  const subjects = Array.from(subjectAgg.values()).map((sub) => ({
    ...sub,
    ...analyticsCalcRates(sub.total, sub.correct, sub.wrong),
  }));
  const yearGroups = Array.from(yearAgg.values()).map((y) => ({
    ...y,
    ...analyticsCalcRates(y.total, y.correct, y.wrong),
  }));

  const units = [];
  unitAgg.forEach((u) => {
    if (u.total === 0) return;
    const rates = analyticsCalcRates(u.total, u.correct, u.wrong);
    const diag = analyticsClassifyUnit(rates);
    units.push({
      ...u,
      ...rates,
      ...diag,
    });
  });

  const weakUnits = units
    .filter((u) => u.tier === 'critical' || u.tier === 'warn')
    .sort((a, b) => a.priorityScore - b.priorityScore);

  const unstartedOrLowUnits = units
    .filter((u) => u.tier === 'unstarted' || u.tier === 'lowcov')
    .sort((a, b) => a.coverage - b.coverage || b.total - a.total);

  return {
    exam,
    poolQuestions,
    overall,
    sessions,
    subjects,
    yearGroups,
    units,
    weakUnits,
    unstartedOrLowUnits,
  };
}

function analyticsAccuracyTextClass(accuracy) {
  if (accuracy === null) return 'text-slate-500';
  if (accuracy >= 80) return 'text-emerald-700';
  if (accuracy >= 60) return 'text-amber-700';
  return 'text-rose-700';
}

function analyticsRenderStackedBar(item, { actionAttr = '', subtitle = '' } = {}) {
  const accText = item.accuracy === null ? '尚無紀錄' : `${item.accuracy}%`;
  const accClass = analyticsAccuracyTextClass(item.accuracy);
  const tag = actionAttr ? 'button' : 'div';
  const typeAttr = actionAttr ? `type="button" ${actionAttr}` : '';

  return `
    <${tag} ${typeAttr} class="analytics-bar-row">
      <div class="analytics-bar-row-top">
        <div class="flex items-center gap-1.5 min-w-0">
          <span class="text-xs font-bold text-slate-900">${escapeHtml(item.emoji ? `${item.emoji} ` : '')}${escapeHtml(item.label)}</span>
          ${subtitle ? `<span class="text-[11px] text-slate-500">${escapeHtml(subtitle)}</span>` : ''}
        </div>
        <div class="flex items-center gap-2 text-[11px] shrink-0">
          <span class="text-slate-500">已答 ${item.answered}/${item.total}</span>
          <span class="text-emerald-700 font-semibold">✓${item.correct}</span>
          <span class="text-rose-700 font-semibold">✗${item.wrong}</span>
          <strong class="${accClass}">${accText}</strong>
        </div>
      </div>
      <div class="analytics-bar-track">
        <div class="analytics-bar-correct" style="width: ${item.correctBarPct.toFixed(1)}%"></div>
        <div class="analytics-bar-wrong" style="width: ${item.wrongBarPct.toFixed(1)}%"></div>
      </div>
    </${tag}>
  `;
}

function analyticsRenderWeakCard(u) {
  const meta = ANALYTICS_TIER_META[u.tier] || ANALYTICS_TIER_META.warn;
  return `
    <div class="analytics-weak-card ${meta.cardClass}">
      <div class="space-y-2">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 space-y-0.5">
            <div class="text-xs font-bold text-slate-900">${escapeHtml(u.shortLabel)}</div>
            <div class="text-[11px] text-slate-600">${escapeHtml(u.subjectTitle)}・${escapeHtml(u.prof)}</div>
          </div>
          <span class="analytics-tier-badge ${meta.badgeClass}">${meta.label}</span>
        </div>

        <div class="text-xs font-semibold text-slate-800">${escapeHtml(u.reasonText)}</div>

        <div class="space-y-1">
          <div class="analytics-bar-track">
            <div class="analytics-bar-correct" style="width: ${u.correctBarPct.toFixed(1)}%"></div>
            <div class="analytics-bar-wrong" style="width: ${u.wrongBarPct.toFixed(1)}%"></div>
          </div>
          <div class="flex items-center justify-between text-[11px] text-slate-500">
            <span>✓ 對 ${u.correct} ｜ ✗ 錯 ${u.wrong} ｜ ⏳ 未答 ${u.unanswered}</span>
            <span>覆蓋率 ${u.coverage}%</span>
          </div>
        </div>
      </div>

      <div class="flex items-center flex-wrap gap-1.5 pt-1">
        ${
          u.wrong > 0
            ? `<button type="button" data-analytics-jump="unit-wrong" data-unit-code="${escapeHtml(u.unitCode)}" class="analytics-action-btn analytics-action-btn-danger">❌ 複習錯題 (${u.wrong})</button>`
            : ''
        }
        ${
          u.unanswered > 0
            ? `<button type="button" data-analytics-jump="unit-unanswered" data-unit-code="${escapeHtml(u.unitCode)}" class="analytics-action-btn">⏳ 補做未答 (${u.unanswered})</button>`
            : ''
        }
        <button type="button" data-analytics-jump="unit-all" data-unit-code="${escapeHtml(u.unitCode)}" class="analytics-action-btn analytics-action-btn-primary">📝 練習全單元</button>
      </div>
    </div>
  `;
}

function analyticsSortUnits(units, sortMode) {
  const list = [...units];
  if (sortMode === 'acc-asc') {
    list.sort((a, b) => {
      if (a.accuracy === null && b.accuracy === null) return a.sortOrder - b.sortOrder;
      if (a.accuracy === null) return 1;
      if (b.accuracy === null) return -1;
      return a.accuracy - b.accuracy || b.wrong - a.wrong || a.sortOrder - b.sortOrder;
    });
  } else if (sortMode === 'wrong-desc') {
    list.sort((a, b) => b.wrong - a.wrong || a.priorityScore - b.priorityScore || a.sortOrder - b.sortOrder);
  } else if (sortMode === 'cov-asc') {
    list.sort((a, b) => a.coverage - b.coverage || b.total - a.total || a.sortOrder - b.sortOrder);
  } else if (sortMode === 'order') {
    list.sort((a, b) => a.sortOrder - b.sortOrder);
  } else {
    list.sort((a, b) => a.priorityScore - b.priorityScore || a.sortOrder - b.sortOrder);
  }
  return list;
}

function analyticsRenderUnitRow(u) {
  const meta = ANALYTICS_TIER_META[u.tier] || ANALYTICS_TIER_META.unstarted;
  const accText = u.accuracy === null ? '—' : `${u.accuracy}%`;
  const accClass = analyticsAccuracyTextClass(u.accuracy);
  const oosTag = u.isOutOfScope
    ? `<span class="px-1.5 py-0.5 rounded text-[11px] font-semibold bg-amber-100 text-amber-900">補充單元</span>`
    : '';

  return `
    <div class="analytics-unit-row">
      <div class="analytics-unit-row-main">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="analytics-tier-badge ${meta.badgeClass}">${meta.label}</span>
          <strong class="text-sm font-bold text-slate-900">${escapeHtml(u.shortLabel)}</strong>
          ${oosTag}
        </div>
        <div class="text-xs text-slate-500">
          ${escapeHtml(u.subjectTitle)}（${escapeHtml(u.prof)}）｜${escapeHtml(u.reasonText)}
        </div>
      </div>

      <div class="analytics-unit-row-stats">
        <div class="flex items-center justify-between text-[11px]">
          <span class="text-slate-600">已答 ${u.answered}/${u.total} (✓${u.correct} ✗${u.wrong})</span>
          <strong class="${accClass}">正確率 ${accText}</strong>
        </div>
        <div class="analytics-bar-track">
          <div class="analytics-bar-correct" style="width: ${u.correctBarPct.toFixed(1)}%"></div>
          <div class="analytics-bar-wrong" style="width: ${u.wrongBarPct.toFixed(1)}%"></div>
        </div>
      </div>

      <div class="analytics-unit-row-actions">
        ${
          u.wrong > 0
            ? `<button type="button" data-analytics-jump="unit-wrong" data-unit-code="${escapeHtml(u.unitCode)}" class="analytics-action-btn analytics-action-btn-danger">❌ 錯題 (${u.wrong})</button>`
            : ''
        }
        ${
          u.unanswered > 0 && u.answered > 0
            ? `<button type="button" data-analytics-jump="unit-unanswered" data-unit-code="${escapeHtml(u.unitCode)}" class="analytics-action-btn">⏳ 未答 (${u.unanswered})</button>`
            : ''
        }
        <button type="button" data-analytics-jump="unit-all" data-unit-code="${escapeHtml(u.unitCode)}" class="analytics-action-btn analytics-action-btn-primary">📝 練習</button>
      </div>
    </div>
  `;
}

export function renderAnalyticsView() {
  if (state.currentView !== 'analytics') return;
  const report = analyticsComputeReport();
  if (!report) return;

  const { exam, overall, sessions, subjects, yearGroups, units, weakUnits, unstartedOrLowUnits } =
    report;

  document.title = `作答分析｜${exam.title}｜易考網 YiKao`;

  const backPortalBtn = document.getElementById('analyticsBackToPortalBtn');
  if (backPortalBtn) {
    backPortalBtn.classList.toggle('hidden', isSingleExamOfflineMode());
  }

  const titleEl = document.getElementById('analyticsExamTitle');
  const subtitleEl = document.getElementById('analyticsExamSubtitle');
  if (titleEl) {
    titleEl.textContent = `${exam.title} — 作答分析與弱點診斷`;
  }
  if (subtitleEl) {
    const scopeNotes = [];
    if (state.analyticsHideCrossDup) scopeNotes.push('已排除跨共筆重複題');
    if (state.analyticsHideOutOfScope) scopeNotes.push('已隱藏非本屆補充單元');
    const suffix = scopeNotes.length ? `（${scopeNotes.join('、')}）` : '（包含全部共筆單元與題目）';
    subtitleEl.textContent = `目前分析範圍共 ${units.length} 個單元、${overall.total} 題 ${suffix}`;
  }

  const examSelector = document.getElementById('analyticsExamSelector');
  if (examSelector) {
    const readyExams = (state.exams || []).filter((e) => e.totalQuestions > 0);
    if (readyExams.length > 1) {
      examSelector.innerHTML = readyExams
        .map(
          (ex) =>
            `<option value="${escapeHtml(ex.slug)}" ${ex.slug === exam.slug ? 'selected' : ''}>${escapeHtml(ex.title)} (${ex.totalQuestions})</option>`
        )
        .join('');
      examSelector.classList.remove('hidden');
    } else {
      examSelector.classList.add('hidden');
    }
  }

  const toggleDedupBtn = document.getElementById('analyticsToggleDedupBtn');
  if (toggleDedupBtn) {
    toggleDedupBtn.className = state.analyticsHideCrossDup
      ? 'px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow-sm transition'
      : 'px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition';
    toggleDedupBtn.textContent = state.analyticsHideCrossDup ? '✓ 已排除跨共筆重複' : '排除跨共筆重複題';
  }

  const toggleOosBtn = document.getElementById('analyticsToggleOosBtn');
  if (toggleOosBtn) {
    toggleOosBtn.className = state.analyticsHideOutOfScope
      ? 'px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-amber-600 text-white shadow-sm transition'
      : 'px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition';
    toggleOosBtn.textContent = state.analyticsHideOutOfScope ? '✓ 已隱藏補充單元' : '隱藏非本屆補充';
  }

  const examNoticeEl = document.getElementById('analyticsExamModeNotice');
  if (examNoticeEl) {
    examNoticeEl.classList.toggle('hidden', !(state.mode === 'exam' && !state.examSubmitted));
  }

  // 1. Summary KPI Cards
  const summaryEl = document.getElementById('analyticsSummaryCards');
  if (summaryEl) {
    const accDisplay = overall.accuracy === null ? '—' : `${overall.accuracy}%`;
    const accColor = analyticsAccuracyTextClass(overall.accuracy);
    summaryEl.innerHTML = `
      <button type="button" data-analytics-jump="unanswered" class="analytics-kpi-card">
        <div class="analytics-kpi-label">整體作答進度</div>
        <div class="analytics-kpi-value">${overall.answered} / ${overall.total}</div>
        <div class="analytics-kpi-sub">完成覆蓋率 ${overall.coverage}% ・ 點擊補做未答題 (${overall.unanswered})</div>
      </button>

      <div class="analytics-kpi-card">
        <div class="analytics-kpi-label">整體正確率</div>
        <div class="analytics-kpi-value ${accColor}">${accDisplay}</div>
        <div class="analytics-kpi-sub">✓ 答對 ${overall.correct} 題 ｜ ✗ 答錯 ${overall.wrong} 題</div>
      </div>

      <div class="analytics-kpi-card">
        <div class="analytics-kpi-label">需優先加強單元</div>
        <div class="analytics-kpi-value ${weakUnits.length > 0 ? 'text-rose-700' : 'text-emerald-700'}">${weakUnits.length} / ${units.length}</div>
        <div class="analytics-kpi-sub">尚未練習 ${units.filter((u) => u.tier === 'unstarted').length} 單元 ・ 建議先補強高錯誤率共筆</div>
      </div>

      <button type="button" data-analytics-jump="wrong-or-starred" class="analytics-kpi-card">
        <div class="analytics-kpi-label">錯題本與收藏</div>
        <div class="analytics-kpi-value text-rose-700">${overall.wrong} <span class="text-sm font-medium text-amber-600">/ ⭐ ${overall.starred}</span></div>
        <div class="analytics-kpi-sub">${overall.wrong > 0 ? '點擊立即進入錯題本複習 →' : '目前尚無錯題，點擊檢視星號收藏 →'}</div>
      </button>
    `;
  }

  // 2. Weak Units Recommendation
  const weakActionsEl = document.getElementById('analyticsWeakHeaderActions');
  const weakBoxEl = document.getElementById('analyticsWeakUnitsBox');
  if (weakActionsEl && weakBoxEl) {
    if (overall.answered === 0) {
      weakActionsEl.innerHTML = '';
      weakBoxEl.innerHTML = `
        <div class="bg-slate-50 border border-slate-200 rounded-xl p-5 text-center space-y-3">
          <div class="text-2xl">📝</div>
          <div class="text-sm font-bold text-slate-900">目前尚未有任何作答紀錄</div>
          <p class="text-xs text-slate-600">先完成部分題目或來一回合隨機抽測後，系統就會自動統計各科與各共筆單元的正確率，並標出您最需要加強的弱點範圍！</p>
          <div class="flex items-center justify-center gap-2 flex-wrap">
            <button type="button" data-analytics-jump="all" class="analytics-action-btn analytics-action-btn-primary">開始進入題庫作題</button>
            <button type="button" data-analytics-jump="random-25" class="analytics-action-btn">🎲 隨機抽 25 題快速檢測</button>
          </div>
        </div>
      `;
    } else if (weakUnits.length > 0) {
      const hasDrillPool = weakUnits.length > 0;
      weakActionsEl.innerHTML = `
        ${
          overall.wrong > 0
            ? `<button type="button" data-analytics-jump="wrong" class="analytics-action-btn analytics-action-btn-danger">❌ 複習全部錯題 (${overall.wrong})</button>`
            : ''
        }
        ${
          hasDrillPool
            ? `<button type="button" data-analytics-jump="weak-drill" class="analytics-action-btn analytics-action-btn-primary">🎯 針對弱點單元抽 25 題特訓</button>`
            : ''
        }
      `;
      const shownWeak = weakUnits.slice(0, 6);
      const lowCovNote =
        unstartedOrLowUnits.length > 0
          ? `<div class="mt-3 text-xs text-slate-600 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 flex items-center justify-between gap-2 flex-wrap">
               <span>💡 另有 <strong>${unstartedOrLowUnits.length}</strong> 個共筆單元尚未作答或覆蓋率未達 30%（可在下方清單篩選「未答與低進度」補齊）。</span>
               <button type="button" data-analytics-filter-tier="unstarted" class="analytics-action-btn">檢視待練習單元</button>
             </div>`
          : '';
      weakBoxEl.innerHTML = `
        <div class="analytics-weak-grid">
          ${shownWeak.map(analyticsRenderWeakCard).join('')}
        </div>
        ${weakUnits.length > 6 ? `<div class="mt-2 text-[11px] text-slate-500">以上顯示優先度最高的 ${shownWeak.length} 個弱點單元，其餘請參考下方完整共筆清單。</div>` : ''}
        ${lowCovNote}
      `;
    } else {
      weakActionsEl.innerHTML =
        unstartedOrLowUnits.length > 0
          ? `<button type="button" data-analytics-jump="weak-drill" class="analytics-action-btn analytics-action-btn-primary">🎯 補齊低覆蓋率單元抽 25 題</button>`
          : '';
      const unstartedHtml =
        unstartedOrLowUnits.length > 0
          ? `<div class="mt-3">
               <div class="text-xs font-bold text-slate-800 mb-2">📌 下一步建議補齊的單元（尚未作答或練習題數偏少）：</div>
               <div class="analytics-weak-grid">
                 ${unstartedOrLowUnits.slice(0, 4).map(analyticsRenderWeakCard).join('')}
               </div>
             </div>`
          : '';
      weakBoxEl.innerHTML = `
        <div class="bg-emerald-50 border border-emerald-200 rounded-xl p-4 space-y-1">
          <div class="text-sm font-bold text-emerald-900">🎉 目前已練習單元的正確率皆達 80% 以上，表現非常穩健！</div>
          <p class="text-xs text-emerald-800">若還有尚未作答或覆蓋率較低的單元，建議在考前逐一補齊以消除知識盲區。</p>
        </div>
        ${unstartedHtml}
      `;
    }
  }

  // 3. Breakdowns
  const sessionListEl = document.getElementById('analyticsSessionList');
  if (sessionListEl) {
    sessionListEl.innerHTML = sessions
      .filter((s) => s.total > 0)
      .map((s) =>
        analyticsRenderStackedBar(s, {
          subtitle: s.description,
          actionAttr: `data-analytics-jump="session" data-session-code="${escapeHtml(s.code)}"`,
        })
      )
      .join('');
  }

  const subjectListEl = document.getElementById('analyticsSubjectList');
  if (subjectListEl) {
    subjectListEl.innerHTML = subjects
      .filter((sub) => sub.total > 0)
      .map((sub) =>
        analyticsRenderStackedBar(sub, {
          subtitle: sub.profs,
          actionAttr: `data-analytics-jump="subject" data-subject-code="${escapeHtml(sub.code)}"`,
        })
      )
      .join('');
  }

  const yearListEl = document.getElementById('analyticsYearList');
  if (yearListEl) {
    yearListEl.innerHTML = yearGroups
      .filter((y) => y.total > 0)
      .map((y) =>
        analyticsRenderStackedBar(y, {
          actionAttr: `data-analytics-jump="year" data-year-code="${escapeHtml(y.code)}"`,
        })
      )
      .join('');
  }

  // 4. Unit List + Filter Tabs + Sort
  const tierCounts = {
    ALL: units.length,
    critical: units.filter((u) => u.tier === 'critical').length,
    warn: units.filter((u) => u.tier === 'warn').length,
    unstarted: units.filter((u) => u.tier === 'unstarted' || u.tier === 'lowcov').length,
    good: units.filter((u) => u.tier === 'good').length,
  };

  const tierTabsEl = document.getElementById('analyticsTierTabs');
  if (tierTabsEl) {
    const tabs = [
      { code: 'ALL', label: `全部單元 (${tierCounts.ALL})` },
      { code: 'critical', label: `🔴 急需加強 (${tierCounts.critical})` },
      { code: 'warn', label: `🟠 建議加強 (${tierCounts.warn})` },
      { code: 'unstarted', label: `🔵 未答與低進度 (${tierCounts.unstarted})` },
      { code: 'good', label: `🟢 掌握良好 (${tierCounts.good})` },
    ];
    tierTabsEl.innerHTML = tabs
      .map((t) => {
        const active = state.analyticsTierFilter === t.code;
        return `<button type="button" data-analytics-tier="${t.code}" class="${
          active
            ? 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow-sm transition'
            : 'px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition'
        }">${t.label}</button>`;
      })
      .join('');
  }

  const sortSelect = document.getElementById('analyticsUnitSort');
  if (sortSelect && sortSelect.value !== state.analyticsUnitSort) {
    sortSelect.value = state.analyticsUnitSort;
  }

  const filteredUnits = units.filter((u) => {
    if (state.analyticsTierFilter === 'ALL') return true;
    if (state.analyticsTierFilter === 'unstarted') {
      return u.tier === 'unstarted' || u.tier === 'lowcov';
    }
    return u.tier === state.analyticsTierFilter;
  });

  const sortedUnits = analyticsSortUnits(filteredUnits, state.analyticsUnitSort);
  const unitListEl = document.getElementById('analyticsUnitList');
  if (unitListEl) {
    if (!sortedUnits.length) {
      unitListEl.innerHTML = `
        <div class="bg-slate-50 border border-slate-200 rounded-xl p-6 text-center text-xs text-slate-500">
          目前分級篩選條件下沒有對應的共筆單元，請切換上方分級頁籤檢視全部單元。
        </div>
      `;
    } else {
      unitListEl.innerHTML = sortedUnits.map(analyticsRenderUnitRow).join('');
    }
  }
}

function analyticsTriggerWeakDrill() {
  const report = analyticsComputeReport();
  if (!report || !analyticsCallbacks.onJumpToQuiz) return;

  let targetUnitCodes = new Set(report.weakUnits.map((u) => u.unitCode));
  let modeDesc = '弱點單元';
  if (targetUnitCodes.size === 0) {
    targetUnitCodes = new Set(report.unstartedOrLowUnits.map((u) => u.unitCode));
    modeDesc = '尚未完成單元';
  }
  if (targetUnitCodes.size === 0) {
    targetUnitCodes = new Set(report.units.map((u) => u.unitCode));
    modeDesc = '全卷題庫';
  }

  const priorityPool = [];
  const secondaryPool = [];
  report.poolQuestions.forEach((q) => {
    if (!targetUnitCodes.has(q.unitCode)) return;
    const chosen = state.userAnswers[q.id];
    const isWrong = chosen && !isAnswerCorrect(q, chosen);
    if (!chosen || isWrong) {
      priorityPool.push(q);
    } else {
      secondaryPool.push(q);
    }
  });

  const shuffle = (arr) => {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  };

  shuffle(priorityPool);
  shuffle(secondaryPool);
  const combined = [...priorityPool, ...secondaryPool].slice(0, 25);
  if (!combined.length) {
    showToast('目前篩選範圍內沒有可供抽測的題目');
    return;
  }

  analyticsCallbacks.onJumpToQuiz({
    slug: report.exam.slug,
    unitFilter: 'ALL',
    statusFilter: 'ALL',
    yearFilter: 'ALL',
    randomIds: new Set(combined.map((q) => q.id)),
    hideCrossDup: state.analyticsHideCrossDup,
    toastMessage: `🎯 已從${modeDesc}抽出 ${combined.length} 題進行弱點特訓！`,
  });
}

function analyticsJumpToQuiz(btn) {
  const action = btn.getAttribute('data-analytics-jump');
  const slug = state.activeExamSlug;
  if (!slug || !analyticsCallbacks.onJumpToQuiz) return;

  const base = {
    slug,
    unitFilter: 'ALL',
    statusFilter: 'ALL',
    yearFilter: 'ALL',
    randomIds: null,
    hideCrossDup: state.analyticsHideCrossDup,
  };

  if (action === 'all') {
    analyticsCallbacks.onJumpToQuiz({ ...base });
  } else if (action === 'wrong') {
    analyticsCallbacks.onJumpToQuiz({
      ...base,
      statusFilter: 'WRONG',
      toastMessage: '已篩選目前考科的所有答錯題目（錯題本）',
    });
  } else if (action === 'wrong-or-starred') {
    const hasWrong = Object.keys(state.userAnswers).some((qid) => {
      const q = state.questionById.get(qid);
      return q && !isAnswerCorrect(q, state.userAnswers[qid]);
    });
    analyticsCallbacks.onJumpToQuiz({
      ...base,
      statusFilter: hasWrong ? 'WRONG' : 'STARRED',
      toastMessage: hasWrong ? '已切換至錯題本複習' : '已切換至⭐星號收藏題庫',
    });
  } else if (action === 'unanswered') {
    analyticsCallbacks.onJumpToQuiz({
      ...base,
      statusFilter: 'UNANSWERED',
      toastMessage: '已篩選尚未作答的題目',
    });
  } else if (action === 'random-25') {
    const pool = state.questions.filter((q) => !q.isCrossDup);
    for (let i = pool.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    const picked = pool.slice(0, Math.min(25, pool.length));
    analyticsCallbacks.onJumpToQuiz({
      ...base,
      randomIds: new Set(picked.map((q) => q.id)),
      toastMessage: `🎲 已隨機抽出 ${picked.length} 題進行快速實力檢測！`,
    });
  } else if (action === 'weak-drill') {
    analyticsTriggerWeakDrill();
  } else if (action === 'session') {
    const code = btn.getAttribute('data-session-code');
    analyticsCallbacks.onJumpToQuiz({ ...base, unitFilter: `SESSION_${code}` });
  } else if (action === 'subject') {
    const code = btn.getAttribute('data-subject-code');
    analyticsCallbacks.onJumpToQuiz({ ...base, unitFilter: `SUBJ_${code}` });
  } else if (action === 'year') {
    const code = btn.getAttribute('data-year-code');
    analyticsCallbacks.onJumpToQuiz({ ...base, yearFilter: code });
  } else if (action === 'unit-wrong') {
    const uc = btn.getAttribute('data-unit-code');
    analyticsCallbacks.onJumpToQuiz({ ...base, unitFilter: uc, statusFilter: 'WRONG' });
  } else if (action === 'unit-unanswered') {
    const uc = btn.getAttribute('data-unit-code');
    analyticsCallbacks.onJumpToQuiz({ ...base, unitFilter: uc, statusFilter: 'UNANSWERED' });
  } else if (action === 'unit-all') {
    const uc = btn.getAttribute('data-unit-code');
    analyticsCallbacks.onJumpToQuiz({ ...base, unitFilter: uc });
  }
}

export function initAnalyticsView({
  onBackToExam,
  onBackToPortal,
  onSwitchExam,
  onJumpToQuiz,
}) {
  analyticsCallbacks = {
    onBackToExam,
    onBackToPortal,
    onSwitchExam,
    onJumpToQuiz,
  };

  const backExamBtn = document.getElementById('analyticsBackToExamBtn');
  const backPortalBtn = document.getElementById('analyticsBackToPortalBtn');
  const examSelector = document.getElementById('analyticsExamSelector');
  const toggleDedupBtn = document.getElementById('analyticsToggleDedupBtn');
  const toggleOosBtn = document.getElementById('analyticsToggleOosBtn');
  const unitSort = document.getElementById('analyticsUnitSort');
  const mainEl = document.getElementById('analyticsMain');

  if (backExamBtn) {
    backExamBtn.addEventListener('click', () => {
      if (analyticsCallbacks.onBackToExam && state.activeExamSlug) {
        analyticsCallbacks.onBackToExam(state.activeExamSlug);
      }
    });
  }

  if (backPortalBtn) {
    backPortalBtn.addEventListener('click', () => {
      if (analyticsCallbacks.onBackToPortal) {
        analyticsCallbacks.onBackToPortal();
      }
    });
  }

  if (examSelector) {
    examSelector.addEventListener('change', (e) => {
      const nextSlug = e.target.value;
      if (nextSlug && nextSlug !== state.activeExamSlug && analyticsCallbacks.onSwitchExam) {
        analyticsCallbacks.onSwitchExam(nextSlug);
      }
    });
  }

  if (toggleDedupBtn) {
    toggleDedupBtn.addEventListener('click', () => {
      state.analyticsHideCrossDup = !state.analyticsHideCrossDup;
      notify();
    });
  }

  if (toggleOosBtn) {
    toggleOosBtn.addEventListener('click', () => {
      state.analyticsHideOutOfScope = !state.analyticsHideOutOfScope;
      notify();
    });
  }

  if (unitSort) {
    unitSort.addEventListener('change', (e) => {
      state.analyticsUnitSort = e.target.value;
      notify();
    });
  }

  if (mainEl) {
    mainEl.addEventListener('click', (e) => {
      const tierBtn = e.target.closest('button[data-analytics-tier]');
      if (tierBtn) {
        state.analyticsTierFilter = tierBtn.getAttribute('data-analytics-tier') || 'ALL';
        notify();
        return;
      }

      const filterTierBtn = e.target.closest('button[data-analytics-filter-tier]');
      if (filterTierBtn) {
        state.analyticsTierFilter =
          filterTierBtn.getAttribute('data-analytics-filter-tier') || 'ALL';
        notify();
        document.getElementById('analyticsUnitsSection')?.scrollIntoView({ behavior: 'smooth' });
        return;
      }

      const jumpBtn = e.target.closest('button[data-analytics-jump]');
      if (jumpBtn) {
        analyticsJumpToQuiz(jumpBtn);
      }
    });
  }
}
