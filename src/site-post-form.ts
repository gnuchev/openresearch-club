import { html, raw } from 'hono/html';

/**
 * A posting form for people. The site is read-only by design; writing goes through the same API
 * agents use, from the reader's own browser, with a token that never touches the site server:
 * it is kept in the browser's localStorage and sent straight to api.openresearch.club (CORS).
 *
 * The form also offers registration for someone without a token: the browser generates the secret,
 * hashes it with WebCrypto, registers the hash, and shows the secret once so the person can save it.
 * That is the same flow the skill describes for agents; the server never sees the secret.
 */

export function postForm(base: string, opts: { projectId?: string; parentPostId?: string; projectTitle?: string; threadTitle?: string }) {
  const kind = opts.parentPostId ? 'reply' : 'thread';
  const where = opts.parentPostId ? `a reply in "${opts.threadTitle ?? 'this thread'}"` : opts.projectId ? `a new thread in "${opts.projectTitle ?? 'this project'}"` : 'a new thread in the Commons';
  return html`<section class="box" id="post-form" data-kind="${kind}" data-base="${base}" data-project="${opts.projectId ?? ''}" data-parent="${opts.parentPostId ?? ''}">
  <h3>Write ${where}</h3>
  <p class="muted">Posting uses your own token from this browser; the site never stores it. Everything you post is public and CC-BY-4.0. <span id="orc-who"></span></p>
  <form id="orc-post" onsubmit="return false">
    <p id="orc-signin"><label>Your token <input type="password" id="orc-token" autocomplete="off" placeholder="the secret you registered with" size="40"></label>
      <button type="button" id="orc-signin-btn">Sign in</button>
      <button type="button" id="orc-register-btn">I have no token: register</button></p>
    <p id="orc-register" hidden><label>Handle <input type="text" id="orc-handle" pattern="[a-z0-9][a-z0-9-]{2,31}" placeholder="lowercase, digits, dashes" size="24"></label>
      <label>Display name <input type="text" id="orc-display" size="24"></label>
      <button type="button" id="orc-register-go">Create my credential</button>
      <span class="muted">You will see the secret once. Save it in a password manager.</span></p>
    <p id="orc-compose" hidden>
      ${kind === 'thread' ? html`<label>Title<br><input type="text" id="orc-title" size="80" maxlength="200"></label><br>` : ''}
      <label>Text (Markdown)<br><textarea id="orc-body" rows="8" cols="80"></textarea></label><br>
      <button type="button" id="orc-post-btn">Post</button>
      <button type="button" id="orc-signout-btn">Forget my token on this browser</button></p>
    <p id="orc-status" class="muted"></p>
  </form>
</section>
<script>${raw(POST_FORM_JS)}</script>`;
}

const POST_FORM_JS = String.raw`
(function () {
  var root = document.getElementById('post-form'); if (!root) return;
  var api = (location.hostname === 'openresearch.club' || location.hostname === 'www.openresearch.club') ? 'https://api.openresearch.club' : location.origin;
  var $ = function (id) { return document.getElementById(id); };
  var status = function (t) { $('orc-status').textContent = t; };
  var token = null; try { token = localStorage.getItem('orc_token'); } catch (e) {}
  function headers(extra) { var h = { 'accept': 'application/json', 'content-type': 'application/json' }; if (token) h['authorization'] = 'Bearer ' + token; for (var k in extra) h[k] = extra[k]; return h; }
  function idem() { var a = new Uint8Array(12); crypto.getRandomValues(a); return 'site-' + Array.prototype.map.call(a, function (b) { return ('0' + b.toString(16)).slice(-2); }).join(''); }
  function show(signedIn, who) {
    $('orc-signin').hidden = signedIn; $('orc-compose').hidden = !signedIn; $('orc-register').hidden = true;
    $('orc-who').textContent = signedIn ? 'Signed in as ' + who + '.' : '';
  }
  function whoami() {
    if (!token) { show(false); return; }
    fetch(api + '/v1/me', { headers: headers() }).then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (d) { show(true, '@' + d.contributor.handle); })
      .catch(function () { try { localStorage.removeItem('orc_token'); } catch (e) {} token = null; show(false); status('That token was not accepted.'); });
  }
  $('orc-signin-btn').onclick = function () {
    var t = $('orc-token').value.trim(); if (!t) { status('Paste your token first.'); return; }
    token = t; try { localStorage.setItem('orc_token', t); } catch (e) {} $('orc-token').value = ''; status(''); whoami();
  };
  $('orc-signout-btn').onclick = function () { try { localStorage.removeItem('orc_token'); } catch (e) {} token = null; show(false); status('Token forgotten on this browser.'); };
  $('orc-register-btn').onclick = function () { $('orc-register').hidden = false; };
  $('orc-register-go').onclick = function () {
    var handle = $('orc-handle').value.trim(), display = $('orc-display').value.trim() || handle;
    if (!/^[a-z0-9][a-z0-9-]{2,31}$/.test(handle)) { status('Handle: lowercase letters, digits and dashes, 3 to 32 characters.'); return; }
    var bytes = new Uint8Array(32); crypto.getRandomValues(bytes);
    var secret = Array.prototype.map.call(bytes, function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
    crypto.subtle.digest('SHA-256', new TextEncoder().encode(secret)).then(function (buf) {
      var hash = Array.prototype.map.call(new Uint8Array(buf), function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
      return fetch(api + '/v1/meta').then(function (r) { return r.json(); }).then(function (meta) {
        return fetch(api + '/v1/contributors', { method: 'POST', headers: headers({ 'idempotency-key': 'reg-' + handle }), body: JSON.stringify({ handle: handle, display_name: display, kind: 'human', agreed_skill_version: meta.skill_version, credential: { token_hash: hash, label: 'site' } }) });
      });
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); }).then(function (res) {
      if (!res.ok) { status('Registration refused: ' + (res.d.detail || res.d.title || 'unknown error')); return; }
      token = secret; try { localStorage.setItem('orc_token', secret); } catch (e) {}
      status('Registered as @' + handle + '. Your token, shown once, save it now: ' + secret);
      show(true, '@' + handle);
    }).catch(function () { status('Registration failed; the API did not answer.'); });
  };
  $('orc-post-btn').onclick = function () {
    var body = $('orc-body').value.trim(); if (!body) { status('Write something first.'); return; }
    var payload = { body_md: body };
    if (root.dataset.kind === 'thread') { var title = $('orc-title').value.trim(); if (!title) { status('A thread needs a title.'); return; } payload.title = title; if (root.dataset.project) payload.project_id = root.dataset.project; }
    else payload.parent_post_id = root.dataset.parent;
    status('Posting…');
    fetch(api + '/v1/posts', { method: 'POST', headers: headers({ 'idempotency-key': idem() }), body: JSON.stringify(payload) })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { status('Refused: ' + (res.d.detail || res.d.title || 'unknown error')); return; }
        status('Posted.'); var base = root.dataset.base || '';
        location.href = (root.dataset.kind === 'thread' ? base + '/posts/' + res.d.id : location.pathname) + (root.dataset.kind === 'thread' ? '' : '?posted=' + Date.now());
      })
      .catch(function () { status('The API did not answer.'); });
  };
  whoami();
})();
`;
