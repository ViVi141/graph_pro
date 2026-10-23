# -*- coding: utf-8 -*-
"""Export full YAAB overlap as three synced H.264 clips + triple-compare HTML.

Columns: 原版 | 全局调色最佳拟合 | 注入
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

DEMO = Path(r"c:\Users\74738\Desktop\Projects\Arma3\graph_pro\demo")
INJ_SRC = Path(r"C:\Users\74738\Videos\2026-10-23 23-41-19.mp4")
VAN_SRC = Path(r"C:\Users\74738\Videos\2026-10-23 23-45-17.mp4")
DELTA = 262  # vanilla_frame = inject_frame + DELTA
BR, CO, SA, GA = 0.006364, 0.984077, 1.014909, 1.349000

OUT_W, OUT_H = 960, 540
OUT_FPS = 30.0  # source 60 → drop every other frame


def apply_grade(
    img: np.ndarray, brightness: float, contrast: float, saturation: float, gamma: float
) -> np.ndarray:
  x = img.astype(np.float32) / 255.0
  x = np.power(np.maximum(x, 1e-6), gamma)
  x = (x - 0.5) * contrast + 0.5 + brightness
  x = np.clip(x, 0.0, 1.0)
  g = (0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2])[..., None]
  x = np.clip(g + (x - g) * saturation, 0.0, 1.0)
  return (x * 255.0).astype(np.uint8)


def open_writer(path: Path) -> subprocess.Popen:
  ff = imageio_ffmpeg.get_ffmpeg_exe()
  cmd = [
      ff,
      "-y",
      "-f",
      "rawvideo",
      "-pix_fmt",
      "rgb24",
      "-s",
      f"{OUT_W}x{OUT_H}",
      "-r",
      str(OUT_FPS),
      "-i",
      "-",
      "-an",
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-preset",
      "veryfast",
      "-crf",
      "24",
      "-movflags",
      "+faststart",
      str(path),
  ]
  return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)


def main() -> None:
  DEMO.mkdir(parents=True, exist_ok=True)
  paths = {
      "vanilla": DEMO / "yaab-triple-vanilla.mp4",
      "graded": DEMO / "yaab-triple-graded.mp4",
      "inject": DEMO / "yaab-triple-inject.mp4",
  }
  writers = {k: open_writer(p) for k, p in paths.items()}

  ci = cv2.VideoCapture(str(INJ_SRC))
  cv_ = cv2.VideoCapture(str(VAN_SRC))
  n_i = int(ci.get(cv2.CAP_PROP_FRAME_COUNT))
  n_v = int(cv_.get(cv2.CAP_PROP_FRAME_COUNT))
  fps_src = float(ci.get(cv2.CAP_PROP_FPS) or 60.0)
  i0 = max(0, -DELTA)
  i1 = min(n_i, n_v - DELTA)
  overlap = i1 - i0
  print(f"overlap inject[{i0},{i1}) = {overlap}f ({overlap/fps_src:.1f}s)", flush=True)

  ci.set(cv2.CAP_PROP_POS_FRAMES, i0)
  cv_.set(cv2.CAP_PROP_POS_FRAMES, i0 + DELTA)

  written = 0
  for src_off in range(overlap):
    ok_i, inj_bgr = ci.read()
    ok_v, van_bgr = cv_.read()
    if not ok_i or not ok_v:
      break
    if src_off % 2 != 0:
      continue  # 60 → 30

    inj = cv2.cvtColor(inj_bgr, cv2.COLOR_BGR2RGB)
    van = cv2.cvtColor(van_bgr, cv2.COLOR_BGR2RGB)
    inj = cv2.resize(inj, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
    van = cv2.resize(van, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
    graded = apply_grade(van, BR, CO, SA, GA)

    for key, frame in (("vanilla", van), ("graded", graded), ("inject", inj)):
      writers[key].stdin.write(frame.tobytes())
    written += 1
    if written % 300 == 0:
      print(f"  {written} out frames ({written/OUT_FPS:.1f}s)", flush=True)

  for w in writers.values():
    w.stdin.close()
    w.wait()
  ci.release()
  cv_.release()
  print(f"wrote {written} frames @ {OUT_FPS}fps", flush=True)
  for k, p in paths.items():
    print(f"  {p.name} {p.stat().st_size/1e6:.1f} MB", flush=True)

  html = DEMO / "yaab-triple-compare.html"
  html.write_text(
      HTML_TMPL.format(
          br=BR,
          co=CO,
          sa=SA,
          ga=GA,
          delta=DELTA,
          dur=written / OUT_FPS,
          overlap=overlap / fps_src,
      ),
      encoding="utf-8",
  )
  print("wrote", html, flush=True)


HTML_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>YAAB 三联对比 · 原版 / 全局调色 / 注入</title>
  <style>
    :root {{
      --bg: #0c0d10;
      --panel: #15171c;
      --text: #e9ebf0;
      --muted: #9aa3b2;
      --accent: #e8b84a;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0; min-height: 100%;
      background: radial-gradient(1000px 500px at 50% -5%, #1a2230 0%, var(--bg) 50%);
      color: var(--text);
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    }}
    main {{ max-width: 1600px; margin: 0 auto; padding: 22px 16px 40px; }}
    h1 {{ margin: 0 0 6px; font-size: 1.35rem; font-weight: 650; }}
    .sub {{ margin: 0 0 18px; color: var(--muted); font-size: 0.9rem; line-height: 1.5; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      background: var(--panel);
      border: 1px solid #2a2f3a;
      border-radius: 12px;
      padding: 10px;
    }}
    @media (max-width: 980px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
    .col {{
      position: relative;
      background: #000;
      border-radius: 8px;
      overflow: hidden;
      aspect-ratio: 16 / 9;
    }}
    .col video {{
      width: 100%; height: 100%;
      object-fit: contain;
      display: block;
      background: #000;
    }}
    .label {{
      position: absolute; left: 10px; top: 10px; z-index: 2;
      padding: 5px 9px; border-radius: 6px;
      font-size: 0.78rem; font-weight: 650; letter-spacing: 0.03em;
      backdrop-filter: blur(6px);
      pointer-events: none;
    }}
    .l-van {{ background: rgba(230,232,236,0.92); color: #111; }}
    .l-grade {{ background: rgba(180,200,255,0.92); color: #0a1020; }}
    .l-inj {{ background: rgba(94,200,255,0.92); color: #041018; }}
    .controls {{
      display: flex; flex-wrap: wrap; gap: 12px 16px;
      align-items: center; margin-top: 14px;
    }}
    button {{
      appearance: none; border: 1px solid #3a4150; background: #222833;
      color: var(--text); border-radius: 8px; padding: 8px 14px;
      font: inherit; cursor: pointer;
    }}
    button:hover {{ border-color: var(--accent); }}
    .slider-row {{
      flex: 1 1 280px; display: flex; align-items: center; gap: 10px; min-width: 200px;
    }}
    .slider-row label {{ color: var(--muted); font-size: 0.85rem; white-space: nowrap; }}
    input[type="range"] {{ width: 100%; accent-color: var(--accent); }}
    .time {{
      font-variant-numeric: tabular-nums; color: var(--muted);
      font-size: 0.85rem; min-width: 8rem;
    }}
    .hint {{ margin-top: 12px; color: var(--muted); font-size: 0.82rem; }}
    .err {{
      display: none; margin-top: 10px; padding: 10px 12px; border-radius: 8px;
      background: #3a1f1f; color: #ffc9c9; font-size: 0.88rem;
    }}
  </style>
</head>
<body>
  <main>
    <h1>YAAB 三联对比（全长对齐）</h1>
    <p class="sub">
      左：原版 · 中：原版 + 全局调色最佳拟合（同一组 br/con/sat/gamma）· 右：注入<br />
      对齐 Δ={delta}f · 导出约 {dur:.0f}s（源重叠 {overlap:.0f}s @30fps 960×540）·
      调色 br{br:+.3f} con{co:.2f} sat{sa:.2f} gam{ga:.2f}<br />
      空格播放/暂停 · 三路同步。
    </p>

    <div class="grid" id="grid">
      <div class="col">
        <span class="label l-van">原版</span>
        <video id="v0" muted playsinline preload="auto" src="yaab-triple-vanilla.mp4"></video>
      </div>
      <div class="col">
        <span class="label l-grade">全局调色拟合</span>
        <video id="v1" muted playsinline preload="auto" src="yaab-triple-graded.mp4"></video>
      </div>
      <div class="col">
        <span class="label l-inj">注入</span>
        <video id="v2" muted playsinline preload="auto" src="yaab-triple-inject.mp4"></video>
      </div>
    </div>

    <div class="controls">
      <button type="button" id="btn-play">播放</button>
      <button type="button" id="btn-restart">重头</button>
      <div class="slider-row">
        <label for="seek">进度</label>
        <input id="seek" type="range" min="0" max="1000" value="0" />
      </div>
      <span class="time" id="time">0:00 / 0:00</span>
    </div>
    <div class="err" id="err"></div>
    <p class="hint">本地打开：在 demo 目录执行 <code>python -m http.server 8765</code> →
      <code>http://127.0.0.1:8765/yaab-triple-compare.html</code></p>
  </main>
  <script>
    const vids = [document.getElementById("v0"), document.getElementById("v1"), document.getElementById("v2")];
    const btnPlay = document.getElementById("btn-play");
    const btnRestart = document.getElementById("btn-restart");
    const seek = document.getElementById("seek");
    const timeEl = document.getElementById("time");
    const errEl = document.getElementById("err");
    let playing = false;
    let scrubbing = false;
    const master = vids[0];

    function fmt(t) {{
      if (!Number.isFinite(t)) return "0:00";
      const s = Math.floor(t % 60).toString().padStart(2, "0");
      return `${{Math.floor(t / 60)}}:${{s}}`;
    }}
    function syncAll(t) {{
      for (const v of vids) {{
        if (Math.abs(v.currentTime - t) > 0.08) v.currentTime = t;
      }}
    }}
    function tick() {{
      const t = master.currentTime;
      const d = master.duration || 0;
      if (!scrubbing && d > 0) seek.value = String(Math.round((t / d) * 1000));
      timeEl.textContent = `${{fmt(t)}} / ${{fmt(d)}}`;
      for (const v of vids) {{
        if (v === master) continue;
        if (Math.abs(v.currentTime - t) > 0.12) v.currentTime = t;
      }}
    }}
    async function playAll() {{
      try {{
        await Promise.all(vids.map((v) => v.play()));
        playing = true;
        btnPlay.textContent = "暂停";
      }} catch (e) {{
        errEl.style.display = "block";
        errEl.textContent = "无法播放，请用本地 http.server 打开本页。";
      }}
    }}
    function pauseAll() {{
      vids.forEach((v) => v.pause());
      playing = false;
      btnPlay.textContent = "播放";
    }}
    btnPlay.addEventListener("click", () => (playing ? pauseAll() : playAll()));
    btnRestart.addEventListener("click", () => {{ syncAll(0); tick(); }});
    seek.addEventListener("pointerdown", () => {{ scrubbing = true; }});
    seek.addEventListener("pointerup", () => {{ scrubbing = false; }});
    seek.addEventListener("input", () => {{
      const d = master.duration || 0;
      if (!d) return;
      syncAll((Number(seek.value) / 1000) * d);
      tick();
    }});
    master.addEventListener("timeupdate", tick);
    master.addEventListener("ended", pauseAll);
    vids.forEach((v) => v.addEventListener("error", () => {{
      errEl.style.display = "block";
      errEl.textContent = "视频加载失败：" + (v.currentSrc || v.src);
    }}));
    window.addEventListener("keydown", (ev) => {{
      if (ev.code === "Space") {{
        ev.preventDefault();
        playing ? pauseAll() : playAll();
      }}
    }});
    Promise.all(vids.map((v) => new Promise((r) => v.addEventListener("loadedmetadata", r, {{ once: true }}))))
      .then(tick);
  </script>
</body>
</html>
"""


if __name__ == "__main__":
  main()
