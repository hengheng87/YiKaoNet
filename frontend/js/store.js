/** Central application store with localStorage persistence, v1.0.6 migration, and cloud sync. */

import {
  deleteCloudProgress,
  fetchCloudProgress,
  isLocalOnlyMode,
  mergeCloudProgress,
  saveCloudProgress,
} from './api.js';

const STORAGE_PREFIX = 'yikao_progress_v2:';
const SYNC_CODE_KEY = 'yikao_sync_code_v2';
const ACTIVE_EXAM_KEY = 'yikao_active_exam_v2';

const listeners = new Set();
let syncDebounceTimer = null;

export const state = {
  currentView: 'portal', // 'portal' | 'exam'
  blocksCatalog: null,
  portalTermFilter: 'ALL',
  portalStatusFilter: 'ALL',
  portalSearchQuery: '',

  exams: [],
  activeExamSlug: null,
  examDetail: null,
  questions: [],
  questionById: new Map(),
  questionByGlobalIdx: new Map(),
  outOfScopeUnits: new Set(),
  exemptDupUnits: new Set(),

  mode: 'practice', // 'practice' | 'exam'
  examSubmitted: false,
  unitFilter: 'ALL',
  yearFilter: 'ALL',
  statusFilter: 'ALL',
  hideCrossDup: false,
  searchQuery: '',
  randomIds: null,
  isAllExplExpanded: false,

  userAnswers: {},
  answerTimestamps: {},
  expandedExpl: {},
  starred: {},
  starredTimestamps: {},
  lastAnsweredQid: null,
  lastViewedQid: null,
  updatedAt: 0,

  syncCode: loadStoredSyncCode(),
  syncStatus: 'off', // 'off' | 'syncing' | 'synced' | 'error'
  syncUpdatedAt: null,
};

function loadStoredSyncCode() {
  try {
    return localStorage.getItem(SYNC_CODE_KEY) || '';
  } catch (_) {
    return '';
  }
}

export function getSavedActiveExamSlug() {
  try {
    return localStorage.getItem(ACTIVE_EXAM_KEY) || '';
  } catch (_) {
    return '';
  }
}

export function getExamLocalProgressSummary(slug) {
  if (!slug) {
    return { answeredCount: 0, starredCount: 0, updatedAt: 0 };
  }
  try {
    let payload = null;
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${slug}`);
    if (raw) {
      payload = JSON.parse(raw);
    } else {
      payload = migrateLegacyV106Storage(slug);
    }
    if (!payload || typeof payload !== 'object') {
      return { answeredCount: 0, starredCount: 0, updatedAt: 0 };
    }
    const answers = payload.answers || {};
    const starred = payload.starred || {};
    const answeredCount = Object.values(answers).filter(Boolean).length;
    const starredCount = Object.values(starred).filter(Boolean).length;
    return {
      answeredCount,
      starredCount,
      updatedAt: Number(payload.updatedAt || 0),
    };
  } catch (_) {
    return { answeredCount: 0, starredCount: 0, updatedAt: 0 };
  }
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function notify() {
  listeners.forEach((fn) => fn(state));
}

export function isAnswerCorrect(q, chosen) {
  if (!chosen) return false;
  return q.acceptedAnswers.includes(chosen);
}

function buildProgressPayload() {
  return {
    answers: { ...state.userAnswers },
    answerTimestamps: { ...state.answerTimestamps },
    starred: { ...state.starred },
    starredTimestamps: { ...state.starredTimestamps },
    lastAnsweredQid: state.lastAnsweredQid,
    lastViewedQid: state.lastViewedQid,
    activeFilters: {
      unitFilter: state.unitFilter,
      yearFilter: state.yearFilter,
      statusFilter: state.statusFilter,
    },
    updatedAt: state.updatedAt || Date.now(),
  };
}

function applyProgressPayload(payload, { autoOpenPractice = true } = {}) {
  state.userAnswers = { ...(payload.answers || {}) };
  state.answerTimestamps = { ...(payload.answerTimestamps || {}) };
  state.starred = { ...(payload.starred || {}) };
  state.starredTimestamps = { ...(payload.starredTimestamps || {}) };
  state.lastAnsweredQid = payload.lastAnsweredQid || null;
  state.lastViewedQid = payload.lastViewedQid || null;
  state.updatedAt = payload.updatedAt || Date.now();
  state.expandedExpl = {};
  if (autoOpenPractice && state.mode === 'practice') {
    Object.keys(state.userAnswers).forEach((qid) => {
      state.expandedExpl[qid] = true;
    });
  }
  saveLocalProgress();
}

function migrateLegacyV106Storage(slug) {
  if (slug !== 'cmu-int2-msk') return null;
  try {
    const rawAns = localStorage.getItem('cmu_int2_msk_answers_v1');
    const rawStars = localStorage.getItem('cmu_int2_msk_stars_v1');
    const rawPatch = localStorage.getItem('CMU_MSK_477_PATCH_PROGRESS_V1');
    if (!rawAns && !rawStars && !rawPatch) return null;

    const patch = rawPatch ? JSON.parse(rawPatch) : {};
    const v1Ans = rawAns ? JSON.parse(rawAns) : {};
    const v1Stars = rawStars ? JSON.parse(rawStars) : {};
    const mergedAns = { ...(patch.answers || {}), ...v1Ans };
    const mergedStars = { ...(patch.starred || {}), ...v1Stars };
    const ts = patch.updatedAt || Date.now();

    const ansTs = {};
    Object.keys(mergedAns).forEach((qid) => {
      ansTs[qid] = ts;
    });
    const starTs = {};
    Object.keys(mergedStars).forEach((qid) => {
      if (mergedStars[qid]) starTs[qid] = ts;
    });

    return {
      answers: mergedAns,
      answerTimestamps: ansTs,
      starred: mergedStars,
      starredTimestamps: starTs,
      lastAnsweredQid: patch.lastAnsweredQid || null,
      lastViewedQid: patch.lastViewedQid || null,
      updatedAt: ts,
    };
  } catch (_) {
    return null;
  }
}

export function loadLocalProgress(slug) {
  const key = `${STORAGE_PREFIX}${slug}`;
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw);
      applyProgressPayload(parsed);
      return;
    }
    const migrated = migrateLegacyV106Storage(slug);
    if (migrated) {
      applyProgressPayload(migrated);
      return;
    }
  } catch (_) {
    // Ignore storage read errors
  }
  applyProgressPayload({
    answers: {},
    answerTimestamps: {},
    starred: {},
    starredTimestamps: {},
    lastAnsweredQid: null,
    lastViewedQid: null,
    updatedAt: 0,
  });
}

export function saveLocalProgress() {
  if (!state.activeExamSlug) return;
  try {
    localStorage.setItem(
      `${STORAGE_PREFIX}${state.activeExamSlug}`,
      JSON.stringify(buildProgressPayload())
    );
  } catch (_) {
    // Ignore quota/sandbox errors
  }
}

function scheduleCloudSync() {
  saveLocalProgress();
  if (isLocalOnlyMode() || !state.syncCode || !state.activeExamSlug) return;

  state.syncStatus = 'syncing';
  notify();

  if (syncDebounceTimer) clearTimeout(syncDebounceTimer);
  syncDebounceTimer = setTimeout(async () => {
    try {
      const res = await saveCloudProgress(
        state.syncCode,
        state.activeExamSlug,
        buildProgressPayload()
      );
      state.syncStatus = 'synced';
      state.syncUpdatedAt = res.updatedAt || Date.now();
    } catch (_) {
      state.syncStatus = 'error';
    }
    notify();
  }, 800);
}

export function setExamData(examDetail, questions) {
  state.activeExamSlug = examDetail.slug;
  state.examDetail = examDetail;
  state.questions = questions;
  state.questionById = new Map();
  state.questionByGlobalIdx = new Map();
  state.outOfScopeUnits = new Set();
  state.exemptDupUnits = new Set();

  questions.forEach((q) => {
    state.questionById.set(String(q.id), q);
    state.questionByGlobalIdx.set(Number(q.globalIndex), q);
  });

  examDetail.units.forEach((u) => {
    if (u.isOutOfScope) state.outOfScopeUnits.add(u.unitCode);
    if (u.exemptFromCrossDupFilter) state.exemptDupUnits.add(u.unitCode);
  });

  state.mode = 'practice';
  state.examSubmitted = false;
  state.unitFilter = 'ALL';
  state.yearFilter = 'ALL';
  state.statusFilter = 'ALL';
  state.hideCrossDup = false;
  state.searchQuery = '';
  state.randomIds = null;
  state.isAllExplExpanded = false;

  try {
    localStorage.setItem(ACTIVE_EXAM_KEY, examDetail.slug);
  } catch (_) {
    // Ignore
  }

  loadLocalProgress(examDetail.slug);
  state.syncStatus = !isLocalOnlyMode() && state.syncCode ? 'syncing' : 'off';
  notify();
}

export async function initialCloudMergeIfConnected() {
  if (isLocalOnlyMode() || !state.syncCode || !state.activeExamSlug) return;
  state.syncStatus = 'syncing';
  notify();
  try {
    const res = await mergeCloudProgress(
      state.syncCode,
      state.activeExamSlug,
      buildProgressPayload()
    );
    applyProgressPayload(res);
    state.syncStatus = 'synced';
    state.syncUpdatedAt = res.updatedAt || Date.now();
  } catch (_) {
    state.syncStatus = 'error';
  }
  notify();
}

export async function connectSyncCode(rawCode, strategy = 'merge') {
  const code = rawCode.trim().toUpperCase();
  if (!code) throw new Error('請輸入同步碼');
  if (!state.activeExamSlug) throw new Error('尚未載入題庫');

  state.syncStatus = 'syncing';
  notify();

  let res;
  if (strategy === 'pull') {
    const fetched = await fetchCloudProgress(code, state.activeExamSlug);
    if (fetched.exists) {
      applyProgressPayload(fetched);
      res = fetched;
    } else {
      res = await saveCloudProgress(code, state.activeExamSlug, buildProgressPayload());
    }
  } else {
    res = await mergeCloudProgress(code, state.activeExamSlug, buildProgressPayload());
    applyProgressPayload(res);
  }

  state.syncCode = res.syncCode || code;
  state.syncStatus = 'synced';
  state.syncUpdatedAt = res.updatedAt || Date.now();
  try {
    localStorage.setItem(SYNC_CODE_KEY, state.syncCode);
  } catch (_) {
    // Ignore
  }
  notify();
  return state.syncCode;
}

export async function syncNow() {
  if (!state.syncCode || !state.activeExamSlug) return;
  if (syncDebounceTimer) {
    clearTimeout(syncDebounceTimer);
    syncDebounceTimer = null;
  }
  await initialCloudMergeIfConnected();
}

export function disconnectSyncCode() {
  if (syncDebounceTimer) {
    clearTimeout(syncDebounceTimer);
    syncDebounceTimer = null;
  }
  state.syncCode = '';
  state.syncStatus = 'off';
  state.syncUpdatedAt = null;
  try {
    localStorage.removeItem(SYNC_CODE_KEY);
  } catch (_) {
    // Ignore
  }
  notify();
}

export function selectOption(qid, opt) {
  const now = Date.now();
  state.userAnswers[qid] = opt;
  state.answerTimestamps[qid] = now;
  state.lastAnsweredQid = qid;
  state.lastViewedQid = qid;
  state.updatedAt = now;
  if (state.mode === 'practice') {
    state.expandedExpl[qid] = true;
  }
  scheduleCloudSync();
  notify();
}

export function toggleExplanation(qid) {
  state.expandedExpl[qid] = !state.expandedExpl[qid];
  notify();
}

export function toggleAllExplanations() {
  state.isAllExplExpanded = !state.isAllExplExpanded;
  getFilteredQuestions().forEach((q) => {
    state.expandedExpl[q.id] = state.isAllExplExpanded;
  });
  notify();
}

export function toggleStar(qid) {
  const now = Date.now();
  const nextVal = !state.starred[qid];
  state.starred[qid] = nextVal;
  state.starredTimestamps[qid] = now;
  state.updatedAt = now;
  scheduleCloudSync();
  notify();
}

export function resetSingleAnswer(qid) {
  const now = Date.now();
  delete state.userAnswers[qid];
  delete state.answerTimestamps[qid];
  delete state.expandedExpl[qid];
  state.updatedAt = now;
  scheduleCloudSync();
  notify();
}

export async function resetAllAnswers() {
  const now = Date.now();
  state.userAnswers = {};
  state.answerTimestamps = {};
  state.expandedExpl = {};
  state.examSubmitted = false;
  state.lastAnsweredQid = null;
  state.lastViewedQid = null;
  state.updatedAt = now;
  saveLocalProgress();
  if (!isLocalOnlyMode() && state.syncCode && state.activeExamSlug) {
    if (syncDebounceTimer) {
      clearTimeout(syncDebounceTimer);
      syncDebounceTimer = null;
    }
    state.syncStatus = 'syncing';
    notify();
    try {
      await deleteCloudProgress(state.syncCode, state.activeExamSlug, true);
      state.syncStatus = 'synced';
      state.syncUpdatedAt = Date.now();
    } catch (_) {
      state.syncStatus = 'error';
    }
  }
  notify();
}

export function updateViewedQuestion(qid) {
  if (!qid || state.lastViewedQid === qid) return;
  state.lastViewedQid = qid;
  state.updatedAt = Date.now();
  scheduleCloudSync();
  notify();
}

export function setMode(nextMode) {
  state.mode = nextMode;
  state.examSubmitted = false;
  if (nextMode === 'exam') {
    state.expandedExpl = {};
  } else {
    Object.keys(state.userAnswers).forEach((qid) => {
      state.expandedExpl[qid] = true;
    });
  }
  notify();
}

export function submitExam() {
  state.examSubmitted = true;
  state.questions.forEach((q) => {
    state.expandedExpl[q.id] = true;
  });
  notify();
}

export function getFilteredQuestions() {
  return state.questions.filter((q) => {
    if (state.randomIds && !state.randomIds.has(q.id)) return false;
    if (
      state.hideCrossDup &&
      q.isCrossDup &&
      !state.exemptDupUnits.has(state.unitFilter)
    ) {
      return false;
    }

    if (state.unitFilter !== 'ALL') {
      if (state.unitFilter.startsWith('SESSION_')) {
        const ses = state.unitFilter.replace('SESSION_', '');
        if (q.session !== ses) return false;
      } else if (state.unitFilter.startsWith('SUBJ_')) {
        const subj = state.unitFilter.replace('SUBJ_', '');
        if (q.subject !== subj) return false;
      } else if (state.unitFilter === 'OUT_OF_SCOPE') {
        if (!state.outOfScopeUnits.has(q.unitCode)) return false;
      } else if (q.unitCode !== state.unitFilter) {
        return false;
      }
    }

    if (state.yearFilter !== 'ALL' && q.yearGroup !== state.yearFilter) {
      return false;
    }

    const chosen = state.userAnswers[q.id];
    if (state.statusFilter === 'UNANSWERED' && chosen) return false;
    if (state.statusFilter === 'WRONG' && (!chosen || isAnswerCorrect(q, chosen))) {
      return false;
    }
    if (state.statusFilter === 'CORRECT' && (!chosen || !isAnswerCorrect(q, chosen))) {
      return false;
    }
    if (state.statusFilter === 'STARRED' && !state.starred[q.id]) return false;
    if (state.statusFilter === 'ERRATA' && !q.hasErrata) return false;

    if (state.searchQuery.trim() !== '') {
      const kw = state.searchQuery.trim().toLowerCase();
      const optVals = Object.values(q.options || {}).join(' ');
      const hay = [
        q.stem,
        optVals,
        q.unitTitle,
        q.prof,
        q.year,
        ...(q.explanations || []),
      ]
        .join(' ')
        .toLowerCase();
      if (!hay.includes(kw)) return false;
    }

    return true;
  });
}

export function getQuestionsByExportScope(scope) {
  if (scope === 'CURRENT') return getFilteredQuestions();
  if (scope === 'ALL') return state.questions;
  if (scope === 'UNIQUE') return state.questions.filter((q) => !q.isCrossDup);
  if (scope === 'ERRATA') return state.questions.filter((q) => q.hasErrata);
  if (scope === 'WRONG') {
    return state.questions.filter(
      (q) => state.userAnswers[q.id] && !isAnswerCorrect(q, state.userAnswers[q.id])
    );
  }
  if (scope === 'STARRED') return state.questions.filter((q) => !!state.starred[q.id]);
  if (scope.startsWith('SESSION_')) {
    const ses = scope.replace('SESSION_', '');
    return state.questions.filter((q) => q.session === ses);
  }
  if (scope.startsWith('SUBJ_')) {
    const subj = scope.replace('SUBJ_', '');
    return state.questions.filter((q) => q.subject === subj);
  }
  return state.questions.filter((q) => q.unitCode === scope);
}

export function buildBackupJson() {
  return JSON.stringify(
    {
      format: 'yikao-progress-v2',
      examSlug: state.activeExamSlug,
      exportedAt: new Date().toISOString(),
      ...buildProgressPayload(),
    },
    null,
    2
  );
}

export async function importBackupJson(rawText) {
  const parsed = JSON.parse(rawText);
  if (!parsed || typeof parsed !== 'object' || typeof parsed.answers !== 'object') {
    throw new Error('無效的進度備份檔案格式');
  }
  if (parsed.examSlug && parsed.examSlug !== state.activeExamSlug) {
    throw new Error(`此備份屬於考科「${parsed.examSlug}」，與目前考科不同`);
  }
  applyProgressPayload({
    answers: parsed.answers || {},
    answerTimestamps: parsed.answerTimestamps || {},
    starred: parsed.starred || {},
    starredTimestamps: parsed.starredTimestamps || {},
    lastAnsweredQid: parsed.lastAnsweredQid || null,
    lastViewedQid: parsed.lastViewedQid || null,
    updatedAt: parsed.updatedAt || Date.now(),
  });
  scheduleCloudSync();
  notify();
}
