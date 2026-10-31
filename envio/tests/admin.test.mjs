import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  keyFor, encryptJson, decryptJson, signSession, verifySession, safeEqual,
} from '../api/_crypto.js';
import {
  generateCode, validateLocutorInput, configFromCodeMap, codeMapFromConfig,
  addLocutor, updateLocutor, replaceCode, removeLocutor,
} from '../api/_admin.js';
import { parseCodeMap, findLocutorByCode } from '../api/_locutores.js';

const SECRET = 'segredo-de-teste-bem-comprido-1234567890';

test('criptografia: ida e volta, e chave errada não abre', () => {
  const key = keyFor(SECRET, 'config');
  const box = encryptJson({ a: 1, nome: 'Patrícia' }, key);
  assert.equal(typeof box, 'string');
  assert.ok(!box.includes('Patr'));
  assert.deepEqual(decryptJson(box, key), { a: 1, nome: 'Patrícia' });
  assert.throws(() => decryptJson(box, keyFor('outro-segredo-qualquer-1234567890', 'config')));
});

test('criptografia: cada gravação usa um IV diferente', () => {
  const key = keyFor(SECRET, 'config');
  assert.notEqual(encryptJson({ a: 1 }, key), encryptJson({ a: 1 }, key));
});

test('chaves de propósitos diferentes são diferentes', () => {
  assert.notDeepEqual(keyFor(SECRET, 'config'), keyFor(SECRET, 'session'));
});

test('sessão: válida até expirar e não aceita adulteração', () => {
  const key = keyFor(SECRET, 'session');
  const now = 1_000_000;
  const token = signSession(now + 60_000, key);
  assert.equal(verifySession(token, key, now), true);
  assert.equal(verifySession(token, key, now + 60_001), false);
  const [exp, mac] = token.split('.');
  assert.equal(verifySession(`${Number(exp) + 999999}.${mac}`, key, now), false);
  assert.equal(verifySession('lixo', key, now), false);
  assert.equal(verifySession(undefined, key, now), false);
  assert.equal(verifySession(token, keyFor('outro-segredo-qualquer-1234567890', 'session'), now), false);
});

test('safeEqual compara textos de tamanhos diferentes sem quebrar', () => {
  assert.equal(safeEqual('abc', 'abc'), true);
  assert.equal(safeEqual('abc', 'abcd'), false);
  assert.equal(safeEqual('', ''), false);
});

test('código novo: prefixo do programa, 8 sorteados e nunca repete', () => {
  const code = generateCode('Clássicos do Talito', []);
  assert.match(code, /^CLASSICOSDOT-[A-HJ-NP-Z2-9]{8}$/);
  let n = 0;
  const fixed = () => (n++ < 8 ? 0 : 1); // primeira tentativa repete, segunda não
  const first = generateCode('Talito', [], fixed);
  n = 0;
  const second = generateCode('Talito', [first], fixed);
  assert.notEqual(first, second);
});

test('validação: programa simples vira um destino só com o nome do programa', () => {
  const r = validateLocutorInput({ nome: ' Talito ', programa: 'Clássicos do Talito', editar: false,
    destinos: [{ playlists: ['PG Clássicos do Talito - Sábado (8h)', ' '] }] });
  assert.equal(r.ok, true);
  assert.deepEqual(r.value, { nome: 'Talito', programa: 'Clássicos do Talito', editar: false,
    destinos: [{ nome: 'Clássicos do Talito', playlists: ['PG Clássicos do Talito - Sábado (8h)'] }] });
});

test('validação: vários destinos precisam de nome e playlist', () => {
  const base = { nome: 'Patricia', programa: 'Palavra Viva', editar: true };
  assert.equal(validateLocutorInput({ ...base, destinos: [
    { nome: 'Segunda', playlists: ['A'] }, { nome: 'Terça', playlists: ['B'] }] }).ok, true);
  assert.equal(validateLocutorInput({ ...base, destinos: [
    { nome: 'Segunda', playlists: ['A'] }, { nome: '', playlists: ['B'] }] }).ok, false);
  assert.equal(validateLocutorInput({ ...base, destinos: [{ playlists: [] }] }).ok, false);
  assert.equal(validateLocutorInput({ ...base, programa: '', destinos: [{ playlists: ['A'] }] }).ok, false);
  assert.equal(validateLocutorInput({ ...base, editar: 'sim', destinos: [{ playlists: ['A'] }] }).ok, false);
  assert.equal(validateLocutorInput(null).ok, false);
});

test('cadastro antigo (variável) vira configuração e volta igual pro link', () => {
  const env = parseCodeMap(JSON.stringify({
    'TALITO-7K2P9QX4': { programa: 'Talito', playlists: ['P1'] },
    'PATRICIA-ZZ99YY88': { programa: 'Palavra Viva', destinos: [
      { nome: 'Segunda', playlists: ['S'] }, { nome: 'Terça', playlists: ['T'] }] },
  }));
  const config = configFromCodeMap(env);
  assert.equal(config.locutores.length, 2);
  assert.ok(config.locutores.every((l) => l.id && l.codigo));
  const map = codeMapFromConfig(config);
  assert.equal(findLocutorByCode(map, 'talito-7k2p9qx4').programa, 'Talito');
  assert.equal(findLocutorByCode(map, 'PATRICIA-ZZ99YY88').destinos.length, 2);
});

test('adicionar, editar, trocar código e remover não mexem no original', () => {
  const empty = { v: 1, locutores: [] };
  const input = validateLocutorInput({ nome: 'Talito', programa: 'Talito', editar: true,
    destinos: [{ playlists: ['P1'] }] }).value;
  const c1 = addLocutor(empty, input, 'TALITO-AAAAAAAA', 'id1');
  assert.equal(empty.locutores.length, 0);
  assert.equal(c1.locutores[0].codigo, 'TALITO-AAAAAAAA');

  const c2 = updateLocutor(c1, 'id1', { ...input, editar: false });
  assert.equal(c1.locutores[0].editar, true);
  assert.equal(c2.locutores[0].editar, false);
  assert.equal(c2.locutores[0].codigo, 'TALITO-AAAAAAAA');
  assert.equal(updateLocutor(c1, 'nao-existe', input), null);

  const c3 = replaceCode(c2, 'id1', 'TALITO-BBBBBBBB');
  assert.equal(c3.locutores[0].codigo, 'TALITO-BBBBBBBB');
  assert.equal(findLocutorByCode(codeMapFromConfig(c3), 'TALITO-AAAAAAAA'), null);
  assert.equal(replaceCode(c2, 'nao-existe', 'X-BBBBBBBB'), null);

  const c4 = removeLocutor(c3, 'id1');
  assert.equal(c4.locutores.length, 0);
  assert.equal(c3.locutores.length, 1);
  assert.equal(removeLocutor(c3, 'nao-existe'), null);
});

test('configuração inválida não derruba: só ignora o cadastro quebrado', () => {
  const map = codeMapFromConfig({ v: 1, locutores: [
    { id: 'a', codigo: 'BOM-12345678', programa: 'Bom', destinos: [{ nome: 'Bom', playlists: ['P'] }] },
    { id: 'b', codigo: 'X', programa: 'Curto', destinos: [{ nome: 'C', playlists: ['P'] }] },
    null,
  ] });
  assert.deepEqual(Object.keys(map), ['BOM-12345678']);
  assert.deepEqual(codeMapFromConfig(null), {});
});
