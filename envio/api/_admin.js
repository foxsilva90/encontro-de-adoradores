// Regras puras do painel de administração (sem I/O). Toda operação devolve
// uma configuração nova; a original nunca é alterada.
import crypto from 'node:crypto';
import { normalizeEntry, normalizeCode, MIN_CODE_LENGTH, MAX_CODE_LENGTH } from './_locutores.js';

const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // sem 0/O, 1/I
const CODE_RANDOM_LENGTH = 8;
const CODE_PREFIX_MAX = 12;
const MAX_TEXT = 100;
const MAX_PLAYLIST_NAME = 200;
const MAX_DESTINOS = 7;
const MAX_PLAYLISTS = 10;

const text = (v, max = MAX_TEXT) => (typeof v === 'string' ? v.trim().slice(0, max) : '');

function codePrefix(programa) {
  const letters = String(programa).normalize('NFKD').replace(/[^A-Za-z0-9]/g, '').toUpperCase();
  return letters.slice(0, CODE_PREFIX_MAX) || 'LOCUTOR';
}

/** Código novo e único: PREFIXO-XXXXXXXX. `randomInt` é injetável pra teste. */
export function generateCode(programa, existing, randomInt = crypto.randomInt) {
  const taken = new Set(existing.map(normalizeCode));
  for (;;) {
    let random = '';
    for (let i = 0; i < CODE_RANDOM_LENGTH; i++) random += CODE_ALPHABET[randomInt(CODE_ALPHABET.length)];
    const code = `${codePrefix(programa)}-${random}`;
    if (!taken.has(code)) return code;
  }
}

function validateDestinos(raw, programa) {
  if (!Array.isArray(raw) || !raw.length || raw.length > MAX_DESTINOS) return null;
  const destinos = raw.map((d) => ({
    nome: raw.length === 1 ? programa : text(d?.nome),
    playlists: (Array.isArray(d?.playlists) ? d.playlists : [])
      .map((p) => text(p, MAX_PLAYLIST_NAME)).filter(Boolean),
  }));
  const ok = destinos.every((d) => d.nome && d.playlists.length && d.playlists.length <= MAX_PLAYLISTS);
  return ok ? destinos : null;
}

/** @returns {{ok: true, value: object} | {ok: false, error: string}} */
export function validateLocutorInput(body) {
  if (!body || typeof body !== 'object') return { ok: false, error: 'Dados inválidos.' };
  const nome = text(body.nome);
  const programa = text(body.programa);
  if (!nome) return { ok: false, error: 'Informe o nome do locutor.' };
  if (!programa) return { ok: false, error: 'Informe o nome do programa.' };
  if (typeof body.editar !== 'boolean') return { ok: false, error: 'Escolha se o programa é editado.' };
  const destinos = validateDestinos(body.destinos, programa);
  if (!destinos) return { ok: false, error: 'Cada dia/destino precisa de nome e de pelo menos uma playlist.' };
  return { ok: true, value: { nome, programa, editar: body.editar, destinos } };
}

/** Primeira vez: transforma o cadastro da variável CODIGOS_LOCUTORES em configuração. */
export function configFromCodeMap(map) {
  return {
    v: 1,
    locutores: Object.entries(map).map(([codigo, entry]) => ({
      id: crypto.randomUUID(), codigo, ...entry, nome: entry.nome || entry.programa,
    })),
  };
}

/** Configuração → mapa código → cadastro, no formato que o link de envio usa. */
export function codeMapFromConfig(config) {
  const list = Array.isArray(config?.locutores) ? config.locutores : [];
  const pairs = list
    .filter((l) => l && typeof l.codigo === 'string')
    .map((l) => [normalizeCode(l.codigo), normalizeEntry(l)])
    .filter(([code, entry]) => entry && code.length >= MIN_CODE_LENGTH && code.length <= MAX_CODE_LENGTH);
  return Object.fromEntries(pairs);
}

export function addLocutor(config, input, codigo, id = crypto.randomUUID()) {
  return { ...config, locutores: [...config.locutores, { id, codigo, ...input }] };
}

function mapOne(config, id, change) {
  if (!config.locutores.some((l) => l.id === id)) return null;
  return { ...config, locutores: config.locutores.map((l) => (l.id === id ? change(l) : l)) };
}

export const updateLocutor = (config, id, input) => mapOne(config, id, (l) => ({ ...l, ...input }));

export const replaceCode = (config, id, codigo) => mapOne(config, id, (l) => ({ ...l, codigo }));

export function removeLocutor(config, id) {
  if (!config.locutores.some((l) => l.id === id)) return null;
  return { ...config, locutores: config.locutores.filter((l) => l.id !== id) };
}
