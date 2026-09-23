/**
 * Pixort front end — bootstrap, routing and interaction.
 *
 * The UI is a static bundle: it talks to the back end purely over HTTP, so it
 * can be hosted anywhere (see `?api=` in api.js).
 */

import { $, debounce } from './dom.js';
import { api } from './api.js';
import { scopeLabel, store } from './state.js';
import { confirmAction, toast } from './overlay.js';
import { renderRail } from './views/rail.js';
import { renderGallery } from './views/gallery.js';
import { renderDetail } from './views/detail.js';
import { openViewer } from './views/viewer.js';
import { openEditDialog } from './views/editDialog.js';
import { openImportDialog } from './views/importDialog.js';
import { openManageDialog } from './views/manageDialog.js';

const hosts = {
  artists: $('[data-artist-index]'),
  tags: $('[data-tag-index]'),
  characters: $('[data-character-index]'),
  stage: $('[data-stage]'),
  counters: $('[data-counters]'),
  status: {
    api: $('[data-status-api]'),
    scope: $('[data-status-scope]'),
    count: $('[data-status-count]'),
  },
  errorBar: $('[data-error-bar]'),
};

const PREF = {
  theme: 'pixort.theme',
  density: 'pixort.density',
  grid: 'pixort.grid',
};

/** Controller of the full-screen viewer, when it is open. */
let viewer = null;

/* -------------------------------------------------------------------------- */
/* preferences                                                                */
/* -------------------------------------------------------------------------- */

function readPref(key, fallback) {
  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writePref(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private mode - preferences simply do not persist */
  }
}

function applyTheme(mode) {
  const root = document.documentElement;
  root.dataset.themeMode = mode;
  if (mode === 'system') delete root.dataset.theme;
  else root.dataset.theme = mode;
  writePref(PREF.theme, mode);
  store.set({ theme: mode });
}

function cycleTheme() {
  const order = ['system', 'light', 'dark'];
  const next = order[(order.indexOf(store.state.theme) + 1) % order.length];
  applyTheme(next);
  toast(`主题：${{ system: '跟随系统', light: '浅色', dark: '深色' }[next]}`, { tag: '外观' });
}

function setGridVisible(visible) {
  document.body.dataset.grid = visible ? 'on' : 'off';
  gridButton.setAttribute('aria-pressed', String(visible));
  store.set({ gridVisible: visible });
  writePref(PREF.grid, visible ? 'on' : 'off');
}

function setDensity(density) {
  store.set({ density });
  writePref(PREF.density, density);
  render();
}

/* -------------------------------------------------------------------------- */
/* data loading                                                               */
/* -------------------------------------------------------------------------- */

function showError(error) {
  const bar = hosts.errorBar;
  if (!error) {
    bar.hidden = true;
    bar.replaceChildren();
    return;
  }
  bar.hidden = false;
  bar.replaceChildren(
    Object.assign(document.createElement('strong'), { textContent: '后端不可用' }),
    document.createTextNode(` ${error.message}`),
    Object.assign(document.createElement('span'), {
      textContent: ` · 目标 ${api.base || window.location.origin}`,
    }),
  );
}

async function loadLibrary() {
  const [health, stats, artists, characters, tags] = await Promise.all([
    api.health(),
    api.stats(),
    api.artists(),
    api.characters(),
    api.tags(),
  ]);
  store.set({
    ready: true,
    error: null,
    health,
    stats,
    artists: artists.items,
    characters: characters.items,
    tags: tags.items,
  });
  updateCounters();
  renderRail(hosts, store.state, handlers);
}

/** The tree is only needed for the expandable index, so it loads separately. */
async function loadTree() {
  try {
    const { artists } = await api.tree();
    store.set({ tree: artists });
    renderRail(hosts, store.state, handlers);
  } catch (error) {
    /* the rail degrades to a flat artist list */
  }
}

function activeFilters(extra = {}) {
  const { filters } = store.state;
  return {
    q: filters.q || undefined,
    artist_id: filters.artistId ?? undefined,
    character_id: filters.characterId ?? undefined,
    tag: filters.tag ?? undefined,
    rating_min: filters.ratingMin ?? undefined,
    unassigned: filters.unassigned ? 1 : undefined,
    sort: filters.sort,
    limit: filters.limit,
    offset: filters.offset,
    ...extra,
  };
}

async function loadItems({ append = false } = {}) {
  store.set({ loading: true });
  if (!append) render();
  try {
    const payload = await api.illustrations(activeFilters());
    const items = append ? [...store.state.items, ...payload.items] : payload.items;
    store.set({ items, total: payload.total, loading: false, error: null });
    showError(null);
  } catch (error) {
    store.set({ loading: false, items: [], total: 0, error });
    showError(error);
  }
  updateStatus();
  render();
}

async function openWork(id) {
  store.set({ selectedId: id, detail: null, view: 'detail', loading: true });
  render();
  try {
    const item = await api.illustration(id);
    store.set({ detail: item, loading: false });
  } catch (error) {
    store.set({ detail: null, loading: false });
    toast(error.message, { tag: '读取失败', kind: 'error' });
  }
  if (window.location.hash !== `#/work/${id}`) window.location.hash = `#/work/${id}`;
  updateStatus();
  render();
  return store.state.detail;
}

function closeDetail() {
  store.set({ view: 'gallery', selectedId: null, detail: null });
  if (window.location.hash.startsWith('#/work/')) {
    history.pushState(null, '', window.location.pathname + window.location.search);
  }
  updateStatus();
  render();
}

/** Availability of the neighbours of one work inside the current result list. */
function viewerNav(item) {
  const index = store.state.items.findIndex((entry) => entry.id === item.id);
  return {
    hasPrev: index > 0,
    hasNext: index >= 0 && index < store.state.items.length - 1,
  };
}

async function step(direction) {
  const index = store.state.items.findIndex((entry) => entry.id === store.state.selectedId);
  const next = store.state.items[index + direction];
  if (!next) return;
  const item = await openWork(next.id);
  // keep the full-screen viewer in sync when stepping from inside it
  if (item && viewer && !viewer.closed) viewer.update(item, viewerNav(item));
}

/* -------------------------------------------------------------------------- */
/* rendering                                                                  */
/* -------------------------------------------------------------------------- */

function render() {
  const state = store.state;
  if (state.view === 'detail') {
    renderDetail(hosts.stage, state, handlers);
  } else {
    renderGallery(hosts.stage, state, handlers);
  }
  renderRail(hosts, state, handlers);
}

function updateCounters() {
  const stats = store.state.stats;
  if (!stats) return;
  for (const node of hosts.counters.querySelectorAll('[data-count]')) {
    const key = node.dataset.count;
    if (key === 'missing') node.textContent = String(stats.missing_files ?? 0);
    else node.textContent = String(stats[key] ?? '—');
  }
}

function updateStatus() {
  const state = store.state;
  hosts.status.api.textContent = state.health
    ? `接口 v${state.health.version} · ${state.health.thumbnailer === 'pillow' ? '缩略图可用' : '缩略图不可用'}`
    : '接口 —';
  hosts.status.scope.textContent = state.view === 'detail' ? '作品详情' : scopeLabel(state);
  hosts.status.count.textContent = `${state.total} 件`;
}

/* -------------------------------------------------------------------------- */
/* actions                                                                    */
/* -------------------------------------------------------------------------- */

const handlers = {
  isSelected: (id) => store.state.selectedId === id,

  rerender: () => render(),

  selectArtist(artist) {
    store.patchFilters({
      artistId: artist ? artist.id : null,
      artistName: artist ? artist.name : null,
      unassigned: false,
      offset: 0,
    });
    closeDetail();
    loadItems();
  },

  selectUnassigned() {
    store.patchFilters({ artistId: null, artistName: null, unassigned: true, offset: 0 });
    closeDetail();
    loadItems();
  },

  selectTag(tag) {
    const current = store.state.filters.tag;
    store.patchFilters({ tag: current === tag ? null : tag, offset: 0 });
    closeDetail();
    loadItems();
  },

  selectCharacter(id) {
    const current = store.state.filters.characterId;
    store.patchFilters({ characterId: current === id ? null : id, offset: 0 });
    closeDetail();
    loadItems();
  },

  setDensity,

  clearFilters() {
    store.resetFilters();
    searchInput.value = '';
    sortSelect.value = store.state.filters.sort;
    for (const button of document.querySelectorAll('[data-rating-filter] .segmented__item')) {
      button.setAttribute('aria-pressed', String(button.dataset.rating === ''));
    }
    closeDetail();
    loadItems();
  },

  openWork,
  closeDetail,
  step,

  openViewer(item) {
    viewer = openViewer(item, {
      ...viewerNav(item),
      onPrev: () => step(-1),
      onNext: () => step(1),
    });
  },

  edit(item) {
    openEditDialog(item, {
      artists: store.state.artists,
      characters: store.state.characters,
      onSaved: async () => {
        await Promise.all([loadLibrary(), loadItems()]);
        openWork(item.id);
      },
    });
  },

  async remove(item) {
    const ok = await confirmAction({
      title: '删除作品',
      message: `「${item.title || item.file_name}」的记录会被删除，图片会移入归档目录而不是直接销毁。`,
      confirm: '删除',
      danger: true,
    });
    if (!ok) return;
    try {
      const result = await api.deleteIllustration(item.id, 'archive');
      toast(
        result.file_action.mode === 'archived'
          ? '记录已删除，图片已归档'
          : '记录已删除（文件未找到）',
        { tag: '删除' },
      );
      closeDetail();
      await Promise.all([loadLibrary(), loadItems()]);
    } catch (error) {
      toast(error.message, { tag: '删除失败', kind: 'error' });
    }
  },

  loadMore() {
    store.patchFilters({ offset: store.state.items.length });
    loadItems({ append: true });
  },
};

/* -------------------------------------------------------------------------- */
/* wiring                                                                     */
/* -------------------------------------------------------------------------- */

const searchInput = $('[data-search]');
const sortSelect = $('[data-sort]');
const gridButton = $('[data-action="grid-mode"]');

searchInput.addEventListener(
  'input',
  debounce((event) => {
    store.patchFilters({ q: event.target.value.trim(), offset: 0 });
    loadItems();
  }, 260),
);

sortSelect.addEventListener('change', (event) => {
  store.patchFilters({ sort: event.target.value, offset: 0 });
  loadItems();
});

for (const button of document.querySelectorAll('[data-rating-filter] .segmented__item')) {
  button.addEventListener('click', () => {
    for (const sibling of document.querySelectorAll('[data-rating-filter] .segmented__item')) {
      sibling.setAttribute('aria-pressed', String(sibling === button));
    }
    const value = button.dataset.rating;
    store.patchFilters({ ratingMin: value ? Number(value) : null, offset: 0 });
    loadItems();
  });
}

$('[data-action="import"]').addEventListener('click', () => {
  openImportDialog({
    artists: store.state.artists,
    characters: store.state.characters,
    onDone: async () => {
      await Promise.all([loadLibrary(), loadItems()]);
      loadTree();
    },
  });
});

$('[data-action="manage"]').addEventListener('click', () => {
  openManageDialog({
    onChanged: async () => {
      await Promise.all([loadLibrary(), loadItems()]);
    },
  });
});

$('[data-action="theme"]').addEventListener('click', cycleTheme);

gridButton.addEventListener('click', () => setGridVisible(!store.state.gridVisible));

document.addEventListener('keydown', (event) => {
  const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName);
  if (event.key === '/' && !typing) {
    event.preventDefault();
    searchInput.focus();
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    searchInput.focus();
    return;
  }
  if (typing || event.ctrlKey || event.metaKey || event.altKey) return;

  const key = event.key.toLowerCase();
  if (key === 'g') {
    setGridVisible(!store.state.gridVisible);
  } else if (key === 'i') {
    $('[data-action="import"]').click();
  } else if (key === 'm') {
    $('[data-action="manage"]').click();
  } else if (key === 'v') {
    const order = ['grid', 'roomy', 'compact', 'rows'];
    setDensity(order[(order.indexOf(store.state.density) + 1) % order.length]);
  } else if (key === 'escape' && store.state.view === 'detail') {
    closeDetail();
  }
});

window.addEventListener('hashchange', route);

function route() {
  const match = window.location.hash.match(/^#\/work\/(\d+)$/);
  if (match) {
    const id = Number(match[1]);
    if (id !== store.state.selectedId) openWork(id);
    return;
  }
  if (store.state.view === 'detail') {
    store.set({ view: 'gallery', selectedId: null, detail: null });
    render();
  }
}

/* -------------------------------------------------------------------------- */
/* start                                                                      */
/* -------------------------------------------------------------------------- */

async function boot() {
  applyTheme(readPref(PREF.theme, 'system'));
  setDensity(readPref(PREF.density, 'grid'));
  setGridVisible(readPref(PREF.grid, 'off') === 'on');

  try {
    await loadLibrary();
    await loadItems();
    route(); // honour a deep link such as #/work/16 on first paint
    loadTree();
  } catch (error) {
    showError(error);
    store.set({ loading: false });
    render();
  }
}

boot();
