/** Application bootstrap, Portal / Quiz / Analytics view routing, and reactive render wiring. */

import {
  fetchBlocksCatalog,
  fetchExamDetail,
  fetchExams,
  fetchQuestions,
  isSingleExamOfflineMode,
} from './api.js';
import { initAnalyticsView, renderAnalyticsView } from './components/analytics.js';
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
  getSavedActiveExamSlug,
  initialCloudMergeIfConnected,
  notify,
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

function parseRequestedRoute() {
  const hash = window.location.hash || '';
  if (hash.startsWith('#')) {
    const raw = hash.slice(1);
    const params = new URLSearchParams(raw);
    if (params.has('analytics')) {
      return { view: 'analytics', slug: (params.get('analytics') || '').trim() };
    }
    if (params.has('exam')) {
      return { view: 'exam', slug: (params.get('exam') || '').trim() };
    }
    const analyticsPathMatch = raw.match(/^\/?analytics(?:\/([A-Za-z0-9-]+))?$/);
    if (analyticsPathMatch) {
      return { view: 'analytics', slug: analyticsPathMatch[1] || '' };
    }
    const examPathMatch = raw.match(/^\/?exam\/([A-Za-z0-9-]+)$/);
    if (examPathMatch) {
      return { view: 'exam', slug: examPathMatch[1] };
    }
  }

  const search = new URLSearchParams(window.location.search);
  const viewParam = (search.get('view') || '').trim();
  const examParam = (search.get('exam') || '').trim();
  if (viewParam === 'analytics') {
    return { view: 'analytics', slug: examParam };
  }
  if (examParam) {
    return { view: 'exam', slug: examParam };
  }
  return { view: 'portal', slug: '' };
}

function syncUrlForRoute(view, slug = '', { replace = false } = {}) {
  if (isSingleExamOfflineMode()) return;
  const method = replace ? 'replaceState' : 'pushState';

  let targetHash = '';
  if (view === 'exam' && slug) {
    targetHash = `#exam=${encodeURIComponent(slug)}`;
  } else if (view === 'analytics' && slug) {
    targetHash = `#analytics=${encodeURIComponent(slug)}`;
  }

  if (targetHash) {
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
  const analyticsEl = document.getElementById('analyticsView');

  if (portalEl) portalEl.classList.toggle('hidden', state.currentView !== 'portal');
  if (quizEl) quizEl.classList.toggle('hidden', state.currentView !== 'exam');
  if (analyticsEl) analyticsEl.classList.toggle('hidden', state.currentView !== 'analytics');

  if (state.currentView !== 'exam') {
    const quizHeader = document.getElementById('quizHeader');
    if (quizHeader) quizHeader.classList.remove('header-scroll-hidden');
    const resumeBarEl = document.getElementById('resumeFloatingBar');
    if (resumeBarEl) resumeBarEl.classList.add('bar-hidden');
  }

  if (state.currentView === 'portal') {
    const catalogTitle = state.blocksCatalog?.title || '易考網 YiKao';
    document.title = `${catalogTitle}｜系統總覽`;
  }
}

function resolveDefaultReadySlug(preferredSlug = '') {
  const readyExams = (state.exams || []).filter((e) => e.totalQuestions > 0);
  if (!readyExams.length) return '';

  const candidates = [
    preferredSlug,
    state.activeExamSlug,
    getSavedActiveExamSlug(),
    readyExams[0].slug,
  ];
  for (const slug of candidates) {
    if (slug && readyExams.some((e) => e.slug === slug)) {
      return slug;
    }
  }
  return readyExams[0].slug;
}

function showPortalView({ updateUrl = true, replaceUrl = false } = {}) {
  state.currentView = 'portal';
  if (updateUrl) {
    syncUrlForRoute('portal', '', { replace: replaceUrl });
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
  if (state.currentView === 'exam') {
    showInitialResumeBanner();
  }
  await initialCloudMergeIfConnected();
  if (state.currentView === 'exam') {
    showInitialResumeBanner();
  }
}

async function enterExamView(
  slug,
  { updateUrl = true, replaceUrl = false, forceReload = false } = {}
) {
  const targetExam = state.exams.find((e) => e.slug === slug);
  if (!targetExam || !targetExam.totalQuestions) {
    showToast(`找不到已開放作題的系統「${slug}」，已返回系統總覽`);
    showPortalView({ updateUrl: true, replaceUrl: true });
    return;
  }

  const alreadyLoaded =
    !forceReload &&
    state.activeExamSlug === slug &&
    state.examDetail &&
    state.questions.length > 0;

  state.currentView = 'exam';
  if (updateUrl) {
    syncUrlForRoute('exam', slug, { replace: replaceUrl });
  }
  applyViewVisibility();
  window.scrollTo({ top: 0, behavior: 'auto' });

  if (alreadyLoaded) {
    renderHeaderMetadata();
    notify();
    showInitialResumeBanner();
    return;
  }

  try {
    await loadExam(slug);
  } catch (err) {
    document.getElementById('examTitle').textContent = '題庫載入失敗';
    document.getElementById('examSubtitle').textContent = err.message;
    showToast(`載入失敗：${err.message}`);
  }
}

async function enterAnalyticsView(slug = '', { updateUrl = true, replaceUrl = false } = {}) {
  const resolvedSlug = resolveDefaultReadySlug(slug);
  if (!resolvedSlug) {
    showToast('目前尚無已開放作題的題庫可分析');
    showPortalView({ updateUrl: true, replaceUrl: true });
    return;
  }

  state.currentView = 'analytics';
  if (updateUrl) {
    syncUrlForRoute('analytics', resolvedSlug, { replace: replaceUrl });
  }
  applyViewVisibility();
  window.scrollTo({ top: 0, behavior: 'auto' });

  const alreadyLoaded =
    state.activeExamSlug === resolvedSlug &&
    state.examDetail &&
    state.questions.length > 0;

  if (alreadyLoaded) {
    renderAnalyticsView();
    return;
  }

  try {
    await loadExam(resolvedSlug);
    renderAnalyticsView();
  } catch (err) {
    document.getElementById('analyticsExamSubtitle').textContent = `載入失敗：${err.message}`;
    showToast(`載入失敗：${err.message}`);
  }
}

async function jumpFromAnalyticsToQuiz({
  slug,
  unitFilter = 'ALL',
  statusFilter = 'ALL',
  yearFilter = 'ALL',
  randomIds = null,
  hideCrossDup,
  toastMessage = '',
}) {
  const resolvedSlug = resolveDefaultReadySlug(slug);
  if (!resolvedSlug) return;

  if (state.activeExamSlug !== resolvedSlug || !state.examDetail) {
    try {
      await loadExam(resolvedSlug);
    } catch (err) {
      showToast(`載入失敗：${err.message}`);
      return;
    }
  }

  state.currentView = 'exam';
  state.unitFilter = unitFilter || 'ALL';
  state.statusFilter = statusFilter || 'ALL';
  state.yearFilter = yearFilter || 'ALL';
  state.randomIds = randomIds || null;
  state.searchQuery = '';
  if (typeof hideCrossDup === 'boolean') {
    state.hideCrossDup = hideCrossDup;
  }

  syncUrlForRoute('exam', resolvedSlug, { replace: false });
  applyViewVisibility();
  renderHeaderMetadata();
  notify();
  window.scrollTo({ top: 0, behavior: 'auto' });

  if (toastMessage) {
    showToast(toastMessage);
  }
}

function handleRouteChange() {
  if (isSingleExamOfflineMode()) return;
  const route = parseRequestedRoute();
  if (route.view === 'analytics') {
    const resolved = resolveDefaultReadySlug(route.slug);
    if (state.currentView !== 'analytics' || state.activeExamSlug !== resolved) {
      enterAnalyticsView(resolved, { updateUrl: false });
    }
  } else if (route.view === 'exam' && route.slug) {
    if (state.currentView !== 'exam' || state.activeExamSlug !== route.slug) {
      enterExamView(route.slug, { updateUrl: false });
    }
  } else if (state.currentView !== 'portal') {
    showPortalView({ updateUrl: false });
  }
}

async function boot() {
  if (typeof window !== 'undefined') {
    window.__YIKAO_BOOTED__ = true;
  }
  initBlockPortal(
    (slug) => enterExamView(slug, { updateUrl: true }),
    () => enterAnalyticsView('', { updateUrl: true })
  );
  initHeader(
    (slug) => enterExamView(slug, { updateUrl: true }),
    () => showPortalView({ updateUrl: true }),
    () => enterAnalyticsView(state.activeExamSlug || '', { updateUrl: true })
  );
  initAnalyticsView({
    onBackToExam: (slug) => enterExamView(slug, { updateUrl: true }),
    onBackToPortal: () => showPortalView({ updateUrl: true }),
    onSwitchExam: (slug) => enterAnalyticsView(slug, { updateUrl: true }),
    onJumpToQuiz: (opts) => jumpFromAnalyticsToQuiz(opts),
  });
  initFilters();
  initQuestionList();
  initResumeBar();
  initModals();

  subscribe(() => {
    if (state.currentView === 'portal') {
      renderBlockPortal();
      return;
    }
    if (state.currentView === 'analytics') {
      renderAnalyticsView();
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

    const route = parseRequestedRoute();
    if (isSingleExamOfflineMode() && state.exams.length) {
      if (route.view === 'analytics') {
        await enterAnalyticsView(state.exams[0].slug, { updateUrl: false });
      } else {
        await enterExamView(state.exams[0].slug, { updateUrl: false });
      }
      return;
    }

    if (route.view === 'analytics') {
      await enterAnalyticsView(route.slug, { updateUrl: false });
    } else if (route.view === 'exam' && route.slug) {
      await enterExamView(route.slug, { updateUrl: false });
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
