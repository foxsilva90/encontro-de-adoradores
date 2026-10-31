// Depois do upload, dispara o workflow que monta e publica o programa.
// Variáveis: CODIGOS_LOCUTORES, GITHUB_DISPATCH_TOKEN, GITHUB_REPO
import { parseCodeMap, findLocutorByCode, resolveDestino, isOurBlobUrl, json } from './_locutores.js';

const WORKFLOW_FILE = 'publicar-programa.yml';
const WORKFLOW_REF = 'main';

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const locutor = findLocutorByCode(parseCodeMap(process.env.CODIGOS_LOCUTORES), body.codigo);
  if (!locutor) return json(401, { error: 'Código não encontrado.' });
  const destino = resolveDestino(locutor, body.destino ?? 0);
  if (!destino) return json(400, { error: 'Escolha para qual dia é o programa.' });
  if (!isOurBlobUrl(body.url)) return json(400, { error: 'Arquivo inválido.' });

  const repo = process.env.GITHUB_REPO;
  const token = process.env.GITHUB_DISPATCH_TOKEN;
  if (!repo || !token) {
    console.error('GITHUB_REPO/GITHUB_DISPATCH_TOKEN não configurados');
    return json(503, { error: 'Serviço não configurado. Avise a equipe da rádio.' });
  }

  const resp = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: WORKFLOW_REF,
        inputs: { audio_url: body.url, programa: destino.titulo, playlists: JSON.stringify(destino.playlists) },
      }),
    },
  );
  if (!resp.ok) {
    console.error('GitHub recusou o disparo:', resp.status, await resp.text().catch(() => ''));
    return json(502, { error: 'O arquivo chegou, mas não consegui iniciar a publicação. Avise a equipe da rádio.' });
  }
  return json(200, { ok: true, programa: destino.titulo });
}
