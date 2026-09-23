/** Dialogs, prompts and toasts. */

import { $, clear, el } from './dom.js';

function overlayRoot() {
  return $('[data-overlay-root]');
}

/**
 * Open a modal dialog. Returns a controller with `close()`.
 * `render(api)` receives helpers so views can update content in place.
 */
export function openDialog({ title, subtitle, className = '', render, footer, onClose, width }) {
  const root = overlayRoot();
  const dialog = el('div', { class: `dialog ${className}`.trim() });
  if (width) dialog.style.width = `min(${width}, 100%)`;

  const body = el('div', { class: 'dialog__body' });
  const foot = el('div', { class: 'dialog__foot' });

  const closeButton = el('button', {
    type: 'button',
    class: 'button button--quiet',
    text: '关闭 ✕',
    'aria-label': '关闭',
    onClick: () => controller.close(),
  });

  dialog.append(
    el('div', { class: 'dialog__head' },
      el('div', {},
        el('h2', { class: 'dialog__title', text: title }),
        subtitle ? el('p', { class: 'dialog__subtitle', text: subtitle }) : null,
      ),
      closeButton,
    ),
    body,
    foot,
  );

  const scrim = el('div', { class: 'scrim', onMousedown: (event) => {
    if (event.target === scrim) controller.close();
  } }, dialog);

  const controller = {
    root: scrim,
    body,
    foot,
    close(result) {
      if (controller.closed) return;
      controller.closed = true;
      scrim.remove();
      document.removeEventListener('keydown', onKeydown, true);
      if (onClose) onClose(result);
    },
    setFooter(...children) {
      clear(foot);
      foot.append(...children.flat().filter(Boolean));
    },
    setBody(...children) {
      clear(body);
      body.append(...children.flat().filter(Boolean));
    },
  };

  const onKeydown = (event) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      controller.close();
    }
  };
  document.addEventListener('keydown', onKeydown, true);

  root.appendChild(scrim);
  if (render) render(controller);
  if (footer) controller.setFooter(...footer);
  dialog.querySelector('button')?.focus();
  return controller;
}

/** Ask for a single line of text. Resolves to the string or null. */
export function promptText({ title, label, value = '', confirm = '确定', type = 'text' }) {
  return new Promise((resolve) => {
    let result = null;
    const input = el('input', { class: 'input', type, value });
    const controller = openDialog({
      title,
      className: 'dialog--narrow',
      onClose: () => resolve(result),
      render(ui) {
        ui.setBody(el('div', { class: 'form-row' }, el('label', { text: label }), input));
        queueMicrotask(() => {
          input.focus();
          input.select();
        });
      },
      footer: [
        el('button', {
          type: 'button',
          class: 'button',
          text: '取消',
          onClick: () => controller.close(),
        }),
        el('button', {
          type: 'button',
          class: 'button button--solid',
          text: confirm,
          onClick: () => {
            result = input.value.trim() || null;
            controller.close();
          },
        }),
      ],
    });
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        controller.root.querySelector('.button--solid')?.click();
      }
    });
  });
}

/** Confirmation dialog. Resolves to a boolean. */
export function confirmAction({ title, message, confirm = '确定', danger = false }) {
  return new Promise((resolve) => {
    let answer = false;
    const controller = openDialog({
      title,
      className: 'dialog--narrow',
      onClose: () => resolve(answer),
      render(ui) {
        ui.setBody(el('p', { class: 'notice', text: message }));
      },
      footer: [
        el('button', {
          type: 'button',
          class: 'button',
          text: '取消',
          onClick: () => controller.close(),
        }),
        el('button', {
          type: 'button',
          class: `button button--solid${danger ? ' button--danger' : ''}`,
          text: confirm,
          onClick: () => {
            answer = true;
            controller.close();
          },
        }),
      ],
    });
  });
}

/* --- toasts --------------------------------------------------------------- */

export function toast(message, { tag = '信息', kind = 'info', timeout = 4200 } = {}) {
  const host = $('[data-toaster]');
  if (!host) return;
  const node = el('div', { class: `toast${kind === 'error' ? ' toast--error' : ''}`, role: 'status' },
    el('span', { class: 'toast__tag', text: tag }),
    el('span', { text: message }),
  );
  host.appendChild(node);
  window.setTimeout(() => node.remove(), timeout);
}
