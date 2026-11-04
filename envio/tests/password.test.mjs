import { test } from 'node:test';
import assert from 'node:assert/strict';

process.env.ADMIN_SECRET = 'segredo-de-teste-bem-comprido-1234567890';
process.env.ADMIN_PASSWORD = 'senha-da-env';

const {
  hashPassword, verifyHash, validateNewPassword, checkPassword, readStoredPassword, writeStoredPassword,
  passwordMark, signResetToken, verifyResetToken, RESET_TTL_MS,
} = await import('../api/_password.js');

function fakeBlob() {
  const files = [];
  let n = 0;
  return {
    files,
    listFn: async ({ prefix }) => ({ blobs: files.filter((f) => f.pathname.startsWith(prefix)) }),
    putFn: async (path, body) => {
      n += 1;
      const pathname = path.replace('.enc', `-${n}.enc`);
      files.push({ pathname, url: `https://x/${pathname}`, body, uploadedAt: new Date(Date.UTC(2026, 0, 1, 0, n)).toISOString() });
      return { pathname };
    },
    delFn: async (urls) => urls.forEach((u) => files.splice(files.findIndex((f) => f.url === u), 1)),
    fetchFn: async (url) => {
      const f = files.find((x) => x.url === url);
      return { ok: true, text: async () => f.body };
    },
  };
}

test('hash scrypt confere só a senha certa', () => {
  const h = hashPassword('minha-senha-nova');
  assert.ok(verifyHash('minha-senha-nova', h));
  assert.ok(!verifyHash('outra-senha-qualquer', h));
  assert.ok(!verifyHash('', h));
  assert.ok(!verifyHash('minha-senha-nova', 'lixo'));
  assert.notEqual(hashPassword('x'), hashPassword('x'));
});

test('valida tamanho da nova senha', () => {
  assert.match(validateNewPassword('curta'), /10 caracteres/);
  assert.match(validateNewPassword(undefined), /10 caracteres/);
  assert.equal(validateNewPassword('senha-boa-123'), null);
  assert.ok(validateNewPassword('a'.repeat(201)));
});

test('sem senha salva vale ADMIN_PASSWORD; depois de redefinir vale a nova', async () => {
  const blob = fakeBlob();
  assert.equal(await readStoredPassword(blob), null);
  assert.ok(await checkPassword('senha-da-env', blob));
  await writeStoredPassword('senha-nova-forte', blob);
  assert.ok(await checkPassword('senha-nova-forte', blob));
  assert.ok(!(await checkPassword('senha-da-env', blob)));
  assert.ok(!blob.files[0].body.includes('scrypt'), 'hash fica criptografado');
});

test('guarda só as últimas versões da senha', async () => {
  const blob = fakeBlob();
  for (let i = 0; i < 5; i += 1) await writeStoredPassword(`senha-numero-${i}0`, blob);
  assert.equal(blob.files.length, 3);
  assert.ok(await checkPassword('senha-numero-40', blob));
});

test('token de recuperação: válido, vencido, adulterado', () => {
  const now = 1_000_000;
  const mark = passwordMark(null);
  const token = signResetToken(mark, now);
  assert.ok(verifyResetToken(token, mark, now + 1000));
  assert.ok(!verifyResetToken(token, mark, now + RESET_TTL_MS + 1));
  const [exp, m, sig] = token.split('.');
  assert.ok(!verifyResetToken(`${Number(exp) + 999999}.${m}.${sig}`, mark, now));
  assert.ok(!verifyResetToken('a.b.c', mark, now));
  assert.ok(!verifyResetToken(undefined, mark, now));
});

test('token morre depois que a senha muda (uso único)', async () => {
  const blob = fakeBlob();
  const token = signResetToken(passwordMark(await readStoredPassword(blob)));
  assert.ok(verifyResetToken(token, passwordMark(await readStoredPassword(blob))));
  await writeStoredPassword('senha-nova-forte', blob);
  assert.ok(!verifyResetToken(token, passwordMark(await readStoredPassword(blob))));
});
