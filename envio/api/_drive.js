// Links do Google Drive: o locutor cola o link do arquivo em vez de fazer upload.
// O arquivo precisa estar compartilhado como "qualquer pessoa com o link".
const DRIVE_HOSTS = new Set(['drive.google.com', 'drive.usercontent.google.com']);
const ID_RE = /^[A-Za-z0-9_-]{20,100}$/;
const FILE_PATH_RE = /^\/file\/d\/([^/]+)/;
const FOLDER_PATH_RE = /^\/drive\/(?:u\/\d+\/)?folders\//;
const ID_QUERY_PATHS = new Set(['/open', '/uc', '/download']);

/** Extrai o id do arquivo. Devolve { id } ou { error: 'pasta' | 'invalido' }. */
export function extractDriveId(link) {
  let url;
  try {
    url = new URL(String(link ?? '').trim());
  } catch {
    return { error: 'invalido' };
  }
  if (url.protocol !== 'https:' || !DRIVE_HOSTS.has(url.hostname)) return { error: 'invalido' };
  if (FOLDER_PATH_RE.test(url.pathname)) return { error: 'pasta' };
  const fromPath = url.pathname.match(FILE_PATH_RE)?.[1];
  const fromQuery = ID_QUERY_PATHS.has(url.pathname) ? url.searchParams.get('id') : null;
  const id = fromPath ?? fromQuery;
  return id && ID_RE.test(id) ? { id } : { error: 'invalido' };
}

/** Link de download direto (confirm=t pula o aviso de "arquivo grande demais pra verificar vírus"). */
export function driveDownloadUrl(id) {
  return `https://drive.usercontent.google.com/download?id=${id}&export=download&confirm=t`;
}

/**
 * Confere se dá pra baixar o arquivo sem login, pedindo só o primeiro byte.
 * Arquivo privado: o Drive responde com uma página HTML (de login ou de erro).
 */
export async function checkDriveFile(id, fetchFn = fetch) {
  let resp;
  try {
    resp = await fetchFn(driveDownloadUrl(id), { headers: { Range: 'bytes=0-0' }, redirect: 'follow' });
  } catch {
    return { ok: false, error: 'indisponivel' };
  }
  await resp.body?.cancel?.().catch(() => {});
  if (resp.status === 404) return { ok: false, error: 'nao-encontrado' };
  if (!resp.ok) return { ok: false, error: resp.status === 401 || resp.status === 403 ? 'privado' : 'indisponivel' };
  const type = resp.headers.get('content-type') || '';
  return type.startsWith('text/html') ? { ok: false, error: 'privado' } : { ok: true };
}

export const DRIVE_ERRORS = {
  invalido: 'Esse link não parece ser de um arquivo do Google Drive. No Drive, toque nos 3 pontinhos do arquivo → Compartilhar → Copiar link.',
  pasta: 'Esse é o link de uma pasta. Abra a pasta e copie o link do arquivo de áudio.',
  privado: 'O arquivo não está liberado. No Drive: Compartilhar → Acesso geral → "Qualquer pessoa com o link" e tente de novo.',
  'nao-encontrado': 'Não achei esse arquivo no Drive. Confira se o link está completo.',
  indisponivel: 'Não consegui acessar o Google Drive agora. Tente de novo em alguns minutos.',
};
