/** Editing the metadata of one work. */

import { el } from '../dom.js';
import { api } from '../api.js';
import { openDialog, toast } from '../overlay.js';

export function openEditDialog(item, { artists, characters, onSaved }) {
  const artistSelect = el('select', { class: 'select' },
    el('option', { value: '', text: '未分类' }),
    artists.map((artist) => el('option', { value: String(artist.id), text: artist.name })),
  );
  artistSelect.value = item.artist_id ? String(item.artist_id) : '';

  const characterSelect = el('select', { class: 'select' },
    el('option', { value: '', text: '无' }),
    characters.map((character) => el('option', { value: String(character.id), text: character.name })),
  );
  characterSelect.value = item.character_id ? String(item.character_id) : '';

  const titleInput = el('input', { class: 'input', value: item.title || '' });
  const tagsInput = el('input', { class: 'input', value: (item.tags || []).join(', ') });
  const ratingInput = el('input', { class: 'input', type: 'number', min: '0', max: '5', value: String(item.rating || 0) });
  const remarkInput = el('textarea', { class: 'textarea' });
  remarkInput.value = item.remark || '';

  const status = el('p', { class: 'rubric rubric--muted', text: '' });

  const submit = el('button', {
    type: 'button',
    class: 'button button--solid',
    text: '保存',
    onClick: async () => {
      submit.disabled = true;
      status.textContent = '正在保存…';
      try {
        const updated = await api.updateIllustration(item.id, {
          artist_id: artistSelect.value ? Number(artistSelect.value) : null,
          character_id: characterSelect.value ? Number(characterSelect.value) : null,
          title: titleInput.value.trim(),
          tags: tagsInput.value,
          rating: Number(ratingInput.value) || 0,
          remark: remarkInput.value,
        });
        toast('作品信息已更新', { tag: '保存' });
        controller.close();
        onSaved(updated);
      } catch (error) {
        status.textContent = '';
        toast(error.message, { tag: '失败', kind: 'error' });
        submit.disabled = false;
      }
    },
  });

  const controller = openDialog({
    title: '编辑作品',
    subtitle: item.file_name,
    className: 'dialog--narrow',
    render(ui) {
      ui.setBody(
        el('div', { class: 'form-grid' },
          el('div', { class: 'form-row' }, el('label', { text: '画师' }), artistSelect),
          el('div', { class: 'form-row' }, el('label', { text: '角色' }), characterSelect),
          el('div', { class: 'form-row form-row--wide' }, el('label', { text: '标题' }), titleInput),
          el('div', { class: 'form-row' }, el('label', { text: '标签（逗号分隔）' }), tagsInput),
          el('div', { class: 'form-row' }, el('label', { text: '评分 0–5' }), ratingInput),
          el('div', { class: 'form-row form-row--wide' }, el('label', { text: '备注' }), remarkInput),
        ),
        status,
      );
    },
    footer: [
      el('button', { type: 'button', class: 'button', text: '取消', onClick: () => controller.close() }),
      submit,
    ],
  });
  return controller;
}
