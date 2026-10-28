#!/usr/bin/env python3
"""Turn a probe capture into one report.

Reads the files the proxy writes next to the game exe:

    GP_passseq.txt   one frame, every fullscreen pass, in execution order
                     (idx crc psLen in out fmt src sfmt min..max mean/>1%)
    GP_upscale.txt   every upscale candidate seen this session (prio, hits)
    GP_shaders.txt   every pixel shader the game created (crc len bytes)

and prints/writes a single markdown summary: what the post-process chain looks
like, which pass is the final stretch, what colour space each stage works in,
and which passes we could replace.

Usage:
    python tools/analyze_capture.py                 # reads the game directory
    python tools/analyze_capture.py <dir>           # or any captured folder
    python tools/analyze_capture.py <dir> -o out.md
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

DEFAULT_DIR = os.environ.get("ARMA3_DIR", "")

FMT = {
    2: "RGBA32F", 6: "R32G32B32A32?", 10: "RGBA16F", 24: "RGB10A2",
    26: "R11G11B10F", 28: "RGBA8", 29: "RGBA8_sRGB", 34: "RG16F",
    41: "R32F", 54: "R16F", 61: "R8", 76: "RGBA8_TYPELESS",
    87: "BGRA8", 88: "BGRX8", 90: "D32F", 91: "R32_TYPELESS",
}
KNOWN_SHADERS = {
    0x42670B06: "tonemap (we replace this with AgX)",
    0xB682EAC0: "final stretch / upscale",
    0x850EE87F: "SSAO final (we replace this)",
    0x9576A9FE: "UI / 2D pass writing the backbuffer",
    0x5EB60161: "UI / 2D pass writing the backbuffer",
}


def fmt_name(v: int) -> str:
    return FMT.get(v, "fmt%d" % v)


def parse_passseq(path: Path) -> tuple[dict, list[dict]]:
    """Returns (header, rows). Tolerates both the old and the new column set."""
    header: dict[str, str] = {}
    rows: list[dict] = []
    if not path.exists():
        return header, rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("# capture:"):
            m = re.search(r"backbuffer=(\d+)x(\d+).*render=(\d+)x(\d+)", s)
            if m:
                header.update(bb=(int(m.group(1)), int(m.group(2))),
                              render=(int(m.group(3)), int(m.group(4))))
            m2 = re.search(r"present=(\d+)", s)
            if m2:
                header["present"] = m2.group(1)
            continue
        if s.startswith("#") or not s or s.startswith("idx"):
            continue
        f = s.split()
        if len(f) < 6:
            continue
        try:
            def wh(tok: str):
                x, y = tok.split("x")
                return (int(x), int(y))

            row = {
                "idx": int(f[0]),
                "crc": int(f[1], 16),
                "psLen": int(f[2]),
                "in": wh(f[3]),
                "out": wh(f[4]),
                "fmt": f[5],
                "src": None, "sfmt": None, "range": None, "tail": None,
            }
            if len(f) > 6 and f[6] != "-":
                row["src"] = wh(f[6])
            if len(f) > 7 and f[7] != "-":
                row["sfmt"] = f[7]
            if len(f) > 8 and ".." in f[8]:
                row["range"] = f[8]
            if len(f) > 9:
                row["tail"] = f[9]
            rows.append(row)
        except (IndexError, ValueError):
            continue
    return header, rows


def parse_candidates(path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*(\d)\s+(\d+)x(\d+)\s+(\d+)x(\d+)\s+(\S+)\s+(\d+)\s+([0-9A-Fa-f]{8})\s+(\S+)\s+hits=(\d+)", line)
        if m:
            out.append({
                "prio": int(m.group(1)),
                "in": (int(m.group(2)), int(m.group(3))),
                "out": (int(m.group(4)), int(m.group(5))),
                "fmt": m.group(6),
                "psLen": int(m.group(7)),
                "crc": int(m.group(8), 16),
                "via": m.group(9),
                "hits": int(m.group(10)),
            })
    return out


def parse_shaders(path: Path) -> list[tuple[int, int]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            continue
        f = line.split()
        if len(f) >= 2:
            try:
                out.append((int(f[0], 16), int(f[1])))
            except ValueError:
                pass
    return out


def colour(row: dict) -> str:
    """HDR / LDR / unknown from the captured min..max column."""
    if not row.get("range"):
        return "?"
    try:
        lo_s, hi_s = row["range"].split("..")
        lo, hi = float(lo_s), float(hi_s)
    except (ValueError, IndexError):
        return "?"
    if lo == 0.0 and hi == 0.0:
        return "?"          # nothing was read (empty/unsupported capture)
    return "HDR" if hi > 1.5 else "LDR"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # CJK out to a GBK console
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default=DEFAULT_DIR)
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    if not a.dir:
        print("pass a capture directory, or set ARMA3_DIR", file=sys.stderr)
        return 2
    d = Path(a.dir)
    header, rows = parse_passseq(d / "GP_passseq.txt")
    cands = parse_candidates(d / "GP_upscale.txt")
    shaders = parse_shaders(d / "GP_shaders.txt")
    bb = header.get("bb")
    render = header.get("render")

    L: list[str] = []
    L.append("# 探针抓帧分析")
    L.append("")
    L.append(f"- 目录：`{d}`")
    if bb and render:
        L.append(f"- backbuffer：**{bb[0]}x{bb[1]}**；内部渲染：**{render[0]}x{render[1]}**"
                 f"（{100.0 * render[0] / bb[0]:.0f}% 采样），抓帧 = present #{header.get('present', '?')}")
    elif bb:
        L.append(f"- backbuffer：**{bb[0]}x{bb[1]}**；内部渲染：**未知**")
    L.append(f"- 本帧全屏 pass 数：**{len(rows)}**；会话内候选签名：**{len(cands)}**；已记录 PS：**{len(shaders)}**")
    if len(rows) < 6:
        L.append("")
        L.append(f"> **低置信度**：本帧只抓到 {len(rows)} 个 fullscreen pass。"
                 "完整的后处理链通常有几十个 pass；2 个 pass 很可能是菜单/加载帧或探针未就绪。"
                 "下面的“最终拉伸”结论只在输入尺寸等于内部渲染尺寸时才可信。")
    if not render:
        L.append("")
        L.append("> `GP_passseq.txt` 没有内部渲染尺寸；无法区分“最终拉伸”和 UI/清屏 pass。")
    L.append("")

    if not rows:
        L.append("> `GP_passseq.txt` 缺失或为空。确认游戏目录里有 `GP_probe_scale.txt`，"
                 "并且启动后至少跑过 240 帧（探针在 240 帧后抓帧）。")
        text = "\n".join(L)
        print(text)
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
        return 1

    # --- chain table -------------------------------------------------------
    L.append("## 后处理链（执行顺序）")
    L.append("")
    L.append("| # | PS crc | psLen | 输入 | 输出 | fmt | 采样源 | 源范围 | 判读 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        tag = ""
        if bb and render and r["out"] == bb and r["in"] == render:
            tag = "**← 最终拉伸**"
        elif render and r["in"] == render and r["out"] == render:
            tag = "内部渲染尺寸"
        elif bb and r["out"] == bb:
            tag = "写 backbuffer"
        L.append("| %d | %08X | %d | %dx%d | %dx%d | %s/%s | %s | %s | %s |" % (
            r["idx"], r["crc"], r["psLen"], r["in"][0], r["in"][1], r["out"][0], r["out"][1],
            fmt_name(int(r["fmt"].split("/")[0])), fmt_name(int(r["fmt"].split("/")[1])),
            "%dx%d %s" % (r["src"][0], r["src"][1], fmt_name(int(r["sfmt"]))) if r["src"] and r["sfmt"] else "-",
            r["range"] or "-", tag or colour(r)))
    L.append("")

    # --- verdicts ----------------------------------------------------------
    complete = bool(render) and len(rows) >= 6
    stretch = [r for r in rows if bb and render and r["out"] == bb and r["in"] == render]
    cand_stretch = [c for c in cands if bb and render and c["out"] == bb and c["in"] == render]
    L.append("## 结论")
    L.append("")
    if stretch:
        s = stretch[-1]
        if not complete:
            L.append("> 低置信度：本帧 pass 数不足，以下结论只基于这一条尺寸匹配的 pass。")
        L.append(f"1. **最终拉伸是一个 PS draw**：`{s['crc']:08X}`，`psLen={s['psLen']}`，"
                 f"{s['in'][0]}x{s['in'][1]} → {s['out'][0]}x{s['out'][1]}，"
                 f"{fmt_name(int(s['fmt'].split('/')[0]))} → {fmt_name(int(s['fmt'].split('/')[1]))}。")
        L.append(f"2. 该 pass 的采样源判读为 **{colour(s)}**"
                 + ("（EASU 可直接用；替换件不必再 tonemap）" if colour(s) == "LDR"
                    else "（HDR：替换件必须先 tonemap，否则会少一道色调映射）" if colour(s) == "HDR"
                    else "（本帧没读到源范围：该输入为空、格式不支持，或读取时机不对）") + "。")
        L.append(f"3. 要替换它，`GP_replace.txt` 写 `{s['psLen']} {s['crc']:08X} <payload.dxbc>`；"
                 "**psLen 会随分辨率/采样率变**，换配置必须重采。")
    elif cand_stretch:
        c = sorted(cand_stretch, key=lambda c: -c["hits"])[0]
        L.append(f"1. 本帧没有抓到“输入 == 内部渲染尺寸 → backbuffer”的 pass；"
                 f"但会话候选表里有 `{c['crc']:08X}`（{c['in'][0]}x{c['in'][1]} → {c['out'][0]}x{c['out'][1]}，"
                 f"psLen={c['psLen']}，hits={c['hits']}）。")
        L.append("2. 这个候选很可能就是拉伸；但缺少这一帧的 pass 顺序，不能确认它相对 tonemap 的位置。")
        L.append("3. 重跑一次探针，等场景稳定后再抓帧；不要用菜单/加载帧做结论。")
    else:
        L.append("1. 本帧没有“输入 == 内部渲染尺寸且写到 backbuffer”的 pass —— "
                 "放大可能不在 PS 里，或抓帧时 Sampling 是 100%，或抓到了菜单帧。")
    hdr = [r for r in rows if colour(r) == "HDR"]
    if hdr:
        L.append("4. 链上处于 HDR 阶段的 pass："
                 + "、".join(f"#{r['idx']} {r['crc']:08X}" for r in hdr[:8]) + "。")
    L.append("")

    # --- candidates --------------------------------------------------------
    if cands:
        L.append("## 候选签名（整局）")
        L.append("")
        L.append("| prio | 输入 | 输出 | psLen | psCrc | via | hits |")
        L.append("|---|---|---|---|---|---|---|")
        for c in sorted(cands, key=lambda c: (-c["prio"], -c["hits"]))[:20]:
            L.append("| %d | %dx%d | %dx%d | %d | %08X | %s | %d |" % (
                c["prio"], c["in"][0], c["in"][1], c["out"][0], c["out"][1],
                c["psLen"], c["crc"], c["via"], c["hits"]))
        L.append("")

    # --- shader table ------------------------------------------------------
    if shaders:
        L.append("## 可替换的 shader（按体积排序，取前 20）")
        L.append("")
        L.append("| crc | psLen | 备注 |")
        L.append("|---|---|---|")
        for crc, ln in sorted(shaders, key=lambda x: -x[1])[:20]:
            L.append("| %08X | %d | %s |" % (crc, ln, KNOWN_SHADERS.get(crc, "")))
        L.append("")

    text = "\n".join(L)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"\n[written] {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
