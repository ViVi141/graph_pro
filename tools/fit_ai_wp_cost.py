"""Fit AI/waypoint cost models from extract/cpu_samples/sweep_g*.json."""
from __future__ import annotations

import glob
import json
import os
import re

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "extract", "cpu_samples")
OUT_JSON = os.path.join(SRC, "ai_wp_cost_model.json")
OUT_MD = os.path.join(ROOT, "docs", "17-ai-wp-cost-table.md")


def load_rows():
    rows = []
    for path in sorted(glob.glob(os.path.join(SRC, "sweep_g*.json"))):
        with open(path, encoding="utf-8-sig") as f:
            rows.append(json.load(f))
    return rows


def linreg(x: np.ndarray, y: np.ndarray):
    """y = a*x + b; return a, b, r2, rmse."""
    if len(x) < 2:
        return None
    A = np.vstack([x, np.ones_like(x)]).T
    a, b = np.linalg.lstsq(A, y, rcond=None)[0]
    pred = a * x + b
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    rmse = float(np.sqrt(ss_res / len(y)))
    return {
        "a": float(a),
        "b": float(b),
        "r2": r2,
        "rmse": rmse,
        "n": int(len(x)),
    }


def multireg(X: np.ndarray, y: np.ndarray, names: list[str]):
    """y = X @ beta (X includes intercept column)."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    rmse = float(np.sqrt(ss_res / len(y)))
    coef = {names[i]: float(beta[i]) for i in range(len(names))}
    return {"coef": coef, "r2": r2, "rmse": rmse, "n": int(len(y))}


def main() -> int:
    rows = load_rows()
    if not rows:
        print("no sweep_g*.json")
        return 1

    # moving = not standing (none)
    for r in rows:
        r["moving"] = 0 if r["wp_mode"] == "none" else 1
        r["units_ai"] = max(0, int(r["units"]) - (1 if r["groups"] == 0 else 0))
        # playable slot may add 1 unit at groups=0
        if r["groups"] == 0:
            r["units_ai"] = 0
        else:
            r["units_ai"] = int(r["groups"]) * int(r["per_group"])

    cycle = [r for r in rows if r["wp_mode"] == "cycle2"]
    none = [r for r in rows if r["wp_mode"] == "none"]
    dens = [r for r in rows if r["groups"] == 24]

    def pack(subset, xkey, ykey):
        x = np.array([r[xkey] for r in subset], dtype=float)
        y = np.array([r[ykey] for r in subset], dtype=float)
        return x, y

    models = {}
    for ykey in ("exe_fn", "exe_pct"):
        models[f"cycle2_{ykey}_vs_units"] = linreg(*pack(cycle, "units_ai", ykey))
        models[f"none_{ykey}_vs_units"] = linreg(*pack(none, "units_ai", ykey))
        # all points: exe = c0 + c_u*units + c_m*units*moving
        X = []
        y = []
        for r in rows:
            u = float(r["units_ai"])
            m = float(r["moving"])
            X.append([1.0, u, u * m])
            y.append(float(r[ykey]))
        models[f"two_factor_{ykey}"] = multireg(
            np.array(X), np.array(y), ["intercept", "units", "units_x_moving"]
        )
        # waypoint density at fixed units (g=24): vs wp_total
        dens_move = [r for r in dens if r["wp_mode"] != "none"]
        if dens_move:
            models[f"g24_moving_{ykey}_vs_wp_total"] = linreg(
                *pack(dens_move, "wp_total", ykey)
            )

    # Marginal costs from cycle2 slope
    c = models["cycle2_exe_fn_vs_units"]
    n = models["none_exe_fn_vs_units"]
    cost = {
        "exe_fn_per_moving_unit": c["a"] if c else None,
        "exe_fn_per_standing_unit": n["a"] if n else None,
        "exe_pct_per_moving_unit": models["cycle2_exe_pct_vs_units"]["a"],
        "exe_pct_per_standing_unit": models["none_exe_pct_vs_units"]["a"],
        "move_vs_stand_ratio": (
            (c["a"] / n["a"]) if c and n and n["a"] != 0 else None
        ),
    }

    payload = {
        "protocol": {
            "exe": "arma3server_x64",
            "mission": "GP_ServerTest.Altis",
            "metric": "gpsample exe_fn / exe_pct (interval 50ms, ~55s)",
            "per_group": 4,
            "note": "diag_fps is NOT used (≈28 constant on this DS)",
        },
        "rows": sorted(rows, key=lambda r: (r["wp_mode"], r["groups"])),
        "models": models,
        "marginal_cost": cost,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    # Markdown
    lines = []
    lines.append("# 17 · AI / 路点性能开销表（无头 DS）")
    lines.append("")
    lines.append("日期：2026-10-24  ")
    lines.append(
        "指标：`gpsample` **exe_fn**（窗口内命中主 exe 函数次数）与 **exe%**；"
        "**不用** `diag_fps`（本机 DS ≈28 常数）。  "
    )
    lines.append("协议：`server/sweep-ai-wp.ps1` · 原始：`extract/cpu_samples/sweep_g*.json`  ")
    lines.append("模型：`extract/cpu_samples/ai_wp_cost_model.json`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. 测量网格")
    lines.append("")
    lines.append("| groups | units | wp_mode | wp/组 | wp 总数 | exe_fn | exe% |")
    lines.append("|---:|---:|---|---:|---:|---:|---:|")
    for r in sorted(rows, key=lambda x: (x["wp_mode"], x["groups"])):
        lines.append(
            f"| {r['groups']} | {r['units_ai']} | `{r['wp_mode']}` | "
            f"{r['wp_per_group']} | {r['wp_total']} | {r['exe_fn']} | {r['exe_pct']:.4f} |"
        )
    lines.append("")
    lines.append("路点模式：`none` = 禁 PATH/MOVE；`move1` = 单 MOVE；"
                 "`cycle2` = MOVE+CYCLE；`cycle4` = 4×MOVE+CYCLE。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. 拟合公式")
    lines.append("")
    lines.append("### 2.1 仅巡逻（cycle2）：线性于单位数")
    lines.append("")
    cm = models["cycle2_exe_fn_vs_units"]
    cp = models["cycle2_exe_pct_vs_units"]
    lines.append(
        f"- **exe_fn ≈ {cm['a']:.3f} · U + {cm['b']:.2f}**"
        f"　(R²={cm['r2']:.4f}, RMSE={cm['rmse']:.1f}, n={cm['n']})"
    )
    lines.append(
        f"- **exe% ≈ {cp['a']:.5f} · U + {cp['b']:.4f}**"
        f"　(R²={cp['r2']:.4f}, RMSE={cp['rmse']:.4f})"
    )
    lines.append("")
    lines.append("其中 **U = groups × 4**（每组 4 人）。")
    lines.append("")
    lines.append("### 2.2 仅站岗（none）：线性于单位数")
    lines.append("")
    nm = models["none_exe_fn_vs_units"]
    npct = models["none_exe_pct_vs_units"]
    lines.append(
        f"- **exe_fn ≈ {nm['a']:.3f} · U + {nm['b']:.2f}**"
        f"　(R²={nm['r2']:.4f}, RMSE={nm['rmse']:.1f})"
    )
    lines.append(
        f"- **exe% ≈ {npct['a']:.5f} · U + {npct['b']:.4f}**"
        f"　(R²={npct['r2']:.4f})"
    )
    lines.append("")
    lines.append("### 2.3 双因子（全体点）")
    lines.append("")
    lines.append("令 `M=1` 表示移动（move1/cycle*），`M=0` 表示站岗：")
    lines.append("")
    tf = models["two_factor_exe_fn"]
    c = tf["coef"]
    lines.append(
        f"**exe_fn ≈ {c['intercept']:.2f} + {c['units']:.3f}·U "
        f"+ {c['units_x_moving']:.3f}·(U·M)**"
        f"　(R²={tf['r2']:.4f}, RMSE={tf['rmse']:.1f})"
    )
    lines.append("")
    tp = models["two_factor_exe_pct"]
    c2 = tp["coef"]
    lines.append(
        f"**exe% ≈ {c2['intercept']:.4f} + {c2['units']:.5f}·U "
        f"+ {c2['units_x_moving']:.5f}·(U·M)**"
        f"　(R²={tp['r2']:.4f})"
    )
    lines.append("")
    lines.append("### 2.4 固定 24 组时，路点「个数」几乎无关")
    lines.append("")
    lines.append("| wp_mode | wp 总数 | exe_fn | exe% |")
    lines.append("|---|---:|---:|---:|")
    for r in sorted(dens, key=lambda x: x["wp_total"]):
        lines.append(
            f"| `{r['wp_mode']}` | {r['wp_total']} | {r['exe_fn']} | {r['exe_pct']:.4f} |"
        )
    lines.append("")
    wfit = models.get("g24_moving_exe_fn_vs_wp_total")
    if wfit:
        lines.append(
            f"仅移动点对 `wp_total` 线性拟合：斜率 **{wfit['a']:.4f} exe_fn / 路点**"
            f"（R²={wfit['r2']:.3f}）→ **路点条数不是主因**；"
            f"**是否在移动**才是主因（none→move 跃迁远大于 move1→cycle4）。"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. 边际开销（便于任务预算）")
    lines.append("")
    lines.append("| 量 | 数值 | 含义 |")
    lines.append("|---|---:|---|")
    lines.append(
        f"| 每 **移动** AI（cycle2 斜率） | **{cost['exe_fn_per_moving_unit']:.2f}** exe_fn "
        f"/ **{cost['exe_pct_per_moving_unit']*100:.3f}**‰ exe | 巡逻单位 |"
    )
    lines.append(
        f"| 每 **站岗** AI（none 斜率） | **{cost['exe_fn_per_standing_unit']:.2f}** exe_fn "
        f"/ **{cost['exe_pct_per_standing_unit']*100:.3f}**‰ exe | 禁 PATH |"
    )
    if cost["move_vs_stand_ratio"]:
        lines.append(
            f"| 移动/站岗 比值 | **{cost['move_vs_stand_ratio']:.2f}×** | "
            f"同人数下巡逻约为站岗的该倍数 |"
        )
    lines.append("")
    lines.append("### 速算示例（exe_fn，cycle2 公式）")
    lines.append("")
    lines.append("| 目标单位（巡逻） | 预估 exe_fn | 预估 exe% |")
    lines.append("|---:|---:|---:|")
    for u in (32, 64, 96, 128, 192):
        ef = cm["a"] * u + cm["b"]
        ep = cp["a"] * u + cp["b"]
        lines.append(f"| {u} | {ef:.0f} | {ep:.3f} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 4. 结论（任务设计）")
    lines.append("")
    lines.append("1. **exe 开销 ≈ 线性于 AI 人数**（移动与站岗各自一条直线，R² 高）。")
    lines.append(
        "2. **路点数量（1/2/5）在已移动前提下几乎无增量**；"
        "从 `none` 打开移动才出现阶跃。"
    )
    lines.append(
        "3. 性能预算优先：**少单位** 与 **能站岗就禁 PATH**；"
        "不要指望靠「少写几个 waypoint」省 CPU。"
    )
    lines.append("4. 复跑：`powershell -File server\\sweep-ai-wp.ps1 -Groups 24 -WpMode cycle2`")
    lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", OUT_JSON)
    print("wrote", OUT_MD)
    print("marginal", cost)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
