r"""
Records scripted drives of the biped policy for the RL page.

    python tools\record_rl.py --rl <rl worktree> --set final
    python tools\record_rl.py --rl <demo-power worktree> --set demo --run ppo_demo

Runs in the biped repo's own environment (its biped_env.py, params.py and
trained run), so what the page replays is exactly what the simulator did.
Each --set is one policy and its clips; recording a set replaces only that
set's entries in rl.json. Writes, into media\rl\:

  policy-<set>.bin   the actor network as float32: obs mean, obs var, then each
                     layer's weights (row-major, out x in) and biases
  <set>-<clip>.bin   one float32 record per saved control step, layout in rl.json
  <set>-ground.bin   uint8 heightfield, for sets with rough-ground clips
  rl.json            shapes, policies, clip list, geometry of every body

The web page runs the network itself on the recorded observations, so the
activations it draws are computed live, not stored. Recorded actions ride
along only so the page can prove its forward pass matches.
"""

import argparse
import glob
import json
import math
import os
import pickle
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "media", "rl")
STRIDE = 2            # save every 2nd control step: 50 Hz, plenty for replay

# ---------------------------------------------------------------- scripts ---
# cmds: (start s, vx m/s, yaw rad/s, height offset m); a segment holds until the next.
# pushes: (time s, dvx m/s, dvy m/s), world frame.
# The heightfield is only 8 m across and the floor beyond it sits 50 mm lower,
# so every script keeps the robot within ~3.5 m of the start.
SETS = {
    "final": dict(
        label="Trained policy",
        clips={
            # no crouch segment: MEASURED 2026-09-15, ppo_final ignores the height
            # command at nominal physics (asked -30 mm, held -1 mm)
            "drive": dict(
                title="Drive and turn", seconds=25, terrain=0.0,
                cmds=[(0.0, 0.0, 0.0, 0.0), (2.0, 0.5, 0.0, 0.0), (4.5, 1.0, 0.0, 0.0),
                      (7.5, 0.8, 1.8, 0.0), (11.0, 0.0, 2.5, 0.0), (13.5, 0.0, 0.0, 0.0),
                      (15.0, -0.7, 0.0, 0.0), (17.5, 0.9, -2.0, 0.0), (21.5, 0.0, 0.0, 0.0)],
                pushes=[]),
            "shove": dict(
                title="Pushes", seconds=22, terrain=0.0,
                cmds=[(0.0, 0.0, 0.0, 0.0), (12.0, 0.5, 0.0, 0.0), (17.0, 0.0, 0.0, 0.0)],
                pushes=[(3.0, 0.7, 0.0), (6.0, -0.7, 0.0), (9.0, 0.0, 0.55), (13.5, -0.6, 0.35),
                        (15.5, 0.3, -0.55), (19.0, 0.7, 0.3)]),
            "terrain": dict(
                title="Rough ground", seconds=24, terrain=1.0,
                cmds=[(0.0, 0.0, 0.0, 0.0), (1.5, 0.7, 0.55, 0.0), (9.0, 0.9, -0.65, 0.0),
                      (16.0, 0.5, 0.9, 0.0), (21.0, 0.0, 0.0, 0.0)],
                pushes=[]),
        }),
    "demo": dict(
        label="Demo mode",
        clips={
            # the demo env caps v x yaw at 4 m/s^2, so fast turns are wide arcs.
            # Commands stay near what it actually reaches (~1.3 m/s): asking for
            # 2.6 only showed a gauge reading half its command. It ignores the
            # height command, same as ppo_final, so no crouch segment.
            "sprint": dict(
                title="Fast driving", seconds=24, terrain=0.0,
                cmds=[(0.0, 0.0, 0.0, 0.0), (1.0, 1.2, 1.2, 0.0), (4.0, 1.8, 1.5, 0.0),
                      (8.5, 1.8, -1.5, 0.0), (13.0, 0.0, 6.0, 0.0), (15.5, 0.0, -6.0, 0.0),
                      (18.0, 1.2, 0.0, 0.0), (20.0, 0.0, 3.0, 0.0), (22.0, 0.0, 0.0, 0.0)],
                pushes=[]),
            # MEASURED: a shove landing while it drives AND turns puts it down on
            # 5 of 6 seeds, so the shoves land while standing or driving straight
            "brawl": dict(
                title="Large pushes", seconds=20, terrain=0.0,
                cmds=[(0.0, 0.0, 0.0, 0.0), (13.0, 1.2, 0.0, 0.0), (15.8, 0.0, 0.0, 0.0)],
                pushes=[(2.0, 1.0, 0.0), (4.5, -1.0, 0.0), (7.0, 0.0, 0.9), (9.0, 0.7, -0.7),
                        (11.0, -0.9, 0.5), (15.0, 0.8, 0.0), (18.5, -1.0, 0.0)]),
            "steps": dict(
                title="Steps and bumps", seconds=24, terrain=1.0, steps=True,
                cmds=[(0.0, 0.0, 0.0, 0.0), (1.0, 1.3, 0.9, 0.0), (8.0, 1.5, -1.1, 0.0),
                      (15.0, 1.2, 1.4, 0.0), (21.0, 0.0, 0.0, 0.0)],
                pushes=[]),
        }),
}


def load_policy(run, model_file, vecnorm):
    from stable_baselines3 import PPO
    import torch
    model = PPO.load(model_file, device="cpu")
    with open(vecnorm, "rb") as fh:
        vn = pickle.load(fh)                              # only the statistics are needed
    mean = vn.obs_rms.mean.astype(np.float64)
    var = vn.obs_rms.var.astype(np.float64)
    pol = model.policy
    lin = [m for m in pol.mlp_extractor.policy_net if isinstance(m, torch.nn.Linear)]
    lin.append(pol.action_net)
    layers = [(l.weight.detach().numpy().astype(np.float64),
               l.bias.detach().numpy().astype(np.float64)) for l in lin]
    return model, mean, var, float(vn.clip_obs), float(vn.epsilon), layers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rl", required=True, help="the biped rl folder / worktree")
    ap.add_argument("--set", default="final", choices=list(SETS))
    ap.add_argument("--run", default="ppo_final")
    ap.add_argument("--model", default="final.zip",
                    help="file in the run folder, or 'latest' for the newest checkpoint")
    ap.add_argument("--clips", default=None, help="comma list; default all in the set")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--dry", action="store_true", help="simulate and report, write nothing")
    args = ap.parse_args()

    sys.path.insert(0, args.rl)
    os.chdir(args.rl)
    import params as P
    import biped_env as E

    run = os.path.join(args.rl, "runs", args.run)
    if args.model == "latest":
        cks = glob.glob(os.path.join(run, "ckpt_*_steps.zip"))
        model_file = max(cks, key=lambda p: int(re.search(r"_(\d+)_steps", p).group(1)))
        n = re.search(r"_(\d+)_steps", model_file).group(1)
        vecnorm = os.path.join(run, "ckpt_vecnormalize_%s_steps.pkl" % n)
        print("checkpoint at %s steps" % n)
    else:
        model_file = os.path.join(run, args.model)
        vecnorm = os.path.join(run, "vecnormalize.pkl")
    model, mean, var, clip_obs, eps, layers = load_policy(run, model_file, vecnorm)

    def forward(obs):
        x = np.clip((obs - mean) / np.sqrt(var + eps), -clip_obs, clip_obs)
        for i, (W, b) in enumerate(layers):
            x = W @ x + b
            if i < len(layers) - 1:
                x = np.tanh(x)
        return np.clip(x, -1.0, 1.0)

    S = SETS[args.set]
    names = args.clips.split(",") if args.clips else list(S["clips"])
    os.makedirs(OUT, exist_ok=True)
    if not args.dry:
        with open(os.path.join(OUT, "policy-%s.bin" % args.set), "wb") as fh:
            for a in [mean, var] + [a for W, b in layers for a in (W.ravel(), b)]:
                fh.write(a.astype("<f4").tobytes())

    E.BipedEnv._resample_command = lambda self: None     # commands come from the script
    step_p = P.TERRAIN_STEP_P
    clips_meta, worst = [], 0.0
    for name in names:
        spec = S["clips"][name]
        P.TERRAIN_STEP_P = step_p
        env = E.BipedEnv(randomize=False)
        if spec["terrain"] > 0:
            P.TERRAIN_STEP_P = 1.0 if spec.get("steps") else 0.0   # plateaus, or noise only
            orig = E.BipedEnv._set_terrain
            env._set_terrain = lambda s, o=orig, e=env, k=spec["terrain"]: o(e, k)
        env.cmd = np.zeros(3)
        obs, _ = env.reset(seed=args.seed)
        env.push_at = 10 ** 9                             # shoves come from the script
        m, d = env.model, env.data
        bodies = list(range(1, m.nbody))
        steps = int(spec["seconds"] * P.CTRL_HZ)
        rec, fell, far = [], None, 0.0
        pushes = list(spec["pushes"])
        track = {}
        for k in range(steps):
            t = k / P.CTRL_HZ
            for (t0, vx, wz, h) in spec["cmds"]:
                if t >= t0:
                    env.cmd = np.array([vx, wz, h])
            kicked = 0.0
            if pushes and t >= pushes[0][0]:
                _, dvx, dvy = pushes.pop(0)
                d.qvel[0] += dvx
                d.qvel[1] += dvy
                kicked = math.hypot(dvx, dvy)

            a = forward(obs.astype(np.float64))
            if k < 200:
                ref, _ = model.predict(((obs - mean) / np.sqrt(var + eps)).clip(-clip_obs, clip_obs),
                                       deterministic=True)
                worst = max(worst, float(np.abs(ref - a).max()))
            obs_used = obs.copy()
            obs, r, term, trunc, info = env.step(a)
            far = max(far, abs(d.xpos[1][0]), abs(d.xpos[1][1]))
            R = env._rot()
            v_body = env._v_body(R)
            hgt = env._leg_height().mean() - P.H_STAND
            seg = tuple(env.cmd)
            track.setdefault(seg, []).append((v_body[0], d.qvel[5], hgt))
            if k % STRIDE == 0:
                terms = info["terms"]
                pos_terms = sum(terms[x] for x in ("vel", "yaw", "height", "upright", "alive"))
                row = []
                for b in bodies:
                    row += list(d.xpos[b]) + list(d.xquat[b])
                row += list(obs_used) + list(a)
                row += list(env.cmd) + [v_body[0], d.qvel[5], hgt]
                row += [r, terms["vel"], terms["yaw"], terms["height"], terms["upright"],
                        terms["alive"], r - pos_terms, kicked]
                rec.append(row)
            if term:
                fell = t
                break
        arr = np.asarray(rec, dtype="<f4")
        fname = "%s-%s.bin" % (args.set, name)
        print("%-8s %5.1f s  %4d frames  furthest %.1f m  %s" % (
            name, len(rec) * STRIDE / P.CTRL_HZ, len(rec), far,
            "FELL at %.2f s" % fell if fell is not None else "survived"))
        for seg, vals in track.items():
            tail = np.array(vals[-150:])
            print("    cmd vx %5.2f wz %5.2f h %6.3f -> did %5.2f %5.2f %6.3f" % (
                seg[0], seg[1], seg[2], *tail.mean(0)))
        entry = dict(name=name, set=args.set, file=fname, title=spec["title"],
                     frames=len(rec), fell=fell, cols=int(arr.shape[1]) if len(arr) else 0,
                     terrain=None)
        if spec["terrain"] > 0:
            hf = env._hf
            gname = "%s-ground-%s.bin" % (args.set, name)
            entry["terrain"] = dict(file=gname, n=int(hf.shape[0]), half=float(P.TERRAIN_HALF),
                                    amp=float(env._amp_max()))
            if not args.dry:
                np.clip(np.round(hf * 255), 0, 255).astype(np.uint8).tofile(os.path.join(OUT, gname))
        if not args.dry:
            arr.tofile(os.path.join(OUT, fname))
        clips_meta.append(entry)
    print("forward pass vs SB3 predict, worst abs diff: %.2e" % worst)
    if args.dry:
        return

    # ---- geometry: every non-ground geom, in its body's frame ----
    TYPES = {2: "sphere", 3: "capsule", 5: "cylinder", 6: "box"}
    geoms = []
    for g in range(m.ngeom):
        tp = TYPES.get(int(m.geom_type[g]))
        if tp is None:
            continue
        geoms.append(dict(type=tp, body=int(m.geom_bodyid[g]) - 1, size=[float(s) for s in m.geom_size[g]],
                          pos=[float(s) for s in m.geom_pos[g]], quat=[float(s) for s in m.geom_quat[g]],
                          name=m.geom(g).name))

    path = os.path.join(OUT, "rl.json")
    meta = {}
    if os.path.exists(path):
        with open(path) as fh:
            meta = json.load(fh)
    if "policies" not in meta:                              # older single-policy layout
        meta = {}
    meta.update(
        ctrl_hz=P.CTRL_HZ, stride=STRIDE, bodies=[m.body(b).name for b in bodies], geoms=geoms,
        columns=dict(pose=len(bodies) * 7, obs=int(len(mean)), action=6, cmd=3, actual=3, reward=8),
        reward_names=["total", "vel", "yaw", "height", "upright", "alive", "penalties", "push"])
    meta.setdefault("policies", {})[args.set] = dict(
        label=S["label"], file="policy-%s.bin" % args.set, run=args.run,
        model=os.path.relpath(model_file, run), obs_dim=int(len(mean)),
        layers=[list(W.shape) for W, b in layers], clip_obs=clip_obs, eps=eps, forward_check=worst)
    order = list(SETS)
    kept = [c for c in meta.get("clips", []) if c.get("set") != args.set]
    meta["clips"] = sorted(kept + clips_meta, key=lambda c: order.index(c["set"]))
    with open(path, "w") as fh:
        json.dump(meta, fh, indent=1)


if __name__ == "__main__":
    main()
