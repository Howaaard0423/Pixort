/** The index rail: artists (expandable), tags and characters. */

import { clear, el, pad2 } from '../dom.js';

const expanded = new Set();

function countLabel(count) {
  return String(count ?? 0);
}

function indexButton({ number, name, count, active, onClick, extra }) {
  return el('button', {
    type: 'button',
    class: 'index__item',
    'aria-current': active ? 'true' : 'false',
    onClick,
  },
    el('span', { class: 'index__number', text: number }),
    el('span', { class: 'index__name', text: name }),
    extra || el('span', { class: 'index__count', text: countLabel(count) }),
  );
}

function renderArtists(host, state, handlers) {
  clear(host);

  host.appendChild(
    indexButton({
      number: '00',
      name: '全部作品',
      count: state.stats?.illustrations ?? 0,
      active: !state.filters.artistName && !state.filters.artistId && !state.filters.unassigned,
      onClick: () => handlers.selectArtist(null),
    }),
  );

  state.artists.forEach((artist, index) => {
    const active = state.filters.artistId === artist.id;
    const isOpen = expanded.has(artist.id);

    const caret = el('button', {
      type: 'button',
      class: 'button button--quiet button--small',
      text: isOpen ? '−' : '+',
      'aria-label': isOpen ? '收起作品' : '展开作品',
      'aria-expanded': isOpen ? 'true' : 'false',
      onClick: (event) => {
        event.stopPropagation();
        if (isOpen) expanded.delete(artist.id);
        else expanded.add(artist.id);
        handlers.rerender();
      },
    });

    host.appendChild(
      indexButton({
        number: pad2(index + 1),
        name: artist.name,
        count: artist.count,
        active,
        onClick: () => handlers.selectArtist(artist),
        extra: el('span', { class: 'index__count', style: { display: 'flex', alignItems: 'center', gap: '6px' } },
          el('span', { text: countLabel(artist.count) }),
          caret,
        ),
      }),
    );

    if (!isOpen) return;
    const works = artistWorks(state, artist);
    if (!works.length) {
      host.appendChild(el('p', { class: 'rail__empty', text: '暂无作品记录' }));
      return;
    }
    for (const work of works.slice(0, 60)) {
      host.appendChild(
        el('button', {
          type: 'button',
          class: 'index__item',
          style: { paddingLeft: 'calc(var(--unit) * 3.5)' },
          onClick: () => handlers.openWork(work.id),
        },
          el('span', { class: 'index__number', text: String(work.id) }),
          el('span', {
            class: 'index__name',
            text: work.title || work.file_name,
            title: work.file_name,
          }),
          el('span', { class: 'index__count', text: work.file_exists ? '●' : '○' }),
        ),
      );
    }
  });

  if (state.tree) {
    const orphans = state.tree.find((entry) => entry.id === null);
    if (orphans) {
      host.appendChild(
        indexButton({
          number: pad2(state.artists.length + 1),
          name: orphans.name,
          count: orphans.count,
          active: state.filters.unassigned,
          onClick: () => handlers.selectUnassigned(),
        }),
      );
    }
  }
}

/** Works are only present for artists already fetched through /api/tree. */
function artistWorks(state, artist) {
  const entry = state.tree?.find((node) => node.id === artist.id);
  return entry ? entry.illustrations : [];
}

function renderTags(host, state, handlers) {
  clear(host);
  if (!state.tags.length) {
    host.appendChild(el('p', { class: 'rail__empty', text: '暂无标签' }));
    return;
  }
  for (const entry of state.tags.slice(0, 40)) {
    host.appendChild(
      el('button', {
        type: 'button',
        class: 'tag',
        'aria-pressed': state.filters.tag === entry.tag ? 'true' : 'false',
        onClick: () => handlers.selectTag(entry.tag),
      },
        el('span', { text: entry.tag }),
        el('span', { class: 'tag__count numeral', text: countLabel(entry.count) }),
      ),
    );
  }
}

function renderCharacters(host, state, handlers) {
  clear(host);
  if (!state.characters.length) {
    host.appendChild(el('p', { class: 'rail__empty', text: '暂无角色' }));
    return;
  }
  for (const character of state.characters) {
    host.appendChild(
      el('button', {
        type: 'button',
        class: 'tag',
        'aria-pressed': state.filters.characterId === character.id ? 'true' : 'false',
        onClick: () => handlers.selectCharacter(character.id),
      },
        el('span', { text: character.name }),
        el('span', { class: 'tag__count numeral', text: countLabel(character.count) }),
      ),
    );
  }
}

export function renderRail(hosts, state, handlers) {
  renderArtists(hosts.artists, state, handlers);
  renderTags(hosts.tags, state, handlers);
  renderCharacters(hosts.characters, state, handlers);
}
