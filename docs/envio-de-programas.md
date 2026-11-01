# Envio de programas pelos locutores

O locutor grava **só a voz** e envia pelo link de envio. O sistema monta o
programa e coloca na playlist dele no AzuraCast, no lugar do episódio anterior.

```
[Vinheta de responsabilidade] → [3s de playback] → [voz + playback com ducking] → [fade-out 4s]
```

## Como funciona

```
Locutor → envio.<domínio> (projeto envio/ na Vercel)
   1. digita o código pessoal → /api/locutor mostra o nome do programa
   2. escolhe o arquivo → vai direto do navegador pro Vercel Blob (/api/upload dá o token)
   3. /api/publicar dispara o GitHub Actions "publicar-programa.yml"
GitHub Actions → scripts/publicar_programa.py
   baixa a voz → scripts/audio_mix.py monta o programa com trilhas/ → AzuraCast
Vercel Cron diário → /api/limpar apaga do Blob os arquivos com mais de 24h
```

- Trilhas usadas: `trilhas/responsabilidade.mp3` e `trilhas/playback.m4a`. Pra
  trocar, substitua o arquivo mantendo o nome (ou mude `INTRO_FILE`/`BED_FILE`
  em `scripts/publicar_programa.py`).
- Ajustes de mixagem (volume do playback, quanto ele abaixa, tempos de
  entrada e fade) ficam no topo de `scripts/audio_mix.py`.
- A voz recebe limpeza leve (corte de graves e redução de chiado) e o programa
  final é normalizado pra -16 LUFS.
- A playlist do programa **precisa existir** no AzuraCast com o nome exato
  cadastrado. O horário dela continua sendo configurado no AzuraCast.
- Episódio anterior enviado pelo sistema (pasta `programas/<programa>/`) é
  apagado. Se tiver sido subido à mão, só sai da playlist e o arquivo fica.

### Link do Google Drive

Em vez de subir o arquivo, o locutor pode colar o link de um arquivo do Drive.
O arquivo precisa estar em Compartilhar → "Qualquer pessoa com o link".
`api/publicar.js` aceita os formatos `drive.google.com/file/d/<id>/…`, `open?id=`, `uc?id=`
(recusa link de pasta) e confere na hora se o arquivo baixa sem login. Se não baixar,
mostra o erro pro locutor. O workflow recebe
`https://drive.usercontent.google.com/download?id=<id>&export=download&confirm=t`
(o `confirm=t` pula o aviso de vírus do Drive em arquivos grandes) e baixa dali.

## Configuração (uma vez)

### 1. Projeto novo na Vercel

1. Vercel → Add New → Project → importar o repositório `encontro-de-adoradores`.
2. **Root Directory: `envio`**. O resto a Vercel lê de `envio/vercel.json`.
3. Depois de criado: aba **Storage** → Create → **Blob** → conectar a este
   projeto. Isso cria a variável `BLOB_READ_WRITE_TOKEN` sozinho.
4. (Opcional) Settings → Domains → `envio.encontrodeadoradores.com`.

### 2. Token do GitHub

GitHub → Settings → Developer settings → Fine-grained tokens → novo token só
para o repositório `encontro-de-adoradores`, com permissão
**Actions: Read and write**.

### 3. Variáveis do projeto `envio` na Vercel

| Nome | Valor |
|------|-------|
| `CODIGOS_LOCUTORES` | `{"MANHA-7K2P9QX4": "Nome exato da playlist", ...}` |
| `GITHUB_DISPATCH_TOKEN` | token do passo 2 |
| `GITHUB_REPO` | `foxsilva90/encontro-de-adoradores` |
| `CRON_SECRET` | texto aleatório longo (protege a limpeza diária) |
| `ADMIN_PASSWORD` | senha do painel de administração |
| `ADMIN_SECRET` | texto aleatório longo (criptografa o cadastro; **não trocar**) |

Os códigos precisam ter pelo menos 8 caracteres. Use códigos aleatórios, não
nomes. Pra trocar o código de alguém, edite o JSON e faça redeploy.

### 4. Secrets no GitHub

`AZURACAST_API_KEY`, `AZURACAST_BASE_URL` e `AZURACAST_STATION` já existem (são
os do boletim). Nada novo é necessário pro link de envio.

## Painel de administração

`https://envio.encontrodeadoradores.com/admin.html` (senha em `ADMIN_PASSWORD`).

- **Novo locutor**: nome, programa, se o áudio é só voz (monta com vinheta e
  playback) ou programa pronto (sobe como veio), e as playlists. Com "o locutor
  escolhe o dia", cada dia tem as próprias playlists. O código é gerado sozinho.
- **Copiar mensagem**: texto pronto com o código e o link, pra colar no WhatsApp.
- **Gerar novo código**: o antigo para de funcionar na hora (use quando alguém
  esqueceu, perdeu ou saiu da equipe).
- **Editar / Remover**: vale a partir do próximo envio.

O cadastro fica no Vercel Blob em `config/locutores.enc`, criptografado com
AES-256-GCM (chave derivada de `ADMIN_SECRET`). Enquanto o painel nunca salvou
nada, vale a variável `CODIGOS_LOCUTORES`; no primeiro acesso ao painel ela é
copiada pro Blob e, dali em diante, **o painel é quem manda** (editar a
variável não muda mais nada).

> **Não troque o `ADMIN_SECRET`**: sem ele o cadastro salvo não abre e o link
> de envio para. Pra trocar a senha, mude só o `ADMIN_PASSWORD`.

Se `AZURACAST_BASE_URL`, `AZURACAST_API_KEY` e `AZURACAST_STATION` estiverem no
projeto `envio-programas`, o formulário sugere as playlists direto do
AzuraCast. Sem elas, sugere as que já estão no cadastro.

## Quando algo dá errado

- Veja a execução em GitHub → Actions → "Publicar programa enviado por locutor".
- `Playlist 'X' não existe no AzuraCast`: o nome no JSON tem que bater com o da
  playlist (maiúsculas e espaços nas pontas não importam).
- A página diz "não consegui iniciar a publicação": confira o
  `GITHUB_DISPATCH_TOKEN` (pode ter expirado).

## WhatsApp (opcional, desligado)

O código pra receber programas pelo WhatsApp também existe
(`api/whatsapp-webhook.js` no site principal) e usa o mesmo workflow. Pra
ligar é preciso migrar o número pra WhatsApp Cloud API da Meta. Depois disso o
número **sai do app do celular**. Variáveis: `WHATSAPP_VERIFY_TOKEN`,
`WHATSAPP_APP_SECRET`, `PROGRAMAS_WHATSAPP`, `GITHUB_DISPATCH_TOKEN`,
`GITHUB_REPO` na Vercel; `PROGRAMAS_WHATSAPP`, `WHATSAPP_TOKEN`,
`WHATSAPP_PHONE_NUMBER_ID` no GitHub.

## Testes

```bash
node --test tests/*.test.mjs        # webhook do WhatsApp
cd envio && npm test                 # link de envio
uvx --with requests pytest scripts/tests   # publicação e mixagem
```
