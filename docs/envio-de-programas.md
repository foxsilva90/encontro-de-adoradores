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

Os códigos precisam ter pelo menos 8 caracteres. Use códigos aleatórios, não
nomes. Pra trocar o código de alguém, edite o JSON e faça redeploy.

### 4. Secrets no GitHub

`AZURACAST_API_KEY`, `AZURACAST_BASE_URL` e `AZURACAST_STATION` já existem (são
os do boletim). Nada novo é necessário pro link de envio.

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
