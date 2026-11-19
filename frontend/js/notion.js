/** Notion toggle markdown formatter, clipboard helper, and file download helpers. */

import { showToast } from './components/toast.js';

export function generateNotionToggleContent(examTitle, qList) {
  const title = examTitle || '易考網互動考古題庫';
  const header = `# ${title}（共 ${qList.length} 題）\n> 💡 **使用說明**：直接貼入 Notion 後，每道題目下方皆有可展開的 **「點擊查看正解與逐項詳解」** 摺疊區塊 (Toggle)！\n\n`;
  const blocks = qList.map((q) => {
    const errTag = q.hasErrata ? ' ⚠️【申覆／爭議題】' : '';
    const optLines = Object.keys(q.options).map((k) => `- (${k}) ${q.options[k]}`);
    const lines = [
      `### [#${q.globalIndex}｜${q.unitTitle} Q${q.qNum}] 〈${q.year}〉 ${q.stem.replace(/\n/g, ' ')}${errTag}`,
      ...optLines,
      `<details><summary>💡 <strong>點擊展開【標準答案：(${q.answer})】與核心機制詳解</strong></summary>`,
      '',
      `- **【標準答案】**：${q.answerDisplay}（來源：[${q.unitTitle}（${q.prof}）共筆](${q.unitUrl})）`,
    ];
    q.explanations.forEach((exp) => {
      lines.push(`- ${exp}`);
    });
    lines.push('</details>\n');
    return lines.join('\n');
  });
  return header + blocks.join('\n');
}

function fallbackCopy(text, successMsg) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
    showToast(successMsg);
  } catch (_) {
    showToast('請手動全選預覽框文字進行複製');
  }
  document.body.removeChild(ta);
}

export function copyTextToClipboard(text, successMsg) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard
      .writeText(text)
      .then(() => showToast(successMsg))
      .catch(() => fallbackCopy(text, successMsg));
  } else {
    fallbackCopy(text, successMsg);
  }
}

export function downloadTextFile(filename, content, mimeType = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
