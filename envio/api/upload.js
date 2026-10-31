// Gera o token pro navegador enviar o arquivo direto pro Vercel Blob
// (sem passar pelo limite de 4,5 MB das funções). Só com código válido.
import { handleUpload } from '@vercel/blob/client';
import {
  parseCodeMap, findLocutorByCode, isAllowedUploadPath, json,
  ALLOWED_CONTENT_TYPES, MAX_UPLOAD_BYTES,
} from './_locutores.js';

export async function POST(request) {
  const body = await request.json().catch(() => null);
  if (!body) return json(400, { error: 'Requisição inválida' });

  try {
    const result = await handleUpload({
      request,
      body,
      onBeforeGenerateToken: async (pathname, clientPayload) => {
        let codigo = '';
        try {
          codigo = JSON.parse(clientPayload || '{}').codigo;
        } catch {
          /* payload inválido cai na checagem abaixo */
        }
        if (!findLocutorByCode(parseCodeMap(process.env.CODIGOS_LOCUTORES), codigo)) {
          throw new Error('Código inválido');
        }
        if (!isAllowedUploadPath(pathname)) throw new Error('Caminho inválido');
        return {
          allowedContentTypes: ALLOWED_CONTENT_TYPES,
          maximumSizeInBytes: MAX_UPLOAD_BYTES,
          addRandomSuffix: true,
        };
      },
    });
    return json(200, result);
  } catch (err) {
    return json(400, { error: err.message || 'Falha ao preparar envio' });
  }
}
