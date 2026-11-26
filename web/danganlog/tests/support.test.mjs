import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveSupport } from '../lib/support.js';

test('unset or malformed values are treated as not configured', () => {
  const s = resolveSupport({ client: 'pub-1', slot: 'abc', bmc: 'http://buymeacoffee.com/x', contact: 'nope' });
  assert.equal(s.adsLive, false);
  assert.equal(s.adsenseClient, '');
  assert.equal(s.coffeeUrl, '');
  assert.equal(s.contactEmail, '');
  assert.equal(s.adsTxt, '');
});

test('client and slot together enable ads and produce the official ads.txt line', () => {
  const s = resolveSupport({ client: 'ca-pub-1234567890123456', slot: '1234567890' });
  assert.equal(s.adsLive, true);
  assert.equal(s.adsTxt, 'google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0\n');
});

test('client without slot does not load ads but still yields ads.txt and ownership id', () => {
  const s = resolveSupport({ client: 'ca-pub-1234567890123456' });
  assert.equal(s.adsLive, false);
  assert.ok(s.adsTxt.startsWith('google.com, pub-1234567890123456'));
});

test('preview is ignored once live ads are configured', () => {
  assert.equal(resolveSupport({ preview: 'true' }).adsPreview, true);
  assert.equal(resolveSupport({ preview: 'true', client: 'ca-pub-1234567890123456', slot: '1234567890' }).adsPreview, false);
});

test('only buymeacoffee.com https profile URLs are accepted', () => {
  assert.equal(resolveSupport({ bmc: 'https://www.buymeacoffee.com/someone' }).coffeeUrl, 'https://www.buymeacoffee.com/someone');
  assert.equal(resolveSupport({ bmc: 'https://evil.example/buymeacoffee.com/x' }).coffeeUrl, '');
  assert.equal(resolveSupport({ bmc: 'https://buymeacoffee.com/a/b' }).coffeeUrl, '');
});
