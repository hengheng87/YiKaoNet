/** Modals: Notion export, Cloud Sync & JSON backup, and Reset confirmation. */

import {
  generateSyncCode,
  getOfflineHtmlDownloadUrl,
  isLocalOnlyMode,
  isOfflineMode,
} from '../api.js';
import { escapeHtml } from '../markdown.js';
import {
  copyTextToClipboard,
  downloadTextFile,
  generateNotionToggleContent,
} from '../notion.js';
import {
  buildBackupJson,
  connectSyncCode,
  disconnectSyncCode,
  getFilteredQuestions,
  getQuestionsByExportScope,
  importBackupJson,
  resetAllAnswers,
  state,
  syncNow,
} from '../store.js';
import { showToast } from './toast.js';

export function populateExportModalOptions() {
  const exam = state.examDetail;
  const sel = document.getElementById('notionExportScope');
  if (!exam || !sel) return;

  const sessionOpts = exam.sessions.map(
    (s) =>
      `<option value="SESSION_${escapeHtml(s.code)}">${escapeHtml(s.emoji)} ${escapeHtml(s.label)}：${escapeHtml(s.description)}（${s.questionCount} 題）</option>`
  );
  const highlightOpts = exam.units
    .filter((u) => u.highlight)
    .map(
      (u) =>
        `<option value="${escapeHtml(u.unitCode)}">${escapeHtml(u.shortLabel)}（${u.questionCount} 題）</option>`
    );
  const subjOpts = exam.subjects.map(
    (sub) =>
      `<option value="SUBJ_${escapeHtml(sub.code)}">${escapeHtml(sub.emoji)} ${escapeHtml(sub.label)}全（${escapeHtml(sub.profs)}｜${sub.questionCount} 題）</option>`
  );

  sel.innerHTML = [
    `<option value="CURRENT">目前篩選顯示的題目</option>`,
    `<option value="ALL">全部題庫（共 ${exam.totalQuestions} 題）</option>`,
    `<option value="UNIQUE">精簡不重複題庫（共 ${exam.uniqueQuestions} 題）</option>`,
    ...sessionOpts,
    `<option value="ERRATA">⚠️ 申覆多解／送分／爭議題（${exam.errataCount} 題）</option>`,
    `<option value="WRONG">❌ 目前答錯的題目（錯題本）</option>`,
    `<option value="STARRED">⭐ 目前加星號收藏的題目</option>`,
    ...highlightOpts,
    ...subjOpts,
  ].join('');

  document.getElementById('resetModalDescription').textContent =
    `這將會清空目前 ${exam.totalQuestions} 題的已選答案與對錯統計（您標記的 ⭐ 星號收藏題目將會保留下來）。`;
}

function updateNotionModalPreview() {
  const scope = document.getElementById('notionExportScope').value;
  const list = getQuestionsByExportScope(scope);
  const text = generateNotionToggleContent(state.examDetail?.title, list);
  document.getElementById('notionPreviewTextarea').value = text;
  document.getElementById('notionPreviewCount').textContent = `共 ${list.length} 題`;
}

export function renderSyncModalState() {
  const cloudSection = document.getElementById('syncCloudConnectSection');
  if (cloudSection) {
    cloudSection.classList.toggle('hidden', isLocalOnlyMode());
  }
  const offlineBtn = document.getElementById('downloadOfflineHtmlBtn');
  if (offlineBtn) {
    offlineBtn.classList.toggle('hidden', isOfflineMode());
  }

  const connectedBox = document.getElementById('syncConnectedBox');
  const codeDisplay = document.getElementById('activeSyncCodeDisplay');
  const updatedText = document.getElementById('syncLastUpdatedText');
  const input = document.getElementById('syncCodeInput');

  if (state.syncCode) {
    connectedBox.classList.remove('hidden');
    codeDisplay.textContent = state.syncCode;
    if (state.syncUpdatedAt) {
      const dt = new Date(state.syncUpdatedAt).toLocaleString('zh-TW');
      updatedText.textContent = `最近同步時間：${dt}（系統會在作答或收藏後自動保存至雲端）`;
    }
    if (!input.value) input.value = state.syncCode;
  } else {
    connectedBox.classList.add('hidden');
  }
}

export function initModals() {
  const notionModal = document.getElementById('notionModal');
  const syncModal = document.getElementById('syncModal');
  const resetModal = document.getElementById('resetConfirmModal');

  // Notion Modal
  document.getElementById('openNotionModalBtn').addEventListener('click', () => {
    updateNotionModalPreview();
    notionModal.classList.remove('hidden');
  });
  document.getElementById('closeNotionModalBtn').addEventListener('click', () => {
    notionModal.classList.add('hidden');
  });
  document
    .getElementById('notionExportScope')
    .addEventListener('change', updateNotionModalPreview);
  document.getElementById('copyNotionToggleBtn').addEventListener('click', () => {
    const text = document.getElementById('notionPreviewTextarea').value;
    copyTextToClipboard(
      text,
      '✅ 已複製 Notion 摺疊題庫格式！請直接在 Notion 頁面按 Ctrl/Cmd+V 貼上'
    );
  });
  document.getElementById('quickCopyNotionBtn').addEventListener('click', () => {
    const list = getFilteredQuestions();
    const text = generateNotionToggleContent(state.examDetail?.title, list);
    copyTextToClipboard(
      text,
      `✅ 已複製目前篩選的 ${list.length} 題 Notion 摺疊題庫格式！`
    );
  });
  document.getElementById('downloadMarkdownBtn').addEventListener('click', () => {
    const scope = document.getElementById('notionExportScope').value;
    const text = document.getElementById('notionPreviewTextarea').value;
    const slug = state.activeExamSlug || 'yikao';
    downloadTextFile(`${slug}-${scope}.md`, text, 'text/markdown;charset=utf-8');
    showToast('✅ 已下載 Notion Markdown (.md) 檔！');
  });
  document.getElementById('downloadQuestionsJsonBtn').addEventListener('click', () => {
    const scope = document.getElementById('notionExportScope').value;
    const list = getQuestionsByExportScope(scope);
    const slug = state.activeExamSlug || 'yikao';
    downloadTextFile(
      `${slug}-${scope}.json`,
      JSON.stringify(list, null, 2),
      'application/json;charset=utf-8'
    );
    showToast(`✅ 已下載 ${list.length} 題 JSON 資料檔！`);
  });
  document.getElementById('downloadOfflineHtmlBtn').addEventListener('click', () => {
    if (!state.activeExamSlug) return;
    const url = getOfflineHtmlDownloadUrl(state.activeExamSlug);
    const a = document.createElement('a');
    a.href = url;
    a.download = `yikao-${state.activeExamSlug}-offline.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast('📦 正在建置並下載單檔離線互動 HTML...');
  });

  // Cloud Sync Modal
  document.getElementById('openSyncModalBtn').addEventListener('click', () => {
    renderSyncModalState();
    syncModal.classList.remove('hidden');
  });
  document.getElementById('closeSyncModalBtn').addEventListener('click', () => {
    syncModal.classList.add('hidden');
  });
  document.getElementById('generateSyncCodeBtn').addEventListener('click', async () => {
    try {
      const res = await generateSyncCode();
      document.getElementById('syncCodeInput').value = res.syncCode;
      showToast(`已產生同步碼：${res.syncCode}，請點擊下方按鈕綁定！`);
    } catch (err) {
      showToast(`產生同步碼失敗：${err.message}`);
    }
  });
  document.getElementById('connectMergeBtn').addEventListener('click', async () => {
    const raw = document.getElementById('syncCodeInput').value;
    try {
      const code = await connectSyncCode(raw, 'merge');
      renderSyncModalState();
      showToast(`☁️ 已綁定並雙向合併雲端紀錄 (${code})`);
    } catch (err) {
      showToast(`綁定失敗：${err.message}`);
    }
  });
  document.getElementById('connectPullBtn').addEventListener('click', async () => {
    const raw = document.getElementById('syncCodeInput').value;
    try {
      const code = await connectSyncCode(raw, 'pull');
      renderSyncModalState();
      showToast(`⬇️ 已載入雲端紀錄並覆蓋本機 (${code})`);
    } catch (err) {
      showToast(`載入失敗：${err.message}`);
    }
  });
  document.getElementById('copySyncCodeBtn').addEventListener('click', () => {
    if (state.syncCode) {
      copyTextToClipboard(state.syncCode, `已複製同步碼：${state.syncCode}`);
    }
  });
  document.getElementById('syncNowBtn').addEventListener('click', async () => {
    await syncNow();
    renderSyncModalState();
    showToast(
      state.syncStatus === 'synced' ? '☁️ 已完成雲端雙向合併！' : '❌ 雲端同步失敗'
    );
  });
  document.getElementById('disconnectSyncBtn').addEventListener('click', () => {
    disconnectSyncCode();
    renderSyncModalState();
    showToast('已中斷雲端同步，目前僅保存於本機瀏覽器');
  });

  document.getElementById('exportProgressJsonBtn').addEventListener('click', () => {
    const slug = state.activeExamSlug || 'yikao';
    downloadTextFile(
      `${slug}-progress-backup.json`,
      buildBackupJson(),
      'application/json;charset=utf-8'
    );
    showToast('✅ 已匯出個人作答進度 JSON 備份！');
  });
  document
    .getElementById('importProgressJsonInput')
    .addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        await importBackupJson(text);
        showToast('✅ 已匯入作答進度備份！');
      } catch (err) {
        showToast(`匯入失敗：${err.message}`);
      } finally {
        e.target.value = '';
      }
    });

  // Reset Modal
  document.getElementById('resetQuizBtn').addEventListener('click', () => {
    resetModal.classList.remove('hidden');
  });
  document.getElementById('cancelResetBtn').addEventListener('click', () => {
    resetModal.classList.add('hidden');
  });
  document.getElementById('confirmResetBtn').addEventListener('click', async () => {
    await resetAllAnswers();
    resetModal.classList.add('hidden');
    showToast('已重置所有作答紀錄！');
  });

  // Backdrop & Escape closing
  [notionModal, syncModal, resetModal].forEach((modal) => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      [notionModal, syncModal, resetModal].forEach((m) => m.classList.add('hidden'));
    }
  });
}
