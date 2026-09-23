/** The work grid (and the list density). */

import { clear, el, formatBytes, pad2, shortPath, starString } from '../dom.js';
import { scopeLabel } from '../state.js';

const DENSITIES = [
  { id: 'compact', label: '紧凑' },
  { id: 'grid', label: '网格' },
  { id: 'roomy', label: '宽松' },
  { id: 'rows', label: '列表' },
];

function thumbUrl(item, width = 640) {
  return `${item.thumbnail_url}?width=${width}`;
}

function workCard(item, index, handlers) {
  const figure = el('figure', { class: 'work__figure' });

  if (item.file_exists) {
    figure.appendChild(
      el('img', {
        class: 'work__image',
        src: thumbUrl(item, 640),
        alt: item.title || item.file_name,
        loading: 'lazy',
        decoding: 'async',
      }),
    );
  } else {
    figure.appendChild(el('div', { class: 'work__placeholder', text: '文件缺失' }));
  }

  figure.appendChild(el('span', { class: 'work__index', text: pad2(index + 1) }));
  if (!item.file_exists) figure.appendChild(el('span', { class: 'work__flag', text: '缺失' }));

  const meta = el('div', { class: 'work__meta' },
    el('h3', { class: 'work__title', text: item.title || item.file_name, title: item.title || item.file_name }),
    el('div', { class: 'work__line' },
      el('span', { text: item.artist_name || '未分类' }),
      el('span', { class: 'stars', text: starString(item.rating) }),
    ),
  );

  return el('article', {
    class: 'work',
    dataset: { id: String(item.id) },
    'data-selected': String(handlers.isSelected(item.id)),
  },
    el('a', {
      class: 'work__link',
      href: `#/work/${item.id}`,
      onClick: (event) => {
        event.preventDefault();
        handlers.openWork(item.id);
      },
    }, figure, meta),
  );
}

function workRow(item, index, handlers) {
  const thumb = el('div', { class: 'row__thumb' });
  if (item.file_exists) {
    thumb.appendChild(el('img', { src: thumbUrl(item, 320), alt: '', loading: 'lazy' }));
  }

  return el('a', {
    class: 'row',
    href: `#/work/${item.id}`,
    dataset: { id: String(item.id) },
    'data-selected': String(handlers.isSelected(item.id)),
    onClick: (event) => {
      event.preventDefault();
      handlers.openWork(item.id);
    },
  },
    thumb,
    el('div', { class: 'row__main' },
      el('div', { class: 'row__title', text: `${pad2(index + 1)} ${item.title || item.file_name}` }),
      el('div', { class: 'row__path', text: shortPath(item.file_path), title: item.file_path }),
    ),
    el('div', { class: 'row__cell row__cell--wide' }, el('span', { text: item.artist_name || '未分类' })),
    el('div', { class: 'row__cell' },
      el('span', { class: 'stars', text: starString(item.rating) }),
    ),
  );
}

export function renderGallery(host, state, handlers) {
  clear(host);

  const head = el('div', { class: 'section-head' },
    el('div', {},
      el('h2', { class: 'section-head__title', text: scopeLabel(state) }),
      el('p', { class: 'rubric rubric--muted', text: `${state.total} 件作品 · 显示 ${state.items.length}` }),
      hasActiveFilters(state)
        ? el('button', {
            type: 'button',
            class: 'button button--small',
            style: { marginTop: 'var(--unit)' },
            text: '清除筛选 ✕',
            onClick: () => handlers.clearFilters(),
          })
        : null,
    ),
    el('div', { class: 'section-head__meta' },
      el('span', { class: 'numeral', text: state.stats ? `库容量 ${formatBytes(state.stats.total_bytes)}` : '' }),
      el('div', { class: 'segmented', role: 'group', 'aria-label': '视图密度' },
        DENSITIES.map((density) =>
          el('button', {
            type: 'button',
            class: 'segmented__item',
            text: density.label,
            'aria-pressed': state.density === density.id ? 'true' : 'false',
            onClick: () => handlers.setDensity(density.id),
          }),
        ),
      ),
    ),
  );
  host.appendChild(head);

  if (!state.items.length) {
    host.appendChild(
      el('div', { class: 'empty' },
        el('p', { class: 'empty__title', text: state.loading ? '正在读取…' : '没有匹配的作品' }),
        el('p', {
          class: 'empty__body',
          text: state.loading
            ? '正在从后端获取数据。'
            : '调整搜索条件，或通过「导入作品」把图片加入档案。',
        }),
      ),
    );
    return;
  }

  if (state.density === 'rows') {
    const list = el('div', { class: 'rows' });
    state.items.forEach((item, index) => list.appendChild(workRow(item, index, handlers)));
    host.appendChild(list);
  } else {
    const grid = el('div', { class: 'gallery', dataset: { density: state.density } });
    state.items.forEach((item, index) => grid.appendChild(workCard(item, index, handlers)));
    host.appendChild(grid);
  }

  if (state.total > state.items.length) {
    host.appendChild(
      el('div', { style: { padding: 'var(--margin)' } },
        el('button', {
          type: 'button',
          class: 'button',
          text: `继续载入（还有 ${state.total - state.items.length} 件）`,
          onClick: () => handlers.loadMore(),
        }),
      ),
    );
  }
}

function hasActiveFilters(state) {
  const filters = state.filters;
  return Boolean(
    filters.q || filters.tag || filters.artistName || filters.characterId
      || filters.unassigned || filters.ratingMin,
  );
}
