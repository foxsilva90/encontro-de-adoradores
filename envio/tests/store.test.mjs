import { test } from 'node:test';
import assert from 'node:assert/strict';

process.env.ADMIN_SECRET = 'segredo-de-teste-com-tamanho-suficiente';
process.env.CODIGOS_LOCUTORES = JSON.stringify({ 'TALITO-7K2P9QX4': 'PG Talito' });
const { readConfig, writeConfig, readConfigForAdmin } = await import('../api/_store.js');
const { BlobPreconditionFailedError } = await import('@vercel/blob');

// Blob falso em memória: cada put com sufixo cria um arquivo novo.
function fakeBlob(initial = []) {
  const files = new Map(initial.map((f) => [f.pathname, f]));
  let n = 0;
  return {
    files,
    listFn: async ({ prefix }) => ({ blobs: [...files.values()].filter((f) => f.pathname.startsWith(prefix)) }),
    putFn: async (path, body) => {
      n += 1;
      const pathname = path.replace('.enc', `-v${n}.enc`);
      files.set(pathname, { pathname, url: `https://b/${pathname}`, body, uploadedAt: new Date(Date.UTC(2026, 0, 1, 0, 0, n)) });
      return { pathname };
    },
    delFn: async (urls) => { for (const u of urls) files.delete(u.replace('https://b/', '')); },
    fetchFn: async (url) => new Response(files.get(url.replace('https://b/', '')).body),
  };
}

test('sem nada salvo, usa a variável e a primeira gravação cria a versão', async () => {
  const b = fakeBlob();
  const first = await readConfig(b);
  assert.equal(first.etag, null);
  assert.equal(first.config.locutores.length, 1);
  const admin = await readConfigForAdmin(b);
  assert.ok(admin.etag);
  assert.equal((await readConfig(b)).etag, admin.etag);
});

test('gravações seguidas não perdem nada (lê sempre a versão mais nova)', async () => {
  const b = fakeBlob();
  let { config, etag } = await readConfigForAdmin(b);
  for (const nome of ['A', 'B', 'C']) {
    const next = { ...config, locutores: config.locutores.map((l) => ({ ...l, nome: l.nome + nome })) };
    await writeConfig(next, etag, b);
    ({ config, etag } = await readConfig(b));
  }
  assert.ok(config.locutores[0].nome.endsWith('ABC'));
});

test('gravar com versão desatualizada dá conflito', async () => {
  const b = fakeBlob();
  const { config, etag } = await readConfigForAdmin(b);
  await writeConfig(config, etag, b);
  await assert.rejects(writeConfig(config, etag, b), BlobPreconditionFailedError);
});

test('guarda só as últimas 10 versões', async () => {
  const b = fakeBlob();
  let { config, etag } = await readConfigForAdmin(b);
  for (let i = 0; i < 15; i += 1) etag = await writeConfig(config, etag, b);
  assert.equal(b.files.size, 10);
  assert.equal((await readConfig(b)).etag, etag);
});

test('migra o arquivo antigo (config/locutores.enc) se existir', async () => {
  const b = fakeBlob();
  const { config } = await readConfigForAdmin(b);
  const legacyBody = [...b.files.values()][0].body;
  const old = fakeBlob([{ pathname: 'config/locutores.enc', url: 'https://b/config/locutores.enc', body: legacyBody, uploadedAt: new Date(0) }]);
  const res = await readConfig(old);
  assert.equal(res.etag, null);
  assert.deepEqual(res.config, config);
});
