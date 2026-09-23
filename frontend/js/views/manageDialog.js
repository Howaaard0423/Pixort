/** Library management: artists, characters, maintenance and backups. */

import { clear, el, formatBytes } from '../dom.js';
import { api } from '../api.js';
import { confirmAction, openDialog, promptText, toast } from '../overlay.js';

const TABS = [
  { id: 'artists', label: '画师' },
  { id: 'characters', label: '角色' },
  { id: 'maintenance', label: '库维护' },
  { id: 'backup', label: '备份恢复' },
];

export function openManageDialog({ onChanged }) {
  let active = 'artists';

  const content = el('div', {});
  const tabButtons = TABS.map((tab) =>
    el('button', {
      type: 'button',
      class: 'segmented__item',
      text: tab.label,
      'aria-pressed': tab.id === active ? 'true' : 'false',
      onClick: () => {
        active = tab.id;
        for (const [index, button] of tabButtons.entries()) {
          button.setAttribute('aria-pressed', TABS[index].id === active ? 'true' : 'false');
        }
        render();
      },
    }),
  );

  const controller = openDialog({
    title: '管理',
    subtitle: '画师 · 角色 · 库维护 · 备份',
    render(ui) {
      ui.setBody(
        el('div', { class: 'segmented', style: { marginBottom: 'calc(var(--unit) * 2)' } }, tabButtons),
        content,
      );
    },
    footer: [el('button', { type: 'button', class: 'button', text: '关闭', onClick: () => controller.close() })],
  });

  async function reload() {
    onChanged();
    render();
  }

  /* --- sections ---------------------------------------------------------- */

  async function renderArtists() {
    const { items } = await api.artists();
    const input = el('input', { class: 'input', placeholder: '新增画师名称' });
    const add = el('button', {
      type: 'button',
      class: 'button button--solid',
      text: '新增',
      onClick: async () => {
        const name = input.value.trim();
        if (!name) return;
        await api.createArtist(name);
        input.value = '';
        toast(`已新增画师「${name}」`, { tag: '新增' });
        await reload();
      },
    });

    const list = el('div', { class: 'list-plain' },
      items.length
        ? items.map((artist) =>
            el('div', { class: 'list-plain__item' },
              el('span', { text: artist.name }),
              el('span', { class: 'pill', text: `${artist.count} 件` }),
              el('span', { class: 'spacer' }),
              el('button', {
                type: 'button',
                class: 'button button--small',
                text: '重命名',
                onClick: async () => {
                  const name = await promptText({
                    title: '重命名画师',
                    label: '新的名称',
                    value: artist.name,
                  });
                  if (!name) return;
                  await api.renameArtist(artist.id, name);
                  toast('已重命名', { tag: '保存' });
                  await reload();
                },
              }),
              el('button', {
                type: 'button',
                class: 'button button--small button--danger',
                text: '删除',
                onClick: async () => {
                  const ok = await confirmAction({
                    title: '删除画师',
                    message: `「${artist.name}」将被删除，其 ${artist.count} 件作品会失去画师关联。`
                      + '文件夹只有在没有任何记录引用时才会被移除。',
                    confirm: '删除',
                    danger: true,
                  });
                  if (!ok) return;
                  const result = await api.deleteArtist(artist.id, true);
                  toast(
                    `已删除，解除关联 ${result.detached_works} 件，移除文件 ${result.files_removed} 个`,
                    { tag: '删除' },
                  );
                  await reload();
                },
              }),
            ),
          )
        : el('p', { class: 'rail__empty', text: '还没有画师。导入作品时会自动创建。' }),
    );

    return [
      el('section', { class: 'dialog__section' },
        el('p', { class: 'dialog__section-title', text: '画师' }),
        el('div', { style: { display: 'flex', gap: 'var(--unit)', marginBottom: 'var(--unit)' } }, input, add),
        list,
      ),
    ];
  }

  async function renderCharacters() {
    const { items } = await api.characters();
    const input = el('input', { class: 'input', placeholder: '新增角色名称' });
    const add = el('button', {
      type: 'button',
      class: 'button button--solid',
      text: '新增',
      onClick: async () => {
        const name = input.value.trim();
        if (!name) return;
        await api.createCharacter(name);
        input.value = '';
        toast(`已新增角色「${name}」`, { tag: '新增' });
        await reload();
      },
    });

    const list = el('div', { class: 'list-plain' },
      items.length
        ? items.map((character) =>
            el('div', { class: 'list-plain__item' },
              el('span', { text: character.name }),
              el('span', { class: 'pill', text: `${character.count} 件` }),
              el('span', { class: 'spacer' }),
              el('button', {
                type: 'button',
                class: 'button button--small',
                text: '重命名',
                onClick: async () => {
                  const name = await promptText({
                    title: '重命名角色',
                    label: '新的名称',
                    value: character.name,
                  });
                  if (!name) return;
                  await api.renameCharacter(character.id, name);
                  await reload();
                },
              }),
              el('button', {
                type: 'button',
                class: 'button button--small button--danger',
                text: '删除',
                onClick: async () => {
                  const ok = await confirmAction({
                    title: '删除角色',
                    message: `「${character.name}」将被删除，${character.count} 件作品会清空角色关联。`,
                    confirm: '删除',
                    danger: true,
                  });
                  if (!ok) return;
                  await api.deleteCharacter(character.id);
                  toast('已删除', { tag: '删除' });
                  await reload();
                },
              }),
            ),
          )
        : el('p', { class: 'rail__empty', text: '还没有角色。' }),
    );

    return [
      el('section', { class: 'dialog__section' },
        el('p', { class: 'dialog__section-title', text: '角色' }),
        el('div', { style: { display: 'flex', gap: 'var(--unit)', marginBottom: 'var(--unit)' } }, input, add),
        list,
      ),
    ];
  }

  function renderMaintenance() {
    const repair = el('input', { type: 'checkbox', checked: true });
    const refresh = el('input', { type: 'checkbox', checked: true });
    const dedupe = el('input', { type: 'checkbox' });
    const report = el('div', {});

    const run = async (dryRun) => {
      clear(report);
      report.appendChild(el('p', { class: 'rubric rubric--muted', text: dryRun ? '正在预演…' : '正在执行…' }));
      try {
        const result = await api.maintenance({
          repair: repair.checked,
          refresh_metadata: refresh.checked,
          dedupe: dedupe.checked,
          dry_run: dryRun,
        });
        renderReport(report, result, dryRun);
        if (!dryRun) {
          toast(`重建关联 ${result.applied.relinked} 条，补齐元数据 ${result.applied.metadata_refreshed} 条`, {
            tag: '维护',
          });
          onChanged();
        }
      } catch (error) {
        clear(report);
        report.appendChild(el('p', { class: 'notice', text: error.message }));
      }
    };

    return [
      el('section', { class: 'dialog__section' },
        el('p', { class: 'dialog__section-title', text: '库维护' }),
        el('p', { class: 'notice', text:
          '重新导入同一批图片会生成带新时间戳的副本，旧记录会指向不存在的文件名。'
          + '维护会按原始文件名把记录重新关联到磁盘上的文件，并补全尺寸与校验值。' }),
        el('div', { class: 'form-grid', style: { marginTop: 'calc(var(--unit) * 1.5)' } },
          el('label', { class: 'checkbox' }, repair, el('span', { text: '重新关联丢失的文件' })),
          el('label', { class: 'checkbox' }, refresh, el('span', { text: '补全尺寸 / 体积 / 校验值' })),
          el('label', { class: 'checkbox' }, dedupe, el('span', { text: '删除指向同一文件的重复记录' })),
        ),
        el('div', { style: { display: 'flex', gap: 'var(--unit)', margin: 'calc(var(--unit) * 1.5) 0' } },
          el('button', { type: 'button', class: 'button', text: '预演（不写入）', onClick: () => run(true) }),
          el('button', { type: 'button', class: 'button button--solid', text: '执行维护', onClick: () => run(false) }),
        ),
        report,
      ),
    ];
  }

  function renderReport(host, result, dryRun) {
    clear(host);
    const cell = (value, label) =>
      el('div', { class: 'report__cell' },
        el('p', { class: 'report__value', text: String(value) }),
        el('p', { class: 'report__label', text: label }),
      );

    host.append(
      el('p', { class: 'rubric', text: dryRun ? '预演结果（未写入）' : '维护结果' }),
      el('div', { class: 'report', style: { marginTop: 'var(--unit)' } },
        cell(result.scanned, '扫描记录'),
        cell(result.relinked.length, '重新关联'),
        cell(result.metadata_refreshed, '补齐元数据'),
        cell(result.duplicates.length, '重复组'),
        cell(result.missing.length, '仍然缺失'),
      ),
    );

    if (result.missing.length) {
      host.appendChild(
        el('div', { class: 'dialog__section' },
          el('p', { class: 'dialog__section-title', text: '找不到文件的记录' }),
          el('div', { class: 'list-plain' },
            result.missing.slice(0, 40).map((entry) =>
              el('div', { class: 'list-plain__item' },
                el('span', { class: 'mono', text: `#${entry.id}` }),
                el('span', { class: 'truncate', text: entry.file_path, title: entry.file_path }),
              ),
            ),
          ),
        ),
      );
    }
  }

  async function renderBackup() {
    const password = el('input', { class: 'input', type: 'password', placeholder: '可选：压缩包密码' });
    const exportsHost = el('div', {});

    const loadExports = async () => {
      clear(exportsHost);
      try {
        const { items } = await api.exports();
        exportsHost.appendChild(
          el('div', { class: 'list-plain' },
            items.length
              ? items.slice(0, 8).map((entry) =>
                  el('div', { class: 'list-plain__item' },
                    el('span', { class: 'mono', text: entry.name }),
                    el('span', { class: 'spacer' }),
                    el('span', { class: 'pill', text: formatBytes(entry.bytes) }),
                    el('a', {
                      class: 'button button--small',
                      href: api.exportFileUrl(entry.name),
                      download: entry.name,
                      text: '下载',
                    }),
                  ),
                )
              : el('p', { class: 'rail__empty', text: '还没有导出记录。' }),
          ),
        );
      } catch (error) {
        exportsHost.appendChild(el('p', { class: 'notice', text: error.message }));
      }
    };

    const restoreInput = el('input', {
      type: 'file',
      accept: '.zip',
      onChange: async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        const ok = await confirmAction({
          title: '恢复数据',
          message:
            `将用「${file.name}」覆盖当前数据库与图片目录。`
            + '现有数据会先被备份到旁边的 .bak-* 与 illustrations_old_* 目录。',
          confirm: '覆盖并恢复',
          danger: true,
        });
        event.target.value = '';
        if (!ok) return;
        try {
          const result = await api.restoreBackupFile(file, {
            password: password.value || undefined,
            confirm: 1,
          });
          toast(`恢复完成：${result.images} 个图片文件`, { tag: '恢复' });
          onChanged();
        } catch (error) {
          toast(error.message, { tag: '恢复失败', kind: 'error' });
        }
      },
    });

    const info = el('p', { class: 'rubric rubric--muted', text: '' });

    const inspectInput = el('input', {
      type: 'file',
      accept: '.zip',
      onChange: async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        info.textContent = '正在读取…';
        try {
          const result = await api.inspectBackupFile(file, { password: password.value || undefined });
          info.textContent =
            `${result.members} 个条目 · 解压后 ${formatBytes(result.uncompressed_bytes)} · `
            + `数据库 ${result.databases.join(',') || '无'} · ${result.valid ? '结构完整' : '结构不完整'}`;
        } catch (error) {
          info.textContent = error.message;
        }
        event.target.value = '';
      },
    });

    loadExports();

    return [
      el('section', { class: 'dialog__section' },
        el('p', { class: 'dialog__section-title', text: '导出备份' }),
        el('p', { class: 'notice', text:
          '导出包含数据库与全部图片的 ZIP。图片已是压缩格式，因此以原样存储，只对数据库做压缩。' }),
        el('div', { style: { display: 'flex', gap: 'var(--unit)', alignItems: 'flex-end', marginTop: 'var(--unit)' } },
          el('div', { class: 'form-row', style: { flex: '1' } },
            el('label', { text: '密码（留空则不加密）' }),
            password,
          ),
          el('a', {
            class: 'button button--solid',
            href: '#',
            text: '导出并下载',
            onClick: (event) => {
              event.preventDefault();
              const url = api.exportUrl({ password: password.value || undefined });
              if (!url) {
                toast('演示模式不提供备份下载，请在本机运行后端。', { tag: '演示', kind: 'error' });
                return;
              }
              window.location.href = url;
              window.setTimeout(loadExports, 1500);
            },
          }),
        ),
        el('div', { style: { marginTop: 'calc(var(--unit) * 1.5)' } },
          el('p', { class: 'rubric rubric--muted', text: '最近的导出' }),
          exportsHost,
          el('div', { style: { marginTop: 'var(--unit)' } },
            el('button', {
              type: 'button',
              class: 'button button--small',
              text: '清空导出记录',
              onClick: async () => {
                const ok = await confirmAction({
                  title: '清空导出记录',
                  message: '导出目录里的 ZIP 会被删除，数据库与图片不受影响。',
                  confirm: '清空',
                  danger: true,
                });
                if (!ok) return;
                const result = await api.clearExports();
                toast(`已删除 ${result.removed} 个导出文件`, { tag: '清理' });
                await loadExports();
              },
            }),
          ),
        ),
      ),
      el('section', { class: 'dialog__section' },
        el('p', { class: 'dialog__section-title', text: '恢复备份' }),
        el('p', { class: 'notice', text: '先校验压缩包结构，确认后再覆盖。恢复会替换数据库与插画目录。' }),
        el('div', { style: { display: 'flex', gap: 'var(--unit)', marginTop: 'var(--unit)', flexWrap: 'wrap' } },
          el('button', { type: 'button', class: 'button', text: '仅校验压缩包', onClick: () => inspectInput.click() }),
          el('button', { type: 'button', class: 'button button--danger', text: '选择备份并恢复', onClick: () => restoreInput.click() }),
          inspectInput,
          restoreInput,
        ),
        info,
      ),
    ];
  }

  async function render() {
    clear(content);
    content.appendChild(el('p', { class: 'skeleton', text: '正在载入…' }));
    try {
      const nodes = await {
        artists: renderArtists,
        characters: renderCharacters,
        maintenance: async () => renderMaintenance(),
        backup: renderBackup,
      }[active]();
      clear(content);
      content.append(...nodes);
    } catch (error) {
      clear(content);
      content.appendChild(el('p', { class: 'notice', text: error.message }));
    }
  }

  render();
  return controller;
}
