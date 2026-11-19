/** Floating toast notification helper. */

let toastTimer = null;

export function showToast(msg) {
  const toast = document.getElementById('toastNotice');
  const text = document.getElementById('toastMessage');
  if (!toast || !text) return;
  text.textContent = msg;
  toast.classList.remove('hidden');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.add('hidden');
  }, 2800);
}
