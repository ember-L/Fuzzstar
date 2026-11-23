import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DISCLAIMER, STATE_LABELS, buildPayload, emptyForm, mediaLimitError, missingFields, stateTone } from '../src/lib/screening.ts';

const config = {
  version: 'sx-2026-11-19',
  duration_bands: ['<2h', '2-12h', '12-24h', '>24h'],
  frequency_bands: ['1', '2-3', '4-6', '>6'],
  spirit_options: ['normal', 'slightly_down', 'markedly_down'],
  appetite_options: ['normal', 'decreased', 'refused'],
  notes_max: 255,
  symptoms: [
    { code: 'vomiting', label: '呕吐', frequency: true, severe_label: null },
    { code: 'limping', label: '跛行', frequency: false, severe_label: '患肢不敢着地' },
  ],
  redlines: [],
};

function validForm() {
  const form = emptyForm();
  form.spirit = 'normal';
  form.appetite = 'normal';
  form.symptoms.vomiting = { duration: '2-12h', frequency: '1', notes: '', severe: false };
  return form;
}

test('emptyForm returns independent instances', () => {
  const a = emptyForm();
  const b = emptyForm();
  a.symptoms.vomiting = { duration: '<2h', frequency: null, notes: '', severe: false };
  assert.deepEqual(b.symptoms, {});
  assert.deepEqual(a.media, []);
});

test('missingFields locates spirit and appetite first', () => {
  assert.deepEqual(missingFields(config, emptyForm()), ['spirit', 'appetite']);
});

test('missingFields locates per-symptom duration and frequency', () => {
  const form = validForm();
  form.symptoms.vomiting = { duration: null, frequency: null, notes: '', severe: false };
  form.symptoms.limping = { duration: null, frequency: null, notes: '', severe: false };
  assert.deepEqual(missingFields(config, form), ['vomiting.duration', 'vomiting.frequency', 'limping.duration']);
});

test('missingFields empty for a complete form', () => {
  assert.deepEqual(missingFields(config, validForm()), []);
});

test('buildPayload omits empty notes and false severe, keeps answers', () => {
  const form = validForm();
  form.symptoms.limping = { duration: '<2h', frequency: null, notes: '不敢着地', severe: true };
  form.redlineOptions = ['lily'];
  form.media = [{ mediaId: 'a'.repeat(32), kind: 'photo' }];
  const payload = buildPayload(form);
  assert.equal(payload.spirit, 'normal');
  assert.deepEqual(payload.symptoms[0], { code: 'vomiting', duration: '2-12h', frequency: '1' });
  assert.deepEqual(payload.symptoms[1], { code: 'limping', duration: '<2h', notes: '不敢着地', severe: true });
  assert.deepEqual(payload.redline_options, ['lily']);
  assert.deepEqual(payload.media_ids, ['a'.repeat(32)]);
});

test('mediaLimitError enforces three photos and one video', () => {
  const photo = { mediaId: 'x', kind: 'photo' };
  const video = { mediaId: 'y', kind: 'video' };
  assert.equal(mediaLimitError([photo, photo, photo, video]), null);
  assert.ok(mediaLimitError([photo, photo, photo, photo]));
  assert.ok(mediaLimitError([video, video]));
});

test('state labels and tones cover all four states', () => {
  assert.equal(STATE_LABELS.urgent, '建议立即就医');
  assert.equal(stateTone('normal'), 'ok');
  assert.equal(stateTone('observe'), 'watch');
  assert.equal(stateTone('vet'), 'vet');
  assert.equal(stateTone('urgent'), 'urgent');
});

test('disclaimer is verbatim FRD appendix F', () => {
  assert.equal(DISCLAIMER, 'AI 结果仅供日常健康管理参考,不替代专业兽医诊断');
});
