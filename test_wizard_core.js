#!/usr/bin/env node
"use strict";
var assert = require("assert");
var WC = require("./wizard-core.js");

var spec = {
  title: "Teste",
  sections: [{ id: "s1", key: "S1", title: "Secao 1", decisions: [
    { tag: "D1", question: "Pergunta 1?", context: "Contexto", plain: "Explicacao",
      options: { a: "Opcao A", b: "Opcao B", c: "Opcao C" },
      optionPlain: { a: "Explicacao A" }, optionBadge: { b: "novo" } },
    { tag: "D2", question: "Pergunta 2?", options: { a: "X", b: "Y", c: "Z" } }
  ]}]
};

var decisions = WC.flattenSpec(spec);
assert.strictEqual(decisions.length, 2);
assert.strictEqual(decisions[0].key, "s1-D1");
assert.strictEqual(decisions[0].context, "Contexto");
assert.strictEqual(decisions[0].plain, "Explicacao");
assert.strictEqual(decisions[0].options[0].plain, "Explicacao A");
assert.strictEqual(decisions[0].options[1].badge, "novo");
assert.strictEqual(decisions[1].context, "", "campo opcional ausente vira string vazia, sem placeholder");
assert.strictEqual(decisions[1].options[0].badge, "");

var answers = { "s1-D1": { option: "a", ts: "2026-09-18T10:00:00" } };
var tree = WC.buildTree(decisions, answers, spec.title, true, "s1-D2");
assert.ok(tree.indexOf("classDef chosen") !== -1);
assert.ok(tree.indexOf(":::chosen") !== -1, "opcao escolhida marcada");
assert.ok(tree.indexOf(":::cur") !== -1, "decisao atual marcada");

var path = WC.buildPath(decisions, answers, spec.title, false);
assert.ok(path.indexOf("Em aberto") !== -1, "decisao sem resposta aparece como em aberto");
assert.ok(path.indexOf("Opcao A") !== -1);

assert.strictEqual(WC.answeredCount(answers), 1);

var followups = {
  f1: { turns: [{ role: "agent", text: "?" }] },
  f2: { turns: [{ role: "agent", text: "?" }, { role: "user", text: "resp" }] }
};
assert.deepStrictEqual(WC.waitingFollowups(followups), ["f1"], "so threads com ultimo turno do agente aguardam usuario");

console.log("ok");
