/* Sanity check: does the compiled engine play real chess?
   Run with the node that ships inside emsdk. */
import { readFileSync } from "fs";

const bytes = readFileSync(new URL("./engine.wasm", import.meta.url));
let ticks = 0;
const { instance } = await WebAssembly.instantiate(bytes, {
  env: { js_tick: () => { ticks++; } }
});
const e = instance.exports;

console.log("exports:", Object.keys(e).filter(k => k !== "memory").sort().join(" "));

const SYM = ".?pnkbrq?P?NKBRQ";
const sq = a => (8 - (+a[1])) * 16 + (a.charCodeAt(0) - 97);
const alg = i => "abcdefgh"[i & 7] + (8 - (i >> 4));

function board() {
  const b = new Uint8Array(e.memory.buffer, e.board_ptr(), 129);
  let s = "";
  for (let r = 0; r < 8; r++) {
    s += "  " + (8 - r) + " ";
    for (let c = 0; c < 8; c++) s += SYM[b[r * 16 + c] & 15] + " ";
    s += "\n";
  }
  return s + "    a b c d e f g h";
}

e.reset_game();
console.log("\n--- start ---\n" + board());

console.log("\nlegality probes (white to move):");
for (const [m, want] of [["e2e4", true], ["e2e5", false], ["g1f3", true],
                         ["g1g3", false], ["d2d4", true], ["a1a3", false]]) {
  const got = !!e.is_legal(sq(m.slice(0, 2)), sq(m.slice(2)));
  console.log(`  ${m}  expected ${want ? "legal " : "illegal"}  got ${got ? "legal " : "illegal"}  ${got === want ? "ok" : "MISMATCH"}`);
}

console.log("\nplaying e2e4 ...");
console.log("  accepted:", !!e.play_move(sq("e2"), sq("e4")));

for (const budget of [63, 20000]) {
  e.reset_game();
  e.play_move(sq("e2"), sq("e4"));
  const t0 = Date.now();
  const packed = e.engine_move(budget);
  const ms = Date.now() - t0;
  if (packed < 0) { console.log(`  budget ${budget}: no move`); continue; }
  const from = (packed >> 8) & 0xff, to = packed & 0xff;
  console.log(`  budget ${String(budget).padStart(6)}: replied ${alg(from)}${alg(to)}  ` +
              `depth ${e.depth_reached()}  nodes ${e.nodes()}  ${ms} ms  ticks ${ticks}`);
}

console.log("\n--- after 1.e4 and black's reply ---\n" + board());

const v = new Uint32Array(e.memory.buffer, e.visits_ptr(), 128);
let touched = 0, total = 0;
for (let i = 0; i < 128; i++) if (!(i & 0x88)) { if (v[i]) touched++; total += v[i]; }
console.log(`\nvisit map: ${touched}/64 squares touched, ${total} visits total`);
console.log("has_moves:", !!e.has_moves());
