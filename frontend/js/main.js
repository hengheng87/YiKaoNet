/** Application bootstrap, Portal-to-Workspace view routing, and reactive render wiring. */

import {
  fetchBlocksCatalog,
  fetchExamDetail,
  fetchExams,
  fetchQuestions,
  isSingleExamOfflineMode,
} from './api.js';
import { initBlockPortal, renderBlockPortal } from './components/blockPortal.js';
import {
  initFilters,
  renderFilterMetadata,
  renderFilterState,
} from './components/filters.js';
import {
  initHeader,
  renderHeaderMetadata,
  renderHeaderState,
} from './components/header.js';
import {
  initModals,
  populateExportModalOptions,
  renderSyncModalState,
} from './components/modals.js';
import { initQuestionList, renderQuestions } from './components/questionList.js';
import {
  initResumeBar,
  renderResumeBarState,
  showInitialResumeBanner,
} from './components/resumeBar.js';
import { showToast } from './components/toast.js';
import {
  initialCloudMergeIfConnected,
  setExamData,
  state,
  subscribe,
} from './store.js';

function buildFallbackBlocksCatalog(exams) {
  const readyBlocks = exams.map((ex, idx) => ({
    slug: ex.slug,
    term: ex.block?.term || 'other',
    examLabel: ex.block?.examLabel || ex.badge || '',
    name: ex.block?.name || ex.title || ex.slug,
    englishName: ex.block?.englishName || ex.badge || '',
    icon: ex.block?.icon || '📚',
    accent: ex.block?.accent || 'indigo',
    order: ex.block?.order ?? idx + 1,
    status: ex.totalQuestions > 0 ? 'ready' : 'planned',
    description: ex.block?.description || ex.subtitle || '',
    sourceHint: ex.source?.name ? `對應知識庫：${ex.source.name}` : '',
    source: ex.source || null,
    subjects: [],
    totalQuestions: ex.totalQuestions || 0,
    uniqueQuestions: ex.uniqueQuestions || 0,
    errataCount: ex.errataCount || 0,
    unitCount: ex.unitCount || 0,
  }));

  const termsByCode = new Map();
  exams.forEach((ex, idx) => {
    const blk = readyBlocks[idx];
    const code = blk.term || 'other';
    if (!termsByCode.has(code)) {
      termsByCode.set(code, {
        code,
        label: ex.block?.termLabel || (code === 'other' ? '整合考題庫' : code),
        shortLabel: ex.block?.termShortLabel || (code === 'other' ? '題庫' : code),
        description: '',
        order: 1,
        readyCount: 0,
        totalCount: 0,
        blocks: [],
      });
    }
    const sec = termsByCode.get(code);
    sec.blocks.push(blk);
    sec.totalCount += 1;
    if (blk.status === 'ready') sec.readyCount += 1;
  });

  const terms = Array.from(termsByCode.values());
  return {
    version: '1.0.0',
    title: '易考網 YiKao 整合考系統題庫',
    subtitle: '依年級學期與器官系統 Block 分類，點選系統即可進入共筆單元作題畫面',
    readyBlocks: readyBlocks.filter((b) => b.status === 'ready').length,
    plannedBlocks: readyBlocks.filter((b) => b.status !== 'ready').length,
    totalBlocks: readyBlocks.length,
    totalQuestions: readyBlocks.reduce((acc, b) => acc + b.totalQuestions, 0),
    totalUnits: readyBlocks.reduce((acc, b) => acc + b.unitCount, 0),
    terms,
  };
}

function parseRequestedExamSlug() {
  const hash = window.location.hash || '';
  if (hash.startsWith('#')) {
    const raw = hash.slice(1);
    const params = new URLSearchParams(raw);
    const hashSlug = params.get('exam');
    if (hashSlug) return hashSlug.trim();
    const pathMatch = raw.match(/^\/?exam\/([A-Za-z0-9-]+)$/);
    if (pathMatch) return pathMatch[1];
  }
  const searchSlug = new URLSearchParams(window.location.search).get('exam');
  return searchSlug ? searchSlug.trim() : '';
}

function syncUrlHashForExam(slug, { replace = false } = {}) {
  if (isSingleExamOfflineMode()) return;
  const method = replace ? 'replaceState' : 'pushState';
  if (slug) {
    const targetHash = `#exam=${encodeURIComponent(slug)}`;
    if (window.location.hash === targetHash) return;
    try {
      window.history[method](null, '', targetHash);
    } catch (_) {
      window.location.hash = targetHash;
    }
  } else if (window.location.hash) {
    const cleanUrl = `${window.location.pathname}${window.location.search}`;
    try {
      window.history[method](null, '', cleanUrl);
    } catch (_) {
      window.location.hash = '';
    }
  }
}

function applyViewVisibility() {
  const portalEl = document.getElementById('portalView');
  const quizEl = document.getElementById('quizWorkspaceView');
  const isPortal = state.currentView === 'portal';

  if (portalEl) portalEl.classList.toggle('hidden', !isPortal);
  if (quizEl) quizEl.classList.toggle('hidden', isPortal);

  if (isPortal) {
    const quizHeader = document.getElementById('quizHeader');
    if (quizHeader) quizHeader.classList.remove('header-scroll-hidden');
    const resumeBarEl = document.getElementById('resumeFloatingBar');
    if (resumeBarEl) resumeBarEl.classList.add('bar-hidden');
    const catalogTitle = state.blocksCatalog?.title || '易考網 YiKao';
    document.title = `${catalogTitle}｜系統總覽`;
  }
}

function showPortalView({ updateUrl = true, replaceUrl = false } = {}) {
  state.currentView = 'portal';
  if (updateUrl) {
    syncUrlHashForExam('', { replace: replaceUrl });
  }
  applyViewVisibility();
  renderBlockPortal();
  window.scrollTo({ top: 0, behavior: 'auto' });
}

async function loadExam(slug) {
  const [detail, questionRes] = await Promise.all([
    fetchExamDetail(slug),
    fetchQuestions(slug),
  ]);
  setExamData(detail, questionRes.questions);
  renderHeaderMetadata();
  renderFilterMetadata();
  populateExportModalOptions();
  renderSyncModalState();
  showInitialResumeBanner();
  await initialCloudMergeIfConnected();
  showInitialResumeBanner();
}

async function enterExamView(slug, { updateUrl = true, replaceUrl = false } = {}) {
  const targetExam = state.exams.find((e) => e.slug === slug);
  if (!targetExam || !targetExam.totalQuestions) {
    showToast(`找不到已開放作題的系統「${slug}」，已返回系統總覽`);
    showPortalView({ updateUrl: true, replaceUrl: true });
    return;
  }

  state.currentView = 'exam';
  if (updateUrl) {
    syncUrlHashForExam(slug, { replace: replaceUrl });
  }
  applyViewVisibility();
  window.scrollTo({ top: 0, behavior: 'auto' });

  try {
    await loadExam(slug);
  } catch (err) {
    document.getElementById('examTitle').textContent = '題庫載入失敗';
    document.getElementById('examSubtitle').textContent = err.message;
    showToast(`載入失敗：${err.message}`);
  }
}

function handleRouteChange() {
  if (isSingleExamOfflineMode()) return;
  const requestedSlug = parseRequestedExamSlug();
  if (requestedSlug) {
    if (state.currentView !== 'exam' || state.activeExamSlug !== requestedSlug) {
      enterExamView(requestedSlug, { updateUrl: false });
    }
  } else if (state.currentView !== 'portal') {
    showPortalView({ updateUrl: false });
  }
}

async function boot() {
  initBlockPortal((slug) => enterExamView(slug, { updateUrl: true }));
  initHeader(
    (slug) => enterExamView(slug, { updateUrl: true }),
    () => showPortalView({ updateUrl: true })
  );
  initFilters();
  initQuestionList();
  initResumeBar();
  initModals();

  subscribe(() => {
    if (state.currentView === 'portal') {
      renderBlockPortal();
      return;
    }
    if (state.examDetail) {
      renderHeaderState();
      renderFilterState();
      renderQuestions();
      renderResumeBarState();
    }
  });

  try {
    const [exams, catalog] = await Promise.all([
      fetchExams(),
      fetchBlocksCatalog().catch(() => null),
    ]);
    state.exams = exams || [];
    state.blocksCatalog = catalog || buildFallbackBlocksCatalog(state.exams);

    if (isSingleExamOfflineMode() && state.exams.length) {
      await enterExamView(state.exams[0].slug, { updateUrl: false });
      return;
    }

    const requestedSlug = parseRequestedExamSlug();
    if (requestedSlug) {
      await enterExamView(requestedSlug, { updateUrl: false });
    } else {
      showPortalView({ updateUrl: false });
    }

    window.addEventListener('popstate', handleRouteChange);
    window.addEventListener('hashchange', handleRouteChange);
  } catch (err) {
    document.getElementById('portalSiteSubtitle').textContent = `載入失敗：${err.message}`;
    showToast(`載入失敗：${err.message}`);
  }
}

document.addEventListener('DOMContentLoaded', boot);
