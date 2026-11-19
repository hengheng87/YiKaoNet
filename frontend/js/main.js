/** Application bootstrap and reactive render wiring. */

import { fetchExamDetail, fetchExams, fetchQuestions } from './api.js';
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
  setExamData,
  state,
  subscribe,
} from './store.js';

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

async function boot() {
  initHeader(loadExam);
  initFilters();
  initQuestionList();
  initResumeBar();
  initModals();

  subscribe(() => {
    renderHeaderState();
    renderFilterState();
    renderQuestions();
    renderResumeBarState();
  });

  try {
    const exams = await fetchExams();
    state.exams = exams;
    if (!exams.length) {
      document.getElementById('examTitle').textContent = '尚未匯入任何題庫';
      document.getElementById('examSubtitle').textContent =
        '請在 data/exams/ 下新增題庫後重新建置靜態網頁或啟動後端。';
      return;
    }

    const savedSlug = getSavedActiveExamSlug();
    const initialExam = exams.find((e) => e.slug === savedSlug) || exams[0];
    await loadExam(initialExam.slug);
  } catch (err) {
    document.getElementById('examTitle').textContent = '題庫載入失敗';
    document.getElementById('examSubtitle').textContent = err.message;
    showToast(`載入失敗：${err.message}`);
  }
}

document.addEventListener('DOMContentLoaded', boot);
