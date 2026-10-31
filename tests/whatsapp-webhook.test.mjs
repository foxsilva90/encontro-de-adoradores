import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';

import { GET, POST } from '../api/whatsapp-webhook.js';

const SECRET = 'segredo-do-app';
const URL_BASE = 'https://exemplo.com/api/whatsapp-webhook';
const realFetch = globalThis.fetch;
let calls;

beforeEach(() => {
  process.env.WHATSAPP_VERIFY_TOKEN = 'tok';
  process.env.WHATSAPP_APP_SECRET = SECRET;
  process.env.PROGRAMAS_WHATSAPP = '{"5511988887777": "Manhã com Deus"}';
  process.env.GITHUB_DISPATCH_TOKEN = 'gh';
  process.env.GITHUB_REPO = 'dono/repo';
  calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, body: JSON.parse(init.body) });
    return new Response(null, { status: 204 });
  };
});
afterEach(() => { globalThis.fetch = realFetch; });

function signedPost(obj, secret = SECRET) {
  const body = JSON.stringify(obj);
  const sig = 'sha256=' + crypto.createHmac('sha256', secret).update(body).digest('hex');
  return new Request(URL_BASE, { method: 'POST', body, headers: { 'x-hub-signature-256': sig } });
}
const audioFrom = (from) => ({
  entry: [{ changes: [{ value: { messages: [{ from, id: 'w1', type: 'audio', audio: { id: 'm1' } }] } }] }],
});

test('GET devolve o challenge só com o token certo', async () => {
  const ok = await GET(new Request(`${URL_BASE}?hub.mode=subscribe&hub.verify_token=tok&hub.challenge=123`));
  assert.equal(ok.status, 200);
  assert.equal(await ok.text(), '123');
  const bad = await GET(new Request(`${URL_BASE}?hub.mode=subscribe&hub.verify_token=x&hub.challenge=123`));
  assert.equal(bad.status, 403);
});

test('POST com assinatura inválida é recusado e não dispara nada', async () => {
  const res = await POST(signedPost(audioFrom('5511988887777'), 'outro'));
  assert.equal(res.status, 401);
  assert.equal(calls.length, 0);
});

test('áudio de locutor cadastrado dispara o workflow sem expor o número', async () => {
  const res = await POST(signedPost(audioFrom('551188887777')));
  assert.equal(res.status, 200);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /dono\/repo\/actions\/workflows\/publicar-programa\.yml\/dispatches$/);
  assert.deepEqual(calls[0].body, { ref: 'main', inputs: { media_id: 'm1', programa: 'Manhã com Deus' } });
  assert.ok(!JSON.stringify(calls[0].body).includes('8888'));
});

test('áudio de ouvinte é ignorado', async () => {
  const res = await POST(signedPost(audioFrom('5521977776666')));
  assert.equal(res.status, 200);
  assert.equal(calls.length, 0);
});

test('falha no GitHub devolve 500 pra Meta reenviar', async () => {
  globalThis.fetch = async () => new Response(null, { status: 422 });
  const original = console.error;
  console.error = () => {};
  try {
    const res = await POST(signedPost(audioFrom('5511988887777')));
    assert.equal(res.status, 500);
  } finally {
    console.error = original;
  }
});
