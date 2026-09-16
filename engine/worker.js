/* ---------------------------------------------------------------------------
   The engine runs here, on its own thread.

   A search at a high node budget takes real time, and JavaScript draws the
   page on the same thread it runs code on. Doing this on the main thread would
   freeze the whole tab -- no scrolling, no cancel button, not even a spinner.
   So the wasm lives in a worker and talks to the page by message.

   The engine calls back into js_tick() every few thousand nodes. That is what
   lets the board show the search happening instead of just its result.
   --------------------------------------------------------------------------- */

let mem, api, tickThrottle = 0, cancelled = false;

function readStats() {
  const u8 = new Uint8Array(mem.buffer);
  const u32 = new Uint32Array(mem.buffer);
  const board = u8.slice(api.board_ptr(), api.board_ptr() + 129);
  const visits = u32.slice(api.visits_ptr() >> 2, (api.visits_ptr() >> 2) + 128);
  return {
    board, visits,
    nodes: api.nodes(),
    depth: api.depth_reached(),
    from: api.best_from(),
    to: api.best_to(),
    score: api.best_score(),
    side: api.side_to_move()
  };
}

function post(type, extra) {
  const s = readStats();
  self.postMessage(Object.assign({ type }, s, extra || {}),
                   [s.board.buffer, s.visits.buffer]);
}

const imports = {
  env: {
    /* called from inside the search */
    js_tick: function () {
      const now = Date.now();
      if (now - tickThrottle < 60) return;   /* ~16 repaints a second is plenty */
      tickThrottle = now;
      post("progress");
    }
  }
};

self.onmessage = async function (e) {
  const m = e.data;

  if (m.cmd === "init") {
    try {
      let res;
      try {
        res = await WebAssembly.instantiateStreaming(fetch(m.url), imports);
      } catch (streamErr) {
        /* instantiateStreaming is fussy about MIME type and rejects outright.
           Fetching the bytes first always works, so fall back rather than die. */
        const r = await fetch(m.url);
        if (!r.ok) throw new Error("fetch " + m.url + " -> HTTP " + r.status);
        res = await WebAssembly.instantiate(await r.arrayBuffer(), imports);
      }
      api = res.instance.exports;
      mem = api.memory;
      if (!mem) throw new Error("wasm exported no memory");
      /* built with --no-entry, so it's a reactor: globals are set up by
         _initialize, not by a start section. Skip this and b[] is all zeros,
         which draws an empty board and looks like nothing loaded. */
      if (typeof api._initialize === "function") api._initialize();
      if (typeof api.reset_game !== "function") {
        throw new Error("missing export reset_game; got: " +
                        Object.keys(api).join(","));
      }
      api.reset_game();
      post("ready");
    } catch (err) {
      self.postMessage({ type: "fail", error: String(err && err.message || err) });
    }
    return;
  }

  if (m.cmd === "reset") {
    api.reset_game();
    post("state");
    return;
  }

  if (m.cmd === "legal") {
    /* every destination for one square, so the board can show dots */
    const out = [];
    for (let t = 0; t < 128; t++) {
      if (t & 0x88) continue;
      if (api.is_legal(m.from, t)) out.push(t);
    }
    self.postMessage({ type: "legal", from: m.from, moves: out });
    return;
  }

  if (m.cmd === "play") {
    const ok = api.play_move(m.from, m.to);
    post("played", { ok: !!ok, from: m.from, to: m.to });
    return;
  }

  if (m.cmd === "think") {
    const t0 = Date.now();
    /* below the Arduino's setting the slider buys blunders, not fewer nodes,
       because the search can't go shallower than depth 3 */
    const blundered = m.blunder > 0 && Math.random() < m.blunder;
    const packed = blundered ? api.random_move() : api.engine_move(m.budget);
    const ms = Date.now() - t0;
    post("moved", {
      ok: packed >= 0,
      from: packed >= 0 ? (packed >> 8) & 0xff : -1,
      to: packed >= 0 ? packed & 0xff : -1,
      ms: ms,
      blundered: blundered
    });
    return;
  }

  if (m.cmd === "hasMoves") {
    self.postMessage({ type: "hasMoves", value: !!api.has_moves() });
    return;
  }
};
