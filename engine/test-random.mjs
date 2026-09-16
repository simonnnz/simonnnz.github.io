/* Does random_move actually produce legal, varied moves? */
import { readFileSync } from "fs";
const bytes = readFileSync(new URL("./engine.wasm", import.meta.url));
const { instance } = await WebAssembly.instantiate(bytes, { env: { js_tick: () => {} } });
const e = instance.exports;

const sq = a => (8 - (+a[1])) * 16 + (a.charCodeAt(0) - 97);
const alg = i => "abcdefgh"[i & 7] + (8 - (i >> 4));

console.log("exports random_move:", typeof e.random_move, "| set_seed:", typeof e.set_seed);

const seen = new Map();
for (let trial = 0; trial < 40; trial++) {
  e.reset_game();
  e.set_seed(trial * 7919 + 13);
  e.play_move(sq("e2"), sq("e4"));
  const p = e.random_move();
  if (p < 0) { console.log("  trial", trial, "no move"); continue; }
  const mv = alg((p >> 8) & 0xff) + alg(p & 0xff);
  seen.set(mv, (seen.get(mv) || 0) + 1);
}
console.log(`\ndistinct random replies to 1.e4 over 40 trials: ${seen.size}`);
console.log([...seen.entries()].sort((a, b) => b[1] - a[1])
  .map(([m, n]) => `${m}(${n})`).join(" "));

/* every one of them must be legal for black */
e.reset_game(); e.play_move(sq("e2"), sq("e4"));
let bad = 0;
for (const mv of seen.keys()) {
  const f = sq(mv.slice(0, 2)), t = sq(mv.slice(2));
  if (!e.is_legal(f, t)) { console.log("  ILLEGAL:", mv); bad++; }
}
console.log(bad ? `${bad} ILLEGAL MOVES` : "all generated moves are legal");

/* and the engine still plays properly at each budget */
console.log("\nengine_move still works:");
for (const b of [63, 200000]) {
  e.reset_game(); e.play_move(sq("e2"), sq("e4"));
  const t0 = Date.now();
  const p = e.engine_move(b);
  console.log(`  budget ${String(b).padStart(7)}: ${alg((p>>8)&0xff)}${alg(p&0xff)}  ` +
              `depth ${e.depth_reached()}  nodes ${e.nodes()}  ${Date.now()-t0} ms`);
}
