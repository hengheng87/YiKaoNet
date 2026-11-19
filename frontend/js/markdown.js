/** Safe HTML-escaped inline Markdown renderer matching v1.0.6 formatting. */

export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function formatMarkdownInline(str) {
  if (!str) return '';
  const escaped = escapeHtml(str).replace(/\n/g, '<br/>');
  return escaped
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-indigo-600 underline hover:text-indigo-800">$1</a>'
    )
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-bold text-slate-900">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(
      /`([^`]+)`/g,
      '<code class="px-1.5 py-0.5 bg-slate-100 text-indigo-700 rounded text-[11px] font-mono">$1</code>'
    );
}
