// Cron diário: apaga do Vercel Blob os arquivos enviados há mais de 24h
// (o GitHub Actions já copiou tudo pro AzuraCast). A Vercel manda
// "Authorization: Bearer $CRON_SECRET" automaticamente.
import { list, del } from '@vercel/blob';
import { isExpired, json, UPLOAD_PREFIX } from './_locutores.js';

export async function GET(request) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get('authorization') !== `Bearer ${secret}`) {
    return json(401, { error: 'Unauthorized' });
  }

  let cursor;
  let removed = 0;
  do {
    const page = await list({ prefix: UPLOAD_PREFIX, cursor });
    const old = page.blobs.filter((b) => isExpired(b.uploadedAt)).map((b) => b.url);
    if (old.length) await del(old);
    removed += old.length;
    cursor = page.hasMore ? page.cursor : undefined;
  } while (cursor);

  return json(200, { removed });
}
