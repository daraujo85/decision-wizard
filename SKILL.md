---
name: decision-wizard
description: Gera um wizard web (decisao por decisao, A/B/C + pergunta livre) pra revisar decisoes abertas de uma analise, hospeda com tunnel gratis e fecha o loop de perguntas sem precisar de humano sincrono no chat.
---

# Decision Wizard

Empacota o padrao ja usado em produção (b2b350 e afins): depois que uma analise
gera decisões em aberto, esta skill gera um HTML de wizard (uma decisão por vez,
A/B/C ou resposta livre), sobe um servidor local protegido por senha, expõe via
tunnel público gratuito e permite fechar as perguntas que a pessoa fizer no
wizard (`askWidget`) direto pelo Claude Code — sem ninguém precisar ficar no chat.

**Zero dependência de ferramenta pessoal.** Não usa CLI/serviço local fora do
padrão nem secrets pessoais — funciona em qualquer máquina que
tenha `python3` e `cloudflared` no PATH. Portanto qualquer colega pode usar. A
única dependência externa é o Mermaid, carregado via CDN pelo navegador de quem
responde (já precisa de internet pra acessar a URL do tunnel mesmo).

## Quando usar

- Terminou uma análise (código, proposta, arquitetura) e sobraram decisões que
  precisam de validação humana, mas não dá pra travar o chat esperando resposta.
- Quer revisão assíncrona, decisão por decisão (não uma parede de perguntas).
- Precisa que a pessoa possa perguntar de volta ("por que essa opção?") e você
  responder sem estar na mesma sessão de chat.

## Quando NÃO usar

- Decisão única, simples — pergunte direto no chat.
- Já existe um canal síncrono aberto (call, mesma sessão) — não crie overhead.

## Pré-requisitos

```bash
which python3      # ja vem no mac/linux
which cloudflared   # brew install cloudflared (mac); senão baixe em
                     # https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
```

Sem conta, sem signup — `cloudflared tunnel --url` gera uma URL pública
`*.trycloudflare.com` na hora.

## Fluxo

### 1. Gerar o spec de decisões (JSON)

Monte um JSON com as decisões abertas da sua análise (ver schema completo no
topo de `generate_wizard.py`):

```json
{
  "title": "Revisão: nome da feature/análise",
  "sections": [
    {
      "id": "s1",
      "key": "S1",
      "title": "Nome da subtarefa/área",
      "decisions": [
        {
          "tag": "D1",
          "question": "Pergunta objetiva da decisão?",
          "options": {"a": "opção A", "b": "opção B", "c": "opção C"}
        }
      ]
    }
  ]
}
```

A opção "nenhuma dessas / escrever resposta livre" é adicionada automaticamente
pelo `answers.js` em runtime — não precisa declarar no spec.

Campos opcionais (ausência esconde a parte correspondente na UI, sem
placeholder forçado): `context` (texto abaixo da pergunta), `plain`
(explicação simples atrás do botão "Explicar em palavras simples" — trate
como obrigatório, ver 1.1), `optionPlain` (o que acontece se escolher a
opção, sempre visível), `optionBadge` (selo curto por opção, ex.: "já
implementado"), `tech` (jargão/detalhe de implementação, recolhido),
`diagram` + `diagramCaption` (diagrama archify, ver 1.2):

```json
{
  "tag": "D4", "question": "Quanto tempo um aviso pode atrasar sem prejudicar o cliente?",
  "context": "Surgiu no onboarding de integrações.",
  "plain": "Quanto mais 'na hora' precisar ser, mais caro e complexo fica manter.",
  "options": {"a": "Até 1 minuto está ok", "b": "Precisa ser na hora (segundos)", "c": "Pode ser no fim do dia"},
  "optionPlain": {"a": "Usa estrutura que o time já conhece; custo baixo."},
  "optionBadge": {"a": "recomendado"},
  "tech": "a = SQS (já usado); b = Kafka/stream; c = job batch noturno."
}
```

### 1.1 Escrever pra quem vai decidir (obrigatório)

Quem responde o wizard muitas vezes é de negócio (PO, gestor, comercial,
suporte), não dev. Antes de montar o spec, pergunte: **quem vai ler?** Na
dúvida, escreva pra pessoa de negócio — dev entende linguagem simples, o
contrário não vale.

Regras pros campos que todo mundo vê (`question`, `options`, `plain`):

| Em vez de (técnico) | Escreva (negócio) |
|---|---|
| "Usar fila SQS ou processar síncrono no endpoint?" | "O cliente deve esperar a confirmação na hora ou pode receber depois (até ~1 min)?" |
| "Criar migration adicionando coluna `status`?" | "Precisamos guardar em que etapa cada pedido está?" |
| "Feature flag por tenant" | "Liberar primeiro só pra alguns clientes, depois pra todos" |
| "Rollback automático" | "Se der erro, voltar sozinho pra versão anterior" |

- **Pergunta = consequência, não mecanismo.** Fale do que muda pro cliente,
  pro time, pro prazo, pro custo ou pro risco. O "como" vai no `tech`.
- **Opção = resultado + trade-off curto.** Ex.: "Mais rápido de entregar
  (1 semana), mas manual pro suporte". Evite opção que é só nome de
  ferramenta ("SQS", "Redis").
- **`plain` sempre preenchido**: 1–3 frases, como se explicasse pra alguém
  de outro setor. Use exemplo concreto do dia a dia do negócio.
- **`optionPlain`** pra cada opção não óbvia: "o que acontece se escolher
  esta". Aparece sempre embaixo da opção (não só depois de escolher).
- **Jargão necessário vai pro `tech`** — fica recolhido em "Detalhe técnico
  (opcional)"; dev abre, negócio ignora.
- Sem siglas sem explicar, sem nome de arquivo/tabela/classe na pergunta.
- Se a decisão é **puramente técnica** (negócio não tem como opinar), não
  ponha no wizard de negócio — decida você ou mande pra revisão técnica.

O gerador avisa no stderr (não bloqueia) quando acha jargão em
pergunta/opção ou decisão sem `plain`. Corrija os avisos antes de publicar.

### 1.2 Diagrama do fluxo (archify) quando ajudar

Quando a decisão mexe num **fluxo** (etapas de um processo, quem fala com
quem, por onde passa o dinheiro/documento, em que status o pedido está),
um desenho explica melhor que texto. Gere com a skill `archify` e embuta na
decisão:

1. Use **quando**: a pergunta depende de entender ordem de etapas, onde a
   mudança entra no processo, ou comparar "como é hoje" vs. "como fica".
   **Não use** em decisão de sim/não simples ou preferência — vira ruído.
2. Gere o diagrama com `archify` (tipo `workflow`, `sequence`, `dataflow`
   ou `lifecycle` conforme o caso), **escrito pra negócio**: rótulos do dia
   a dia ("Cliente paga", "Financeiro aprova"), não nome de serviço/tabela.
   Destaque o ponto onde a decisão entra (nó/etapa com nome tipo
   "← decisão D2 aqui").
3. Copie o HTML final pra `<workdir>/diagrams/<nome>.html` (nome só com
   letras, números, `-`, `_`) e aplique a paleta do wizard (cores, fonte
   Archivo, vermelho de destaque) pra não destoar da página:

   ```bash
   python3 ~/.claude/skills/decision-wizard/theme_diagram.py <workdir>/diagrams/<nome>.html
   ```

   Só redefine as variáveis de cor do tema claro do archify (não mexe no
   desenho); rodar de novo não duplica. Dica de cor no archify: nó
   `security` sai em vermelho (use pro ponto da decisão), `backend` em
   preto, `external` em cinza. Um diagrama pode servir várias decisões.
4. No spec: `"diagram": "<nome>"` + `"diagramCaption": "o que olhar"`
   (ex.: "Veja a etapa em vermelho: é onde o cliente ficaria esperando").

```json
{
  "tag": "D2",
  "question": "O cliente deve esperar a confirmação do pagamento na tela?",
  "plain": "Hoje ele espera ~20s olhando um carregando. A alternativa é liberar na hora e avisar por WhatsApp quando confirmar.",
  "diagram": "fluxo-pagamento",
  "diagramCaption": "Etapa 3 é onde o cliente fica esperando hoje.",
  "options": {"a": "Esperar na tela (como hoje)", "b": "Liberar na hora e avisar depois"},
  "optionPlain": {"b": "Experiência mais rápida; raramente (~1%) o pagamento falha depois e o suporte precisa contatar."},
  "tech": "Mover confirmação do gateway pra processamento assíncrono via fila + webhook."
}
```

O diagrama aparece num quadro dentro da decisão (entre explicação e
opções), com link "Abrir diagrama em tela cheia". Fica atrás do mesmo login
do wizard.

### 1.3 Áudio narrado da decisão (TTS, opcional)

Pra quem prefere ouvir (ou responde pelo celular), cada decisão ganha **um**
botão "Ouvir a pergunta e as opções" com uma narração única. Usa uma API HTTP de TTS
(`POST $TTS_BASE_URL/tts`, URL no ambiente ou em `~/.config/decision-wizard/tts.env`;
contrato no topo do `generate_audio.py`). Sem a API configurada, pule este
passo: o wizard funciona igual, só sem botão de áudio.

- Ligar: `"audio": true` no topo do spec (todas as decisões) ou só na
  decisão. `"audio": false` numa decisão desliga só ela.
- Roteiro (sempre nesta ordem, montado pelo `generate_audio.py`):
  1. o problema: pergunta + `plain`;
  2. se tem `diagram`: "clique no diagrama pra ver onde isso entra no processo";
  3. pedido de ajuda: "preciso da sua ajuda… qual é a mais indicada: A, B ou C";
  4. cada opção: "Opção A[, marcada como <badge>]: <texto>. <optionPlain>";
  5. cobrança: "qual você escolhe? Se nenhuma servir, escreva sua própria resposta".
- O `tech` **nunca** é falado — mais um motivo pra deixar pergunta/opções em
  linguagem simples (jargão falado soa pior que escrito). Narração passa de
  ~2 min acima de 1800 caracteres: o script avisa; encurte `plain`/`optionPlain`.
- Gerar (antes do `generate_wizard.py`):

```bash
python3 ~/.claude/skills/decision-wizard/generate_audio.py spec.json /tmp/meu-wizard \
  [--voice pt-BR-AntonioNeural]
```

Grava `/tmp/meu-wizard/audio/<hash>.mp3` e escreve `audioFiles` dentro do
spec. Rodar de novo só gera o que mudou (nome = hash de voz+texto). Formato
mp3, não ogg: ogg não toca em Safari/iPhone. Não ponha dado sensível (CPF,
valor de cliente identificado) em texto que vira áudio.

### 2. Gerar o HTML

```bash
mkdir -p /tmp/meu-wizard/docs /tmp/meu-wizard/diagrams
# (opcional) cp .archify/<pasta>/<slug>.html /tmp/meu-wizard/diagrams/fluxo-pagamento.html
python3 ~/.claude/skills/decision-wizard/generate_wizard.py spec.json \
  --diagrams-dir /tmp/meu-wizard/diagrams > /tmp/meu-wizard/docs/revisao.html
```

`--diagrams-dir` é opcional; com ele o gerador avisa se algum `diagram` do
spec aponta pra arquivo que não existe.

A tela inicial (overview) mostra o mapa mental (Mermaid) com todas as
opções de todas as decisões. Dentro de cada decisão o topo traz a trilha
(Início › D1: resposta › D2 agora, clicável pra voltar) e o mapa fica
recolhido no fim da página. O resumo final repete o mapa com o caminho
escolhido destacado — incluindo o texto de respostas livres ("outra").

### 2.0 Favicon e "quem está vendo"

- Favicon SVG servido pelo `server.py` em `/favicon.svg` (público), já linkado no wizard e no login.
- Cada página aberta manda heartbeat em `POST /api/presence?doc=` a cada 4s (junto do polling).
  O servidor conta IPs distintos ativos nos últimos 45s e o header mostra discreto
  "● N pessoas vendo agora". IP vem de `CF-Connecting-IP` (túnel cloudflared), país de `CF-IPCountry`.
- Ao abrir, o navegador pede permissão de localização (`navigator.geolocation`). Se o visitante
  aceitar, lat/lon (4 casas, ~11 m) vão uma vez no heartbeat. Recusar não quebra nada.
- Clicar em "● N pessoas vendo agora" abre um modal com mapa (Leaflet + OpenStreetMap, carregado sob demanda)
  e um marcador piscando por pessoa que autorizou a localização; a lista atualiza sozinha a cada heartbeat.
  O mapa nunca mostra IP: só país, coordenada e há quanto tempo a pessoa entrou.
  Navegação: ‹ Anterior / Próxima › (ou setas do teclado) voa até cada pessoa com localização; clicar na linha
  da lista ou no marcador também foca; "Ver todos" volta a enquadrar todo mundo. Mapa tem altura fixa e a
  lista rola embaixo, então muita gente não espreme o mapa.
- Evidência de quem respondeu: cada resposta (`answers.json`), dúvida (`questions.json`) e réplica ao
  assistente (`followups.json`, turnos `user`) grava `evidence: {ip, country, ua, lat, lon, acc}`.
  A coordenada vem do próprio envio (se autorizou); senão da última presença daquele IP (`geo_from: "presenca"`).
  Os GETs de `/api/answers` e `/api/followups` removem `evidence` antes de mandar pro navegador.
- Quem está/esteve online: `cat <workdir>/presence.json` (ip, país, lat/lon/acc, first/last).
  É dado pessoal — não compartilhar o arquivo; apagar ao encerrar o wizard.

### 2.0.1 Avisos ao vivo (sem F5)

- Polling de 4s já traz perguntas novas do assistente (`agent_followup.py ask`) e respostas de dúvidas;
  a tela re-renderiza sozinha preservando o que estiver digitado. Ao voltar pra aba, atualiza na hora.
- Revisão lista as perguntas do assistente com caixa de resposta no topo.
- Título da aba vira `(N) ...` com perguntas esperando resposta.
- Botão "Avisar-me" no header pede permissão de notificação do sistema (só aparece se ainda não decidida).
  Com permissão, cada pergunta/resposta nova dispara notificação nativa (fora do navegador); clicar abre a decisão.
  Limitação: a aba precisa estar aberta (pode estar em segundo plano/minimizada). Aba fechada = sem aviso
  (exigiria Web Push + service worker). Android Chrome não aceita `new Notification` sem service worker: lá fica só o título/badge.

### 2.1 Preview do link (thumb no WhatsApp, opcional)

Pra o link colado no WhatsApp/Slack/Teams aparecer com título, subtítulo e
imagem (em vez de "Acesso restrito" sem imagem):

```bash
python3 ~/.claude/skills/decision-wizard/og_image.py spec.json /tmp/meu-wizard revisao \
  [--subtitle "3 decisões rápidas sobre X · ~5 min"]
```

Gera `docs/revisao.og.png` (1200×630, nas cores do wizard) + `docs/revisao.og.json`.
O servidor põe as meta tags `og:*` na tela de senha só desse doc; a imagem
(`/og/revisao.png`) é pública porque o robô do WhatsApp não faz login. Título
e subtítulo ficam visíveis pra quem tiver o link: **sem dado sensível**.
Requer Pillow. O WhatsApp guarda o preview em cache: gere antes de mandar o
link pela primeira vez.

### 3. Subir servidor + tunnel gratuito

```bash
bash ~/.claude/skills/decision-wizard/start.sh /tmp/meu-wizard
```

Imprime `URL=https://xxxx.trycloudflare.com` e `PASSWORD=<senha gerada>`.
Mande pra pessoa: `<URL>/?doc=revisao` + a senha (canal separado — nunca a
mesma mensagem que leva a URL, se possível). A senha é gerada nova a cada
execução e só existe em memória/stdout desse comando — nunca é gravada em
arquivo, HTML, JS ou log em texto puro (só o hash SHA-256 vai pro processo do
servidor).

### 4. Esperar respostas sem travar o chat

Use `ScheduleWakeup` (loop) ou `Monitor` (ex.: `tail -f
/tmp/meu-wizard/questions.log`) pra ser avisado quando a pessoa responder uma
decisão (`/tmp/meu-wizard/answers.json`) ou fizer uma pergunta (`questions.log`
+ `questions.json`). Não faça polling manual em loop apertado — agende.

### 5. Responder perguntas feitas no wizard (sem humano sincrono)

Quando a pessoa usa "Dúvida nessa decisão?" no wizard, a pergunta cai em
`questions.json` (answer: null). Você (Claude, com o contexto da sua própria
análise) responde direto:

```bash
python3 ~/.claude/skills/decision-wizard/answer_questions.py list /tmp/meu-wizard/questions.json
python3 ~/.claude/skills/decision-wizard/answer_questions.py answer /tmp/meu-wizard/questions.json <qid> "resposta"
```

O wizard já faz polling automático (`askWidget`) e mostra a resposta pra pessoa
em até ~4s, sem reload.

### 6. Followups (agente pergunta, usuário responde)

Contrário do fluxo de dúvida (usuário pergunta, agente responde): aqui é o
agente que, ao revisar uma resposta em texto livre, precisa de mais
detalhe. Suporta múltiplas rodadas (thread de turnos).

```bash
# Claude abre um followup sobre a resposta livre da decisão s3-D4
python3 agent_followup.py ask followups.json meu-doc s3-D4 "Qual biblioteca voce usou pra isso?"

# Claude lista o que está esperando o usuário responder
python3 agent_followup.py list followups.json meu-doc --waiting-user
```

O usuário responde pelo próprio wizard (painel da decisão). O servidor expõe:
- `GET /api/followups?doc=<doc>` — lista as threads do doc
- `POST /api/followups/reply` `{"id", "text"}` (com `?doc=<doc>` na query) —
  acrescenta o turno do usuário

```bash
curl -b cookies.txt "https://<tunnel>/api/followups?doc=meu-doc"
curl -b cookies.txt -X POST -d '{"id":"<fid>","text":"usei o pacote X"}' \
  "https://<tunnel>/api/followups/reply?doc=meu-doc"
```

A badge "Esperando você" no header do wizard e o card no overview aparecem
sozinhos (o client faz polling de `/api/followups` a cada ~4s), sem precisar
de F5.

### 7. Encerrar

```bash
kill "$(cat /tmp/meu-wizard/server.pid)" "$(cat /tmp/meu-wizard/tunnel.pid)"
```

## Segurança (obrigatório respeitar)

- Senha real **nunca** em texto puro em HTML/JS/JSON/log — só
  `ARTIFACT_PASSWORD_SHA256` valida com `hmac.compare_digest`.
- Sessão via cookie `HttpOnly; Secure; SameSite=Strict` assinado por HMAC com
  expiração (12h default).
- Toda mutação (`/api/answers`, `/api/question`) é `POST`, nunca `GET`.
- Escritas em `answers.json`/`questions.json` são atômicas (`.tmp` +
  `os.replace`).

## Arquivos da skill

| Arquivo | Papel |
|---|---|
| `generate_wizard.py` | JSON de decisões → HTML compatível com `answers.js` |
| `theme_diagram.py` | Aplica a paleta do wizard num diagrama HTML do archify |
| `generate_audio.py` | Gera 1 mp3 narrado por decisão (TTS) e grava `audioFiles` no spec |
| `og_image.py` | Gera thumb + título/subtítulo do preview do link (WhatsApp) |
| `answer_questions.py` | Lista/responde perguntas feitas no `askWidget` |
| `agent_followup.py` | CLI de followups: `ask` (abre pergunta), `list` (mostra threads esperando resposta do usuário) |
| `server.py` | Servidor standalone (login, docs protegidos, diagramas em `diagrams/`, API de respostas) — copiado pra pasta de trabalho pelo `start.sh` |
| `answers.js` | Client do wizard (navegação decisão-por-decisão, A/B/C, pergunta livre, `askWidget`, polling de followups) — genérico, não precisa editar |
| `wizard.css` | Estilos Modernist (design clean, dark/light) — copiado pra pasta de trabalho pelo `start.sh` |
| `wizard-core.js` | Helpers puros (árvore Mermaid, spec, followups) — testável isolado com `node test_wizard_core.js` |
| `start.sh` | Sobe servidor local + tunnel `cloudflared` gratuito, imprime URL+senha |

## Self-check

```bash
python3 ~/.claude/skills/decision-wizard/generate_wizard.py --selfcheck
```
