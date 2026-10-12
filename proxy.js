// Vercel Routing Middleware: password gate for the whole site (deployed only; server.py has no auth).
// Env: APP_PASSWORD (the login password), AUTH_SECRET (random string used to sign session cookies).
// Cookie format "<expiry>.<hex hmac(expiry)>" — api/run.py verifies the same format.
import { next } from '@vercel/functions';
import { createHmac, timingSafeEqual } from 'node:crypto';

const COOKIE = 'pv_session';
const MAX_AGE = 60 * 60 * 24 * 30; // 30 days

const hmac = s => createHmac('sha256', process.env.AUTH_SECRET).update(String(s));
const sign = exp => hmac(exp).digest('hex');

function validSession(token) {
  const [exp, sig] = (token || '').split('.');
  if (!exp || !sig || Number(exp) < Date.now() / 1000) return false;
  const a = Buffer.from(sig), b = Buffer.from(sign(exp));
  return a.length === b.length && timingSafeEqual(a, b);
}

// Compare digests so the check takes the same time whatever the input length.
const passwordMatches = input => timingSafeEqual(hmac(input).digest(), hmac(process.env.APP_PASSWORD).digest());

function readCookie(request) {
  for (const part of (request.headers.get('cookie') || '').split(/;\s*/)) {
    const i = part.indexOf('=');
    if (part.slice(0, i) === COOKIE) return decodeURIComponent(part.slice(i + 1));
  }
  return null;
}

const cookie = (value, maxAge) => `${COOKIE}=${value}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;

function loginPage(error = '', status = 200) {
  return new Response(`<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Python Visualiser · Login</title>
<style>
  body { margin:0; min-height:100vh; display:grid; place-items:center; background:#f6f6f7; color:#1d1d1f; font:14px/1.4 system-ui, sans-serif; }
  form { background:#fff; border:1px solid #ddd; border-radius:10px; padding:28px; width:min(320px, calc(100vw - 32px)); display:grid; gap:12px; }
  h1 { font-size:17px; margin:0 0 4px; }
  input, button { font:inherit; padding:9px 10px; border-radius:6px; border:1px solid #ddd; }
  button { background:#2563eb; color:#fff; border-color:#2563eb; font-weight:600; cursor:pointer; }
  .err { color:#d33; margin:0; }
</style></head><body>
<form method="post" action="/login">
  <h1>🐍 Python Visualiser</h1>
  <input type="password" name="password" placeholder="Password" autofocus required autocomplete="current-password">
  <button type="submit">Log in</button>
  ${error ? `<p class="err">${error}</p>` : ''}
</form></body></html>`, { status, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });
}

export default async function proxy(request) {
  if (!process.env.APP_PASSWORD || !process.env.AUTH_SECRET) {
    return new Response('Login is not configured (set APP_PASSWORD and AUTH_SECRET).', { status: 500 });
  }
  const url = new URL(request.url);

  if (url.pathname === '/login') {
    if (request.method !== 'POST') return loginPage();
    const form = await request.formData();
    if (!passwordMatches(String(form.get('password') || ''))) return loginPage('Wrong password.', 401);
    const exp = Math.floor(Date.now() / 1000) + MAX_AGE;
    return new Response(null, { status: 303, headers: { Location: '/', 'Set-Cookie': cookie(`${exp}.${sign(exp)}`, MAX_AGE) } });
  }

  if (url.pathname === '/logout') {
    return new Response(null, { status: 303, headers: { Location: '/login', 'Set-Cookie': cookie('', 0) } });
  }

  if (validSession(readCookie(request))) return next();

  if (request.method !== 'GET') {
    return Response.json({ steps: [], error: 'Not logged in. Reload the page to log in.' }, { status: 401 });
  }
  return new Response(null, { status: 303, headers: { Location: '/login' } });
}
