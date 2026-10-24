"""Estimate whether a mission AI load can run smoothly on a given CPU.

Uses standing-equivalent units (SEU) from docs/17:
  SEU = U_stand + k * U_move,  k≈2.63
Scale budgets by PassMark single-thread ratio vs the calibrated reference PC.

Usage:
  python tools/estimate_mission_cpu.py --move 96 --stand 32 --cpu r5_5600
  python tools/estimate_mission_cpu.py --move 120 --cpu this_pc --role client
  python tools/estimate_mission_cpu.py --list-cpus
  python tools/estimate_mission_cpu.py --calibrate-help
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "config", "cpu_catalog.json")
MODEL = os.path.join(ROOT, "extract", "cpu_samples", "ai_wp_cost_model.json")

# Fallback if model file missing
K_MOVE_DEFAULT = 2.63


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def k_move() -> float:
    if not os.path.isfile(MODEL):
        return K_MOVE_DEFAULT
    m = load_json(MODEL).get("marginal_cost") or {}
    r = m.get("move_vs_stand_ratio")
    return float(r) if r else K_MOVE_DEFAULT


def seu(u_move: float, u_stand: float, k: float) -> float:
    return float(u_stand) + k * float(u_move)


def find_cpu(catalog: dict, cpu_id: str) -> dict:
    if cpu_id == catalog["reference"]["id"] or cpu_id == "this_pc":
        ref = catalog["reference"]
        return {
            "id": ref["id"],
            "label": ref.get("label", "reference"),
            "passmark_st": float(ref.get("passmark_st") or 0),
            "is_reference": True,
        }
    for c in catalog.get("cpus", []):
        if c["id"] == cpu_id:
            return {**c, "is_reference": False, "passmark_st": float(c["passmark_st"])}
    raise SystemExit(
        f"unknown cpu id: {cpu_id}\nUse --list-cpus or add it to config/cpu_catalog.json"
    )


def predict_exe(u_move: float, u_stand: float) -> dict:
    """Optional: absolute exe_fn/exe% on the *reference* DS box (not scaled)."""
    if not os.path.isfile(MODEL):
        return {}
    models = load_json(MODEL).get("models") or {}
    out = {}
    # Prefer two-factor; for pure move/stand use dedicated fits
    u = u_move + u_stand
    m = 1.0 if u_move > 0 and u_stand == 0 else (0.0 if u_move == 0 else None)
    tf = models.get("two_factor_exe_fn")
    if tf and m is not None:
        c = tf["coef"]
        out["exe_fn_ref"] = (
            c["intercept"] + c["units"] * u + c["units_x_moving"] * (u * m)
        )
    # Mix: standing on none-line, moving on cycle-line (additive approximation)
    cm = models.get("cycle2_exe_fn_vs_units")
    nm = models.get("none_exe_fn_vs_units")
    cp = models.get("cycle2_exe_pct_vs_units")
    np_ = models.get("none_exe_pct_vs_units")
    if cm and nm:
        # Use slopes only for marginal (ignore negative intercepts for mixed)
        out["exe_fn_ref_mixed"] = max(
            0.0, nm["a"] * u_stand + cm["a"] * u_move
        )
    if cp and np_:
        out["exe_pct_ref_mixed"] = max(
            0.0, np_["a"] * u_stand + cp["a"] * u_move
        )
    return out


def verdict(seu_val: float, budget: float, st_ref: float, st_tgt: float) -> dict:
    if st_ref <= 0 or budget <= 0:
        return {
            "status": "UNCALIBRATED",
            "detail": "请先在 config/cpu_catalog.json 填写 reference.passmark_st 与 budgets",
            "budget_scaled": None,
            "headroom_seu": None,
            "load_ratio": None,
        }
    scale = st_tgt / st_ref
    budget_scaled = budget * scale
    headroom = budget_scaled - seu_val
    ratio = seu_val / budget_scaled if budget_scaled > 0 else 999.0
    if ratio <= 0.85:
        status = "SMOOTH"
    elif ratio <= 1.0:
        status = "OK"
    elif ratio <= 1.25:
        status = "MARGINAL"
    else:
        status = "HEAVY"
    return {
        "status": status,
        "budget_scaled": budget_scaled,
        "headroom_seu": headroom,
        "load_ratio": ratio,
        "st_scale": scale,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--move", type=float, default=0, help="moving AI count")
    ap.add_argument("--stand", type=float, default=0, help="standing AI (PATH off)")
    ap.add_argument("--cpu", default="this_pc", help="cpu id from catalog")
    ap.add_argument(
        "--role",
        choices=("client", "server", "both"),
        default="client",
        help="which budget to use",
    )
    ap.add_argument("--list-cpus", action="store_true")
    ap.add_argument(
        "--calibrate-help",
        dest="calibrate_help",
        action="store_true",
    )
    ap.add_argument("--json", action="store_true", help="print machine JSON")
    args = ap.parse_args()

    catalog = load_json(CATALOG)
    k = k_move()

    if args.list_cpus:
        ref = catalog["reference"]
        print(f"reference\t{ref['id']}\tST={ref.get('passmark_st')}\t{ref.get('label')}")
        for c in catalog.get("cpus", []):
            print(f"catalog\t{c['id']}\tST={c['passmark_st']}\t{c['label']}")
        return 0

    if args.calibrate_help:
        print(
            """
校准步骤（一次）：
1. 查本机 CPU PassMark Single Thread，写入 config/cpu_catalog.json → reference.passmark_st
2. 客户端：用目标画质跑一局代表性任务（或 YAAB），记下仍「流畅」的最大移动 AI / 站岗 AI
3. 计算 SEU = U_stand + {k:.2f}*U_move，填入 budgets.client_smooth_seu
   （可玩但掉帧可填 client_playable_seu，约 smooth 的 1.3–1.5 倍）
4. 专用服：用 server/sweep 或实战 RPT，填 server_ok_seu
5. 之后：python tools/estimate_mission_cpu.py --move N --stand M --cpu r5_5600

注意：Arma 偏单线程+作业；ST 缩放是一阶近似，不是帧率保证。
""".format(
                k=k
            )
        )
        return 0

    cpu = find_cpu(catalog, args.cpu)
    ref = catalog["reference"]
    st_ref = float(ref.get("passmark_st") or 0)
    st_tgt = float(cpu["passmark_st"] or 0)
    budgets = ref.get("budgets") or {}

    seu_val = seu(args.move, args.stand, k)
    exe = predict_exe(args.move, args.stand)

    roles = []
    if args.role in ("client", "both"):
        roles.append(
            (
                "client_smooth",
                float(budgets.get("client_smooth_seu") or 0),
            )
        )
        roles.append(
            (
                "client_playable",
                float(budgets.get("client_playable_seu") or 0),
            )
        )
    if args.role in ("server", "both"):
        roles.append(("server_ok", float(budgets.get("server_ok_seu") or 0)))

    results = {
        "mission": {
            "u_move": args.move,
            "u_stand": args.stand,
            "k_move": k,
            "seu": seu_val,
        },
        "cpu": cpu,
        "reference_st": st_ref,
        "exe_on_reference_ds": exe,
        "verdicts": {},
    }
    for name, budget in roles:
        results["verdicts"][name] = verdict(seu_val, budget, st_ref, st_tgt)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    print(f"任务负载  移动AI={args.move:g}  站岗AI={args.stand:g}  k={k:.2f}")
    print(f"SEU（站岗当量）= {seu_val:.1f}")
    if exe:
        if "exe_fn_ref_mixed" in exe:
            print(
                f"本机 DS 粗估（不跨CPU） exe_fn≈{exe['exe_fn_ref_mixed']:.0f}"
                + (
                    f"  exe%≈{exe['exe_pct_ref_mixed']:.3f}"
                    if "exe_pct_ref_mixed" in exe
                    else ""
                )
            )
    print(f"目标CPU  {cpu['label']}  ST={st_tgt:g}  (ref ST={st_ref:g})")
    for name, v in results["verdicts"].items():
        if v["status"] == "UNCALIBRATED":
            print(f"  [{name}] {v['status']}: {v['detail']}")
            continue
        print(
            f"  [{name}] {v['status']}  "
            f"load={v['load_ratio']:.2f}×budget  "
            f"budget_SEU={v['budget_scaled']:.0f}  "
            f"余量={v['headroom_seu']:+.0f}  "
            f"(ST×{v['st_scale']:.2f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
