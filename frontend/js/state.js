/** A minimal observable store - enough structure, no framework. */

const initialState = {
  ready: false,
  error: null,
  health: null,
  stats: null,
  artists: [],
  characters: [],
  tags: [],
  items: [],
  total: 0,
  loading: false,
  view: 'gallery',
  selectedId: null,
  detail: null,
  tree: null,
  filters: {
    q: '',
    artistId: null,
    artistName: null,
    unassigned: false,
    characterId: null,
    tag: null,
    ratingMin: null,
    sort: 'created_desc',
    limit: 120,
    offset: 0,
  },
  density: 'grid',
  theme: 'system',
  gridVisible: false,
};

const listeners = new Set();

export const store = {
  state: { ...initialState },

  subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  set(patch) {
    Object.assign(this.state, patch);
    for (const listener of listeners) listener(this.state);
  },

  patchFilters(patch) {
    this.state.filters = { ...this.state.filters, ...patch };
    this.set({});
  },

  resetFilters() {
    this.state.filters = { ...initialState.filters };
    this.set({});
  },

};

/** Human-readable description of the active filter set. */
export function scopeLabel(state) {
  const { filters } = state;
  if (filters.tag) return `标签 · ${filters.tag}`;
  if (filters.characterId) {
    const character = state.characters.find((entry) => entry.id === filters.characterId);
    return `角色 · ${character ? character.name : filters.characterId}`;
  }
  if (filters.unassigned) return '未分类作品';
  if (filters.artistName) return `画师 · ${filters.artistName}`;
  if (filters.q) return `搜索 · ${filters.q}`;
  return '全部作品';
}
