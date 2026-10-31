import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  parseCodeMap,
  findProgramByCode,
  isOurBlobUrl,
  isAllowedUploadPath,
  isExpired,
} from '../api/_locutores.js';

const MAP = parseCodeMap('{"MANHA-7K2P9QX4": "Manhã com Deus", "curto": "X", "NOITE-AB12CD34": ""}');

test('lê só códigos válidos (8+ caracteres e programa preenchido)', () => {
  assert.deepEqual(MAP, { 'MANHA-7K2P9QX4': 'Manhã com Deus' });
  assert.deepEqual(parseCodeMap('lixo'), {});
  assert.deepEqual(parseCodeMap(undefined), {});
});

test('código ignora maiúsculas e espaços em volta', () => {
  assert.equal(findProgramByCode(MAP, '  manha-7k2p9qx4 '), 'Manhã com Deus');
  assert.equal(findProgramByCode(MAP, 'MANHA-7K2P9QX5'), null);
  assert.equal(findProgramByCode(MAP, ''), null);
  assert.equal(findProgramByCode(MAP, null), null);
  assert.equal(findProgramByCode(MAP, 'x'.repeat(500)), null);
});

test('aceita só links públicos do Vercel Blob na pasta programas/', () => {
  assert.equal(isOurBlobUrl('https://abc123.public.blob.vercel-storage.com/programas/a-XyZ.mp3'), true);
  assert.equal(isOurBlobUrl('https://abc123.public.blob.vercel-storage.com/outra/a.mp3'), false);
  assert.equal(isOurBlobUrl('http://abc123.public.blob.vercel-storage.com/programas/a.mp3'), false);
  assert.equal(isOurBlobUrl('https://abc.public.blob.vercel-storage.com.evil.com/programas/a.mp3'), false);
  assert.equal(isOurBlobUrl('não é url'), false);
});

test('caminho de upload precisa ficar em programas/ sem subir pasta', () => {
  assert.equal(isAllowedUploadPath('programas/manha-com-deus/voz.mp3'), true);
  assert.equal(isAllowedUploadPath('outra/voz.mp3'), false);
  assert.equal(isAllowedUploadPath('programas/../x.mp3'), false);
});

test('arquivo temporário expira depois de 24h', () => {
  const now = Date.parse('2026-10-31T12:00:00Z');
  assert.equal(isExpired('2026-10-30T11:59:00Z', now), true);
  assert.equal(isExpired('2026-10-31T10:00:00Z', now), false);
});
