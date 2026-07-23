function clientIp(req) {
  const fwd = req.headers['x-forwarded-for'];
  if (typeof fwd === 'string' && fwd.length) return fwd.split(',')[0].trim();
  return req.socket?.remoteAddress || 'unknown';
}

// Retorna true se a requisição pode prosseguir. Em caso de falha ao
// consultar o Supabase, permite a requisição (não pode travar o site
// inteiro por causa do rate limiter).
export async function checkRateLimit(req, scope, maxCount, windowSeconds) {
  if (!process.env.SUPABASE_URL || !process.env.SUPABASE_ANON_KEY) return true;

  const key = `${scope}:${clientIp(req)}`;
  try {
    const response = await fetch(`${process.env.SUPABASE_URL}/rest/v1/rpc/check_rate_limit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        apikey: process.env.SUPABASE_ANON_KEY,
        Authorization: `Bearer ${process.env.SUPABASE_ANON_KEY}`,
      },
      body: JSON.stringify({ p_key: key, p_max_count: maxCount, p_window_seconds: windowSeconds }),
    });
    if (!response.ok) return true;
    return await response.json();
  } catch (err) {
    return true;
  }
}
