/** Question card renderer and delegated click handling. */

import { escapeHtml, formatMarkdownInline } from '../markdown.js';
import { generateNotionToggleContent, copyTextToClipboard } from '../notion.js';
import {
  getFilteredQuestions,
  isAnswerCorrect,
  resetSingleAnswer,
  selectOption,
  state,
  toggleExplanation,
  toggleStar,
} from '../store.js';

export function initQuestionList() {
  const container = document.getElementById('questionsContainer');
  container.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const action = btn.getAttribute('data-action');
    const qid = btn.getAttribute('data-qid');

    if (action === 'select-option') {
      selectOption(qid, btn.getAttribute('data-opt'));
    } else if (action === 'toggle-expl') {
      toggleExplanation(qid);
    } else if (action === 'toggle-star') {
      toggleStar(qid);
    } else if (action === 'reset-single') {
      resetSingleAnswer(qid);
    } else if (action === 'copy-single-notion') {
      const q = state.questionById.get(qid);
      if (q) {
        const text = generateNotionToggleContent(state.examDetail?.title, [q]);
        copyTextToClipboard(text, `已複製第 #${q.globalIndex} 題 Notion 摺疊格式！`);
      }
    }
  });
}

export function renderQuestions() {
  const filtered = getFilteredQuestions();
  document.getElementById('filteredCount').textContent = String(filtered.length);

  const container = document.getElementById('questionsContainer');
  if (!state.examDetail) {
    container.innerHTML = '';
    return;
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="bg-white rounded-xl border border-slate-200 p-10 text-center space-y-2">
        <div class="text-2xl">🔍</div>
        <div class="text-sm font-bold text-slate-800">沒有符合目前篩選條件的整合考考古題</div>
        <p class="text-xs text-slate-500">請嘗試切換上方科目／共筆單元標籤、狀態篩選或清除搜尋關鍵字。</p>
      </div>
    `;
    return;
  }

  const showGrading = state.mode === 'practice' || state.examSubmitted;

  const cardsHtml = filtered
    .map((q) => {
      const chosen = state.userAnswers[q.id];
      const isStarred = !!state.starred[q.id];
      const isExplOpen = !!state.expandedExpl[q.id];
      const isCorrect = isAnswerCorrect(q, chosen);

      let statusBadge = '';
      if (chosen && showGrading) {
        if (isCorrect) {
          statusBadge = `<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800">✓ 答對（您的選擇：${escapeHtml(chosen)}）</span>`;
        } else {
          statusBadge = `<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800">✗ 答錯（您的選擇：${escapeHtml(chosen)}｜標準答案：${escapeHtml(q.answer)}）</span>`;
        }
      } else if (chosen && !showGrading) {
        statusBadge = `<span class="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-100 text-indigo-800">已選 (${escapeHtml(chosen)})・待交卷</span>`;
      }

      const errataBadge = q.hasErrata
        ? `<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-900 border border-amber-300">⚠️ 申覆多解／送分／爭議題</span>`
        : '';

      const sessionBadge =
        q.session === 'A'
          ? `<span class="px-2 py-0.5 rounded-md text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">第一節 A卷・${escapeHtml(q.subjectTitle)}</span>`
          : `<span class="px-2 py-0.5 rounded-md text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">第二節 B卷・${escapeHtml(q.subjectTitle)}</span>`;

      const optionsHtml = Object.keys(q.options)
        .map((letter) => {
          const optText = q.options[letter] || '';
          const isThisChosen = chosen === letter;
          const isThisAccepted = q.acceptedAnswers.includes(letter);
          const isPrimaryAnswer = q.answer === letter;

          let btnStyle = 'bg-slate-50 hover:bg-indigo-50/60 border-slate-200 text-slate-800';
          let badgeStyle = 'bg-white border border-slate-300 text-slate-700';
          let rightIcon = '';

          if (chosen) {
            if (showGrading) {
              if (isPrimaryAnswer || (isThisChosen && isThisAccepted)) {
                btnStyle =
                  'bg-emerald-50 border-emerald-500 text-emerald-950 font-semibold ring-1 ring-emerald-500';
                badgeStyle = 'bg-emerald-600 text-white border-emerald-600';
                rightIcon = `<span class="text-emerald-700 font-bold text-xs shrink-0">✓ 正解</span>`;
              } else if (isThisChosen && !isThisAccepted) {
                btnStyle =
                  'bg-rose-50 border-rose-400 text-rose-950 ring-1 ring-rose-400';
                badgeStyle = 'bg-rose-600 text-white border-rose-600';
                rightIcon = `<span class="text-rose-700 font-bold text-xs shrink-0">✗ 誤選</span>`;
              } else if (isThisAccepted) {
                btnStyle = 'bg-amber-50/70 border-amber-400 text-amber-950';
                badgeStyle = 'bg-amber-500 text-white border-amber-500';
                rightIcon = `<span class="text-amber-800 font-semibold text-[11px] shrink-0">申覆亦給分</span>`;
              } else {
                btnStyle = 'bg-white border-slate-200 text-slate-500 opacity-80';
              }
            } else if (isThisChosen) {
              btnStyle =
                'bg-indigo-50 border-indigo-500 text-indigo-950 font-semibold ring-1 ring-indigo-500';
              badgeStyle = 'bg-indigo-600 text-white border-indigo-600';
            }
          }

          return `
            <button
              type="button"
              data-action="select-option"
              data-qid="${escapeHtml(q.id)}"
              data-opt="${escapeHtml(letter)}"
              class="option-btn w-full text-left p-3 rounded-xl border ${btnStyle} flex items-start justify-between gap-3"
            >
              <div class="flex items-start gap-2.5 text-xs md:text-sm leading-relaxed">
                <span class="w-6 h-6 rounded-lg text-xs font-bold flex items-center justify-center shrink-0 mt-0.5 ${badgeStyle}">${escapeHtml(letter)}</span>
                <span>${formatMarkdownInline(optText)}</span>
              </div>
              ${rightIcon}
            </button>
          `;
        })
        .join('');

      const explItemsHtml = q.explanations
        .map((line) => {
          const isWarn = line.includes('⚠️');
          const isCorrectLine =
            line.startsWith(`**(${q.answer})`) || line.includes('【本題應選正解】');
          const isCoreMech = line.includes('【核心觀念與機制詳解】');
          let itemClass = 'text-slate-700 border-l-2 border-slate-300 pl-3 py-0.5';
          if (isWarn) {
            itemClass =
              'bg-amber-50 border-l-4 border-amber-500 p-2.5 rounded-r-lg text-amber-950';
          } else if (isCorrectLine) {
            itemClass =
              'bg-emerald-50/70 border-l-4 border-emerald-500 p-2 rounded-r-lg text-emerald-950';
          } else if (isCoreMech) {
            itemClass =
              'bg-indigo-50/70 border-l-4 border-indigo-500 p-2.5 rounded-r-lg text-indigo-950';
          }
          return `<div class="${itemClass} text-xs leading-relaxed">${formatMarkdownInline(line)}</div>`;
        })
        .join('');

      const imageHtml = q.image
        ? `<div class="my-2 flex justify-center bg-slate-50 border border-slate-200 rounded-xl p-3">
             <img src="${escapeHtml(q.image)}" alt="考題附圖" loading="lazy" class="max-h-72 w-auto rounded-lg shadow-sm" />
           </div>`
        : '';

      return `
        <article id="card-${escapeHtml(q.id)}" data-qid="${escapeHtml(q.id)}" class="bg-white rounded-2xl border ${q.hasErrata ? 'border-amber-300' : 'border-slate-200'} p-4 md:p-5 shadow-sm space-y-3.5">
          <div class="flex items-center justify-between gap-2 flex-wrap border-b border-slate-100 pb-2.5">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="px-2 py-0.5 rounded-md text-xs font-bold bg-slate-900 text-white">#${q.globalIndex}</span>
              ${sessionBadge}
              <a href="${escapeHtml(q.unitUrl)}" target="_blank" rel="noopener noreferrer" class="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition">
                📄 ${escapeHtml(q.unitTitle)}（${escapeHtml(q.prof)}）・第 ${q.qNum} 題 ↗
              </a>
              <span class="px-2 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-600">${escapeHtml(q.year)}</span>
              ${errataBadge}
              ${statusBadge}
            </div>

            <div class="flex items-center gap-1.5">
              ${chosen ? `<button type="button" data-action="reset-single" data-qid="${escapeHtml(q.id)}" class="px-2 py-1 rounded-lg text-[11px] font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition">重答</button>` : ''}
              <button type="button" data-action="toggle-star" data-qid="${escapeHtml(q.id)}" class="px-2.5 py-1 rounded-lg text-xs font-semibold border ${isStarred ? 'bg-amber-50 border-amber-300 text-amber-700' : 'bg-white border-slate-200 text-slate-500 hover:bg-slate-50'} transition">
                ${isStarred ? '⭐ 已收藏' : '☆ 收藏'}
              </button>
              <button type="button" data-action="toggle-expl" data-qid="${escapeHtml(q.id)}" class="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition">
                ${isExplOpen ? '▲ 收合詳解' : '▼ 查看詳解'}
              </button>
            </div>
          </div>

          <div class="text-sm md:text-base font-semibold text-slate-900 leading-relaxed">
            ${formatMarkdownInline(q.stem)}
          </div>

          ${imageHtml}

          <div class="grid grid-cols-1 gap-2">
            ${optionsHtml}
          </div>

          <div class="${isExplOpen ? 'block' : 'hidden'} explanation-box pt-2">
            <div class="rounded-xl border ${chosen && showGrading ? (isCorrect ? 'bg-emerald-50/40 border-emerald-300' : 'bg-rose-50/40 border-rose-300') : 'bg-slate-50 border-slate-200'} p-3.5 space-y-2.5">
              ${
                chosen && showGrading
                  ? `
                <div class="flex items-center justify-between flex-wrap gap-2 px-3 py-2 rounded-lg ${isCorrect ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'} text-xs font-bold">
                  <div>
                    ${
                      isCorrect
                        ? `🎉 答對了！您選擇了 (${escapeHtml(chosen)})，標準答案為 (${escapeHtml(q.answer)})`
                        : `❌ 答錯了！您選擇了 (${escapeHtml(chosen)})，正確標準答案應為 (${escapeHtml(q.answer)})`
                    }
                  </div>
                  <div class="text-[11px] opacity-95">${formatMarkdownInline(q.answerDisplay)}</div>
                </div>
              `
                  : ''
              }
              <div class="flex items-center justify-between flex-wrap gap-2 border-b border-slate-200 pb-2">
                <div class="text-xs font-bold text-indigo-950 flex items-center gap-1.5">
                  <span>💡 正解與各選項逐項詳解：</span>
                  <span class="text-emerald-700">${formatMarkdownInline(q.answerDisplay)}</span>
                </div>
                <button type="button" data-action="copy-single-notion" data-qid="${escapeHtml(q.id)}" class="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">
                  📋 複製此題 Notion 格式
                </button>
              </div>
              <div class="space-y-2">
                ${explItemsHtml}
              </div>
            </div>
          </div>
        </article>
      `;
    })
    .join('');

  container.innerHTML = cardsHtml;
}
