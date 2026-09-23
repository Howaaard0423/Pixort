/**
 * Offline demo data.
 *
 * GitHub Pages can only serve static files, so the published site runs on this
 * module instead of the HTTP API: the catalogue below is generated in memory,
 * the pictures are the SVG tiles in `frontend/demo/`, and every write action is
 * applied to that in-memory list only.
 *
 * It is selected by `js/api.js` when:
 *   - the URL carries `?demo=1` (`?demo=0` forces the real client), or
 *   - `window.PIXORT_DEMO === true` (injected by tools/build_pages.py), or
 *   - the page is opened from disk, or served from *.github.io.
 */

const VERSION = '2.0.0';
const TILES = Array.from(
  { length: 8 },
  (_, index) => `demo/tile-${String(index + 1).padStart(2, '0')}.svg`,
);

/** Fictional handles - nothing here refers to a real artist. */
const ARTISTS = ['aoba.', 'kite-lab', 'nori_04', 'Yuki M.'];
const CHARACTERS = ['Aster', 'Kuro', 'Nagi', 'Shiro'];

/** [title, artist, character, tags, rating, day, width, height, MB] */
const CATALOGUE = [
  ['Inverted World-0001', 'aoba.', 'Aster', ['科幻', '练习'], 5, '2026-05-22', 4000, 4000, 1.8],
  ['Inverted World-0002', 'aoba.', 'Aster', ['科幻'], 5, '2026-05-22', 4096, 2305, 2.4],
  ['Singularity', 'aoba.', 'Kuro', ['科幻', '夜景'], 4, '2026-05-23', 2387, 1455, 1.1],
  ['夏', 'aoba.', 'Kuro', ['風景', '练习'], 3, '2026-04-02', 2808, 2862, 3.2],
  ['虚空の夢', 'kite-lab', 'Nagi', ['風景'], 5, '2026-03-18', 1650, 1308, 0.9],
  ['Solitary Drift', 'kite-lab', 'Nagi', ['科幻', '夜景'], 4, '2026-03-18', 1920, 1080, 1.4],
  ['Paper Study 04', 'kite-lab', '', ['线稿'], 2, '2026-02-09', 1400, 1400, 0.3],
  ['Paper Study 05', 'kite-lab', '', ['线稿', '练习'], 3, '2026-02-09', 1400, 1400, 0.3],
  ['Halftone Study', 'nori_04', 'Shiro', ['练习'], 4, '2026-01-27', 2048, 2048, 1.2],
  ['Grid System', 'nori_04', 'Shiro', ['科幻', '何意味'], 5, '2026-01-27', 3000, 2000, 2.0],
  ['Type Specimen 08', 'nori_04', '', [], 3, '2025-12-11', 1800, 2400, 0.6],
  ['Rote Studie', 'Yuki M.', 'Aster', ['线稿'], 2, '2025-11-30', 1600, 1200, 0.5],
  ['Portrait 03', 'Yuki M.', 'Shiro', ['portrait'], 5, '2025-11-30', 2480, 3508, 4.1],
  ['Portrait 04', 'Yuki M.', 'Kuro', ['portrait', '练习'], 4, '2025-10-14', 2480, 3508, 3.9],
  ['Untitled 01', '', '', [], 0, '2025-09-05', 1500, 1500, 0.4],
  ['Untitled 02', '', '', [], 0, '2025-09-05', 1500, 1500, 0.4],
  ['过往作品补档', '', '', ['练习'], 0, '2025-08-21', 1920, 1080, 0.8],
  ['Twilight A', 'aoba.', 'Nagi', ['風景', '夜景'], 4, '2025-07-19', 3200, 1800, 2.7],
  ['Twilight B', 'aoba.', 'Nagi', ['風景'], 3, '2025-07-19', 3200, 1800, 2.7],
  ['Marginalia', 'kite-lab', 'Shiro', ['何意味'], 1, '2025-06-08', 1200, 1600, 0.2],
];

let artistRows = [];
let characterRows = [];
let works = [];
let nextArtistId = 0;
let nextCharacterId = 0;
let nextWorkId = 0;

function checksumFor(id, title) {
  // stable pseudo-hash so the detail sheet shows something checksum-shaped
  let hash = 2166136261;
  for (const char of `${id}:${title}`) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0').repeat(8).slice(0, 64);
}

function ensureArtist(name) {
  const cleaned = String(name || '').trim();
  if (!cleaned) return null;
  let row = artistRows.find((entry) => entry.name === cleaned);
  if (!row) {
    row = { id: ++nextArtistId, name: cleaned, created_at: null };
    artistRows.push(row);
  }
  return row;
}

function ensureCharacter(name) {
  const cleaned = String(name || '').trim();
  if (!cleaned) return null;
  let row = characterRows.find((entry) => entry.name === cleaned);
  if (!row) {
    row = { id: ++nextCharacterId, name: cleaned, created_at: null };
    characterRows.push(row);
  }
  return row;
}

/** Hand the views a copy so a stray mutation cannot corrupt the store. */
const decorate = (work) => ({ ...work });

function createWork(entry, index) {
  const [title, artist, character, tags, rating, day, width, height, megabytes] = entry;
  const artistRow = ensureArtist(artist);
  const characterRow = ensureCharacter(character);
  const id = ++nextWorkId;
  const tile = TILES[index % TILES.length];
  const folder = artist ? artist.replace(/[^\w.\-]+/g, '_') : '未分类';
  // Real archives hold raster files, so the sample rows use a plausible name
  // and byte count. Only `url`/`thumbnail_url` point at the SVG tile above -
  // those two are what the browser actually renders.
  const fileName = `2026052100${String(index).padStart(4, '0')}_${title}.png`;
  const bytes = Math.round(megabytes * 1024 * 1024);
  return {
    id,
    artist_id: artistRow ? artistRow.id : null,
    artist_name: artistRow ? artistRow.name : null,
    character_id: characterRow ? characterRow.id : null,
    character_name: characterRow ? characterRow.name : null,
    title,
    file_path: `illustrations/${folder}/${fileName}`,
    file_name: fileName,
    tags: [...tags],
    tags_raw: tags.join(', '),
    rating,
    remark: index % 7 === 3 ? '演示备注：记录纸纹与打光参考。' : '',
    created_at: `${day}T${String(9 + (index % 9)).padStart(2, '0')}:${String((index * 7) % 60).padStart(2, '0')}:00`,
    updated_at: '',
    file_size: bytes,
    width,
    height,
    checksum: checksumFor(id, title),
    sort_order: works.filter((work) => work.artist_id === (artistRow ? artistRow.id : null)).length,
    file_exists: true,
    url: tile,
    thumbnail_url: tile,
    download_url: tile,
  };
}

function reset() {
  artistRows = [];
  characterRows = [];
  works = [];
  nextArtistId = 0;
  nextCharacterId = 0;
  nextWorkId = 0;
  CATALOGUE.forEach((entry, index) => works.push(createWork(entry, index)));
}

reset();

/* --- aggregations --------------------------------------------------------- */

function countFor(rows, key) {
  return rows.map((row) => ({
    ...row,
    count: works.filter((work) => work[key] === row.id).length,
  }));
}

function tagRows() {
  const counter = new Map();
  for (const work of works) {
    for (const tag of work.tags) counter.set(tag, (counter.get(tag) || 0) + 1);
  }
  return [...counter.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
}

function statsPayload() {
  const ratings = { 0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  for (const work of works) ratings[work.rating] += 1;
  const dates = works.map((work) => work.created_at).filter(Boolean).sort();
  return {
    illustrations: works.length,
    artists: artistRows.length,
    characters: characterRows.length,
    unassigned: works.filter((work) => work.artist_id === null).length,
    total_bytes: works.reduce((sum, work) => sum + (work.file_size || 0), 0),
    ratings,
    latest_created_at: dates.length ? dates[dates.length - 1] : null,
    missing_files: 0,
    disk: null,
  };
}

const SORTS = {
  created_desc: (a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id,
  created_asc: (a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id,
  updated_desc: (a, b) => (b.updated_at || '').localeCompare(a.updated_at || '') || b.id - a.id,
  title_asc: (a, b) => a.title.localeCompare(b.title, 'zh') || a.id - b.id,
  title_desc: (a, b) => b.title.localeCompare(a.title, 'zh') || b.id - a.id,
  rating_desc: (a, b) => b.rating - a.rating || b.created_at.localeCompare(a.created_at),
  artist_asc: (a, b) =>
    String(a.artist_name || '').localeCompare(String(b.artist_name || ''), 'zh')
    || a.sort_order - b.sort_order || a.id - b.id,
  manual: (a, b) => a.sort_order - b.sort_order || a.id - b.id,
};

function matches(work, filters = {}) {
  if (filters.unassigned) {
    if (work.artist_id !== null) return false;
  } else if (filters.artist_id && work.artist_id !== Number(filters.artist_id)) {
    return false;
  }
  if (filters.character_id && work.character_id !== Number(filters.character_id)) return false;
  if (filters.tag && !work.tags.includes(filters.tag)) return false;
  if (filters.rating_min && work.rating < Number(filters.rating_min)) return false;
  if (filters.q) {
    const needle = String(filters.q).toLowerCase();
    const haystack = [
      work.title, work.artist_name, work.character_name, work.tags.join(' '),
      work.remark, work.file_path,
    ].join(' ').toLowerCase();
    if (!haystack.includes(needle)) return false;
  }
  return true;
}

/* --- API surface ---------------------------------------------------------- */

const offline = (message) => Promise.reject(new Error(message));

export const demoApi = {
  demo: true,
  base: '',

  mediaUrl: (path) => path || '',

  async health() {
    return {
      status: 'ok',
      version: VERSION,
      time: new Date().toISOString().slice(0, 19),
      python: '静态演示',
      thumbnailer: 'svg',
      data_root: 'GitHub Pages（只读）',
      demo: true,
    };
  },

  async stats() {
    return statsPayload();
  },

  async artists() {
    return { items: countFor(artistRows, 'artist_id') };
  },

  async characters() {
    return { items: countFor(characterRows, 'character_id') };
  },

  async tags() {
    return { items: tagRows() };
  },

  async tree() {
    const nodes = artistRows.map((artist) => ({
      ...artist,
      count: works.filter((work) => work.artist_id === artist.id).length,
      illustrations: works.filter((work) => work.artist_id === artist.id).map(decorate),
    }));
    const orphans = works.filter((work) => work.artist_id === null);
    if (orphans.length) {
      const taken = new Set(nodes.map((node) => node.name));
      nodes.push({
        id: null,
        name: taken.has('未分类') ? '未分类（无画师）' : '未分类',
        count: orphans.length,
        created_at: null,
        synthetic: true,
        illustrations: orphans.map(decorate),
      });
    }
    return { artists: nodes };
  },

  async illustrations(filters = {}) {
    const limit = Number(filters.limit) || 120;
    const offset = Number(filters.offset) || 0;
    const rows = works.filter((work) => matches(work, filters)).sort(SORTS[filters.sort] || SORTS.manual);
    return {
      items: rows.slice(offset, offset + limit).map(decorate),
      total: rows.length,
      limit,
      offset,
      has_more: offset + limit < rows.length,
    };
  },

  async illustration(id) {
    const work = works.find((entry) => entry.id === Number(id));
    if (!work) throw new Error(`作品 ${id} 不存在`);
    return decorate(work);
  },

  async updateIllustration(id, changes) {
    const work = works.find((entry) => entry.id === Number(id));
    if (!work) throw new Error(`作品 ${id} 不存在`);
    Object.assign(work, normaliseChanges(changes));
    work.updated_at = new Date().toISOString().slice(0, 19);
    return decorate(work);
  },

  async bulkUpdate({ ids = [], tags_add = [], tags_remove = [], ...changes } = {}) {
    const updated = [];
    for (const id of ids) {
      const work = works.find((entry) => entry.id === Number(id));
      if (!work) continue;
      Object.assign(work, normaliseChanges(changes));
      const remove = new Set(tags_remove);
      const kept = work.tags.filter((tag) => !remove.has(tag));
      work.tags = [...kept, ...tags_add.filter((tag) => !kept.includes(tag))];
      work.updated_at = new Date().toISOString().slice(0, 19);
      updated.push(decorate(work));
    }
    return { updated: updated.length, items: updated };
  },

  async deleteIllustration(id) {
    const index = works.findIndex((entry) => entry.id === Number(id));
    if (index < 0) throw new Error(`作品 ${id} 不存在`);
    const [removed] = works.splice(index, 1);
    return {
      deleted: decorate(removed),
      file_action: { mode: 'demo', path: removed.file_path, moved_to: null },
    };
  },

  async createArtist(name) {
    const row = ensureArtist(name);
    if (!row) throw new Error('画师名称不能为空');
    return { ...row, count: 0 };
  },

  async renameArtist(id, name) {
    const row = artistRows.find((entry) => entry.id === Number(id));
    if (!row) throw new Error(`画师 ${id} 不存在`);
    const cleaned = String(name || '').trim();
    if (!cleaned) throw new Error('画师名称不能为空');
    if (artistRows.some((entry) => entry.name === cleaned && entry.id !== row.id)) {
      throw new Error(`画师「${cleaned}」已存在`);
    }
    const previous = row.name;
    row.name = cleaned;
    for (const work of works) {
      if (work.artist_name === previous) work.artist_name = cleaned;
    }
    return { ...row, count: works.filter((work) => work.artist_id === row.id).length };
  },

  async deleteArtist(id) {
    const index = artistRows.findIndex((entry) => entry.id === Number(id));
    if (index < 0) throw new Error(`画师 ${id} 不存在`);
    const [row] = artistRows.splice(index, 1);
    let detached = 0;
    for (const work of works) {
      if (work.artist_id === row.id) {
        work.artist_id = null;
        work.artist_name = null;
        detached += 1;
      }
    }
    return { deleted: row, detached_works: detached, files_removed: 0, folder_kept: false };
  },

  async mergeArtist(sourceId, targetId) {
    const source = artistRows.find((entry) => entry.id === Number(sourceId));
    const target = artistRows.find((entry) => entry.id === Number(targetId));
    if (!source || !target) throw new Error('画师不存在');
    if (source.id === target.id) throw new Error('源画师与目标画师不能相同');
    for (const work of works) {
      if (work.artist_id === source.id) {
        work.artist_id = target.id;
        work.artist_name = target.name;
      }
    }
    artistRows = artistRows.filter((entry) => entry.id !== source.id);
    return { merged_into: { ...target, count: works.filter((work) => work.artist_id === target.id).length } };
  },

  async createCharacter(name) {
    const row = ensureCharacter(name);
    if (!row) throw new Error('角色名称不能为空');
    return { ...row, count: 0 };
  },

  async renameCharacter(id, name) {
    const row = characterRows.find((entry) => entry.id === Number(id));
    if (!row) throw new Error(`角色 ${id} 不存在`);
    const cleaned = String(name || '').trim();
    if (!cleaned) throw new Error('角色名称不能为空');
    if (characterRows.some((entry) => entry.name === cleaned && entry.id !== row.id)) {
      throw new Error(`角色「${cleaned}」已存在`);
    }
    const previous = row.name;
    row.name = cleaned;
    for (const work of works) {
      if (work.character_name === previous) work.character_name = cleaned;
    }
    return { ...row, count: works.filter((work) => work.character_id === row.id).length };
  },

  async deleteCharacter(id) {
    const index = characterRows.findIndex((entry) => entry.id === Number(id));
    if (index < 0) throw new Error(`角色 ${id} 不存在`);
    const [row] = characterRows.splice(index, 1);
    let detached = 0;
    for (const work of works) {
      if (work.character_id === row.id) {
        work.character_id = null;
        work.character_name = null;
        detached += 1;
      }
    }
    return { deleted: row, detached_works: detached };
  },

  /** Dropped files become extra cards, reusing the bundled tiles. */
  async upload(files = [], fields = {}) {
    const results = [];
    const imported = [];
    for (const [index, entry] of [...files].entries()) {
      const name = entry.file?.name || entry.relativePath || `demo-${index}.png`;
      const record = createWork(
        [name.replace(/\.[^.]+$/, ''), fields.artist || '', fields.character || '',
          parseTags(fields.tags), Number(fields.rating) || 0,
          new Date().toISOString().slice(0, 10), 1600, 1200, 0.4],
        works.length + index,
      );
      works.push(record);
      imported.push(decorate(record));
      results.push({ status: 'imported', filename: name, illustration: decorate(record) });
    }
    return { imported: imported.length, skipped: 0, failed: 0, results, illustrations: imported };
  },

  async scanLocal(paths = []) {
    return {
      total: 0,
      folders: paths.map((path) => ({ path: String(path), exists: false, is_dir: false, count: 0 })),
    };
  },

  /** The static demo cannot read a server folder - say so instead of pretending. */
  async importLocal({ paths = [] } = {}) {
    return {
      imported: 0,
      skipped: 0,
      failed: paths.length,
      results: paths.map((path) => ({
        status: 'failed', filename: String(path), reason: '演示模式不读取服务器路径',
      })),
      illustrations: [],
    };
  },

  async maintenance({ dry_run } = {}) {
    return {
      dry_run: dry_run !== false,
      scanned: works.length,
      relinked: [],
      ambiguous: [],
      missing: [],
      unreadable_paths: [],
      metadata_refreshed: 0,
      duplicates: [],
      applied: { relinked: 0, metadata_refreshed: 0, removed_duplicates: 0 },
    };
  },

  async exports() {
    return { items: [], directory: 'GitHub Pages（只读）' };
  },

  async clearExports() {
    return { removed: 0 };
  },

  /** Downloading a backup needs the real backend; the views guard empty URLs. */
  exportUrl: () => '',
  exportFileUrl: () => '',

  inspectBackupFile: () => offline('演示模式无法校验备份，请在本机运行后端。'),
  restoreBackupFile: () => offline('演示模式无法恢复备份，请在本机运行后端。'),
};

function parseTags(value) {
  if (!value) return [];
  const text = Array.isArray(value) ? value.join(', ') : String(value);
  return text.split(/[,，、;；]/).map((tag) => tag.trim()).filter(Boolean);
}

function normaliseChanges(changes = {}) {
  const next = { ...changes };
  delete next.tags_add;
  delete next.tags_remove;
  if ('tags' in next) {
    const tags = parseTags(next.tags);
    next.tags = tags;
    next.tags_raw = tags.join(', ');
  }
  if ('artist_id' in next) {
    const row = artistRows.find((entry) => entry.id === Number(next.artist_id));
    next.artist_id = row ? row.id : null;
    next.artist_name = row ? row.name : null;
  }
  if ('character_id' in next) {
    const row = characterRows.find((entry) => entry.id === Number(next.character_id));
    next.character_id = row ? row.id : null;
    next.character_name = row ? row.name : null;
  }
  if ('title' in next) next.title = String(next.title ?? '');
  if ('remark' in next) next.remark = String(next.remark ?? '');
  if ('rating' in next) next.rating = Math.max(0, Math.min(5, Number(next.rating) || 0));
  return next;
}
