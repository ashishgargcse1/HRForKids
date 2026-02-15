export async function api(path, options = {}) {
  const resp = await fetch(path, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  });

  const ct = resp.headers.get('content-type') || '';
  const payload = ct.includes('application/json') ? await resp.json() : await resp.text();

  if (!resp.ok) {
    const message = typeof payload === 'object' && payload && payload.error
      ? payload.error
      : `HTTP ${resp.status}`;
    throw new Error(message);
  }

  return payload;
}
