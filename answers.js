// answers.js — client do decision-wizard. Le SPEC embutido, busca estado real do server, renderiza 3 views.
(function () {
  "use strict";
  var WC = window.WizardCore;
  var DOC = new URLSearchParams(location.search).get("doc") || document.body.dataset.doc || "";
  var api = function (path) { return path + (path.indexOf("?") === -1 ? "?" : "&") + "doc=" + encodeURIComponent(DOC); };

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    for (var k in attrs || {}) {
      if (k === "text") node.textContent = attrs[k];
      else if (k === "html") node.innerHTML = attrs[k];
      else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
      else if (attrs[k] === false || attrs[k] == null) continue;
      else node.setAttribute(k, attrs[k] === true ? "true" : attrs[k]);
    }
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  var decisions = WC.flattenSpec(SPEC);
  var state = { view: "overview", idx: 0, answers: {}, followups: {}, threads: {}, treeOpen: false, repaintChat: null, online: 0, people: [], repaintMap: null, geo: null, geoSent: false };

  function fetchJSON(path, opts) {
    return fetch(path, opts).then(function (r) {
      if (r.status === 401) { location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search); return Promise.reject("unauthorized"); }
      return r.json().then(function (body) {
        if (!r.ok) return Promise.reject((body && body.error) || r.status);
        return body;
      });
    });
  }

  // every renderer reads .option; server (and the optimistic write below) only knows .choice
  function mirrorOptions() {
    Object.keys(state.answers).forEach(function (k) { state.answers[k].option = state.answers[k].choice; });
  }

  function loadAnswers() { return fetchJSON(api("/api/answers")).then(function (data) { state.answers = data || {}; mirrorOptions(); }); }

  function saveAnswer(decisionKey, choice, text) {
    return fetchJSON(api("/api/answers"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: decisionKey, choice: choice, text: text, geo: state.geo }),
    }).then(function () {
      if (choice === null) { delete state.answers[decisionKey]; return; }
      state.answers[decisionKey] = { choice: choice, text: text, ts: new Date().toISOString() };
      mirrorOptions();
    }).catch(function (err) { alert("Não foi possível salvar a resposta: " + err); });
  }

  var root = document.getElementById("wizard-root");

  function setView(view, idx) {
    state.view = view;
    state.treeOpen = false;
    if (typeof idx === "number") state.idx = idx;
    render();
  }

  function renderHeader() {
    var waitingCount = WC.waitingFollowups(state.followups).length;
    return el("header", { class: "wz-header" }, [
      el("div", { class: "wz-header-inner" }, [
        el("div", { class: "wz-header-title" }, [
          el("div", { class: "wz-eyebrow" }, [
            document.createTextNode(DOC || "wizard"),
            el("button", { class: "wz-presence", hidden: !state.online, title: "Ver no mapa onde estão as pessoas com esta página aberta", text: presenceText(), onClick: openPresenceMap }),
          ]),
          el("div", { class: "wz-titletext", text: SPEC.title }),
        ]),
        el("nav", { class: "wz-tabs" }, [
          el("button", { class: "wz-tab", "aria-current": state.view === "overview", onClick: function () { setView("overview"); } }, [document.createTextNode("Visão geral")]),
          el("button", { class: "wz-tab", "aria-current": state.view === "decision", onClick: function () { setView("decision", state.idx); } }, [document.createTextNode("Decisões")]),
          el("button", { class: "wz-tab", "aria-current": state.view === "review", onClick: function () { setView("review"); } }, [document.createTextNode("Revisão")]),
        ]),
        el("button", { class: "wz-badge-waiting", hidden: waitingCount === 0, onClick: function () { setView("decision", firstWaitingIdx()); } }, [document.createTextNode("Esperando você · " + waitingCount)]),
        notifyButton(),
        el("button", { class: "wz-btn wz-btn-secondary wz-map-btn", text: "Ver mapa", "aria-pressed": state.treeOpen, onClick: function () { state.treeOpen = !state.treeOpen; render(); } }),
      ]),
    ]);
  }

  // --- avisos: notificacao do sistema (fora do navegador) + contador no titulo da aba ---
  var BASE_TITLE = document.title;
  var seenTurns = null; // {chave: true} do que ja foi avisado; null = primeira carga, nao avisa o que ja existia

  function notifySupported() { return "Notification" in window && window.isSecureContext; }

  function notifyButton() {
    if (!notifySupported() || Notification.permission !== "default") return null;
    return el("button", {
      class: "wz-btn wz-btn-secondary wz-notify-btn", title: "Receber aviso no computador/celular quando o assistente perguntar algo",
      onClick: function () { Notification.requestPermission().then(function () { render(); }); },
    }, [bellIcon(), document.createTextNode("Avisar-me")]);
  }

  function bellIcon() {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", "wz-icon"); svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>';
    return svg;
  }

  // o que merece aviso: pergunta do assistente esperando voce + resposta do assistente pra sua duvida
  function pendingAlerts() {
    var out = [];
    WC.waitingFollowups(state.followups).forEach(function (fid) {
      var f = state.followups[fid], turns = f.turns || [];
      var d = decisions.filter(function (x) { return x.key === f.decision; })[0];
      out.push({ key: "f:" + fid + ":" + turns.length, tag: "f:" + fid, title: "O assistente tem uma dúvida" + (d ? " sobre " + d.id : ""),
                 body: turns[turns.length - 1].text, idx: d ? decisions.indexOf(d) : state.idx });
    });
    Object.keys(state.threads).forEach(function (qid) {
      var t = state.threads[qid];
      if (t.answer) out.push({ key: "q:" + qid, tag: "q:" + qid, title: "Sua dúvida foi respondida", body: t.answer, idx: null, decision: t.decision });
    });
    return out;
  }

  function checkAlerts() {
    var alerts = pendingAlerts();
    var waiting = WC.waitingFollowups(state.followups).length;
    document.title = (waiting ? "(" + waiting + ") " : "") + BASE_TITLE;
    var first = seenTurns === null;
    seenTurns = seenTurns || {};
    alerts.forEach(function (a) {
      if (seenTurns[a.key]) return;
      seenTurns[a.key] = true;
      if (first || !notifySupported() || Notification.permission !== "granted") return;
      try {
        var n = new Notification(a.title, { body: WC.cut(a.body, 140), tag: a.tag, icon: "/favicon.svg" });
        n.onclick = function () {
          window.focus();
          if (a.idx !== null) setView("decision", a.idx);
          n.close();
        };
      } catch (e) { /* Android Chrome exige service worker pra Notification: fica so o titulo/badge */ }
    });
  }

  function firstWaitingIdx() {
    var waitingKeys = {};
    WC.waitingFollowups(state.followups).forEach(function (fid) { waitingKeys[state.followups[fid].decision] = true; });
    for (var i = 0; i < decisions.length; i++) if (waitingKeys[decisions[i].key]) return i;
    return state.idx;
  }

  function renderOverview() {
    var answered = WC.answeredCount(state.answers);
    var waiting = WC.waitingFollowups(state.followups).length;
    var openDoubts = Object.keys(state.threads).filter(function (id) { return state.threads[id].pending; }).length;
    var sections = {};
    decisions.forEach(function (d) { sections[d.section] = true; });

    var pct = Math.round((100 * answered) / decisions.length);
    var stats = [["Assuntos", Object.keys(sections).length], ["Dúvidas abertas", openDoubts], ["Esperando você", waiting]];

    // mesma "carinha" da tela de pergunta: cartao, progresso com %, opcoes em cartoes clicaveis
    var box = el("div", { class: "wz-decision wz-home" }, [
      el("div", { class: "wz-kicker" }, [el("span", { text: "Decisões para você revisar" }), el("span", { text: decisions.length + " decisões" })]),
      el("h1", { class: "wz-question wz-home-title", text: SPEC.title }),
      el("div", { class: "wz-home-progress" }, [
        el("div", { class: "wz-progress", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct) }, [
          el("div", { class: "wz-progress-bar", style: "width:" + pct + "%" }),
        ]),
        el("div", { class: "wz-progress-label" }, [el("strong", { text: pct + "%" }), el("span", { text: answered + " de " + decisions.length + " respondidas" })]),
      ]),
      el("div", { class: "wz-home-stats" }, stats.map(function (m) {
        return el("span", { class: "wz-home-stat" + (m[0] === "Esperando você" && m[1] > 0 ? " wz-home-stat-alert" : "") }, [el("strong", { text: String(m[1]) }), document.createTextNode(" " + m[0])]);
      })),
    ]);

    if (waiting > 0) {
      box.appendChild(el("div", { class: "wz-waiting-card" }, [
        el("strong", { text: waiting + " pergunta(s) esperando sua resposta" }),
        el("div", {}, [el("button", { class: "wz-btn wz-btn-primary", onClick: function () { setView("decision", firstWaitingIdx()); }, text: "Responder agora" })]),
      ]));
    }

    var list = el("ul", { class: "wz-options", style: "--n:" + Math.min(decisions.length, 3) }, []);
    decisions.forEach(function (d, i) {
      var done = !!state.answers[d.key];
      list.appendChild(el("li", {}, [el("button", {
        class: "wz-option" + (done ? " wz-option-selected" : ""), onClick: function () { setView("decision", i); },
      }, [
        el("span", { class: "wz-option-letter wz-home-id", text: d.id }),
        el("span", { class: "wz-option-body" }, [
          el("div", { class: "wz-option-title", text: d.question }),
          el("div", { class: "wz-option-detail", text: d.kicker }),
          el("div", { class: "wz-option-badge" + (done ? "" : " wz-badge-open"), text: done ? "Respondida · " + answerLabel(d) : "Em aberto" }),
        ]),
      ])]));
    });
    box.appendChild(list);
    box.appendChild(el("button", {
      class: "wz-btn wz-btn-primary wz-home-cta", text: answered === decisions.length ? "Revisar respostas" : answered > 0 ? "Continuar respondendo" : "Começar",
      onClick: function () { if (answered === decisions.length) setView("review"); else setView("decision", firstUnansweredIdx()); },
    }));

    var tree = el("div", { class: "mermaid wz-overview-tree" }, []);
    var mapBox = el("section", { class: "wz-home-map" }, [
      el("div", { class: "wz-kicker" }, [el("span", { text: "Mapa de todas as decisões" })]),
      tree, renderTreeLegend(),
    ]);
    root.appendChild(box);
    root.appendChild(mapBox);
    renderMermaidInto(tree, WC.buildTree(decisions, state.answers, SPEC.title, true, null));
  }

  function firstUnansweredIdx() {
    for (var i = 0; i < decisions.length; i++) if (!state.answers[decisions[i].key]) return i;
    return 0;
  }

  // um player so: tocar outro audio (ou o mesmo de novo) para o anterior
  var player = { audio: null, btn: null, name: "" };
  // icones em traco (currentColor) no lugar de emoji: seguem cor/tema do botao. Strings fixas, sem dado do usuario.
  var ICON_SPEAKER = '<svg class="wz-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>';
  var ICON_STOP = '<svg class="wz-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="1.5"/></svg>';
  function setAudioLabel(btn, playing) {
    btn.innerHTML = (playing ? ICON_STOP : ICON_SPEAKER) + "<span>" + (playing ? "Parar" : "Ouvir") + "</span>";
    btn.setAttribute("aria-pressed", playing ? "true" : "false");
  }
  function stopAudio() {
    if (player.audio) player.audio.pause();
    if (player.btn) setAudioLabel(player.btn, false);
    player.audio = null; player.btn = null; player.name = "";
  }
  // polling re-renderiza a tela a cada mudanca: se o audio ainda esta na tela, so troca o botao em vez de parar
  function reattachAudio() {
    if (!player.audio) return;
    var btn = root.querySelector('.wz-audio-btn[data-audio="' + player.name + '"]');
    if (!btn) { stopAudio(); return; }
    player.btn = btn;
    setAudioLabel(btn, true);
  }
  function audioButton(name, label) {
    var btn = el("button", { class: "wz-audio-btn", "aria-label": label, "data-audio": name });
    setAudioLabel(btn, false);
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var same = player.btn === btn;
      stopAudio();
      if (same) return;
      var audio = new Audio("/audio/" + encodeURIComponent(name) + ".mp3");
      player.audio = audio; player.btn = btn; player.name = name;
      setAudioLabel(btn, true);
      audio.addEventListener("ended", stopAudio);
      audio.play().catch(function () { stopAudio(); alert("Não foi possível tocar o áudio."); });
    });
    return btn;
  }

  function closeDiagramFull() {
    document.querySelectorAll(".wz-diagram-full").forEach(function (n) { n.remove(); });
    document.removeEventListener("keydown", onDiagramKey);
  }
  function onDiagramKey(e) { if (e.key === "Escape") closeDiagramFull(); }
  function openDiagramFull(src, title) {
    closeDiagramFull();
    document.body.appendChild(el("div", { class: "wz-diagram-full", role: "dialog", "aria-label": title }, [
      el("div", { class: "wz-diagram-full-bar" }, [
        el("strong", { text: title }),
        el("a", { class: "wz-btn", href: src, target: "_blank", rel: "noopener", text: "Abrir em nova aba ↗" }),
        el("button", { class: "wz-btn wz-btn-primary", text: "× Fechar (Esc)", onClick: closeDiagramFull }),
      ]),
      el("iframe", { src: src, title: title }),
    ]));
    document.addEventListener("keydown", onDiagramKey);
  }

  function renderOptionRow(d, opt, letter) {
    var ans = state.answers[d.key];
    var selected = ans && ans.option === opt.id;
    var body = [el("div", { class: "wz-option-title", text: opt.title })];
    if (opt.badge) body.push(el("div", { class: "wz-option-badge", text: opt.badge }));
    if (opt.plain) body.push(el("div", { class: "wz-option-detail", text: opt.plain }));
    return el("button", { class: "wz-option" + (selected ? " wz-option-selected" : ""), "aria-pressed": selected, onClick: function () { saveAnswer(d.key, selected ? null : opt.id, null).then(render); } }, [
      el("span", { class: "wz-option-letter", text: letter }),
      el("div", { class: "wz-option-body" }, body),
    ]);
  }

  function renderFreeOption(d) {
    var ans = state.answers[d.key];
    var isFree = ans && ans.option === "other";
    var wrap = el("div", { class: "wz-option" + (isFree ? " wz-option-selected" : ""), "aria-pressed": isFree }, []);
    var textarea = el("textarea", { class: "wz-free-textarea", placeholder: "Escreva sua resposta...", rows: 3 });
    if (isFree) textarea.value = ans.text || "";
    wrap.appendChild(el("span", { class: "wz-option-letter", text: "✎" }));
    var body = el("div", { class: "wz-option-body" }, [el("div", { class: "wz-option-title", text: "Escrever minha resposta" }), textarea,
      el("button", { class: "wz-btn wz-save-btn", text: "Salvar", onClick: function (e) { e.stopPropagation(); saveAnswer(d.key, "other", textarea.value).then(render); } })]);
    wrap.appendChild(body);
    return wrap;
  }

  function renderDecision() {
    var d = decisions[state.idx];
    var box = el("div", { class: "wz-decision" }, [
      renderCrumbs(),
      el("div", { class: "wz-kicker" }, [el("span", { text: d.kicker }), el("span", { text: (state.idx + 1) + " / " + decisions.length })]),
      el("h2", { class: "wz-question", text: d.question }),
    ]);
    if (d.audio) box.appendChild(audioButton(d.audio, "Ouvir a pergunta e as opções"));
    if (d.context) box.appendChild(el("div", { class: "wz-context", text: d.context }));
    if (d.plain) {
      var tip = el("div", { class: "wz-tip-box", hidden: true, text: d.plain });
      box.appendChild(el("button", { class: "wz-tip-btn", text: "Explicar em palavras simples", onClick: function () { tip.hidden = !tip.hidden; } }));
      box.appendChild(tip);
    }
    // diagrama archify (diagrams/<nome>.html) mostra o fluxo afetado antes das opcoes
    if (d.diagram) {
      // theme=light: wizard so tem tema claro; embed=1 esconde barra/cards do archify no quadro pequeno
      var src = "/diagrams/" + encodeURIComponent(d.diagram) + ".html?theme=light";
      var title = d.diagramCaption || "Diagrama da decisão";
      var open = function () { openDiagramFull(src, title); };
      box.appendChild(el("figure", { class: "wz-diagram" }, [
        el("div", { class: "wz-diagram-head" }, [
          el("figcaption", { text: d.diagramCaption || "Diagrama do fluxo" }),
          el("button", { class: "wz-btn wz-btn-primary wz-diagram-full-btn", text: "⛶ Ver em tela cheia", onClick: open }),
        ]),
        // iframe engole o clique; a camada por cima leva pra tela cheia
        el("div", { class: "wz-diagram-frame" }, [
          el("iframe", { src: src + "&embed=1", title: title, loading: "lazy", tabindex: "-1" }),
          el("button", { class: "wz-diagram-hit", "aria-label": "Ver diagrama em tela cheia", onClick: open }, [
            el("span", { text: "⛶ Clique para ampliar" }),
          ]),
        ]),
      ]));
    }
    // detalhe tecnico fica recolhido: quem e de negocio decide sem ler jargao
    if (d.tech) {
      box.appendChild(el("details", { class: "wz-tech" }, [el("summary", { text: "Detalhe técnico (opcional)" }), el("div", { text: d.tech })]));
    }
    var followupBox = el("div", {}, []);
    box.appendChild(followupBox);
    renderFollowupsFor(followupBox, d);

    // --n = colunas: uma por opcao (ate 4); a linha "escrever minha resposta" ocupa a largura toda
    var list = el("ul", { class: "wz-options", style: "--n:" + Math.min(d.options.length, 4) }, []);
    d.options.forEach(function (opt, i) { list.appendChild(el("li", {}, [renderOptionRow(d, opt, String.fromCharCode(65 + i))])); });
    list.appendChild(el("li", {}, [renderFreeOption(d)]));
    box.appendChild(list);
    box.appendChild(el("button", { class: "wz-doubt-link", text: "Tenho uma dúvida nesta decisão", onClick: function () { openDoubtChat(d); } }));
    root.appendChild(box);
    root.appendChild(renderTreeBottom());
    root.appendChild(renderFooter());
  }

  // trilha "Início › D1: resposta › D2: resposta › D3 (agora)": mostra o caminho ja feito sem tirar o foco da pergunta
  function answerLabel(d) {
    var ans = state.answers[d.key];
    if (!ans) return "em aberto";
    if (ans.option === "other") return "resposta própria";
    var j = d.options.findIndex(function (o) { return o.id === ans.option; });
    return j < 0 ? "em aberto" : String.fromCharCode(65 + j) + " · " + WC.cut(d.options[j].title, 28);
  }

  function renderCrumbs() {
    var nav = el("nav", { class: "wz-crumbs", "aria-label": "Caminho percorrido" }, []);
    var ol = el("ol", {}, [el("li", {}, [el("button", { class: "wz-crumb", text: "Início", onClick: function () { setView("overview"); } })])]);
    decisions.slice(0, state.idx).forEach(function (d, i) {
      var answered = !!state.answers[d.key];
      ol.appendChild(el("li", {}, [el("button", {
        class: "wz-crumb" + (answered ? " wz-crumb-done" : " wz-crumb-open"), title: d.question,
        onClick: function () { setView("decision", i); },
      }, [el("strong", { text: d.id }), document.createTextNode(" " + answerLabel(d))])]));
    });
    ol.appendChild(el("li", {}, [el("span", { class: "wz-crumb wz-crumb-current", "aria-current": "step" }, [el("strong", { text: decisions[state.idx].id }), document.createTextNode(" agora")])]));
    nav.appendChild(ol);
    return nav;
  }

  // mapa completo fica no fim, recolhido: quem quiser ver rola e abre
  function renderTreeBottom() {
    var tree = el("div", { class: "mermaid" }, []);
    var drawn = false;
    var box = el("details", { class: "wz-tree-bottom" }, [el("summary", { text: "Ver mapa de todas as decisões" }), tree, renderTreeLegend()]);
    box.addEventListener("toggle", function () {
      if (box.open && !drawn) { drawn = true; renderMermaidInto(tree, WC.buildTree(decisions, state.answers, SPEC.title, true, decisions[state.idx].key)); }
    });
    return box;
  }

  function renderFooter() {
    // barra mede o que ja foi respondido (nao a posicao): pular decisao nao infla o progresso
    var done = decisions.filter(function (d) { return state.answers[d.key]; }).length;
    var pct = Math.round((100 * done) / decisions.length);
    return el("div", { class: "wz-footer" }, [
      el("button", { class: "wz-btn", text: "Anterior", disabled: state.idx === 0, onClick: function () { setView("decision", state.idx - 1); } }),
      el("div", { class: "wz-progress-wrap" }, [
        el("div", { class: "wz-progress", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct) }, [
          el("div", { class: "wz-progress-bar", style: "width:" + pct + "%" }),
        ]),
        el("div", { class: "wz-progress-label" }, [
          el("strong", { text: pct + "%" }),
          el("span", { text: done + " de " + decisions.length + " respondidas" }),
        ]),
      ]),
      el("button", { class: "wz-btn wz-btn-primary", text: state.idx === decisions.length - 1 ? "Ir pra revisão" : "Próxima", onClick: function () {
        if (state.idx === decisions.length - 1) setView("review"); else setView("decision", state.idx + 1);
      } }),
    ]);
  }

  function renderReview() {
    var container = el("div", {}, [el("h1", { text: "Revisão" })]);
    // perguntas do assistente aparecem aqui tambem: quem esta na revisao responde sem trocar de tela
    var withFollowups = decisions.filter(function (d) {
      return Object.keys(state.followups).some(function (fid) { return state.followups[fid].decision === d.key; });
    });
    if (withFollowups.length) {
      var ask = el("section", { class: "wz-review-followups" }, [el("div", { class: "wz-kicker", text: "Perguntas do assistente sobre suas respostas" })]);
      withFollowups.forEach(function (d) {
        ask.appendChild(el("div", { class: "wz-review-followup-q", text: d.id + " · " + d.question }));
        renderFollowupsFor(ask, d);
      });
      container.appendChild(ask);
    }
    var tree = el("div", { class: "mermaid" }, []);
    container.appendChild(tree);
    decisions.forEach(function (d, i) {
      var ans = state.answers[d.key];
      var row = el("div", { class: "wz-review-row" }, [el("div", {}, [document.createTextNode(d.kicker + " — " + d.question)])]);
      var chips = el("div", {}, []);
      d.options.forEach(function (opt, j) {
        var letter = String.fromCharCode(65 + j);
        chips.appendChild(el("button", { class: "wz-chip", "aria-selected": ans && ans.option === opt.id, text: letter, onClick: function () { saveAnswer(d.key, opt.id, null).then(render); } }));
      });
      chips.appendChild(el("button", { class: "wz-chip", "aria-selected": ans && ans.option === "other", text: "Outra", onClick: function () { setView("decision", i); } }));
      row.appendChild(chips);
      container.appendChild(row);
    });
    container.appendChild(el("button", {
      class: "wz-btn wz-btn-primary", text: "Copiar minhas respostas",
      onClick: function () {
        navigator.clipboard.writeText(JSON.stringify(state.answers, null, 2)).catch(function () { alert("Não foi possível copiar para a área de transferência."); });
      },
    }));
    root.appendChild(container);
    renderMermaidInto(tree, WC.buildPath(decisions, state.answers, SPEC.title, window.innerWidth < 760));
  }

  var mermaidSeq = 0;
  function renderMermaidInto(node, source) {
    var id = "mm" + (mermaidSeq++);
    node.id = id;
    if (window.mermaid) window.mermaid.render(id + "-svg", source).then(function (r) { node.innerHTML = r.svg; });
  }

  function renderTreeLegend() {
    return el("div", { class: "wz-tree-legend" }, [
      el("span", { text: "● Atual" }), el("span", { text: "● Respondida" }), el("span", { text: "○ Em aberto" }),
    ]);
  }

  function renderTreeOverlay() {
    var tree = el("div", { class: "mermaid" }, []);
    var panel = el("div", { class: "wz-tree-overlay-panel", onClick: function (e) { e.stopPropagation(); } }, [tree, renderTreeLegend()]);
    var overlay = el("div", { class: "wz-tree-overlay", onClick: function () { state.treeOpen = false; render(); } }, [panel]);
    renderMermaidInto(tree, WC.buildTree(decisions, state.answers, SPEC.title, true, state.view === "decision" ? decisions[state.idx].key : null));
    return overlay;
  }

  function render() {
    root.innerHTML = "";
    root.appendChild(renderHeader());
    var main = el("div", { class: "wz-main" }, []);
    var content = el("div", { class: "wz-content" }, []);
    main.appendChild(content);
    root.appendChild(main);
    var prevRoot = root; // renderOverview/renderDecision/renderReview append straight to root below
    root = content;
    if (state.view === "overview") renderOverview();
    else if (state.view === "decision") renderDecision();
    else renderReview();
    root = prevRoot;
    if (state.treeOpen) root.appendChild(renderTreeOverlay());
    reattachAudio(); // trocou de decisao/tela: para; mesma decisao: continua tocando
  }

  function loadFollowups() {
    return fetchJSON(api("/api/followups")).then(function (list) {
      state.followups = {};
      (list || []).forEach(function (f) { state.followups[f.id] = f; });
    });
  }

  function replyFollowup(fid, text) {
    return fetchJSON(api("/api/followups/reply"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: fid, text: text, geo: state.geo }),
    }).then(loadFollowups).then(render).catch(function (err) { alert("Não foi possível enviar a resposta: " + err); });
  }

  function renderFollowupsFor(container, decision) {
    var mine = Object.keys(state.followups).filter(function (fid) { return state.followups[fid].decision === decision.key; });
    mine.forEach(function (fid) {
      var f = state.followups[fid];
      var box = el("div", { class: "wz-followup" }, []);
      (f.turns || []).forEach(function (t) {
        box.appendChild(el("div", { class: "wz-followup-turn" }, [
          el("div", { class: "wz-followup-role", text: t.role === "agent" ? "Assistente" : "Você" }),
          el("div", { text: t.text }),
        ]));
      });
      var lastTurn = (f.turns || [])[(f.turns || []).length - 1];
      if (lastTurn && lastTurn.role === "agent") {
        var textarea = el("textarea", { rows: 2, placeholder: "Responder..." });
        box.appendChild(el("div", { class: "wz-followup-reply" }, [
          textarea,
          el("button", { class: "wz-btn wz-btn-primary", text: "Enviar", onClick: function () { if (textarea.value.trim()) replyFollowup(fid, textarea.value.trim()); } }),
        ]));
      }
      container.appendChild(box);
    });
  }

  var CHAT_SUGGESTIONS = ["O que muda na prática?", "Qual você recomenda e por quê?", "Isso afeta outra decisão?"];

  function openDoubtChat(decision) {
    var backdrop = el("div", { class: "wz-chat-backdrop", onClick: closeDoubtChat });
    var messages = el("div", { class: "wz-chat-messages" }, []);
    var textarea = el("textarea", { placeholder: "Digite sua dúvida...", onKeydown: function (e) { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") send(); } });

    function paintMessages() {
      messages.innerHTML = "";
      Object.keys(state.threads).forEach(function (qid) {
        var t = state.threads[qid];
        if (t.decision !== decision.key) return;
        messages.appendChild(el("div", { class: "wz-chat-msg wz-chat-msg-user", text: t.text }));
        if (t.answer) messages.appendChild(el("div", { class: "wz-chat-msg", text: t.answer }));
        else messages.appendChild(el("div", { class: "wz-chat-msg", text: "Aguardando resposta do assistente (costuma levar alguns minutos)..." }));
      });
    }

    function send() {
      var text = textarea.value.trim();
      if (!text) return;
      fetchJSON(api("/api/question"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: decision.key, text: text, geo: state.geo }),
      }).then(function (r) {
        state.threads[r.id] = { decision: decision.key, text: text, pending: true, answer: null };
        textarea.value = "";
        paintMessages();
      });
    }

    var panel = el("div", { class: "wz-chat-panel" }, [
      el("div", { class: "wz-chat-header" }, [el("strong", { text: "Dúvida" }), el("button", { class: "wz-btn", text: "×", onClick: closeDoubtChat })]),
      el("div", { class: "wz-chat-suggestions" }, CHAT_SUGGESTIONS.map(function (s) {
        return el("button", { class: "wz-chat-suggestion", text: s, onClick: function () { textarea.value = s; send(); } });
      })),
      messages,
      el("div", { class: "wz-chat-input" }, [textarea, el("button", { class: "wz-btn wz-btn-primary", text: "Enviar", onClick: send })]),
    ]);
    paintMessages();
    state.repaintChat = paintMessages;
    document.body.appendChild(backdrop);
    document.body.appendChild(panel);
  }

  function closeDoubtChat() {
    state.repaintChat = null;
    document.querySelectorAll(".wz-chat-backdrop, .wz-chat-panel").forEach(function (n) { n.remove(); });
  }

  function presenceText() {
    return "● " + state.online + (state.online === 1 ? " pessoa vendo agora" : " pessoas vendo agora");
  }

  // heartbeat: o servidor conta IPs ativos; coordenada so vai se o visitante permitir no navegador
  function sendPresence() {
    var body = state.geo && !state.geoSent ? { geo: state.geo } : {};
    fetchJSON(api("/api/presence"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) {
        if (body.geo) state.geoSent = true;
        state.online = r.online;
        state.people = r.people || [];
        if (state.repaintMap) state.repaintMap();
        // atualiza so o rotulo: re-render inteiro aqui cortaria audio/foco do textarea
        document.querySelectorAll(".wz-presence").forEach(function (n) { n.textContent = presenceText(); n.hidden = !r.online; });
      }).catch(function () {});
  }

  // --- mapa de quem esta vendo: Leaflet + OpenStreetMap, carregado so quando abre ---
  var LEAFLET = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min";
  function loadLeaflet() {
    if (window.L) return Promise.resolve();
    if (loadLeaflet.p) return loadLeaflet.p;
    var css = document.createElement("link"); css.rel = "stylesheet"; css.href = LEAFLET + ".css";
    document.head.appendChild(css);
    loadLeaflet.p = new Promise(function (ok, fail) {
      var js = document.createElement("script"); js.src = LEAFLET + ".js"; js.onload = ok; js.onerror = fail;
      document.head.appendChild(js);
    });
    return loadLeaflet.p;
  }

  function sinceText(sec) { return sec < 60 ? "agora há pouco" : "há " + Math.round(sec / 60) + " min"; }

  function openPresenceMap() {
    var mapBox = el("div", { class: "wz-presence-map" }, []);
    var list = el("ul", { class: "wz-presence-list" }, []);
    var navLabel = el("span", { class: "wz-presence-nav-label" });
    var prevBtn = el("button", { class: "wz-btn wz-btn-secondary", text: "‹ Anterior", "aria-label": "Pessoa anterior", onClick: function () { step(-1); } });
    var nextBtn = el("button", { class: "wz-btn wz-btn-secondary", text: "Próxima ›", "aria-label": "Próxima pessoa", onClick: function () { step(1); } });
    var allBtn = el("button", { class: "wz-btn wz-btn-secondary", text: "Ver todos", onClick: function () { selected = null; fitAll(); paint(); } });
    var nav = el("div", { class: "wz-presence-nav" }, [prevBtn, navLabel, nextBtn, allBtn]);
    var close = function () { state.repaintMap = null; overlay.remove(); document.removeEventListener("keydown", onKey); };
    var onKey = function (e) {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") step(1);
      else if (e.key === "ArrowLeft") step(-1);
    };
    var overlay = el("div", { class: "wz-tree-overlay", onClick: function (e) { if (e.target === overlay) close(); } }, [
      el("div", { class: "wz-tree-overlay-panel wz-presence-panel", role: "dialog", "aria-label": "Quem está vendo agora" }, [
        el("div", { class: "wz-presence-head" }, [
          el("strong", { class: "wz-presence-heading" }),
          el("button", { class: "wz-btn wz-btn-secondary", text: "Fechar", onClick: close }),
        ]),
        nav, mapBox, list,
      ]),
    ]);
    document.body.appendChild(overlay);
    document.addEventListener("keydown", onKey);
    var map = null, layer = null, fitted = false;
    var selected = null; // id da pessoa em foco; null = visao geral

    function located() { return (state.people || []).filter(function (p) { return p.lat != null; }); }
    function label(p) { return p.me ? "Você" : "Pessoa " + ((state.people || []).indexOf(p) + 1); }

    function focus(p) {
      selected = p.id;
      if (map) map.flyTo([p.lat, p.lon], Math.max(map.getZoom(), 13), { duration: 0.8 });
      paint();
    }

    function fitAll() {
      var pts = located().map(function (p) { return [p.lat, p.lon]; });
      if (map && pts.length) map.flyToBounds(pts, { padding: [40, 40], maxZoom: 12, duration: 0.8 });
    }

    // anda em circulo so entre quem tem localizacao (sem coordenada nao ha onde focar)
    function step(dir) {
      var ps = located();
      if (!ps.length) return;
      var i = ps.map(function (p) { return p.id; }).indexOf(selected);
      focus(ps[i === -1 ? (dir > 0 ? 0 : ps.length - 1) : (i + dir + ps.length) % ps.length]);
    }

    function paint() {
      var people = state.people || [];
      var ps = located();
      if (selected && !ps.some(function (p) { return p.id === selected; })) selected = null; // pessoa saiu
      var pos = ps.map(function (p) { return p.id; }).indexOf(selected);
      navLabel.textContent = !ps.length ? "ninguém autorizou a localização"
        : pos === -1 ? ps.length + (ps.length === 1 ? " pessoa no mapa" : " pessoas no mapa")
        : label(ps[pos]) + " · " + (pos + 1) + " de " + ps.length;
      prevBtn.disabled = nextBtn.disabled = ps.length < 2 && pos !== -1 || !ps.length;
      allBtn.hidden = pos === -1;
      overlay.querySelector(".wz-presence-heading").textContent = presenceText().replace("● ", "");
      list.innerHTML = "";
      people.forEach(function (p, i) {
        var where = p.lat != null ? p.lat.toFixed(3) + ", " + p.lon.toFixed(3) + (p.acc ? " (±" + (p.acc > 1000 ? Math.round(p.acc / 1000) + " km" : p.acc + " m") + ")" : "")
                                  : "localização não autorizada";
        var canFocus = p.lat != null;
        list.appendChild(el("li", {}, [
          el(canFocus ? "button" : "div", {
            class: "wz-presence-row" + (p.id === selected ? " wz-presence-row-on" : ""),
            "aria-current": p.id === selected, onClick: canFocus ? function () { focus(p); } : null,
          }, [
            el("span", { class: "wz-presence-pin" + (canFocus ? "" : " wz-presence-pin-off") + (p.me ? " wz-presence-pin-me" : "") }),
            el("strong", { text: label(p) }),
            document.createTextNode(" · " + (p.country || "país ?") + " · " + where + " · entrou " + sinceText(p.since)),
          ]),
        ]));
      });
      if (!map) return;
      layer.clearLayers();
      var pts = [];
      people.forEach(function (p, i) {
        if (p.lat == null) return;
        pts.push([p.lat, p.lon]);
        var icon = window.L.divIcon({ className: "", html: '<span class="wz-blip' + (p.me ? " wz-blip-me" : "") + (p.id === selected ? " wz-blip-on" : "") + '"></span>', iconSize: [18, 18], iconAnchor: [9, 9] });
        var m = window.L.marker([p.lat, p.lon], { icon: icon, zIndexOffset: p.id === selected ? 1000 : 0 })
          .bindTooltip(label(p), { permanent: p.id === selected, direction: "top", offset: [0, -10] })
          .on("click", function () { focus(p); }).addTo(layer);
      });
      // enquadra so na primeira vez com pontos: depois respeita o zoom que a pessoa escolheu
      if (pts.length && !fitted) { fitted = true; map.fitBounds(pts, { padding: [40, 40], maxZoom: 12 }); }
    }

    state.repaintMap = paint;
    paint();
    loadLeaflet().then(function () {
      if (!overlay.isConnected) return;
      map = window.L.map(mapBox, { worldCopyJump: true }).setView([-15, -50], 3);
      window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18, attribution: "&copy; OpenStreetMap",
      }).addTo(map);
      layer = window.L.layerGroup().addTo(map);
      paint();
      setTimeout(function () { map.invalidateSize(); }, 50);
    }).catch(function () { mapBox.textContent = "Não foi possível carregar o mapa."; });
  }

  function askLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(function (pos) {
      state.geo = { lat: pos.coords.latitude, lon: pos.coords.longitude, acc: pos.coords.accuracy };
      sendPresence();
    }, function () {}, { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
  }

  function pollPending() {
    sendPresence();
    var beforeFollowups = JSON.stringify(state.followups);
    var pendingQ = Object.keys(state.threads).filter(function (qid) { return state.threads[qid].pending; });
    var answered = false;
    var work = [loadFollowups()];
    pendingQ.forEach(function (qid) {
      work.push(fetchJSON(api("/api/question/" + qid)).then(function (r) {
        if (r.answer) { state.threads[qid].answer = r.answer; state.threads[qid].pending = false; answered = true; }
      }));
    });
    Promise.all(work).then(function () {
      if (answered && state.repaintChat) state.repaintChat();
      if (answered || JSON.stringify(state.followups) !== beforeFollowups) renderKeepingDrafts();
      checkAlerts();
    });
  }

  // re-render do polling preserva texto digitado (resposta livre, resposta ao assistente) e o foco
  function renderKeepingDrafts() {
    var drafts = [], active = document.activeElement, activeIdx = -1;
    document.querySelectorAll("#wizard-root textarea").forEach(function (t, i) { drafts.push(t.value); if (t === active) activeIdx = i; });
    render();
    var now = document.querySelectorAll("#wizard-root textarea");
    if (now.length !== drafts.length) return; // layout mudou (pergunta nova): nao arrisca colar no lugar errado
    now.forEach(function (t, i) { if (drafts[i] && !t.value) t.value = drafts[i]; });
    if (activeIdx >= 0) now[activeIdx].focus();
  }

  window.__wizardBoot = function () {
    Promise.all([loadAnswers(), loadFollowups()]).then(render).then(checkAlerts).then(sendPresence);
    // aba em segundo plano roda timer devagar; ao voltar pra ela, atualiza na hora
    document.addEventListener("visibilitychange", function () { if (!document.hidden) pollPending(); });
    askLocation();
    setInterval(pollPending, 4000);
  };

  window.__wizardBoot();
})();
