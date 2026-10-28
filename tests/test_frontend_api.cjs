"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../frontend/app.js"), "utf8");
const apiSource = source.slice(source.indexOf("async function api("), source.indexOf("function renderMedia("));
function setup(responses, onWait = () => {}) {
  let calls = 0;
  const context = {
    AbortController, DOMException,
    fetch: async () => { calls++; return responses.shift(); },
    setTimeout: (callback, delay) => { if (delay === 1000) queueMicrotask(() => { onWait(); callback(); }); return 1; },
    clearTimeout: () => {},
  };
  vm.createContext(context);
  vm.runInContext(apiSource + ";globalThis.callApi = api", context);
  return { api: context.callApi, calls: () => calls };
}
const busy = () => ({ status: 429, ok: false, json: async () => ({ error: { code: "busy", message: "busy" } }) });
test("info retries a busy worker slot then returns the result", async () => {
  const harness = setup([busy(), { status: 200, ok: true, json: async () => ({ type: "profile" }) }]);
  assert.equal((await harness.api("/info")).type, "profile");
  assert.equal(harness.calls(), 2);
});
test("download creation never retries", async () => {
  const harness = setup([busy()]);
  await assert.rejects(harness.api("/download"), /busy/);
  assert.equal(harness.calls(), 1);
});
test("info access errors never retry", async () => {
  const harness = setup([{ status: 403, ok: false, json: async () => ({ error: { code: "private", message: "private" } }) }]);
  await assert.rejects(harness.api("/info"), /private/);
  assert.equal(harness.calls(), 1);
});
test("cancelling while waiting does not send another request", async () => {
  const controller = new AbortController();
  const harness = setup([busy()], () => controller.abort());
  await assert.rejects(harness.api("/info", { signal: controller.signal }));
  assert.equal(harness.calls(), 1);
});
