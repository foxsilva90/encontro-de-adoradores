import { test } from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';

import {
  verifySignature,
  phoneVariants,
  parseProgramMap,
  findProgram,
  extractAudioMessages,
} from '../api/_whatsapp.js';

const SECRET = 'segredo-do-app';
const sign = (body) =>
  'sha256=' + crypto.createHmac('sha256', SECRET).update(body).digest('hex');

test('aceita assinatura válida da Meta', () => {
  const body = '{"a":1}';
  assert.equal(verifySignature(body, sign(body), SECRET), true);
});

test('rejeita assinatura de outro corpo, ausente ou sem segredo', () => {
  assert.equal(verifySignature('{"a":2}', sign('{"a":1}'), SECRET), false);
  assert.equal(verifySignature('{"a":1}', undefined, SECRET), false);
  assert.equal(verifySignature('{"a":1}', 'sha256=abc', SECRET), false);
  assert.equal(verifySignature('{"a":1}', sign('{"a":1}'), ''), false);
});

test('gera variantes do celular brasileiro com e sem o nono dígito', () => {
  assert.deepEqual(phoneVariants('5511988887777').sort(), ['551188887777', '5511988887777']);
  assert.deepEqual(phoneVariants('551188887777').sort(), ['551188887777', '5511988887777']);
  assert.deepEqual(phoneVariants('+55 (11) 98888-7777').sort(), ['551188887777', '5511988887777']);
  assert.deepEqual(phoneVariants('14155550123'), ['14155550123']);
});

test('lê o mapa número→programa e ignora entradas inválidas', () => {
  const map = parseProgramMap('{"+55 11 98888-7777": "Manhã com Deus", "x": "", "5521": 3}');
  assert.deepEqual(map, { '5511988887777': 'Manhã com Deus' });
  assert.deepEqual(parseProgramMap('não é json'), {});
  assert.deepEqual(parseProgramMap(undefined), {});
});

test('encontra o programa mesmo quando a Meta manda o número sem o 9', () => {
  const map = parseProgramMap('{"5511988887777": "Manhã com Deus"}');
  assert.equal(findProgram(map, '551188887777'), 'Manhã com Deus');
  assert.equal(findProgram(map, '5511988887777'), 'Manhã com Deus');
  assert.equal(findProgram(map, '5511900000000'), null);
});

function payload(messages) {
  return {
    object: 'whatsapp_business_account',
    entry: [{ changes: [{ field: 'messages', value: { messages } }] }],
  };
}

test('extrai áudio de voz e arquivo de áudio enviado como documento', () => {
  const out = extractAudioMessages(
    payload([
      { from: '5511988887777', id: 'w1', type: 'audio', audio: { id: 'm1', mime_type: 'audio/ogg' } },
      { from: '5511988887777', id: 'w2', type: 'document', document: { id: 'm2', mime_type: 'audio/mpeg' } },
      { from: '5511988887777', id: 'w3', type: 'document', document: { id: 'm3', mime_type: 'application/pdf' } },
      { from: '5511988887777', id: 'w4', type: 'text', text: { body: 'oi' } },
    ]),
  );
  assert.deepEqual(out, [
    { from: '5511988887777', messageId: 'w1', mediaId: 'm1' },
    { from: '5511988887777', messageId: 'w2', mediaId: 'm2' },
  ]);
});

test('ignora payload vazio, de status ou malformado', () => {
  assert.deepEqual(extractAudioMessages({}), []);
  assert.deepEqual(extractAudioMessages(null), []);
  assert.deepEqual(
    extractAudioMessages({ entry: [{ changes: [{ value: { statuses: [{ id: 's' }] } }] }] }),
    [],
  );
  assert.deepEqual(
    extractAudioMessages(payload([{ from: '55', type: 'audio', audio: { id: 'bad id!' } }])),
    [],
  );
});
