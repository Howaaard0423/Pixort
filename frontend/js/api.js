/**
 * HTTP client for the Pixort backend.
 *
 * The front end is served by the backend in the default setup, but it is a
 * standalone static app: point it at another host with `?api=https://…` or by
 * setting `window.PIXORT_API_BASE` before this module loads.
 *
 * When there is no backend at all - the GitHub Pages build, or any `?demo=1`
 * link - the same interface is served from the bundled data in `demo.js`.
 */

import { demoApi } from './demo.js';

/**
 * GitHub Pages only serves static files, so the published site runs on the
 * bundled sample library. `?demo=0` and an explicit `?api=` always win.
 */
const IS_DEMO = (() => {
  const params = new URLSearchParams(window.location.search);
  const flag = params.get('demo');
  if (flag !== null) return !['0', 'false', 'off'].includes(flag.trim().toLowerCase());
  if (params.get('api')) return false;
  if (window.PIXORT_DEMO === true) return true;
  return window.location.protocol === 'file:' || window.location.hostname.endsWith('github.io');
})();

const BASE = (() => {
  const override = new URLSearchParams(window.location.search).get('api');
  if (override) return override.replace(/\/+$/, '');
  if (typeof window.PIXORT_API_BASE === 'string' && window.PIXORT_API_BASE) {
    return window.PIXORT_API_BASE.replace(/\/+$/, '');
  }
  const meta = document.querySelector('meta[name="pixort-api"]');
  if (meta && meta.content) return meta.content.replace(/\/+$/, '');
  return '';
})();

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

async function request(path, { method = 'GET', body, headers = {}, raw = false } = {}) {
  const init = { method, headers: { ...headers } };
  if (body !== undefined) {
    if (body instanceof FormData) init.body = body;
    else {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
  }

  let response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch (cause) {
    throw new ApiError('无法连接后端服务，请确认 API 已启动。', 0, cause);
  }

  if (raw) {
    if (!response.ok) throw new ApiError(`下载失败 (${response.status})`, response.status);
    return response;
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const message = payload?.error?.message || `请求失败 (${response.status})`;
    throw new ApiError(message, response.status, payload?.error?.details);
  }
  return payload;
}

function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === null || value === undefined || value === '' || value === false) continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

function mediaUrl(path) {
  return path ? `${BASE}${path}` : '';
}

/** Make `/api/...` media paths valid from whatever origin hosts this bundle. */
function absolutise(item) {
  if (!item) return item;
  return {
    ...item,
    url: mediaUrl(item.url),
    thumbnail_url: mediaUrl(item.thumbnail_url),
    download_url: mediaUrl(item.download_url),
  };
}

function absolutiseList(payload) {
  if (!payload) return payload;
  return {
    ...payload,
    items: (payload.items || []).map(absolutise),
    illustrations: (payload.illustrations || []).map(absolutise),
  };
}

const liveApi = {
  base: BASE,

  health: () => request('/api/health'),
  stats: () => request('/api/stats'),

  artists: () => request('/api/artists'),
  createArtist: (name) => request('/api/artists', { method: 'POST', body: { name } }),
  renameArtist: (id, name) => request(`/api/artists/${id}`, { method: 'PATCH', body: { name } }),
  deleteArtist: (id, deleteFiles = true) =>
    request(`/api/artists/${id}${query({ delete_files: deleteFiles })}`, { method: 'DELETE' }),
  mergeArtist: (sourceId, targetId) =>
    request('/api/artists/merge', { method: 'POST', body: { source_id: sourceId, target_id: targetId } }),

  characters: () => request('/api/characters'),
  createCharacter: (name) => request('/api/characters', { method: 'POST', body: { name } }),
  renameCharacter: (id, name) => request(`/api/characters/${id}`, { method: 'PATCH', body: { name } }),
  deleteCharacter: (id) => request(`/api/characters/${id}`, { method: 'DELETE' }),

  tree: async () => {
    const payload = await request('/api/tree');
    return {
      ...payload,
      artists: (payload.artists || []).map((artist) => ({
        ...artist,
        illustrations: (artist.illustrations || []).map(absolutise),
      })),
    };
  },
  tags: () => request('/api/tags'),

  illustrations: async (filters = {}) =>
    absolutiseList(await request(`/api/illustrations${query(filters)}`)),
  illustration: async (id) => absolutise(await request(`/api/illustrations/${id}`)),
  updateIllustration: (id, changes) =>
    request(`/api/illustrations/${id}`, { method: 'PATCH', body: changes }),
  deleteIllustration: (id, fileMode = 'archive') =>
    request(`/api/illustrations/${id}${query({ file: fileMode })}`, { method: 'DELETE' }),
  bulkUpdate: async (payload) =>
    absolutiseList(await request('/api/illustrations/bulk-update', { method: 'POST', body: payload })),
  scanLocal: (paths, recursive = true) =>
    request('/api/illustrations/scan-local', { method: 'POST', body: { paths, recursive } }),
  importLocal: (payload) => request('/api/illustrations/import-local', { method: 'POST', body: payload }),

  maintenance: (payload) => request('/api/library/maintenance', { method: 'POST', body: payload }),

  exportUrl: (params = {}) => `${BASE}/api/transfer/export${query(params)}`,
  exportFileUrl: (name) => `${BASE}/api/transfer/exports/${encodeURIComponent(name)}`,
  exports: () => request('/api/transfer/exports'),
  clearExports: () => request('/api/transfer/exports', { method: 'DELETE' }),

  /** Backup files travel as multipart, so they are not read into JSON. */
  inspectBackupFile(file, { password } = {}) {
    const form = new FormData();
    form.append('archive', file, file.name);
    return request(`/api/transfer/inspect${query({ password })}`, { method: 'POST', body: form });
  },
  restoreBackupFile(file, { password, confirm } = {}) {
    const form = new FormData();
    form.append('archive', file, file.name);
    return request(`/api/transfer/restore${query({ password, confirm })}`, { method: 'POST', body: form });
  },

  mediaUrl,

  /**
   * Multipart upload with real progress. `XMLHttpRequest` is used because
   * `fetch` cannot report upload progress.
   */
  upload(files, fields, onProgress) {
    const form = new FormData();
    for (const [key, value] of Object.entries(fields)) {
      if (value !== null && value !== undefined && value !== '') form.append(key, String(value));
    }
    for (const entry of files) {
      form.append('files', entry.file, entry.file.name);
      form.append('relative_path', entry.relativePath || '');
    }

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${BASE}/api/illustrations/upload`);
      xhr.upload.addEventListener('progress', (event) => {
        if (onProgress && event.lengthComputable) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      });
      xhr.addEventListener('load', () => {
        let payload = null;
        try {
          payload = JSON.parse(xhr.responseText);
        } catch {
          payload = null;
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(absolutiseList(payload));
        else reject(new ApiError(payload?.error?.message || `上传失败 (${xhr.status})`, xhr.status));
      });
      xhr.addEventListener('error', () => reject(new ApiError('上传失败：网络中断', 0)));
      xhr.send(form);
    });
  },
};

/** What every view imports; swapped for the offline client in demo mode. */
export const api = IS_DEMO ? demoApi : liveApi;
export const isDemo = IS_DEMO;
