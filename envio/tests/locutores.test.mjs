import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  parseCodeMap,
  findLocutorByCode,
  resolveDestino,
  isOurBlobUrl,
  isAllowedUploadPath,
  isExpired,
} from '../api/_locutores.js';

const RAW = JSON.stringify({
  'TALITO-7K2P9QX4': 'PG Clássicos do Talito - Sábado (8h)',
  'ANDERSON-AB12CD34': {
    programa: 'Encontro de Adoradores',
    playlists: ['PG A (06h30)', 'PG A (11h', 'PG A (17h)', 'PG A (22h)'],
  },
  'PATRICIA-ZZ99YY88': {
    programa: 'Palavra Viva',
    destinos: [
      { nome: 'Segunda', playlists: ['PG Palavra Viva - 15h (Seg)'] },
      { nome: 'Terça', playlists: ['PG Palavra Viva - 15h (Ter)'] },
    ],
  },
  curto: 'X',
  'VAZIO-12345678': { programa: 'Sem playlists', playlists: [] },
});
const MAP = parseCodeMap(RAW);

test('aceita os três formatos de cadastro e descarta inválidos', () => {
  assert.deepEqual(Object.keys(MAP).sort(), ['ANDERSON-AB12CD34', 'PATRICIA-ZZ99YY88', 'TALITO-7K2P9QX4']);
  assert.deepEqual(MAP['TALITO-7K2P9QX4'], {
    programa: 'PG Clássicos do Talito - Sábado (8h)',
    nome: '',
    editar: true,
    destinos: [{ nome: 'PG Clássicos do Talito - Sábado (8h)', playlists: ['PG Clássicos do Talito - Sábado (8h)'] }],
  });
  assert.equal(MAP['ANDERSON-AB12CD34'].destinos.length, 1);
  assert.equal(MAP['ANDERSON-AB12CD34'].destinos[0].playlists.length, 4);
  assert.deepEqual(MAP['PATRICIA-ZZ99YY88'].destinos.map((d) => d.nome), ['Segunda', 'Terça']);
  assert.deepEqual(parseCodeMap('lixo'), {});
  assert.deepEqual(parseCodeMap(undefined), {});
});

test('código ignora maiúsculas e espaços em volta', () => {
  assert.equal(findLocutorByCode(MAP, '  talito-7k2p9qx4 ').programa, 'PG Clássicos do Talito - Sábado (8h)');
  assert.equal(findLocutorByCode(MAP, 'TALITO-7K2P9QX5'), null);
  assert.equal(findLocutorByCode(MAP, ''), null);
  assert.equal(findLocutorByCode(MAP, null), null);
  assert.equal(findLocutorByCode(MAP, 'x'.repeat(500)), null);
});

test('destino único: título é o nome do programa e vai pra todas as playlists', () => {
  const d = resolveDestino(MAP['ANDERSON-AB12CD34'], 0);
  assert.equal(d.titulo, 'Encontro de Adoradores');
  assert.equal(d.playlists.length, 4);
});

test('vários destinos: título leva o dia e índice inválido é recusado', () => {
  assert.deepEqual(resolveDestino(MAP['PATRICIA-ZZ99YY88'], 1), {
    titulo: 'Palavra Viva - Terça',
    playlists: ['PG Palavra Viva - 15h (Ter)'],
  });
  assert.equal(resolveDestino(MAP['PATRICIA-ZZ99YY88'], 2), null);
  assert.equal(resolveDestino(MAP['PATRICIA-ZZ99YY88'], -1), null);
  assert.equal(resolveDestino(MAP['PATRICIA-ZZ99YY88'], '1'), null);
  assert.equal(resolveDestino(MAP['PATRICIA-ZZ99YY88'], undefined), null);
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

test('cadastro guarda nome do locutor e permite desligar a edição', () => {
  const map = parseCodeMap(JSON.stringify({
    'TALITO-7K2P9QX4': { programa: 'Talito', nome: 'Talito', editar: false, playlists: ['P'] },
    'OUTRO-7K2P9QX4': { programa: 'Outro', playlists: ['P'] },
  }));
  assert.equal(map['TALITO-7K2P9QX4'].editar, false);
  assert.equal(map['TALITO-7K2P9QX4'].nome, 'Talito');
  assert.equal(map['OUTRO-7K2P9QX4'].editar, true);
});
