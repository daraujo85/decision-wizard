// wizard-core.js — pure logic, no DOM. Browser: window.WizardCore. Node: require("./wizard-core.js").
(function (root) {
  "use strict";

  function flattenSpec(spec) {
    var out = [];
    spec.sections.forEach(function (sec) {
      sec.decisions.forEach(function (dec) {
        var optionPlain = dec.optionPlain || {};
        var optionBadge = dec.optionBadge || {};
        var audio = dec.audioFiles || {};
        var opts = Object.keys(dec.options).map(function (k) {
          return { id: k, title: dec.options[k], plain: optionPlain[k] || "", badge: optionBadge[k] || "" };
        });
        out.push({
          key: sec.id + "-" + dec.tag, id: dec.tag, section: sec.key,
          kicker: sec.key + " · " + sec.title, question: dec.question,
          context: dec.context || "", plain: dec.plain || "", tech: dec.tech || "",
          diagram: dec.diagram || "", diagramCaption: dec.diagramCaption || "",
          audio: audio.question || "", options: opts
        });
      });
    });
    return out;
  }

  function clean(t) { return String(t).replace(/["<>{}|;#%]/g, "").replace(/\s+/g, " ").trim(); }
  function cut(t, n) { var s = clean(t); return s.length > n ? s.slice(0, n - 1).trim() + "…" : s; }

  var MERMAID_HEADER = "%%{init:{'theme':'base','themeVariables':{'fontFamily':'Archivo, sans-serif','fontSize':'13px','lineColor':'#7d7979','primaryColor':'#eae9e9','primaryTextColor':'#201e1d','primaryBorderColor':'#201e1d'},'flowchart':{'curve':'linear','nodeSpacing':14,'rankSpacing':28,'padding':6,'useMaxWidth':false}}}%%\n";
  var CLASS_DEFS = [
    "classDef root fill:#201e1d,stroke:#201e1d,color:#f3f2f2",
    "classDef dec fill:#eae9e9,stroke:#201e1d,stroke-width:2px,color:#201e1d",
    "classDef cur fill:#201e1d,stroke:#201e1d,stroke-width:2px,color:#f3f2f2",
    "classDef opt fill:#f8f4f4,stroke:#bab6b6,color:#605d5d",
    "classDef chosen fill:#ec3013,stroke:#ec3013,color:#f3f2f2"
  ].join("\n");

  function findOption(decision, optId) {
    for (var i = 0; i < decision.options.length; i++) if (decision.options[i].id === optId) return decision.options[i];
    return null;
  }

  function buildTree(decisions, answers, title, compact, currentKey) {
    var lines = ["flowchart LR", 'T["' + clean(title) + '"]:::root'];
    decisions.forEach(function (d) {
      var isCurrent = d.key === currentKey;
      lines.push(d.id + '["' + d.id + " · " + cut(d.question, compact ? 30 : 70) + '"]:::' + (isCurrent ? "cur" : "dec"));
      lines.push("T --> " + d.id);
      var ans = answers[d.key];
      d.options.forEach(function (o, j) {
        var nid = d.id + "o" + j;
        var chosen = ans && ans.option === o.id;
        lines.push(nid + '["' + String.fromCharCode(65 + j) + " · " + cut(o.title, compact ? 26 : 40) + '"]:::' + (chosen ? "chosen" : "opt"));
        lines.push(d.id + " --> " + nid);
      });
      if (ans && ans.option === "other") {
        lines.push(d.id + 'free["Resposta livre"]:::chosen');
        lines.push(d.id + " --> " + d.id + "free");
      }
    });
    lines.push(CLASS_DEFS);
    return MERMAID_HEADER + lines.join("\n");
  }

  function buildPath(decisions, answers, title, narrow) {
    var lines = ["flowchart TB", 'T["' + clean(title) + '"]:::root'];
    var prev = "T";
    decisions.forEach(function (d) {
      var ans = answers[d.key];
      lines.push(d.id + '["' + d.id + " · " + cut(d.question, narrow ? 34 : 60) + '"]:::dec');
      lines.push(prev + " --> " + d.id);
      var raw = !ans ? "Em aberto" : ans.option === "other" ? "Resposta livre" : ((findOption(d, ans.option) || {}).title || "");
      var nid = d.id + "c";
      lines.push(nid + '["' + clean(cut(raw, narrow ? 30 : 44)) + '"]:::' + (ans ? "chosen" : "opt"));
      lines.push(d.id + " --> " + nid);
      prev = nid;
    });
    lines.push(CLASS_DEFS);
    return MERMAID_HEADER + lines.join("\n");
  }

  function answeredCount(answers) { return Object.keys(answers).length; }

  function waitingFollowups(followups) {
    return Object.keys(followups).filter(function (id) {
      var turns = followups[id].turns || [];
      return turns.length > 0 && turns[turns.length - 1].role === "agent";
    });
  }

  var WizardCore = {
    flattenSpec: flattenSpec, clean: clean, cut: cut,
    buildTree: buildTree, buildPath: buildPath,
    answeredCount: answeredCount, waitingFollowups: waitingFollowups
  };

  if (typeof module !== "undefined" && module.exports) module.exports = WizardCore;
  else root.WizardCore = WizardCore;
})(typeof window !== "undefined" ? window : this);
