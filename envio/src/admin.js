// Painel de locutores: lista, cadastra, edita, troca código e remove.
// Tudo montado com textContent (nada de innerHTML com dado do cadastro).
const ENVIO_URL = 'https://envio.encontrodeadoradores.com';
const DIAS_PADRAO = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta'];

const $ = (id) => document.getElementById(id);
let locutores = [];
let editingId = null;

function el(tag, props = {}, children = []) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

function showMsg(node, text) {
  node.textContent = text || '';
  node.hidden = !text;
}

async function api(method, url, body) {
  const resp = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (resp.status === 401 && url !== '/api/admin/login') showLogin();
  if (!resp.ok) throw new Error(data.error || 'Algo deu errado. Tente de novo.');
  return data;
}

// ------------------------------------------------------------ telas

function showLogin() {
  $('login').hidden = false;
  $('painel').hidden = true;
  $('form').hidden = true;
  $('logout').hidden = true;
}

function showPainel() {
  $('login').hidden = true;
  $('form').hidden = true;
  $('painel').hidden = false;
  $('logout').hidden = false;
}

function aviso(text) {
  showMsg($('aviso'), text);
  if (text) window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ------------------------------------------------------------ lista

function mensagemPara(l) {
  return `Olá, ${l.nome}! Seu código pra enviar o programa "${l.programa}" é: ${l.codigo}\n`
    + `Envie o áudio por este link: ${ENVIO_URL}`;
}

async function copiar(texto, ok) {
  try {
    await navigator.clipboard.writeText(texto);
    aviso(ok);
  } catch {
    window.prompt('Copie o texto abaixo:', texto);
  }
}

function resumoDestinos(l) {
  if (l.destinos.length === 1) {
    return [el('b', { textContent: 'Playlists: ' }), l.destinos[0].playlists.join(' · ')];
  }
  return l.destinos.flatMap((d, i) => [
    ...(i ? [el('br')] : []), el('b', { textContent: `${d.nome}: ` }), d.playlists.join(' · '),
  ]);
}

function itemLocutor(l) {
  const botao = (texto, cls, onClick) => el('button', { type: 'button', className: cls, textContent: texto, onclick: onClick });
  return el('article', { className: 'card item' }, [
    el('h3', { textContent: l.programa }),
    el('div', { className: 'who', textContent: l.nome }),
    el('div', {}, [
      el('span', { className: 'code', textContent: l.codigo }),
      el('span', { className: l.editar === false ? 'tag pronto' : 'tag',
        textContent: l.editar === false ? 'Programa pronto (sem edição)' : 'Com vinheta e playback' }),
    ]),
    el('div', { className: 'dest' }, resumoDestinos(l)),
    el('div', { className: 'row actions' }, [
      botao('Copiar mensagem pro locutor', '', () => copiar(mensagemPara(l), `Mensagem pro(a) ${l.nome} copiada. É só colar no WhatsApp.`)),
      botao('Editar', 'ghost', () => openForm(l)),
      botao('Gerar novo código', 'ghost', () => novoCodigo(l)),
      botao('Remover', 'danger', () => remover(l)),
    ]),
  ]);
}

function renderLista() {
  const lista = $('lista');
  lista.replaceChildren(...(locutores.length
    ? locutores.map(itemLocutor)
    : [el('p', { className: 'card empty', textContent: 'Nenhum locutor cadastrado ainda.' })]));
}

async function carregar() {
  const data = await api('GET', '/api/admin/locutores');
  locutores = data.locutores;
  renderLista();
  showPainel();
}

async function novoCodigo(l) {
  const ok = window.confirm(`Gerar um código novo pro(a) ${l.nome}?\n\nO código atual (${l.codigo}) para de funcionar na hora.`);
  if (!ok) return;
  try {
    const data = await api('POST', '/api/admin/locutores', { acao: 'novo-codigo', id: l.id });
    locutores = data.locutores;
    renderLista();
    aviso(`Novo código do(a) ${l.nome}: ${data.codigo}. Use "Copiar mensagem" pra mandar pra pessoa.`);
  } catch (err) {
    showMsg($('lista-error'), err.message);
  }
}

async function remover(l) {
  const ok = window.confirm(`Remover ${l.nome} (${l.programa})?\n\nO código dele(a) para de funcionar. Os programas que já estão na rádio continuam lá.`);
  if (!ok) return;
  try {
    const data = await api('DELETE', '/api/admin/locutores', { id: l.id });
    locutores = data.locutores;
    renderLista();
    aviso(`${l.nome} foi removido(a).`);
  } catch (err) {
    showMsg($('lista-error'), err.message);
  }
}

// ------------------------------------------------------------ formulário

const modo = () => document.querySelector('input[name=modo]:checked').value;

function playlistInput(value = '') {
  const input = el('input', { type: 'text', value, maxLength: 200, placeholder: 'Nome da playlist no AzuraCast' });
  input.setAttribute('list', 'playlists');
  const tirar = el('button', { type: 'button', className: 'danger', textContent: 'tirar', onclick: () => row.remove() });
  const row = el('div', { className: 'row pl' }, [input, tirar]);
  return row;
}

function destinoBox(destino = { nome: '', playlists: [''] }) {
  const lista = el('div', {}, destino.playlists.map((p) => playlistInput(p)));
  const nome = el('input', { type: 'text', value: destino.nome, maxLength: 100, placeholder: 'Ex.: Segunda', className: 'dia' });
  const head = el('div', { className: 'row dia-row' }, [
    nome, el('button', { type: 'button', className: 'danger', textContent: 'tirar dia', onclick: () => box.remove() }),
  ]);
  const box = el('div', { className: 'destino' }, [
    head, lista,
    el('button', { type: 'button', className: 'ghost', textContent: '+ playlist', style: 'margin-top:8px',
      onclick: () => lista.append(playlistInput()) }),
  ]);
  return box;
}

function aplicarModo() {
  const porDia = modo() === 'dias';
  $('add-destino').hidden = !porDia;
  const boxes = [...$('destinos').children];
  boxes.forEach((b, i) => {
    b.querySelector('.dia-row').hidden = !porDia;
    b.hidden = !porDia && i > 0;
  });
}

function setModo(value) {
  document.querySelector(`input[name=modo][value=${value}]`).checked = true;
}

function openForm(l = null) {
  editingId = l?.id ?? null;
  $('form-title').textContent = l ? `Editar: ${l.programa}` : 'Novo locutor';
  $('f-nome').value = l?.nome ?? '';
  $('f-programa').value = l?.programa ?? '';
  document.querySelector(`input[name=editar][value=${l?.editar === false ? 'nao' : 'sim'}]`).checked = true;
  const porDia = (l?.destinos.length ?? 1) > 1;
  setModo(porDia ? 'dias' : 'unico');
  const destinos = l ? l.destinos : [{ nome: '', playlists: [''] }];
  $('destinos').replaceChildren(...destinos.map((d) => destinoBox(porDia ? d : { ...d, nome: '' })));
  aplicarModo();
  showMsg($('form-error'), '');
  $('painel').hidden = true;
  $('form').hidden = false;
  $('f-nome').focus();
}

function lerFormulario() {
  const porDia = modo() === 'dias';
  const boxes = [...$('destinos').children].filter((b) => porDia || !b.hidden);
  return {
    nome: $('f-nome').value,
    programa: $('f-programa').value,
    editar: document.querySelector('input[name=editar]:checked').value === 'sim',
    destinos: boxes.map((b) => ({
      nome: porDia ? b.querySelector('.dia').value : '',
      playlists: [...b.querySelectorAll('.pl input')].map((i) => i.value).filter((v) => v.trim()),
    })),
  };
}

async function salvar(e) {
  e.preventDefault();
  const body = lerFormulario();
  if (modo() === 'dias' && body.destinos.length < 2) {
    return showMsg($('form-error'), 'Com escolha de dia, cadastre pelo menos 2 dias. Se é um só, use "Um envio".');
  }
  $('salvar').disabled = true;
  try {
    const data = editingId
      ? await api('PUT', '/api/admin/locutores', { ...body, id: editingId })
      : await api('POST', '/api/admin/locutores', body);
    locutores = data.locutores;
    renderLista();
    showPainel();
    aviso(editingId
      ? 'Alterações salvas. Valem a partir do próximo envio.'
      : `${body.nome.trim()} cadastrado(a)! Código: ${data.codigo}. Use "Copiar mensagem" pra mandar pra pessoa.`);
  } catch (err) {
    showMsg($('form-error'), err.message);
  } finally {
    $('salvar').disabled = false;
  }
}

async function carregarPlaylists() {
  try {
    const data = await api('GET', '/api/admin/playlists');
    $('playlists').replaceChildren(...data.playlists.map((p) => el('option', { value: p })));
    if (data.fonte === 'azuracast') $('pl-hint').textContent = 'As sugestões vêm direto do AzuraCast.';
  } catch {
    /* sem sugestões: o campo continua aceitando texto livre */
  }
}

// ------------------------------------------------------------ eventos

$('login').addEventListener('submit', async (e) => {
  e.preventDefault();
  showMsg($('login-error'), '');
  $('login-btn').disabled = true;
  try {
    await api('POST', '/api/admin/login', { senha: $('senha').value });
    $('senha').value = '';
    await carregar();
    carregarPlaylists();
  } catch (err) {
    showMsg($('login-error'), err.message);
  } finally {
    $('login-btn').disabled = false;
  }
});

$('logout').addEventListener('click', async () => {
  await api('DELETE', '/api/admin/login').catch(() => {});
  showLogin();
});

$('novo').addEventListener('click', () => { aviso(''); openForm(); });
$('cancelar').addEventListener('click', showPainel);
$('form').addEventListener('submit', salvar);
document.querySelectorAll('input[name=modo]').forEach((r) => r.addEventListener('change', () => {
  if (modo() === 'dias' && $('destinos').children.length === 1) {
    const primeira = [...$('destinos').children[0].querySelectorAll('.pl input')].map((i) => i.value);
    $('destinos').replaceChildren(...DIAS_PADRAO.map((nome, i) => destinoBox({ nome, playlists: i ? [''] : primeira })));
  }
  aplicarModo();
}));
$('add-destino').addEventListener('click', () => {
  $('destinos').append(destinoBox());
  aplicarModo();
});

carregar().then(carregarPlaylists).catch(() => showLogin());
