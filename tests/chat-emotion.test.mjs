import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createEmotionBus, emotionBus } from '../src/lib/chat-emotion.ts';

test('publish assigns increasing ids and carries petId', () => {
  const bus = createEmotionBus();
  assert.deepEqual(bus.publish(7, 'happy'), { id: 1, petId: 7, emotion: 'happy' });
  assert.deepEqual(bus.publish(9, 'sad'), { id: 2, petId: 9, emotion: 'sad' });
});

test('subscribers receive events in order', () => {
  const bus = createEmotionBus();
  const seen = [];
  bus.subscribe(e => seen.push(e));
  bus.publish(1, 'happy');
  bus.publish(1, 'relaxed');
  assert.deepEqual(seen.map(e => e.emotion), ['happy', 'relaxed']);
});

test('unsubscribe stops delivery', () => {
  const bus = createEmotionBus();
  const seen = [];
  const off = bus.subscribe(e => seen.push(e));
  bus.publish(1, 'happy');
  off();
  bus.publish(1, 'sad');
  assert.equal(seen.length, 1);
});

test('multiple subscribers and shared singleton', () => {
  const bus = createEmotionBus();
  const a = []; const b = [];
  bus.subscribe(e => a.push(e.id));
  bus.subscribe(e => b.push(e.id));
  bus.publish(1, 'happy');
  assert.deepEqual(a, [1]);
  assert.deepEqual(b, [1]);
  assert.equal(typeof emotionBus.publish, 'function');
  assert.equal(typeof emotionBus.subscribe, 'function');
});

test('consumers can filter events by pet (Ruling 12: only selected cat animates)', () => {
  const bus = createEmotionBus();
  const selected = [];
  bus.subscribe(e => { if (e.petId === 7) selected.push(e.emotion); });
  bus.publish(9, 'happy');
  bus.publish(7, 'painful');
  assert.deepEqual(selected, ['painful']);
});
