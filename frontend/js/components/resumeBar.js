/** Viewport reading tracker, inline jump badge, and bottom floating resume bar. */

import { notify, state, updateViewedQuestion } from '../store.js';

let isJumping = false;
let viewportTimer = null;

function getTargetQuestion() {
  const targetId = state.lastViewedQid || state.lastAnsweredQid;
  return targetId ? state.questionById.get(String(targetId)) : null;
}

function captureViewportQuestion() {
  if (isJumping || state.currentView !== 'exam') return;
  const containerEl = document.getElementById('questionsContainer');
  if (!containerEl) return;
  const cards = Array.from(containerEl.children);
  if (!cards.length) return;

  const anchorY = 140;
  let bestCard = null;
  for (let i = 0; i < cards.length; i++) {
    const rect = cards[i].getBoundingClientRect();
    if (rect.bottom > anchorY && rect.top < window.innerHeight * 0.75) {
      bestCard = cards[i];
      break;
    }
  }
  if (bestCard && bestCard.dataset.qid) {
    updateViewedQuestion(bestCard.dataset.qid);
  }
}

export function jumpToInterruptedSpot() {
  const q = getTargetQuestion();
  if (!q) return;

  const resumeBarEl = document.getElementById('resumeFloatingBar');
  const headerEl = document.getElementById('quizHeader');
  const containerEl = document.getElementById('questionsContainer');

  isJumping = true;
  resumeBarEl.classList.add('bar-hidden');

  let targetCard = containerEl.querySelector(`article[data-qid="${CSS.escape(q.id)}"]`);
  if (!targetCard) {
    state.randomIds = null;
    state.unitFilter = 'ALL';
    state.yearFilter = 'ALL';
    state.statusFilter = 'ALL';
    state.searchQuery = '';
    notify();
    targetCard = containerEl.querySelector(`article[data-qid="${CSS.escape(q.id)}"]`);
  }

  if (targetCard) {
    if (headerEl) headerEl.classList.remove('header-scroll-hidden');
    const headerOffset = headerEl ? headerEl.offsetHeight + 14 : 90;
    const targetTop = targetCard.getBoundingClientRect().top + window.scrollY - headerOffset;
    window.scrollTo({ top: Math.max(0, targetTop), behavior: 'smooth' });

    targetCard.classList.remove('resume-target-highlight');
    void targetCard.offsetWidth;
    targetCard.classList.add('resume-target-highlight');
  }

  setTimeout(() => {
    isJumping = false;
  }, 900);
}

export function renderResumeBarState() {
  const inlineJumpBtn = document.getElementById('inlineJumpBtn');
  if (state.currentView !== 'exam') {
    if (inlineJumpBtn) inlineJumpBtn.classList.add('hidden');
    document.getElementById('resumeFloatingBar')?.classList.add('bar-hidden');
    return;
  }
  const q = getTargetQuestion();
  if (!q) {
    inlineJumpBtn.classList.add('hidden');
    document.getElementById('resumeFloatingBar').classList.add('bar-hidden');
    return;
  }

  const tagType = state.lastAnsweredQid === q.id ? '上次作答' : '上次瀏覽';
  inlineJumpBtn.textContent = `📍 跳至${tagType} #${q.globalIndex} (${q.origQ})`;
  inlineJumpBtn.classList.remove('hidden');
}

export function showInitialResumeBanner() {
  const resumeBarEl = document.getElementById('resumeFloatingBar');
  if (state.currentView !== 'exam') {
    resumeBarEl?.classList.add('bar-hidden');
    return;
  }
  const q = getTargetQuestion();
  if (!q) {
    resumeBarEl.classList.add('bar-hidden');
    return;
  }

  const answeredCount = Object.keys(state.userAnswers || {}).length;
  const stemShort = (q.stem || '').replace(/\s+/g, ' ').slice(0, 26);
  document.getElementById('resumeBarTitle').textContent =
    `上次進度：第 ${q.globalIndex} 題｜${q.unitTitle} (${q.origQ})`;
  document.getElementById('resumeBarSub').textContent =
    `累積已答 ${answeredCount} 題 — 「${stemShort}...」`;
  resumeBarEl.classList.remove('bar-hidden');
}

export function initResumeBar() {
  document.getElementById('inlineJumpBtn').addEventListener('click', jumpToInterruptedSpot);
  document.getElementById('resumeJumpNowBtn').addEventListener('click', jumpToInterruptedSpot);
  document.getElementById('resumeDismissBtn').addEventListener('click', () => {
    document.getElementById('resumeFloatingBar').classList.add('bar-hidden');
  });

  window.addEventListener(
    'scroll',
    () => {
      if (isJumping) return;
      clearTimeout(viewportTimer);
      viewportTimer = setTimeout(captureViewportQuestion, 350);
    },
    { passive: true }
  );

  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') captureViewportQuestion();
  });
  window.addEventListener('pagehide', captureViewportQuestion);
  window.addEventListener('beforeunload', captureViewportQuestion);
}
