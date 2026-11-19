/** Organ-system Block portal landing view with term grouping, search, and local progress summary. */

import { escapeHtml } from '../markdown.js';
import { getExamLocalProgressSummary, getSavedActiveExamSlug, notify, state } from '../store.js';
import { showToast } from './toast.js';

const PORTAL_ALLOWED_ACCENTS = new Set(['indigo', 'blue', 'rose', 'amber', 'emerald']);

let portalOnEnterExam = null;

function portalSafeAccent(raw) {
  const clean = String(raw || '').trim().toLowerCase();
  return PORTAL_ALLOWED_ACCENTS.has(clean) ? clean : 'indigo';
}

function portalResetFilters() {
  state.portalTermFilter = 'ALL';
  state.portalStatusFilter = 'ALL';
  state.portalSearchQuery = '';
  const searchInput = document.getElementById('portalSearchInput');
  if (searchInput) searchInput.value = '';
  renderBlockPortal();
}

function portalMatchesQuery(block, term, queryLower) {
  if (!queryLower) return true;
  const hay = [
    block.name,
    block.englishName,
    block.examLabel,
    block.description,
    block.slug,
    block.sourceHint,
    term.label,
    term.shortLabel,
    ...(block.subjects || []).map((s) => s.label),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return hay.includes(queryLower);
}

function portalRenderBlockCard(block) {
  const accent = portalSafeAccent(block.accent);
  const isReady = block.status === 'ready';

  const statusBadgeHtml = isReady
    ? `<span class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 shrink-0">✓ 已開放作題</span>`
    : `<span class="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600 border border-slate-200 shrink-0">⏳ 題庫建置中</span>`;

  const subjectsHtml = (block.subjects || [])
    .map((s) => {
      const emojiPrefix = s.emoji ? `${escapeHtml(s.emoji)} ` : '';
      const countSuffix = s.questionCount > 0 ? ` (${s.questionCount})` : '';
      return `<span class="block-subject-chip">${emojiPrefix}${escapeHtml(s.label)}${countSuffix}</span>`;
    })
    .join('');

  let progressBlockHtml = '';
  let footerHtml = '';

  if (isReady) {
    const prog = getExamLocalProgressSummary(block.slug);
    const totalQ = Math.max(0, Number(block.totalQuestions || 0));
    const answered = Math.min(totalQ, prog.answeredCount);
    const pct = totalQ > 0 ? Math.round((answered / totalQ) * 100) : 0;

    progressBlockHtml = `
      <div class="space-y-1.5 pt-1">
        <div class="flex items-center justify-between text-[11px]">
          <span class="text-slate-600 font-medium">
            本機作答進度：<strong class="text-slate-900">${answered} / ${totalQ}</strong> 題 (${pct}%)
          </span>
          ${
            prog.starredCount > 0
              ? `<span class="text-amber-700 font-semibold">⭐ ${prog.starredCount} 收藏</span>`
              : `<span class="text-slate-500">獨立題 ${block.uniqueQuestions}・${block.unitCount} 單元</span>`
          }
        </div>
        <div class="block-progress-track">
          <div class="block-progress-fill" style="width: ${pct}%"></div>
        </div>
      </div>
    `;

    footerHtml = `
      <div class="text-[11px] text-slate-500 font-medium">
        共 <strong class="text-slate-800">${block.unitCount}</strong> 個共筆單元 ・ <strong class="text-slate-800">${totalQ}</strong> 題
      </div>
      <span class="text-xs font-bold text-indigo-700 shrink-0">進入系統作題 →</span>
    `;
  } else {
    footerHtml = `
      <div class="text-[11px] text-slate-500">${escapeHtml(block.sourceHint || '尚未匯入共筆題庫')}</div>
      <span class="text-[11px] font-semibold text-slate-400 shrink-0">敬請期待</span>
    `;
  }

  return `
    <button
      type="button"
      data-block-slug="${escapeHtml(block.slug)}"
      data-block-status="${escapeHtml(block.status)}"
      data-block-name="${escapeHtml(block.name)}"
      class="block-card ${isReady ? 'block-card-ready' : 'block-card-planned'}"
    >
      <div class="block-card-stripe block-accent-${accent}"></div>
      <div class="block-card-body">
        <div class="block-card-top">
          <div class="flex items-start gap-3 min-w-0">
            <div class="block-icon-box block-icon-${accent}">${escapeHtml(block.icon || '📚')}</div>
            <div class="space-y-0.5 min-w-0">
              ${
                block.examLabel
                  ? `<div class="text-[11px] font-bold text-indigo-700">${escapeHtml(block.examLabel)}</div>`
                  : ''
              }
              <h3 class="text-base font-bold text-slate-900 leading-snug">${escapeHtml(block.name)}</h3>
              ${
                block.englishName
                  ? `<div class="text-[11px] text-slate-400 font-medium">${escapeHtml(block.englishName)}</div>`
                  : ''
              }
            </div>
          </div>
          ${statusBadgeHtml}
        </div>

        ${
          block.description
            ? `<p class="text-xs text-slate-600 leading-relaxed">${escapeHtml(block.description)}</p>`
            : ''
        }

        ${subjectsHtml ? `<div class="flex flex-wrap gap-1.5">${subjectsHtml}</div>` : ''}

        ${progressBlockHtml}
      </div>
      <div class="block-card-footer">
        ${footerHtml}
      </div>
    </button>
  `;
}

export function renderBlockPortal() {
  const catalog = state.blocksCatalog;
  if (!catalog) return;

  const titleEl = document.getElementById('portalSiteTitle');
  const subtitleEl = document.getElementById('portalSiteSubtitle');
  const headerStatsEl = document.getElementById('portalHeaderStats');
  const metricsEl = document.getElementById('portalHeroMetrics');
  const termTabsEl = document.getElementById('portalTermTabs');
  const statusTabsEl = document.getElementById('portalStatusTabs');
  const searchInput = document.getElementById('portalSearchInput');
  const clearSearchBtn = document.getElementById('clearPortalSearchBtn');
  const resumeLastBtn = document.getElementById('portalResumeLastBtn');
  const sectionsEl = document.getElementById('portalSectionsContainer');

  if (titleEl && catalog.title) titleEl.textContent = catalog.title;
  if (subtitleEl && catalog.subtitle) subtitleEl.textContent = catalog.subtitle;
  if (headerStatsEl) {
    headerStatsEl.textContent = `已開放 ${catalog.readyBlocks}/${catalog.totalBlocks} 系統 ・ ${catalog.totalUnits} 單元 ・ ${catalog.totalQuestions} 題`;
  }

  if (metricsEl) {
    metricsEl.innerHTML = `
      <div class="portal-metric-card">
        <div class="portal-metric-val text-indigo-700">${catalog.readyBlocks}</div>
        <div class="portal-metric-label">已開放系統</div>
      </div>
      <div class="portal-metric-card">
        <div class="portal-metric-val text-slate-900">${catalog.totalUnits}</div>
        <div class="portal-metric-label">收錄共筆單元</div>
      </div>
      <div class="portal-metric-card">
        <div class="portal-metric-val text-emerald-700">${catalog.totalQuestions}</div>
        <div class="portal-metric-label">總考題數量</div>
      </div>
    `;
  }

  // Show quick resume button if the saved active exam is available & ready
  if (resumeLastBtn) {
    const savedSlug = getSavedActiveExamSlug();
    let savedReadyBlock = null;
    if (savedSlug) {
      for (const term of catalog.terms || []) {
        const match = (term.blocks || []).find(
          (b) => b.slug === savedSlug && b.status === 'ready'
        );
        if (match) {
          savedReadyBlock = match;
          break;
        }
      }
    }
    if (savedReadyBlock) {
      resumeLastBtn.textContent = `▶ 繼續：${savedReadyBlock.name}`;
      resumeLastBtn.setAttribute('data-resume-slug', savedReadyBlock.slug);
      resumeLastBtn.classList.remove('hidden');
    } else {
      resumeLastBtn.classList.add('hidden');
    }
  }

  // Term tabs
  if (termTabsEl) {
    const terms = catalog.terms || [];
    const termBtns = [
      `<button type="button" data-portal-term="ALL" class="${
        state.portalTermFilter === 'ALL'
          ? 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow-sm transition'
          : 'px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition'
      }">全部學期系統 (${catalog.totalBlocks})</button>`,
      ...terms.map((t) => {
        const isActive = state.portalTermFilter === t.code;
        return `<button type="button" data-portal-term="${escapeHtml(t.code)}" class="${
          isActive
            ? 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow-sm transition'
            : 'px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition'
        }">${escapeHtml(t.shortLabel)}（已開放 ${t.readyCount}/${t.totalCount}）</button>`;
      }),
    ];
    termTabsEl.innerHTML = termBtns.join('');
  }

  // Status filter buttons
  if (statusTabsEl) {
    const statusOpts = [
      { code: 'ALL', label: `全部系統 (${catalog.totalBlocks})` },
      { code: 'ready', label: `✓ 已開放作題 (${catalog.readyBlocks})` },
      { code: 'planned', label: `⏳ 題庫建置中 (${catalog.plannedBlocks})` },
    ];
    statusTabsEl.innerHTML = statusOpts
      .map((opt) => {
        const active = state.portalStatusFilter === opt.code;
        return `<button type="button" data-portal-status="${opt.code}" class="${
          active
            ? 'px-2.5 py-1 rounded-md text-xs font-semibold bg-slate-900 text-white shadow-sm transition'
            : 'px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-600 hover:bg-slate-200 transition'
        }">${opt.label}</button>`;
      })
      .join('');
  }

  if (searchInput && searchInput.value !== state.portalSearchQuery) {
    searchInput.value = state.portalSearchQuery;
  }
  if (clearSearchBtn) {
    clearSearchBtn.classList.toggle('hidden', !state.portalSearchQuery);
  }

  // Render filtered term sections & block cards
  if (!sectionsEl) return;
  const kw = state.portalSearchQuery.trim().toLowerCase();
  const visibleSections = [];

  for (const term of catalog.terms || []) {
    if (state.portalTermFilter !== 'ALL' && term.code !== state.portalTermFilter) {
      continue;
    }
    const matchingBlocks = (term.blocks || []).filter((blk) => {
      if (state.portalStatusFilter !== 'ALL' && blk.status !== state.portalStatusFilter) {
        return false;
      }
      return portalMatchesQuery(blk, term, kw);
    });
    if (!matchingBlocks.length) continue;

    visibleSections.push(`
      <section class="portal-term-section">
        <div class="portal-term-header">
          <div>
            <div class="flex items-center gap-2 flex-wrap">
              <span class="px-2 py-0.5 text-[11px] font-bold bg-indigo-100 text-indigo-800 rounded-md">${escapeHtml(term.shortLabel)}</span>
              <h2 class="text-base font-bold text-slate-900">${escapeHtml(term.label)}</h2>
            </div>
            ${
              term.description
                ? `<p class="text-xs text-slate-500 mt-1">${escapeHtml(term.description)}</p>`
                : ''
            }
          </div>
          <div class="text-xs text-slate-500 font-medium shrink-0">
            顯示 <strong class="text-slate-800">${matchingBlocks.length}</strong> 個系統 Block（已開放 ${term.readyCount}/${term.totalCount}）
          </div>
        </div>
        <div class="portal-card-grid">
          ${matchingBlocks.map(portalRenderBlockCard).join('')}
        </div>
      </section>
    `);
  }

  if (!visibleSections.length) {
    sectionsEl.innerHTML = `
      <div class="bg-white rounded-2xl border border-slate-200 p-10 text-center space-y-3">
        <div class="text-2xl">🗂️</div>
        <div class="text-sm font-bold text-slate-800">沒有符合目前篩選條件的整合考系統 Block</div>
        <p class="text-xs text-slate-500">請嘗試切換學期分類、開放狀態或清除搜尋關鍵字。</p>
        <div>
          <button type="button" data-action="portal-clear-filters" class="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition">顯示全部系統</button>
        </div>
      </div>
    `;
    return;
  }

  sectionsEl.innerHTML = visibleSections.join('');
}

export function initBlockPortal(onEnterExam) {
  portalOnEnterExam = onEnterExam;

  const termTabsEl = document.getElementById('portalTermTabs');
  const statusTabsEl = document.getElementById('portalStatusTabs');
  const searchInput = document.getElementById('portalSearchInput');
  const clearSearchBtn = document.getElementById('clearPortalSearchBtn');
  const resumeLastBtn = document.getElementById('portalResumeLastBtn');
  const sectionsEl = document.getElementById('portalSectionsContainer');

  if (termTabsEl) {
    termTabsEl.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-portal-term]');
      if (!btn) return;
      state.portalTermFilter = btn.getAttribute('data-portal-term') || 'ALL';
      notify();
    });
  }

  if (statusTabsEl) {
    statusTabsEl.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-portal-status]');
      if (!btn) return;
      state.portalStatusFilter = btn.getAttribute('data-portal-status') || 'ALL';
      notify();
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      state.portalSearchQuery = searchInput.value;
      notify();
    });
  }

  if (clearSearchBtn) {
    clearSearchBtn.addEventListener('click', () => {
      state.portalSearchQuery = '';
      if (searchInput) searchInput.value = '';
      notify();
    });
  }

  if (resumeLastBtn) {
    resumeLastBtn.addEventListener('click', () => {
      const slug = resumeLastBtn.getAttribute('data-resume-slug');
      if (slug && portalOnEnterExam) {
        portalOnEnterExam(slug);
      }
    });
  }

  if (sectionsEl) {
    sectionsEl.addEventListener('click', (e) => {
      const clearBtn = e.target.closest('button[data-action="portal-clear-filters"]');
      if (clearBtn) {
        portalResetFilters();
        return;
      }

      const card = e.target.closest('button[data-block-slug]');
      if (!card) return;
      const slug = card.getAttribute('data-block-slug');
      const blockStatus = card.getAttribute('data-block-status');
      const blockName = card.getAttribute('data-block-name') || slug;

      if (blockStatus === 'ready') {
        if (portalOnEnterExam) {
          portalOnEnterExam(slug);
        }
      } else {
        showToast(`「${blockName}」題庫建置中，未來匯入共筆後將自動開放作題！`);
      }
    });
  }
}
