/** Sticky header, exam selector, mode switcher, live scoreboard, and mobile auto-hide. */

import { isLocalOnlyMode } from '../api.js';
import { escapeHtml } from '../markdown.js';
import { isAnswerCorrect, notify, setMode, state, submitExam } from '../store.js';
import { showToast } from './toast.js';

let lastScrollY = window.scrollY || 0;
let scrollTicking = false;
let boundExamSelector = null;

function handleHeaderAutoHide() {
  const headerEl = document.querySelector('header.sticky');
  const currentY = window.scrollY || 0;
  const delta = currentY - lastScrollY;
  if (headerEl) {
    if (currentY < 70 || delta < -10) {
      headerEl.classList.remove('header-scroll-hidden');
    } else if (currentY > 90 && delta > 12) {
      headerEl.classList.add('header-scroll-hidden');
    }
  }
  lastScrollY = currentY;
  scrollTicking = false;
}

export function initHeader(onSelectExam) {
  boundExamSelector = onSelectExam;

  const modePracticeBtn = document.getElementById('modePracticeBtn');
  const modeExamBtn = document.getElementById('modeExamBtn');
  const submitExamBtn = document.getElementById('submitExamBtn');
  const examSelector = document.getElementById('examSelector');

  modePracticeBtn.addEventListener('click', () => {
    setMode('practice');
  });

  modeExamBtn.addEventListener('click', () => {
    state.expandedExpl = {};
    setMode('exam');
  });

  submitExamBtn.addEventListener('click', () => {
    submitExam();
    showToast('已批改試卷並展開全卷詳解！');
  });

  examSelector.addEventListener('change', (e) => {
    const nextSlug = e.target.value;
    if (nextSlug && nextSlug !== state.activeExamSlug && boundExamSelector) {
      boundExamSelector(nextSlug);
    }
  });

  window.addEventListener(
    'scroll',
    () => {
      if (!scrollTicking) {
        window.requestAnimationFrame(handleHeaderAutoHide);
        scrollTicking = true;
      }
    },
    { passive: true }
  );
}

export function renderHeaderMetadata() {
  const exam = state.examDetail;
  if (!exam) return;

  document.title = `${exam.title}｜易考網 YiKao`;
  document.getElementById('examBadge').textContent = exam.badge;
  document.getElementById('examTitle').textContent = `${exam.title}（全 ${exam.totalQuestions} 題）`;

  const subtitleEl = document.getElementById('examSubtitle');
  const src = exam.source || {};
  if (src.url) {
    subtitleEl.innerHTML = `整合 <a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="text-indigo-600 hover:underline font-medium">${escapeHtml(src.name || '知識庫')}</a> ・ ${escapeHtml(exam.subtitle)}`;
  } else {
    subtitleEl.textContent = exam.subtitle;
  }

  const selector = document.getElementById('examSelector');
  if (state.exams.length > 1) {
    selector.innerHTML = state.exams
      .map(
        (ex) =>
          `<option value="${escapeHtml(ex.slug)}" ${ex.slug === exam.slug ? 'selected' : ''}>${escapeHtml(ex.title)} (${ex.totalQuestions})</option>`
      )
      .join('');
    selector.classList.remove('hidden');
  } else {
    selector.classList.add('hidden');
  }

  notify();
}

export function renderHeaderState() {
  const total = state.questions.length;
  let answered = 0;
  let correct = 0;
  let wrong = 0;

  state.questions.forEach((q) => {
    const chosen = state.userAnswers[q.id];
    if (chosen) {
      answered++;
      if (isAnswerCorrect(q, chosen)) correct++;
      else wrong++;
    }
  });

  const rate = answered > 0 ? Math.round((correct / answered) * 100) : 0;
  document.getElementById('statAnswered').textContent = `${answered}/${total}`;
  document.getElementById('statCorrect').textContent = String(correct);
  document.getElementById('statWrong').textContent = String(wrong);
  document.getElementById('statRate').textContent = `${rate}%`;

  const cPct = total > 0 ? (correct / total) * 100 : 0;
  const wPct = total > 0 ? (wrong / total) * 100 : 0;
  document.getElementById('progressBarCorrect').style.width = `${cPct}%`;
  document.getElementById('progressBarWrong').style.width = `${wPct}%`;

  const modePracticeBtn = document.getElementById('modePracticeBtn');
  const modeExamBtn = document.getElementById('modeExamBtn');
  const examBanner = document.getElementById('examModeBanner');

  if (state.mode === 'practice') {
    modePracticeBtn.className =
      'px-2.5 py-1 rounded-md bg-white text-indigo-700 shadow-sm font-semibold transition';
    modeExamBtn.className =
      'px-2.5 py-1 rounded-md text-slate-600 hover:text-slate-900 transition';
    examBanner.classList.add('hidden');
  } else {
    modeExamBtn.className =
      'px-2.5 py-1 rounded-md bg-white text-amber-700 shadow-sm font-semibold transition';
    modePracticeBtn.className =
      'px-2.5 py-1 rounded-md text-slate-600 hover:text-slate-900 transition';
    examBanner.classList.remove('hidden');
  }

  const dot = document.getElementById('syncStatusDot');
  const label = document.getElementById('syncStatusLabel');
  if (isLocalOnlyMode()) {
    dot.className = 'sync-dot sync-dot-off';
    label.textContent = '💾 進度備份';
    return;
  }
  dot.className = `sync-dot sync-dot-${state.syncStatus}`;
  if (state.syncStatus === 'off') {
    label.textContent = '☁️ 雲端同步';
  } else if (state.syncStatus === 'syncing') {
    label.textContent = '☁️ 同步中...';
  } else if (state.syncStatus === 'synced') {
    label.textContent = `☁️ 已同步 (${state.syncCode})`;
  } else {
    label.textContent = '☁️ 同步失敗';
  }
}
