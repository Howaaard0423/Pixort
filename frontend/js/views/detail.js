/** The detail sheet for a single work. */

import { clear, el, formatBytes, formatDate, pad2, starString } from '../dom.js';

function metaRow(label, value) {
  return el('tr', {},
    el('th', { text: label }),
    el('td', {}, value instanceof Node ? value : String(value ?? '—')),
  );
}

export function renderDetail(host, state, handlers) {
  clear(host);
  const item = state.detail;

  if (!item) {
    host.appendChild(
      el('div', { class: 'empty' },
        el('p', { class: 'empty__title', text: state.loading ? '正在读取…' : '作品不存在' }),
        el('p', { class: 'empty__body', text: '该记录可能已被删除。' }),
        el('div', { style: { marginTop: 'var(--unit)' } },
          el('button', { type: 'button', class: 'button', text: '返回列表', onClick: () => handlers.closeDetail() }),
        ),
      ),
    );
    return;
  }

  const index = Math.max(0, state.items.findIndex((entry) => entry.id === item.id));
  const figure = el('div', { class: 'sheet__figure' });
  if (item.file_exists) {
    figure.appendChild(
      el('img', {
        src: `${item.url}${item.url.includes('?') ? '&' : '?'}width=1600`,
        alt: item.title || item.file_name,
        onClick: () => handlers.openViewer(item),
        style: { cursor: 'zoom-in' },
      }),
    );
  } else {
    figure.appendChild(
      el('div', { class: 'sheet__missing' },
        el('p', { class: 'rubric', text: '文件缺失' }),
        el('p', { class: 'mono', style: { marginTop: 'var(--unit)', wordBreak: 'break-all' }, text: item.file_path }),
        el('p', {
          style: { marginTop: 'var(--unit)' },
          text: '可在「管理 → 库维护」中尝试重新关联，或直接移除该记录。',
        }),
      ),
    );
  }

  const tags = el('div', { class: 'taglist', style: { marginTop: 'var(--unit)' } });
  if (item.tags.length) {
    for (const tag of item.tags) {
      tags.appendChild(
        el('button', {
          type: 'button',
          class: 'tag',
          text: tag,
          onClick: () => handlers.selectTag(tag),
        }),
      );
    }
  } else {
    tags.appendChild(el('span', { class: 'rubric rubric--muted', text: '无标签' }));
  }

  const panel = el('div', { class: 'sheet__panel' },
    el('p', { class: 'sheet__index', text: `NO. ${pad2(index + 1)} / ${pad2(state.total)} · ID ${item.id}` }),
    el('h2', { class: 'sheet__title', text: item.title || item.file_name }),
    el('div', { class: 'sheet__actions' },
      el('button', { type: 'button', class: 'button button--solid', text: '编辑', onClick: () => handlers.edit(item) }),
      el('button', {
        type: 'button',
        class: 'button',
        text: '全屏',
        disabled: !item.file_exists,
        onClick: () => handlers.openViewer(item),
      }),
      el('a', {
        class: 'button',
        href: `${item.download_url}`,
        text: '下载',
        download: '',
      }),
      el('a', {
        class: 'button',
        href: item.url,
        text: '原图',
        target: '_blank',
        rel: 'noopener',
      }),
      el('button', {
        type: 'button',
        class: 'button button--danger',
        text: '删除',
        onClick: () => handlers.remove(item),
      }),
    ),
    el('table', { class: 'meta-table' },
      el('tbody', {},
        metaRow('画师', item.artist_name || '未分类'),
        metaRow('角色', item.character_name || '—'),
        metaRow('评分', el('span', { class: 'stars', text: starString(item.rating) })),
        metaRow('尺寸', item.width && item.height ? `${item.width} × ${item.height}` : '未记录'),
        metaRow('体积', formatBytes(item.file_size)),
        metaRow('导入', formatDate(item.created_at)),
        metaRow('更新', formatDate(item.updated_at)),
        metaRow('文件', el('span', { class: 'mono', style: { wordBreak: 'break-all' }, text: item.file_path })),
        metaRow('校验', el('span', { class: 'mono', text: item.checksum ? item.checksum.slice(0, 16) : '未计算' })),
      ),
    ),
    el('div', { style: { marginTop: 'calc(var(--unit) * 2)' } },
      el('p', { class: 'rubric', text: '标签' }),
      tags,
    ),
    item.remark
      ? el('div', {},
          el('p', { class: 'rubric', style: { marginTop: 'calc(var(--unit) * 2)' }, text: '备注' }),
          el('p', { class: 'sheet__remark', text: item.remark }),
        )
      : null,
  );

  const bar = el('div', { class: 'sheet__bar' },
    el('button', { type: 'button', class: 'button', text: '← 返回列表', onClick: () => handlers.closeDetail() }),
    el('span', { class: 'rubric rubric--muted', text: `${pad2(index + 1)} / ${pad2(state.total)}` }),
    el('span', { class: 'spacer' }),
    el('button', {
      type: 'button',
      class: 'button',
      text: '上一个',
      disabled: index <= 0,
      onClick: () => handlers.step(-1),
    }),
    el('button', {
      type: 'button',
      class: 'button',
      text: '下一个',
      disabled: index >= state.items.length - 1 && state.items.length >= state.total,
      onClick: () => handlers.step(1),
    }),
  );

  host.append(bar, el('div', { class: 'sheet' }, figure, panel));
}
