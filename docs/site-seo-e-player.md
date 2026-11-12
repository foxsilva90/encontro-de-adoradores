# Site: SEO, ícone na tela de início e player com a tela desligada

Feito em 09/11/2026 (commit `9cf6a23`). **Testado num celular de verdade e funcionando**:
a rádio continua tocando com a tela desligada e o ícone aparece na tela de início.

## Páginas de SEO

O site tinha só a home, a página de parceiros e duas páginas legais, e não aparecia
nas buscas. Foram criadas três páginas, cada uma mirando uma busca diferente:

| Página | Busca |
|---|---|
| `programacao.html` | "programação rádio encontro de adoradores". Grade semanal em texto puro, que o Google lê (na home a grade é montada por JavaScript). |
| `locutores.html` | nome dos apresentadores |
| `anderson-gustavo.html` | "Anderson Gustavo" |

- Todas têm título, descrição, canonical e dados estruturados (`RadioStation`,
  `Person`, `BreadcrumbList`).
- Recebem links da home (programação, seção Sobre e rodapé) e estão no `sitemap.xml`.
- O HTML é estático: para mudar algo, edite o arquivo direto.
- Depois de publicar, peça a indexação no Search Console (Inspeção de URL → Solicitar indexação).

## A grade fica em 3 lugares

Quando mudar um programa ou horário, atualize os três:

1. `radio.html`, no bloco `// ── SCHEDULE ──` (grade da home)
2. `programacao.html` e `locutores.html` (páginas de SEO)
3. App: `src/screens/ProgramacaoScreen.js`, no repo do app
   (`Documents/FELIPE/RadioEncontroAdoradores`). Só chega aos ouvintes numa versão nova do app.

Grade em 09/11/2026: além da programação da Equipe EA, tem Encontro de Adoradores
(seg a sex, 10h e 17h), Jesus é a Resposta (Pr Tiago Iracet, qua 9h), Palavra Viva
(Patricia Bambrila, seg a sex 15h), Palavras de Fé (Pr Anderson Barbosa, qui 11h),
Momento Profético (Ap Igor Santos, qua 18h30), Sexta Gospel Hits (sex 8h30 e 19h) e
Clássicos do Talito (sáb 8h).

## Ícone na tela de início

- O ícone é o microfone do app (`assets/icon.png` do repo do app).
- Arquivos: `favicon.ico`, `icons/` (favicon 16/32/48, `apple-touch-icon.png` 180,
  `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`) e `manifest.webmanifest`.
- Ao abrir pelo ícone, o site abre em tela cheia (`display: standalone`), em
  `/radio.html?origem=tela-inicial`.
- As tags ficam no `<head>` de todas as páginas públicas. Página nova precisa
  copiar esse bloco (`rel="manifest"`, `apple-touch-icon`, `theme-color`).

## Player tocando com a tela desligada (`radio.html`)

- **Media Session:** o site avisa o celular que está tocando mídia. Aparecem play/pause
  e o nome da música na tela de bloqueio, e o sistema não suspende a página.
  O título e o artista vêm do "tocando agora" do AzuraCast (`updateMediaSession`).
- **Reconexão automática:** se o stream cair (`error`, `ended` ou quando a internet
  volta), ele reconecta em 2s, 4s, 8s… até 30s entre tentativas. Cada conexão usa
  `?t=<hora>` no endereço para não reaproveitar um buffer velho.
- **Soluços da rede não reconectam (corrigido em 12/11/2026, commit `1fc213f`):**
  `stalled` e `waiting` disparam em qualquer falha curta, como a troca de antena no 4G.
  Reconectar na hora descartava o buffer e fazia a rádio engasgar na rua. Agora esses
  eventos só armam um vigia: se o áudio ficar parado por 10s (`STALL_TIMEOUT_MS`), aí
  reconecta. Qualquer `timeupdate` (áudio andando) desarma o vigia.
- Funções: `startRadio`, `stopRadio`, `toggleRadio`, `scheduleReconnect`,
  `armStallWatchdog`, `clearStallWatchdog`.
- **Se ainda engasgar no celular:** o stream é MP3 192 kbps vindo de um servidor em
  Boston, e o Icecast manda só uns 3s de áudio adiantado. No AzuraCast dá para baixar o
  mount `/radio.mp3` para 128 kbps e aumentar o `burst-size` do Icecast (ex.: 262144)
  para o celular começar com uns 10s guardados.
- Em alguns Android com economia de bateria agressiva (Xiaomi, Samsung no modo
  economia), o sistema ainda pode cortar o navegador. Nesse caso, tire o navegador
  da economia de bateria no próprio celular.

## App ainda não lançado

A seção "Baixe o App" (download do APK) foi removida. Não divulgar o app, nem com
link de download nem com página, até ele ser lançado.
