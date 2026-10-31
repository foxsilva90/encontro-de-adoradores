// Webhook da WhatsApp Cloud API (número da rádio em modo coexistência).
//
// Quando um locutor cadastrado manda um áudio, dispara o workflow
// "publicar-programa.yml" no GitHub Actions, que baixa o áudio, converte e
// substitui o programa na playlist do AzuraCast.
//
// O número do locutor NÃO é repassado ao GitHub (o repositório é público e
// os inputs do workflow aparecem na página da execução). Só vão o id da mídia
// e o nome da playlist.
//
// Variáveis de ambiente (Vercel):
// - WHATSAPP_VERIFY_TOKEN  : texto livre, o mesmo colocado no painel da Meta
// - WHATSAPP_APP_SECRET    : App Secret do app da Meta (valida a assinatura)
// - PROGRAMAS_WHATSAPP     : {"5511988887777": "Nome exato da playlist"}
// - GITHUB_DISPATCH_TOKEN  : token fine-grained com "Actions: read and write" no repo
// - GITHUB_REPO            : ex. foxsilva90/encontro-de-adoradores
import { verifySignature, parseProgramMap, findProgram, extractAudioMessages } from './_whatsapp.js';

const WORKFLOW_FILE = 'publicar-programa.yml';
const WORKFLOW_REF = 'main';

// Inscrição do webhook: a Meta manda um GET com hub.challenge.
export function GET(request) {
  const params = new URL(request.url).searchParams;
  const token = process.env.WHATSAPP_VERIFY_TOKEN;
  if (token && params.get('hub.mode') === 'subscribe' && params.get('hub.verify_token') === token) {
    return new Response(params.get('hub.challenge') || '', { status: 200 });
  }
  return new Response('Forbidden', { status: 403 });
}

async function dispatchWorkflow(mediaId, programa) {
  const repo = process.env.GITHUB_REPO;
  const token = process.env.GITHUB_DISPATCH_TOKEN;
  if (!repo || !token) throw new Error('GITHUB_REPO/GITHUB_DISPATCH_TOKEN não configurados');

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
      body: JSON.stringify({ ref: WORKFLOW_REF, inputs: { media_id: mediaId, programa } }),
    },
  );
  if (!resp.ok) throw new Error(`GitHub respondeu ${resp.status}`);
}

export async function POST(request) {
  const rawBody = await request.text();
  if (!verifySignature(rawBody, request.headers.get('x-hub-signature-256'), process.env.WHATSAPP_APP_SECRET)) {
    return new Response('Invalid signature', { status: 401 });
  }

  let body;
  try {
    body = JSON.parse(rawBody);
  } catch {
    return new Response('Bad request', { status: 400 });
  }

  const programMap = parseProgramMap(process.env.PROGRAMAS_WHATSAPP);
  // Áudios de ouvintes (números fora da lista) são ignorados.
  const jobs = extractAudioMessages(body)
    .map((m) => ({ ...m, programa: findProgram(programMap, m.from) }))
    .filter((m) => m.programa);

  try {
    await Promise.all(jobs.map((j) => dispatchWorkflow(j.mediaId, j.programa)));
  } catch (err) {
    console.error('Falha ao disparar workflow do programa:', err.message);
    // 500 faz a Meta reenviar a notificação mais tarde.
    return new Response('Dispatch failed', { status: 500 });
  }

  return new Response('OK', { status: 200 });
}
