/* Reproduces exactly what the worker does, against the running dev server,
   so a browser-only failure shows up here instead of as a silent hang. */
const URL_WASM = "http://localhost:8742/engine/engine.wasm";

const imports = { env: { js_tick: () => {} } };

console.log("1. plain fetch");
const r = await fetch(URL_WASM);
console.log("   status", r.status, "| content-type", r.headers.get("content-type"),
            "| length", r.headers.get("content-length"));

console.log("2. instantiateStreaming (what the worker tries first)");
let inst = null;
try {
  const res = await WebAssembly.instantiateStreaming(fetch(URL_WASM), imports);
  inst = res.instance;
  console.log("   OK");
} catch (e) {
  console.log("   FAILED:", e.constructor.name, "-", e.message);
}

if (!inst) {
  console.log("3. arrayBuffer fallback");
  const rr = await fetch(URL_WASM);
  const res = await WebAssembly.instantiate(await rr.arrayBuffer(), imports);
  inst = res.instance;
  console.log("   OK");
}

const api = inst.exports;
console.log("4. imports the module actually demands:");
const mod = await WebAssembly.compile(await (await fetch(URL_WASM)).arrayBuffer());
for (const i of WebAssembly.Module.imports(mod)) {
  console.log(`   ${i.module}.${i.name} : ${i.kind}`);
}

console.log("5. has _initialize:", typeof api._initialize);
console.log("6. board BEFORE reset_game (should already be set by data segments):");
const peek = () => Array.from(new Uint8Array(api.memory.buffer, api.board_ptr(), 8)).join(",");
console.log("   ", peek());
api.reset_game();
console.log("7. board AFTER reset_game:");
console.log("   ", peek());
console.log("   expected: 22,19,21,23,20,21,19,22");
