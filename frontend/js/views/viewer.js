/** Full-screen image viewer. */

import { el, starString } from '../dom.js';

/**
 * Open (or re-target) the full-screen viewer.
 *
 * The controller can be updated in place so that stepping through works
 * while the viewer stays open - rebuilding it would stack key listeners.
 */
export function openViewer(item, { onPrev, onNext, hasPrev, hasNext } = {}) {
  const host = document.querySelector('[data-viewer]');
  if (!host) return null;

  let current = item;
  let nav = { onPrev, onNext, hasPrev, hasNext };

  const image = el('img', { alt: '' });
  const caption = el('span', {});
  const bar = el('div', { class: 'viewer__bar' });

  const controller = {
    closed: false,

    close() {
      if (controller.closed) return;
      controller.closed = true;
      host.hidden = true;
      host.replaceChildren();
      document.removeEventListener('keydown', onKey);
    },

    /** Show another work without closing the overlay. */
    update(nextItem, nextNav = {}) {
      current = nextItem;
      nav = { ...nav, ...nextNav };
      render();
    },
  };

  function closeButton() {
    return el('button', {
      type: 'button',
      class: 'button',
      text: '关闭 ✕',
      onClick: () => controller.close(),
    });
  }

  function render() {
    image.src = current.url;
    image.alt = current.title || current.file_name;
    caption.textContent =
      `${current.title || current.file_name} · ${current.artist_name || '未分类'} · ${starString(current.rating)}`;

    const buttons = [];
    if (nav.hasPrev) {
      buttons.push(el('button', { type: 'button', class: 'button', text: '← 上一个', onClick: () => nav.onPrev() }));
    }
    buttons.push(closeButton());
    if (nav.hasNext) {
      buttons.push(el('button', { type: 'button', class: 'button', text: '下一个 →', onClick: () => nav.onNext() }));
    }

    bar.replaceChildren(
      el('span', { class: 'mono', text: `ID ${String(current.id).padStart(4, '0')}` }),
      caption,
      el('span', { class: 'spacer' }),
      ...buttons,
    );
    host.hidden = false;
  }

  const onKey = (event) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      controller.close();
    } else if (event.key === 'ArrowLeft' && nav.hasPrev) {
      nav.onPrev();
    } else if (event.key === 'ArrowRight' && nav.hasNext) {
      nav.onNext();
    }
  };

  host.replaceChildren(bar, el('div', { class: 'viewer__body' }, image));
  render();
  document.addEventListener('keydown', onKey);
  return controller;
}
