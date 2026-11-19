/** Client data fetchers supporting FastAPI backend, GitHub Pages static site, and single-file offline HTML. */

export function isOfflineMode() {
  return Boolean(typeof window !== 'undefined' && window.__YIKAO_OFFLINE_DATA__);
}

export function isStaticSiteMode() {
  return Boolean(typeof window !== 'undefined' && window.__YIKAO_STATIC_MODE__);
}

export function isLocalOnlyMode() {
  return isOfflineMode() || isStaticSiteMode();
}

async function requestJson(url, options = {}) {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch (_) {
      // Ignore parse errors on error bodies
    }
    throw new Error(detail);
  }
  return res.json();
}

export function fetchExams() {
  if (isOfflineMode()) {
    return Promise.resolve(window.__YIKAO_OFFLINE_DATA__.exams || []);
  }
  if (isStaticSiteMode()) {
    return requestJson('./static-api/exams.json');
  }
  return requestJson('/api/exams');
}

export function fetchExamDetail(slug) {
  if (isOfflineMode()) {
    const detail = window.__YIKAO_OFFLINE_DATA__.details?.[slug];
    if (!detail) return Promise.reject(new Error(`找不到題庫：${slug}`));
    return Promise.resolve(detail);
  }
  if (isStaticSiteMode()) {
    return requestJson(`./static-api/exams/${encodeURIComponent(slug)}/detail.json`);
  }
  return requestJson(`/api/exams/${encodeURIComponent(slug)}`);
}

export function fetchQuestions(slug, params = {}) {
  if (isOfflineMode()) {
    const list = window.__YIKAO_OFFLINE_DATA__.questions?.[slug] || [];
    return Promise.resolve({
      examSlug: slug,
      total: list.length,
      filtered: list.length,
      questions: list,
    });
  }
  if (isStaticSiteMode()) {
    return requestJson(`./static-api/exams/${encodeURIComponent(slug)}/questions.json`);
  }
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      qs.set(k, String(v));
    }
  });
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return requestJson(`/api/exams/${encodeURIComponent(slug)}/questions${suffix}`);
}

export function getOfflineHtmlDownloadUrl(slug) {
  if (isStaticSiteMode()) {
    return `./static-api/exams/${encodeURIComponent(slug)}/offline.html`;
  }
  return `/api/exams/${encodeURIComponent(slug)}/export/offline-html`;
}

export function generateSyncCode() {
  return requestJson('/api/progress/generate-code', { method: 'POST' });
}

export function fetchCloudProgress(syncCode, slug) {
  return requestJson(
    `/api/progress/${encodeURIComponent(syncCode)}/${encodeURIComponent(slug)}`
  );
}

export function saveCloudProgress(syncCode, slug, payload) {
  return requestJson(
    `/api/progress/${encodeURIComponent(syncCode)}/${encodeURIComponent(slug)}`,
    { method: 'PUT', body: JSON.stringify(payload) }
  );
}

export function mergeCloudProgress(syncCode, slug, payload) {
  return requestJson(
    `/api/progress/${encodeURIComponent(syncCode)}/${encodeURIComponent(slug)}/merge`,
    { method: 'POST', body: JSON.stringify(payload) }
  );
}

export function deleteCloudProgress(syncCode, slug, keepStarred = true) {
  return requestJson(
    `/api/progress/${encodeURIComponent(syncCode)}/${encodeURIComponent(slug)}?keep_starred=${keepStarred}`,
    { method: 'DELETE' }
  );
}

export function exportNotionApi(slug, body) {
  return requestJson(`/api/exams/${encodeURIComponent(slug)}/export/notion`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
