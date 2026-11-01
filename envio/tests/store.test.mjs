import { test } from 'node:test';
import assert from 'node:assert/strict';

process.env.ADMIN_SECRET = 'segredo-de-teste-com-tamanho-suficiente';
process.env.CODIGOS_LOCUTORES = JSON.stringify({ 'TALITO-7K2P9QX4': 'PG Talito' });
const { readConfig, CONFIG_PATH } = await import('../api/_store.js');
const { encryptJson, keyFor } = await import('../api/_crypto.js');

test('usa o etag do head e baixa a versão exata', async () => {
  const config = { locutores: [] };
  const body = encryptJson(config, keyFor(process.env.ADMIN_SECRET, 'config'));
  let fetched;
  const res = await readConfig({
    headFn: async (p) => { assert.equal(p, CONFIG_PATH); return { url: 'https://x.public.blob.vercel-storage.com/config/locutores.enc', etag: '"abc"' }; },
    fetchFn: async (url) => { fetched = url; return new Response(body); },
  });
  assert.deepEqual(res, { config, etag: '"abc"' });
  assert.equal(new URL(fetched).searchParams.get('v'), '"abc"');
});

test('sem cadastro salvo, cai na variável de ambiente', async () => {
  const err = Object.assign(new Error('x'), { name: 'BlobNotFoundError' });
  const res = await readConfig({ headFn: async () => { throw err; }, fetchFn: async () => assert.fail() });
  assert.equal(res.etag, null);
  assert.equal(res.config.locutores.length, 1);
});

test('outros erros do head sobem', async () => {
  await assert.rejects(readConfig({ headFn: async () => { throw new Error('rede'); } }), /rede/);
});
