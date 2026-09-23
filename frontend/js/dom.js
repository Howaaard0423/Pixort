/**
 * DOM construction and formatting helpers.
 *
 * Everything the app renders is built from real nodes - `innerHTML` is never
 * fed with library data, so a file name can never inject markup.
 */

export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key === 'style') Object.assign(node.style, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, String(value));
  }
  append(node, children);
  return node;
}

export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false || child === '') continue;
    parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

export function mount(host, ...children) {
  clear(host);
  append(host, children);
  return host;
}

export const $ = (selector, scope = document) => scope.querySelector(selector);

/* --- formatting ----------------------------------------------------------- */

export function pad2(value) {
  return String(value).padStart(2, '0');
}

export function starString(rating, length = 5) {
  const filled = Math.max(0, Math.min(length, Number(rating) || 0));
  return '★'.repeat(filled) + '☆'.repeat(length - filled);
}

export function formatBytes(bytes) {
  const value = Number(bytes);
  if (!value || value < 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatDate(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

export function shortPath(path, max = 42) {
  const value = String(path || '').replace(/\\/g, '/');
  if (value.length <= max) return value;
  return `…${value.slice(-max)}`;
}

export function debounce(fn, wait = 200) {
  let timer = 0;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}
