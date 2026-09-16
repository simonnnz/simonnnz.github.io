/* ---------------------------------------------------------------------------
   micro-Max, by H.G. Muller  <https://home.hccnet.nl/h.g.muller/max-src2.html>

   This is the same search that runs on the board, lifted out of the Arduino
   sketch so it can be compiled to WebAssembly. Nothing about D() has been
   changed except instrumentation: it reports which squares it looks at, how
   deep it got, and what it currently thinks is best, so the page can show the
   search happening rather than just its answer.

   Everything Arduino-specific (Serial, String, setup/loop, the board printer)
   is gone. gameOver()'s `for(;;);` is gone too -- an infinite loop is fine on
   a microcontroller and fatal in a browser tab.

   MUST be compiled with -fsigned-char. AVR's char is signed; wasm32's is not,
   and w[]/o[] hold negative values. Without the flag the engine plays garbage
   that still looks like chess.
   --------------------------------------------------------------------------- */

#define W while
#define M 0x88
#define S 128
#define I 8000
#define MYRAND_MAX 65535

long  N, T;                  /* N = nodes searched, T = node budget         */
short Q, O, K, R, k = 16;    /* k = side to move                            */
char  *p, c[5], Z;           /* c = move in/out, Z = recursion depth        */

char L,
w[] = {0,2,2,7,-1,8,12,23},
o[] = {-16,-15,-17,0,1,16,0,1,16,15,17,0,14,18,31,33,0,
       7,-1,11,6,8,3,6,
       6,3,5,7,4,5,3,6};

char b[] = {
  22, 19, 21, 23, 20, 21, 19, 22, 28, 21, 16, 13, 12, 13, 16, 21,
  18, 18, 18, 18, 18, 18, 18, 18, 22, 15, 10,  7,  6,  7, 10, 15,
   0,  0,  0,  0,  0,  0,  0,  0, 18, 11,  6,  3,  2,  3,  6, 11,
   0,  0,  0,  0,  0,  0,  0,  0, 16,  9,  4,  1,  0,  1,  4,  9,
   0,  0,  0,  0,  0,  0,  0,  0, 16,  9,  4,  1,  0,  1,  4,  9,
   0,  0,  0,  0,  0,  0,  0,  0, 18, 11,  6,  3,  2,  3,  6, 11,
   9,  9,  9,  9,  9,  9,  9,  9, 22, 15, 10,  7,  6,  7, 10, 15,
  14, 11, 13, 15, 12, 13, 11, 14, 28, 21, 16, 13, 12, 13, 16, 21, 0
};

static const char b0[129] = {
  22, 19, 21, 23, 20, 21, 19, 22, 28, 21, 16, 13, 12, 13, 16, 21,
  18, 18, 18, 18, 18, 18, 18, 18, 22, 15, 10,  7,  6,  7, 10, 15,
   0,  0,  0,  0,  0,  0,  0,  0, 18, 11,  6,  3,  2,  3,  6, 11,
   0,  0,  0,  0,  0,  0,  0,  0, 16,  9,  4,  1,  0,  1,  4,  9,
   0,  0,  0,  0,  0,  0,  0,  0, 16,  9,  4,  1,  0,  1,  4,  9,
   0,  0,  0,  0,  0,  0,  0,  0, 18, 11,  6,  3,  2,  3,  6, 11,
   9,  9,  9,  9,  9,  9,  9,  9, 22, 15, 10,  7,  6,  7, 10, 15,
  14, 11, 13, 15, 12, 13, 11, 14, 28, 21, 16, 13, 12, 13, 16, 21, 0
};

unsigned int seed = 0;

/* ---- instrumentation the page reads ---- */
unsigned int visits[128];    /* how often the search touched each square    */
int  vis_depth;              /* deepest root iteration reached              */
int  vis_from, vis_to;       /* best move so far, as 0x88 squares           */
int  vis_score;              /* its score                                   */
int  vis_active;             /* 1 while a search is running                 */

/* Provided by the worker. Called every few thousand nodes so the page can
   repaint mid-search instead of freezing until the answer arrives. */
extern void js_tick(void);
static long tick_at;

unsigned short myrand(void) {
  unsigned short r = (unsigned short)(seed % MYRAND_MAX);
  return r = ((r << 11) + (r << 7) + r) >> 1;
}

short D(short q, short l, short e, unsigned char E, unsigned char z, unsigned char n) {
  short m, v, i, P, V, s;
  unsigned char t, p, u, x, y, X, Y, H, B, j, d, h, F, G, C;
  signed char r;
  if (++Z > 30) { --Z; return e; }
  q--;
  k ^= 24;
  d = Y = 0;
  X = myrand() & ~M;
  W(d++ < n || d < 3 ||
    z & K == I && (N < T & d < 98 ||
                   (K = X, L = Y & ~M, d = 3)))
  { x = B = X;
    h = Y & S;
    P = d < 3 ? I : D(-l, 1 - l, -e, S, 0, d - 3);
    m = -P < l | R > 35 ? d > 2 ? -I : e : -P;
    ++N;

    /* let the page breathe, and hand it something to draw */
    if (N > tick_at) { tick_at = N + 3000; js_tick(); }
    if (z && d > vis_depth) vis_depth = d;

    do {
      u = b[x];
      if (u & k) {
        r = p = u & 7;
        j = o[p + 16];
        W(r = p > 2 & r < 0 ? -r : -o[++j])
        { A:
          y = x; F = G = S;
          do {
            H = y = h ? Y ^ h : y + r;
            if (y & M)break;
            if (!(y & M)) visits[y & 127]++;      /* <-- the only added line in the ray loop */
            m = E - S & b[E] && y - E < 2 & E - y < 2 ? I : m;
            if (p < 3 & y == E)H ^= 16;
            t = b[H]; if (t & k | p < 3 & !(y - x & 7) - !t)break;
            i = 37 * w[t & 7] + (t & 192);
            m = i < 0 ? I : m;
            if (m >= l & d > 1)goto C;
            v = d - 1 ? e : i - p;
            if (d - !t > 1)
            { v = p < 6 ? b[x + 8] - b[y + 8] : 0;
              b[G] = b[H] = b[x] = 0; b[y] = u | 32;
              if (!(G & M))b[F] = k + 6, v += 50;
              v -= p - 4 | R > 29 ? 0 : 20;
              if (p < 3)
              { v -= 9 * ((x - 2 & M || b[x - 2] - u) +
                          (x + 2 & M || b[x + 2] - u) - 1
                          + (b[x ^ 16] == k + 36))
                     - (R >> 2);
                V = y + r + 1 & S ? 647 - p : 2 * (u & y + 16 & 32);
                b[y] += V; i += V;
              }
              v += e + i; V = m > q ? m : q;
              C = d - 1 - (d > 5 & p > 2 & !t & !h);
              C = R > 29 | d < 3 | P - I ? C : d;
              do
                s = C > 2 | v > V ? -D(-l, -V, -v, F, 0, C) : v;
              W(s > q&++C < d); v = s;
              if (z && K - I && v + I && x == K & y == L)
              { Q = -e - i; O = F;
                R += i >> 7; --Z; return l;
              }
              b[G] = k + 6; b[F] = b[y] = 0; b[x] = u; b[H] = t;
            }
            if (v > m) {
              m = v, X = x, Y = y | S & F;
              if (z) { vis_from = x; vis_to = y & ~M; vis_score = v; }
            }
            if (h) { h = 0; goto A; }
            if (x + r - y | u & 32 |
                p > 2 & (p - 4 | j - 7 ||
                         b[G = x + 3 ^ r >> 1 & 7] - k - 6
                         || b[G ^ 1] | b[G ^ 2])
               )t += p < 5;
            else F = y;
          } W(!t);
        }
      }
    } W((x = x + 9 & ~M) - B);
C: if (m > I - M | m < M - I)d = 98;
    m = m + I | P == I ? m : 0;
    if (z && d > 2)
    { *c = 'a' + (X & 7); c[1] = '8' - (X >> 4); c[2] = 'a' + (Y & 7); c[3] = '8' - (Y >> 4 & 7); c[4] = 0;
    }
  }
  k ^= 24;
  --Z; return m += m < e;
}

/* =======================================================================
   The bit the page talks to.
   ======================================================================= */

static void clear_vis(void) {
  int i;
  for (i = 0; i < 128; i++) visits[i] = 0;
  vis_depth = 0; vis_from = -1; vis_to = -1; vis_score = 0;
}

/* --- saved state, so legality can be probed without disturbing the game --- */
static char sb[129];
static short sQ, sO, sK, sR, sk;
static char sZ, sL;
static long sN, sT;

static void snapshot(void) {
  int i; for (i = 0; i < 129; i++) sb[i] = b[i];
  sQ = Q; sO = O; sK = K; sR = R; sk = k; sZ = Z; sL = L; sN = N; sT = T;
}
static void restore(void) {
  int i; for (i = 0; i < 129; i++) b[i] = sb[i];
  Q = sQ; O = sO; K = sK; R = sR; k = sk; Z = sZ; L = sL; N = sN; T = sT;
}

void reset_game(void) {
  int i;
  for (i = 0; i < 129; i++) b[i] = b0[i];
  Q = O = R = 0; K = 0; k = 16; Z = 0; N = 0; T = 0x3F; L = 0;
  seed = 0;
  clear_vis();
}

/* squares are 0x88: rank*16 + file, rank 0 = the 8th rank */

/* How micro-Max reports "I made that move": when the root search finds the
   requested move it returns early, BEFORE the closing k ^= 24, so the side to
   move stays flipped. A search that merely finished normally flips it back.
   The return value can't tell these apart -- a legal move and a quiet position
   both come back well above -I. The original sketch tests `k == 0x10` for
   exactly this reason. */
static int move_taken(int k_before) {
  return k != k_before;
}

static short apply(int from, int to) {
  K = from; L = to;
  N = 0; Z = 0;
  return D(-I, I, Q, O, 1, 3);
}

/* Is this move legal for the side to move? Probes and rolls back. */
int is_legal(int from, int to) {
  int before, ok;
  snapshot();
  before = k;
  apply(from, to);
  ok = move_taken(before);
  restore();
  return ok;
}

/* Play a human move. Returns 1 if it was legal and has been made. */
int play_move(int from, int to) {
  int before;
  snapshot();
  before = k;
  apply(from, to);
  if (!move_taken(before)) { restore(); return 0; }
  return 1;
}

/* Let the engine move, with `budget` nodes of thinking. Returns packed
   from<<8 | to, or -1 if it has no move. */
int engine_move(int budget) {
  int before;
  clear_vis();
  vis_active = 1;
  K = I; N = 0; Z = 0;
  T = budget < 1 ? 1 : budget;
  tick_at = 0;
  before = k;
  D(-I, I, Q, O, 1, 3);
  vis_active = 0;
  if (!move_taken(before)) return -1;
  return ((c[0] - 'a') + (('8' - c[1]) << 4)) << 8
       | ((c[2] - 'a') + (('8' - c[3]) << 4));
}

/* k is stored as the value D() will flip, so the side actually to move is
   k ^ 24: 8 selects white pieces, 16 selects black. */
int side_to_move(void) { return k ^ 24; }

/* --- deliberately worse play -------------------------------------------
   The node budget can't make it weaker than depth 3: the root loop runs
   `d < 3` regardless of T, so 63 nodes and 6 nodes play identically. To go
   below the Arduino we replace the engine's choice outright some of the time.

   micro-Max's own myrand() can't help here. It reads a seed the sketch never
   advances, so it returns 0 on every call and the engine is fully
   deterministic. This is a separate generator. */
static unsigned int rng = 0x2545F491;
static unsigned int rnd(void) {
  rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
  return rng;
}
void set_seed(unsigned int s) { rng = s ? s : 1; }

/* Play a uniformly random legal move. Returns from<<8|to, or -1. */
int random_move(void) {
  int mine = side_to_move();
  int froms[40], nf = 0, f, t, i;
  clear_vis();
  for (f = 0; f < 128; f++)
    if (!(f & M) && (b[f] & mine) && nf < 40) froms[nf++] = f;
  if (!nf) return -1;

  for (i = 0; i < 1200; i++) {                 /* rejection sampling is plenty */
    f = froms[rnd() % (unsigned)nf];
    t = ((rnd() % 8u) << 4) | (rnd() % 8u);
    if (f == t) continue;
    if (play_move(f, t)) { vis_from = f; vis_to = t; return (f << 8) | t; }
  }
  /* pinned to almost nothing: fall back to an exhaustive scan */
  for (i = 0; i < nf; i++)
    for (t = 0; t < 128; t++) {
      if (t & M) continue;
      if (play_move(froms[i], t)) {
        vis_from = froms[i]; vis_to = t;
        return (froms[i] << 8) | t;
      }
    }
  return -1;
}

/* Does the side to move have any legal reply? 0 means the game is over. */
int has_moves(void) {
  int f, t, mine = side_to_move();
  for (f = 0; f < 128; f++) {
    if (f & M) continue;
    if (!(b[f] & mine)) continue;
    for (t = 0; t < 128; t++) {
      if (t & M) continue;
      if (is_legal(f, t)) return 1;
    }
  }
  return 0;
}

char *board_ptr(void)          { return b; }
unsigned int *visits_ptr(void) { return visits; }
long nodes(void)               { return N; }
int  depth_reached(void)       { return vis_depth; }
int  best_from(void)           { return vis_from; }
int  best_to(void)             { return vis_to; }
int  best_score(void)          { return vis_score; }
