/** Importing pictures: local files, whole folders, or paths on the server. */

import { clear, el, formatBytes } from '../dom.js';
import { api } from '../api.js';
import { openDialog, toast } from '../overlay.js';

const DROP_LIMIT = 4000;

async function readDirectory(entry, prefix = '') {
  const reader = entry.createReader();
  const collected = [];
  // readEntries() returns at most ~100 entries per call, so keep asking.
  for (;;) {
    const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
    if (!batch.length) break;
    for (const child of batch) collected.push(...(await readEntry(child, prefix)));
  }
  return collected;
}

async function readEntry(entry, prefix = '') {
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
    return [{ file, relativePath: `${prefix}${entry.name}` }];
  }
  if (entry.isDirectory) return readDirectory(entry, `${prefix}${entry.name}/`);
  return [];
}

async function fromDataTransfer(dataTransfer) {
  const entries = Array.from(dataTransfer.items || [])
    .filter((item) => item.kind === 'file')
    .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null));

  if (entries.some(Boolean)) {
    const nested = await Promise.all(entries.filter(Boolean).map((entry) => readEntry(entry)));
    return nested.flat();
  }
  return Array.from(dataTransfer.files || []).map((file) => ({
    file,
    relativePath: file.webkitRelativePath || file.name,
  }));
}

function resolveArtist(entry, defaults) {
  if (defaults.artistMode === 'none') return null;
  if (defaults.artistMode === 'fixed') return defaults.artist || null;
  const segments = (entry.relativePath || '').split('/').filter(Boolean);
  if (segments.length > 1) return segments[0];
  return defaults.artist || null;
}

export function openImportDialog({ artists, characters, onDone }) {
  let entries = [];
  let serverPaths = [];
  let scan = null;
  let busy = false;

  const defaults = {
    artist: '',
    character: '',
    tags: '',
    rating: 0,
    artistMode: 'auto',
    skipDuplicates: true,
  };

  const fileInput = el('input', {
    type: 'file', multiple: true, accept: 'image/*', hidden: true,
    onChange: (event) => addEntries(
      Array.from(event.target.files).map((file) => ({
        file,
        relativePath: file.webkitRelativePath || file.name,
      })),
    ),
  });
  const folderInput = el('input', {
    type: 'file', webkitdirectory: true, directory: true, multiple: true, hidden: true,
    onChange: (event) => addEntries(
      Array.from(event.target.files).map((file) => ({
        file,
        relativePath: file.webkitRelativePath || file.name,
      })),
    ),
  });

  const summary = el('p', { class: 'rubric rubric--muted', text: '尚未选择文件' });
  const previewHost = el('div', { class: 'preview-list' });
  const serverSummary = el('p', { class: 'rubric rubric--muted', text: '' });
  const progressBar = el('div', { class: 'progress__bar' });
  const progress = el('div', { class: 'progress', hidden: true }, progressBar);
  const progressLabel = el('p', { class: 'rubric rubric--muted', text: '' });

  const serverInput = el('textarea', {
    class: 'textarea',
    placeholder: '后端所在机器上的绝对路径，每行一个，例如\nD:\\\\Pictures\\\\mechari',
  });

  const submit = el('button', {
    type: 'button',
    class: 'button button--solid',
    text: '开始导入',
    disabled: true,
    onClick: () => runImport(),
  });

  const artistSelect = el('select', { class: 'select', onChange: (event) => {
    defaults.artist = event.target.value;
    refreshPreview();
  } },
    el('option', { value: '', text: '未分类 / 自动推断' }),
    artists.map((artist) => el('option', { value: artist.name, text: artist.name })),
  );

  const characterSelect = el('select', { class: 'select', onChange: (event) => {
    defaults.character = event.target.value;
  } },
    el('option', { value: '', text: '无' }),
    characters.map((character) => el('option', { value: character.name, text: character.name })),
  );

  const modeButtons = ['auto', 'fixed', 'none'].map((mode) =>
    el('button', {
      type: 'button',
      class: 'segmented__item',
      text: { auto: '按文件夹推断', fixed: '统一指定', none: '不分配' }[mode],
      'aria-pressed': defaults.artistMode === mode ? 'true' : 'false',
      onClick: (event) => {
        defaults.artistMode = mode;
        for (const button of modeButtons) {
          button.setAttribute('aria-pressed', button === event.currentTarget ? 'true' : 'false');
        }
        refreshPreview();
      },
    }),
  );

  const dropzone = el('div', {
    class: 'dropzone',
    onDragover: (event) => {
      event.preventDefault();
      dropzone.dataset.active = 'true';
    },
    onDragleave: () => {
      dropzone.dataset.active = 'false';
    },
    onDrop: async (event) => {
      event.preventDefault();
      dropzone.dataset.active = 'false';
      const dropped = await fromDataTransfer(event.dataTransfer);
      addEntries(dropped);
    },
  },
    el('p', { class: 'rubric', text: '拖放图片或文件夹到此处' },
    ),
    el('p', { class: 'rubric rubric--muted', text: '也可以使用下方按钮选择' }),
  );

  function addEntries(incoming) {
    const known = new Set(entries.map((entry) => `${entry.relativePath}:${entry.file.size}`));
    let added = 0;
    for (const entry of incoming) {
      const key = `${entry.relativePath}:${entry.file.size}`;
      if (known.has(key) || entries.length >= DROP_LIMIT) continue;
      known.add(key);
      entries.push(entry);
      added += 1;
    }
    toast(`已加入 ${added} 个文件`, { tag: '选择' });
    refreshPreview();
  }

  function refreshPreview() {
    const total = entries.length + (scan ? scan.total : 0);
    submit.disabled = busy || total === 0;
    summary.textContent = entries.length
      ? `已选择 ${entries.length} 个文件`
      : '尚未选择文件';

    clear(previewHost);
    const shown = entries.slice(0, 200);
    for (const entry of shown) {
      previewHost.appendChild(
        el('div', { class: 'preview-row' },
          el('span', { class: 'preview-row__name', text: entry.relativePath, title: entry.relativePath }),
          el('span', { class: 'preview-row__artist', text: resolveArtist(entry, defaults) || '未分类' }),
          el('span', { class: 'preview-row__size', text: formatBytes(entry.file.size) }),
        ),
      );
    }
    if (entries.length > shown.length) {
      previewHost.appendChild(
        el('p', { class: 'rubric rubric--muted', text: `…以及另外 ${entries.length - shown.length} 个文件` }),
      );
    }
  }

  async function scanServerPaths() {
    const paths = serverInput.value
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    if (!paths.length) {
      toast('请先填写服务器路径', { tag: '提示', kind: 'error' });
      return;
    }
    serverPaths = paths;
    serverSummary.textContent = '正在扫描…';
    try {
      scan = await api.scanLocal(paths, true);
      serverSummary.textContent = `扫描到 ${scan.total} 张图片（${scan.folders
        .map((folder) => `${folder.path} → ${folder.count}`)
        .join('，')}）`;
    } catch (error) {
      scan = null;
      serverSummary.textContent = '';
      toast(error.message, { tag: '扫描失败', kind: 'error' });
    }
    refreshPreview();
  }

  async function runImport() {
    busy = true;
    submit.disabled = true;
    progress.hidden = false;
    progressBar.style.width = '0%';

    const fields = {
      artist: defaults.artist,
      character: defaults.character,
      tags: defaults.tags,
      rating: defaults.rating,
      artist_mode: defaults.artistMode,
      skip_duplicates: defaults.skipDuplicates ? 1 : 0,
    };

    try {
      let summaryPayload = null;
      if (entries.length) {
        progressLabel.textContent = '正在上传…';
        summaryPayload = await api.upload(entries, fields, (percent) => {
          progressBar.style.width = `${percent}%`;
          progressLabel.textContent = `正在上传 ${percent}%`;
        });
      }
      if (serverPaths.length) {
        progressBar.style.width = '100%';
        progressLabel.textContent = '正在导入服务器文件…';
        const local = await api.importLocal({
          paths: serverPaths,
          recursive: true,
          ...fields,
          skip_duplicates: defaults.skipDuplicates,
        });
        summaryPayload = summaryPayload
          ? {
              imported: summaryPayload.imported + local.imported,
              skipped: summaryPayload.skipped + local.skipped,
              failed: summaryPayload.failed + local.failed,
              results: [...summaryPayload.results, ...local.results],
            }
          : local;
      }

      clear(previewHost);
      const failures = (summaryPayload?.results || []).filter((entry) => entry.status === 'failed');
      previewHost.appendChild(
        el('div', { class: 'report' },
          el('div', { class: 'report__cell' },
            el('p', { class: 'report__value', text: String(summaryPayload?.imported ?? 0) }),
            el('p', { class: 'report__label', text: '已导入' }),
          ),
          el('div', { class: 'report__cell' },
            el('p', { class: 'report__value', text: String(summaryPayload?.skipped ?? 0) }),
            el('p', { class: 'report__label', text: '重复跳过' }),
          ),
          el('div', { class: 'report__cell' },
            el('p', { class: 'report__value', text: String(summaryPayload?.failed ?? 0) }),
            el('p', { class: 'report__label', text: '失败' }),
          ),
        ),
        failures.length
          ? el('div', { class: 'dialog__section' },
              el('p', { class: 'dialog__section-title', text: '失败明细' }),
              el('div', { class: 'list-plain' },
                failures.slice(0, 40).map((entry) =>
                  el('div', { class: 'list-plain__item' },
                    el('span', { class: 'truncate', text: entry.filename }),
                    el('span', { class: 'spacer' }),
                    el('span', { class: 'pill pill--alert', text: String(entry.reason || '未知') }),
                  ),
                ),
              ),
            )
          : null,
      );
      progressLabel.textContent = '导入完成';
      toast(`导入 ${summaryPayload?.imported ?? 0} 件，跳过 ${summaryPayload?.skipped ?? 0} 件`, { tag: '完成' });
      entries = [];
      serverPaths = [];
      onDone();
    } catch (error) {
      progressLabel.textContent = '';
      toast(error.message, { tag: '导入失败', kind: 'error' });
    } finally {
      busy = false;
      submit.disabled = false;
    }
  }

  const controller = openDialog({
    title: '导入作品',
    subtitle: '支持多文件、整个文件夹，或后端机器上的路径',
    render(ui) {
      ui.setBody(
        el('section', { class: 'dialog__section' },
          el('p', { class: 'dialog__section-title', text: '01 选择来源' }),
          dropzone,
          el('div', { style: { display: 'flex', gap: 'var(--unit)', marginTop: 'var(--unit)', flexWrap: 'wrap' } },
            el('button', { type: 'button', class: 'button', text: '选择文件', onClick: () => fileInput.click() }),
            el('button', { type: 'button', class: 'button', text: '选择文件夹', onClick: () => folderInput.click() }),
            el('button', {
              type: 'button',
              class: 'button',
              text: '清空',
              onClick: () => {
                entries = [];
                refreshPreview();
              },
            }),
            fileInput,
            folderInput,
          ),
          summary,
          el('div', { style: { marginTop: 'calc(var(--unit) * 1.5)' } },
            el('p', { class: 'rubric rubric--muted', text: '或者：从后端机器直接读取文件夹（不占用上传带宽）' }),
            serverInput,
            el('div', { style: { display: 'flex', gap: 'var(--unit)', marginTop: 'var(--unit)' } },
              el('button', { type: 'button', class: 'button', text: '扫描路径', onClick: scanServerPaths }),
            ),
            serverSummary,
          ),
        ),
        el('section', { class: 'dialog__section' },
          el('p', { class: 'dialog__section-title', text: '02 默认元数据' }),
          el('div', { class: 'form-grid' },
            el('div', { class: 'form-row form-row--wide' },
              el('label', { text: '画师归属方式' }),
              el('div', { class: 'segmented' }, modeButtons),
            ),
            el('div', { class: 'form-row' }, el('label', { text: '默认画师' }), artistSelect),
            el('div', { class: 'form-row' }, el('label', { text: '默认角色' }), characterSelect),
            el('div', { class: 'form-row' },
              el('label', { text: '默认标签（逗号分隔）' }),
              el('input', {
                class: 'input',
                onChange: (event) => {
                  defaults.tags = event.target.value;
                },
              }),
            ),
            el('div', { class: 'form-row' },
              el('label', { text: '默认评分 0–5' }),
              el('input', {
                class: 'input', type: 'number', min: '0', max: '5', value: '0',
                onChange: (event) => {
                  defaults.rating = Number(event.target.value) || 0;
                },
              }),
            ),
            el('div', { class: 'form-row form-row--wide' },
              el('label', { class: 'checkbox' },
                el('input', {
                  type: 'checkbox', checked: true,
                  onChange: (event) => {
                    defaults.skipDuplicates = event.target.checked;
                  },
                }),
                el('span', { text: '按内容校验值跳过重复图片' }),
              ),
            ),
          ),
        ),
        el('section', { class: 'dialog__section' },
          el('p', { class: 'dialog__section-title', text: '03 预览' }),
          previewHost,
          el('div', { style: { marginTop: 'var(--unit)' } }, progress, progressLabel),
        ),
      );
    },
    footer: [
      el('button', { type: 'button', class: 'button', text: '完成', onClick: () => controller.close() }),
      el('span', { class: 'spacer' }),
      submit,
    ],
  });

  refreshPreview();
  return controller;
}
