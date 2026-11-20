import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  AUDIO_FOOTER, AUDIO_MAX_SECONDS, AUDIO_MIN_SECONDS, confidenceText, emotionLabel,
  recordingContentType, validateDuration,
} from '../src/lib/audio-message.ts';

test('validateDuration enforces 1–60 seconds', () => {
  assert.deepEqual(validateDuration(1), { ok: true, value: 1 });
  assert.deepEqual(validateDuration(60), { ok: true, value: 60 });
  assert.equal(validateDuration(0.5).ok, false);
  assert.equal(validateDuration(60.5).ok, false);
  assert.equal(validateDuration(Number.NaN).ok, false);
  assert.equal(validateDuration(-3).ok, false);
  assert.equal(AUDIO_MIN_SECONDS, 1);
  assert.equal(AUDIO_MAX_SECONDS, 60);
});

test('emotionLabel covers six emotions plus unrecognized', () => {
  assert.equal(emotionLabel('happy'), '开心');
  assert.equal(emotionLabel('relaxed'), '放松');
  assert.equal(emotionLabel('annoyed'), '烦躁');
  assert.equal(emotionLabel('fearful'), '害怕');
  assert.equal(emotionLabel('painful'), '疼痛');
  assert.equal(emotionLabel('seeking_attention'), '求关注');
  assert.equal(emotionLabel('unrecognized'), '未识别');
  assert.equal(emotionLabel('whatever'), '未识别');
  assert.equal(emotionLabel(null), '未识别');
});

test('confidenceText marks low confidence as uncertain', () => {
  assert.equal(confidenceText('happy', 0.82), '置信度 82%');
  assert.equal(confidenceText('happy', 0.3), '不太确定');
  assert.equal(confidenceText('happy', 0.4), '置信度 40%');
  assert.equal(confidenceText('happy', null), '不太确定');
  assert.equal(confidenceText('unrecognized', 0.9), '未识别');
  assert.equal(confidenceText('unrecognized', null), '未识别');
});

test('audio footer matches FRD appendix verbatim', () => {
  assert.equal(AUDIO_FOOTER, '情绪解读为娱乐性参考,置信度仅供判断展示。');
});

test('recordingContentType maps recorder output extensions', () => {
  assert.equal(recordingContentType('file:///tmp/rec.m4a'), 'audio/mp4');
  assert.equal(recordingContentType('file:///tmp/rec.wav'), 'audio/wav');
  assert.equal(recordingContentType('file:///tmp/rec.webm'), 'audio/webm');
  assert.equal(recordingContentType('file:///tmp/rec.mp3'), 'audio/mpeg');
  assert.equal(recordingContentType('file:///tmp/unknown'), 'audio/mp4');
});