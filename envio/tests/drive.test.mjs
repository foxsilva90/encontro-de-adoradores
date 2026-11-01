import { test } from 'node:test';
import assert from 'node:assert/strict';

import { extractDriveId, driveDownloadUrl, checkDriveFile } from '../api/_drive.js';

const ID = '1AbCdEfGhIjKlMnOpQrStUvWxYz012345';

test('extrai o id dos formatos de link de arquivo do Drive', () => {
  for (const link of [
    `https://drive.google.com/file/d/${ID}/view?usp=sharing`,
    `https://drive.google.com/file/d/${ID}/view?usp=drive_link`,
    `https://drive.google.com/file/d/${ID}`,
    `https://drive.google.com/open?id=${ID}`,
    `https://drive.google.com/uc?id=${ID}&export=download`,
    `https://drive.usercontent.google.com/download?id=${ID}&export=download`,
    `  https://drive.google.com/file/d/${ID}/view  `,
  ]) {
    assert.deepEqual(extractDriveId(link), { id: ID }, link);
  }
});

test('avisa quando o link é de pasta', () => {
  assert.equal(extractDriveId(`https://drive.google.com/drive/folders/${ID}`).error, 'pasta');
});

test('recusa link que não é do Drive', () => {
  for (const link of ['', 'abc', `https://evil.com/file/d/${ID}/view`,
    `https://drive.google.com.evil.com/file/d/${ID}/view`, `http://drive.google.com/file/d/${ID}/view`,
    'https://drive.google.com/file/d/curto/view', `https://docs.google.com/document/d/${ID}/edit`]) {
    assert.equal(extractDriveId(link).id, undefined, link);
    assert.equal(extractDriveId(link).error, 'invalido', link);
  }
});

test('monta o link de download direto', () => {
  assert.equal(driveDownloadUrl(ID),
    `https://drive.usercontent.google.com/download?id=${ID}&export=download&confirm=t`);
});

function fakeFetch(status, contentType) {
  const calls = [];
  const fn = async (url, opts) => {
    calls.push({ url, opts });
    return { status, ok: status < 400, headers: new Headers({ 'content-type': contentType }), body: { cancel: async () => {} } };
  };
  return { fn, calls };
}

test('arquivo compartilhado: ok', async () => {
  const { fn, calls } = fakeFetch(206, 'audio/mpeg');
  assert.deepEqual(await checkDriveFile(ID, fn), { ok: true });
  assert.equal(calls[0].url, driveDownloadUrl(ID));
  assert.equal(calls[0].opts.headers.Range, 'bytes=0-0');
});

test('arquivo não compartilhado (Drive devolve página de login): privado', async () => {
  const { fn } = fakeFetch(200, 'text/html; charset=utf-8');
  assert.deepEqual(await checkDriveFile(ID, fn), { ok: false, error: 'privado' });
});

test('arquivo inexistente: nao-encontrado', async () => {
  const { fn } = fakeFetch(404, 'text/html');
  assert.deepEqual(await checkDriveFile(ID, fn), { ok: false, error: 'nao-encontrado' });
});

test('falha de rede: indisponivel', async () => {
  const fn = async () => { throw new Error('rede'); };
  assert.deepEqual(await checkDriveFile(ID, fn), { ok: false, error: 'indisponivel' });
});
