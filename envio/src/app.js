import { upload } from '@vercel/blob/client';

const STORAGE_KEY = 'codigo-locutor';
const MAX_BYTES = 500 * 1024 * 1024;
const MULTIPART_FROM_BYTES = 20 * 1024 * 1024;

const $ = (id) => document.getElementById(id);
const steps = { code: $('step-code'), file: $('step-file'), done: $('step-done') };

let codigo = '';
let programa = '';
let file = null;
let uploading = false;

function show(step) {
  Object.entries(steps).forEach(([name, el]) => { el.hidden = name !== step; });
}

function showError(el, text) {
  el.textContent = text;
  el.hidden = !text;
}

function slugify(text) {
  return text.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'programa';
}

function formatSize(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

async function postJson(url, body) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || 'Algo deu errado. Tente de novo.');
  return data;
}

async function checkCode(value) {
  const data = await postJson('/api/locutor', { codigo: value });
  codigo = value;
  programa = data.programa;
  localStorage.setItem(STORAGE_KEY, value);
  $('program-name').textContent = programa;
  show('file');
}

function selectFile(f) {
  showError($('file-error'), '');
  if (!f) return;
  if (f.size > MAX_BYTES) {
    showError($('file-error'), 'Arquivo maior que 500 MB.');
    return;
  }
  file = f;
  $('file-name').textContent = `🎧 ${f.name} (${formatSize(f.size)})`;
  $('file-name').hidden = false;
  $('send-btn').disabled = false;
}

function setProgress(pct, text) {
  $('bar').hidden = false;
  $('bar-fill').style.width = `${pct}%`;
  $('status').textContent = text;
}

function resetFileStep() {
  file = null;
  $('arquivo').value = '';
  $('file-name').hidden = true;
  $('bar').hidden = true;
  $('status').textContent = '';
  $('send-btn').disabled = true;
  $('send-btn').textContent = 'Enviar programa';
}

async function sendFile() {
  uploading = true;
  $('send-btn').disabled = true;
  $('send-btn').textContent = 'Enviando…';
  showError($('file-error'), '');
  try {
    const ext = (file.name.match(/\.[a-z0-9]{1,5}$/i) || ['.mp3'])[0].toLowerCase();
    const blob = await upload(`programas/${slugify(programa)}/voz${ext}`, file, {
      access: 'public',
      handleUploadUrl: '/api/upload',
      clientPayload: JSON.stringify({ codigo }),
      contentType: file.type || 'application/octet-stream',
      multipart: file.size > MULTIPART_FROM_BYTES,
      onUploadProgress: ({ percentage }) =>
        setProgress(percentage, `Enviando… ${Math.round(percentage)}% (não feche esta página)`),
    });
    setProgress(100, 'Preparando publicação…');
    await postJson('/api/publicar', { codigo, url: blob.url });
    $('done-name').textContent = programa;
    show('done');
  } catch (err) {
    showError($('file-error'), err.message || 'Falha no envio. Confira sua internet e tente de novo.');
    $('send-btn').disabled = false;
    $('send-btn').textContent = 'Tentar de novo';
  } finally {
    uploading = false;
  }
}

$('step-code').addEventListener('submit', async (e) => {
  e.preventDefault();
  const value = $('codigo').value.trim().toUpperCase();
  showError($('code-error'), '');
  if (!value) return showError($('code-error'), 'Digite o seu código.');
  $('code-btn').disabled = true;
  try {
    await checkCode(value);
  } catch (err) {
    showError($('code-error'), err.message);
  } finally {
    $('code-btn').disabled = false;
  }
});

$('arquivo').addEventListener('change', (e) => selectFile(e.target.files[0]));
const drop = $('drop');
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', (e) => {
  e.preventDefault();
  drop.classList.remove('over');
  selectFile(e.dataTransfer.files[0]);
});

$('step-file').addEventListener('submit', (e) => {
  e.preventDefault();
  if (file && !uploading) sendFile();
});

$('change-code').addEventListener('click', () => {
  localStorage.removeItem(STORAGE_KEY);
  $('codigo').value = '';
  resetFileStep();
  show('code');
});

$('again').addEventListener('click', () => {
  resetFileStep();
  show('file');
});

window.addEventListener('beforeunload', (e) => {
  if (uploading) e.preventDefault();
});

const saved = localStorage.getItem(STORAGE_KEY);
if (saved) {
  $('codigo').value = saved;
  checkCode(saved).catch(() => show('code'));
}
