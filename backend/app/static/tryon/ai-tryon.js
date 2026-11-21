/**
 * MyStore AI Try-On (realistic, generative) — powered by Decart realtime virtual try-on.
 *
 * Complements the on-device overlay try-on already in index.html:
 *   - overlay engine  -> glasses, earrings, lipstick, headphones, watch (runs locally)
 *   - AI engine (this)-> sarees, kurtas, dresses, shirts, shoes (video is processed by Decart)
 *
 * Public API (attached to window):
 *   startAiTryon(product)       open the AI try-on for a product object from /search
 *   isAiTryonEligible(product)  true for Fashion products
 */

// Pinned on purpose. Bump after testing a newer release.
const SDK_URL = 'https://esm.sh/@decartai/sdk@0.2.13';

let sdk = null;
let cfg = null;          // { ai_enabled, model, maxSessionSeconds }
let client = null;
let rt = null;           // realtime client
let camStream = null;
let active = null;       // product being tried
let sessionSeconds = 120;
let timerId = null;
let endsAt = 0;
let modalEl = null;

// ───────────────────────── helpers ─────────────────────────

const $ = (id) => document.getElementById(id);

function parseAttrs(p) {
  let a = p && p.attrs;
  if (typeof a === 'string') { try { a = JSON.parse(a); } catch (e) { a = {}; } }
  return a || {};
}

export function isAiTryonEligible(p) {
  return !!p && /fashion/i.test(p.category || '');
}

/**
 * Build a prompt in Decart's recommended "Substitute ... / Add ..." form:
 * one action, one region, only details that are actually in the product data.
 * A product can override everything with attrs.tryon_ai_prompt.
 */
function buildPrompt(p) {
  const attrs = parseAttrs(p);
  if (attrs.tryon_ai_prompt) return attrs.tryon_ai_prompt;

  const name = (p.name || '').trim();
  const sub = String(attrs.subcategory || '').toLowerCase();
  const hay = `${name} ${sub}`.toLowerCase();

  let action;
  if (/saree|sari|lehenga|gown|dress|jumpsuit|anarkali|salwar|co-?ord|suit set/.test(hay)) {
    action = 'Substitute the outfit with';
  } else if (/jean|trouser|pant|skirt|short|legging|palazzo|churidar|jogger/.test(hay)) {
    action = 'Substitute the lower body garment with';
  } else if (/shoe|sneaker|sandal|flat|heel|boot|loafer|slipper|ballerina|derby/.test(hay)) {
    action = 'Substitute the footwear with';
  } else if (/\bcap\b|\bhat\b|beanie/.test(hay)) {
    action = 'Substitute the hat with';
  } else {
    action = 'Substitute the upper body garment with';
  }

  const desc = (p.description || '').trim();
  let prompt = `${action} ${name}${desc ? `. ${desc}` : ''}. Match the garment shown in the reference image exactly.`;
  // Decart prompts have a length cap (~750 chars). Stay well under it.
  if (prompt.length > 600) prompt = prompt.slice(0, 597) + '...';
  return prompt;
}

async function loadSdk() {
  if (!sdk) sdk = await import(SDK_URL);
  return sdk;
}

async function loadConfig() {
  const res = await fetch('/api/tryon/config');
  if (!res.ok) throw new Error('Could not reach the try-on service.');
  cfg = await res.json();
  return cfg;
}

async function referenceBlob(p) {
  const attrs = parseAttrs(p);
  const url = attrs.tryon_ai_image || p.image_url;   // clean garment shot beats a model photo
  if (!url) return null;
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return await res.blob();
  } catch (e) {
    return null;
  }
}

function emit(eventType, p) {
  try {
    fetch('/api/tryon/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_type: eventType,
        product_id: String(p.id),
        sku: p.sku,
        tryon_type: 'ai_vton'
      })
    });
  } catch (e) { /* analytics must never break the UI */ }
}

// ───────────────────────── UI ─────────────────────────

function ensureModal() {
  if (modalEl) return modalEl;
  modalEl = document.createElement('div');
  modalEl.id = 'aiTryonModal';
  modalEl.className = 'hidden fixed inset-0 z-[60] bg-black/95 flex flex-col text-white select-none';
  modalEl.innerHTML = `
    <div class="flex items-center justify-between gap-3 p-4 border-b border-white/10">
      <div class="flex items-center gap-3 min-w-0">
        <img id="aiThumb" class="w-11 h-11 object-cover rounded-lg bg-white/10 border border-white/20" alt="">
        <div class="min-w-0">
          <h3 id="aiTitle" class="font-bold text-sm truncate"></h3>
          <div class="flex items-center gap-2 text-xs mt-0.5">
            <span id="aiPrice" class="text-orange-400 font-black"></span>
            <span id="aiStatus" class="bg-white/10 px-2.5 py-0.5 rounded-full text-[10px] border border-white/10">Ready</span>
            <span id="aiTimer" class="hidden font-mono text-[10px] text-emerald-300 bg-black/40 px-1.5 py-0.5 rounded border border-white/10"></span>
          </div>
        </div>
      </div>
      <button id="aiClose" class="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center" aria-label="Close">
        <i class="fa-solid fa-xmark"></i>
      </button>
    </div>

    <div class="relative flex-1 min-h-0 flex items-center justify-center p-3">
      <!-- consent -->
      <div id="aiConsent" class="max-w-md text-center space-y-4 p-4">
        <div class="text-3xl">✨</div>
        <h4 class="font-extrabold text-lg">See it on you, realistically</h4>
        <p class="text-sm text-gray-300">AI try-on re-draws the clothing on your live camera feed, so sarees, kurtas and dresses drape the way they would on you.</p>
        <p class="text-xs text-amber-300/90 bg-amber-400/10 border border-amber-400/20 rounded-xl p-3">
          Unlike our on-device overlay try-on, your camera video is streamed to our AI partner (Decart) to generate this view. We do not store it.
          Sessions end automatically after <span id="aiConsentSecs">2 minutes</span>.
        </p>
        <button id="aiStart" class="w-full py-3 rounded-xl bg-gradient-to-r from-fuchsia-600 to-orange-500 font-bold text-sm shadow-lg">Allow camera &amp; start</button>
      </div>

      <!-- error / ended -->
      <div id="aiMessage" class="hidden max-w-md text-center space-y-4 p-4">
        <p id="aiMessageText" class="text-sm text-gray-200"></p>
        <div class="flex gap-2 justify-center">
          <button id="aiRetry" class="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-700 text-xs font-bold">Start again</button>
          <button id="aiFallback" class="hidden px-4 py-2 rounded-xl bg-white/15 hover:bg-white/25 text-xs font-bold">Use camera overlay instead</button>
        </div>
      </div>

      <!-- live view -->
      <div id="aiStage" class="hidden relative w-full h-full max-w-5xl flex items-center justify-center">
        <video id="aiOut" autoplay playsinline muted class="max-w-full max-h-full rounded-2xl bg-black object-contain"></video>
        <video id="aiRaw" autoplay playsinline muted class="hidden absolute left-3 bottom-3 w-28 sm:w-40 rounded-xl border-2 border-white/60 shadow-xl object-cover -scale-x-100"></video>
        <span id="aiRawLabel" class="hidden absolute left-4 bottom-4 text-[10px] bg-black/70 px-1.5 py-0.5 rounded">Original</span>
        <div id="aiBusy" class="hidden absolute inset-0 flex items-center justify-center bg-black/60 rounded-2xl">
          <div class="flex items-center gap-3 text-sm"><div class="w-6 h-6 border-4 border-orange-500 border-t-transparent rounded-full animate-spin"></div><span id="aiBusyText">Connecting…</span></div>
        </div>
      </div>
    </div>

    <!-- outfit rail -->
    <div id="aiRailWrap" class="hidden px-4 pt-2">
      <p class="text-[11px] text-gray-400 mb-1.5">Swap outfit without reconnecting</p>
      <div id="aiRail" class="flex gap-2 overflow-x-auto pb-2"></div>
    </div>

    <div class="p-4 flex flex-wrap items-center justify-center gap-3 border-t border-white/10">
      <button id="aiCompare" class="hidden px-4 py-2.5 rounded-xl bg-white/15 hover:bg-white/25 text-xs font-bold border border-white/20"><i class="fa-solid fa-table-columns"></i> Before / after</button>
      <button id="aiCapture" class="hidden px-4 py-2.5 rounded-xl bg-white/15 hover:bg-white/25 text-xs font-bold border border-white/20"><i class="fa-solid fa-camera"></i> Capture photo</button>
      <button id="aiCart" class="px-5 py-2.5 rounded-xl bg-orange-600 hover:bg-orange-700 text-xs font-bold shadow-lg"><i class="fa-solid fa-cart-plus"></i> Add to cart</button>
    </div>
  `;
  document.body.appendChild(modalEl);

  $('aiClose').onclick = closeAiTryon;
  $('aiStart').onclick = () => beginSession();
  $('aiRetry').onclick = () => beginSession();
  $('aiCompare').onclick = () => {
    $('aiRaw').classList.toggle('hidden');
    $('aiRawLabel').classList.toggle('hidden');
  };
  $('aiCapture').onclick = capturePhoto;
  $('aiCart').onclick = addToCartAndClose;
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modalEl.classList.contains('hidden')) closeAiTryon();
  });
  return modalEl;
}

function show(which) {
  ['aiConsent', 'aiMessage', 'aiStage'].forEach((id) => $(id).classList.toggle('hidden', id !== which));
  const live = which === 'aiStage';
  $('aiRailWrap').classList.toggle('hidden', !live);
  $('aiCapture').classList.toggle('hidden', !live);
  $('aiCompare').classList.toggle('hidden', !live);
}

function setStatus(text, color) {
  const el = $('aiStatus');
  el.textContent = text;
  el.style.color = color || '';
}

function showMessage(text, { fallback = false } = {}) {
  $('aiMessageText').textContent = text;
  $('aiFallback').classList.toggle('hidden', !fallback);
  show('aiMessage');
}

function busy(text) {
  $('aiBusyText').textContent = text || 'Working…';
  $('aiBusy').classList.toggle('hidden', !text);
}

function fmtSecs(s) {
  const m = Math.floor(s / 60);
  return m >= 1 && s % 60 === 0 ? `${m} minute${m > 1 ? 's' : ''}` : `${s} seconds`;
}

function renderRail() {
  const rail = $('aiRail');
  rail.innerHTML = '';
  const pool = (window.__lastHits || []).filter((h) => isAiTryonEligible(h) && h.id !== active.id).slice(0, 12);
  $('aiRailWrap').dataset.has = pool.length ? '1' : '';
  pool.forEach((h) => {
    const b = document.createElement('button');
    b.className = 'flex-shrink-0 w-16 text-left';
    b.title = h.name;
    const img = document.createElement('img');
    img.src = h.image_url;
    img.alt = h.name;
    img.className = 'w-16 h-16 object-cover rounded-lg border border-white/20 hover:border-orange-400';
    const cap = document.createElement('span');
    cap.textContent = `₹${Number(h.price_inr).toLocaleString('en-IN')}`;
    cap.className = 'block text-[10px] text-gray-300 mt-0.5';
    b.append(img, cap);
    b.onclick = () => swapProduct(h);
    rail.appendChild(b);
  });
  if (!pool.length) $('aiRailWrap').classList.add('hidden');
}

function paintProduct(p) {
  $('aiThumb').src = p.image_url || '';
  $('aiTitle').textContent = p.name;
  $('aiPrice').textContent = `₹${Number(p.price_inr).toLocaleString('en-IN')}`;
}

// ───────────────────────── session ─────────────────────────

export async function startAiTryon(product) {
  if (!isAiTryonEligible(product)) { alert('AI try-on is available for Fashion items.'); return; }
  active = product;
  ensureModal();
  modalEl.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  paintProduct(product);
  setStatus('Ready');
  $('aiTimer').classList.add('hidden');

  try {
    await loadConfig();
  } catch (e) {
    showMessage(e.message, { fallback: !!product.tryon_supported });
    return;
  }
  if (!cfg.ai_enabled) {
    showMessage('AI try-on is not switched on for this store yet.', { fallback: !!product.tryon_supported });
    return;
  }
  sessionSeconds = cfg.maxSessionSeconds || 120;
  $('aiConsentSecs').textContent = fmtSecs(sessionSeconds);
  $('aiFallback').onclick = () => {
    const p = active;
    closeAiTryon();
    if (window.startLiveTryon) window.startLiveTryon(p);
  };
  show('aiConsent');
}

async function beginSession() {
  show('aiStage');
  busy('Starting camera…');
  setStatus('Connecting', '#facc15');

  try {
    const { createDecartClient, models } = await loadSdk();
    const model = models.realtime(cfg.model);

    camStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: 'user', frameRate: model.fps, width: model.width, height: model.height }
    });
    $('aiRaw').srcObject = camStream;

    // Fresh client token per dial (they live ~60 s). The permanent key stays on the server.
    client = createDecartClient({
      apiKeyProvider: async () => {
        const res = await fetch('/api/tryon/token', { method: 'POST' });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `Token request failed (${res.status})`);
        }
        const data = await res.json();
        sessionSeconds = data.maxSessionSeconds || sessionSeconds;
        return data.apiKey;
      }
    });

    busy('Connecting to AI try-on…');
    const prompt = buildPrompt(active);
    const image = await referenceBlob(active);

    rt = await client.realtime.connect(camStream, {
      model,
      mirror: 'auto',
      onCapacityWait: ({ retryAfterMs }) => busy(`Busy right now — retrying in ${Math.round(retryAfterMs / 1000)}s…`),
      onRemoteStream: (stream) => {
        const out = $('aiOut');
        out.srcObject = stream;
        out.play && out.play().catch(() => {});
        busy('');
        setStatus('Live', '#34d399');
      },
      initialState: { prompt: { text: prompt, enhance: false }, image: image || undefined }
    });

    rt.on('connectionChange', (state) => {
      if (state === 'reconnecting') { busy('Reconnecting…'); setStatus('Reconnecting', '#facc15'); }
      if (state === 'disconnected' && camStream) {
        endSession('The session ended. Start again to keep trying outfits.');
      }
    });
    rt.on('error', (err) => {
      console.error('AI try-on error', err);
      endSession(err && err.code === 'TOKEN_EXPIRED'
        ? 'Session expired. Start again.'
        : 'Connection problem. Check your network and start again.');
    });

    startTimer();
    emit('tryon_ai_started', active);
    renderRail();
  } catch (e) {
    console.error('AI try-on failed to start', e);
    const msg = e && e.name === 'NotAllowedError'
      ? 'Camera permission was denied. Allow camera access and try again.'
      : (e && e.message) || 'Could not start AI try-on.';
    teardown();
    showMessage(msg, { fallback: !!(active && active.tryon_supported) });
  }
}

async function swapProduct(p) {
  if (!rt || !p) return;
  active = p;
  paintProduct(p);
  busy('Changing outfit…');
  try {
    const image = await referenceBlob(p);
    // set() replaces the whole state, so always send prompt AND image together.
    await rt.set({ prompt: buildPrompt(p), image: image || undefined, enhance: false });
    emit('tryon_ai_swapped', p);
    renderRail();
  } catch (e) {
    console.error('Outfit swap failed', e);
  } finally {
    busy('');
  }
}

function startTimer() {
  clearInterval(timerId);
  endsAt = Date.now() + sessionSeconds * 1000;
  const el = $('aiTimer');
  el.classList.remove('hidden');
  const tick = () => {
    const left = Math.max(0, Math.round((endsAt - Date.now()) / 1000));
    el.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
    el.style.color = left <= 15 ? '#f87171' : '';
    if (left <= 0) endSession('Time limit reached. Start again to keep trying outfits.');
  };
  tick();
  timerId = setInterval(tick, 1000);
}

function teardown() {
  clearInterval(timerId);
  timerId = null;
  try { rt && rt.disconnect(); } catch (e) { /* ignore */ }
  rt = null;
  client = null;
  if (camStream) camStream.getTracks().forEach((t) => t.stop());
  camStream = null;
  if (modalEl) {
    $('aiOut').srcObject = null;
    $('aiRaw').srcObject = null;
    busy('');
  }
}

function endSession(message) {
  teardown();
  setStatus('Ended');
  showMessage(message);
}

export function closeAiTryon() {
  teardown();
  if (modalEl) modalEl.classList.add('hidden');
  document.body.style.overflow = '';
  active = null;
}

// ───────────────────────── actions ─────────────────────────

function capturePhoto() {
  const v = $('aiOut');
  if (!v || !v.videoWidth) return;
  const c = document.createElement('canvas');
  c.width = v.videoWidth;
  c.height = v.videoHeight;
  const ctx = c.getContext('2d');
  ctx.drawImage(v, 0, 0, c.width, c.height);   // already pre-mirrored by mirror:'auto'
  ctx.fillStyle = 'rgba(0,0,0,0.65)';
  ctx.fillRect(0, c.height - 44, c.width, 44);
  ctx.fillStyle = '#fff';
  ctx.font = 'bold 14px system-ui, sans-serif';
  ctx.fillText(`MyStore AI Try-On: ${active.name}`.slice(0, 70), 16, c.height - 22);
  const a = document.createElement('a');
  a.download = `MyStore_AI_TryOn_${active.sku || 'item'}.png`;
  a.href = c.toDataURL('image/png');
  a.click();
}

function addToCartAndClose() {
  const p = active;
  if (!p || !window.addToCart) return;
  let qty = 0;
  // `currentCity` is a top-level `let` in index.html: reachable by bare name, not via window.
  const homeCity = typeof currentCity !== 'undefined' ? currentCity : 'Bengaluru';
  let city = homeCity;
  if (p.city_stock) {
    const here = p.city_stock.find((cs) => cs.city === homeCity);
    if (here) qty = here.qty;
    if (qty <= 0) {
      const alt = p.city_stock.find((cs) => cs.qty > 0);
      if (alt) { qty = alt.qty; city = alt.city; }
    }
  }
  window.addToCart(p, qty > 0 ? qty : 10, city);
  emit('tryon_added_to_cart', p);
  closeAiTryon();
}

window.startAiTryon = startAiTryon;
window.closeAiTryon = closeAiTryon;
window.isAiTryonEligible = isAiTryonEligible;
