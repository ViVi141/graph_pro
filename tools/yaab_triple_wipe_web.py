# -*- coding: utf-8 -*-
"""Export YAAB from content start (inj 31s / van 35s) + triple wipe HTML."""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

DEMO = Path(r"c:\Users\user\Desktop\Projects\Arma3\graph_pro\demo")
INJ_SRC = Path(r"<USERPROFILE>\Videos\2026-10-23 23-41-19.mp4")
VAN_SRC = Path(r"<USERPROFILE>\Videos\2026-10-23 23-45-17.mp4")

# User anchors: cut everything before YAAB content
INJ_START_S = 31.0
VAN_START_S = 35.0
# Prefer explicit starts; delta for logging
DELTA = int(round((VAN_START_S - INJ_START_S) * 60))  # 240; refine below

BR, CO, SA, GA = 0.006364, 0.984077, 1.014909, 1.349000
OUT_W, OUT_H = 960, 540
OUT_FPS = 30.0


def apply_grade(rgb_u8: np.ndarray) -> np.ndarray:
  x = rgb_u8.astype(np.float32) / 255.0
  x = np.power(np.maximum(x, 1e-6), GA)
  x = (x - 0.5) * CO + 0.5 + BR
  x = np.clip(x, 0.0, 1.0)
  g = (0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2])[..., None]
  x = np.clip(g + (x - g) * SA, 0.0, 1.0)
  return (x * 255.0).astype(np.uint8)


def to_sig(bgr: np.ndarray) -> np.ndarray:
  g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
  g = cv2.resize(g, (128, 72), interpolation=cv2.INTER_AREA).astype(np.float32)
  return g - g.mean()


def refine_van_start(ci: cv2.VideoCapture, cv_: cv2.VideoCapture, fi: int, fv0: int, radius: int = 40) -> int:
  """Find vanilla frame near fv0 that best matches inject frame fi."""
  ci.set(cv2.CAP_PROP_POS_FRAMES, fi)
  ok, a = ci.read()
  if not ok:
    return fv0
  sa = to_sig(a)
  best = (fv0, -1e9)
  for fv in range(max(0, fv0 - radius), fv0 + radius + 1):
    cv_.set(cv2.CAP_PROP_POS_FRAMES, fv)
    ok, b = cv_.read()
    if not ok:
      continue
    sb = to_sig(b)
    c = float((sa * sb).mean() / (sa.std() * sb.std() + 1e-6))
    if c > best[1]:
      best = (fv, c)
  print(f"refine: inj@{fi} best van@{best[0]} corr={best[1]:.3f}", flush=True)
  return best[0]


def skip_to(cap: cv2.VideoCapture, target: int) -> None:
  """Frame-accurate skip by sequential decode (avoids keyframe seek error)."""
  cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, target - 60))
  cur = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
  while cur < target:
    if not cap.read()[0]:
      break
    cur += 1


def open_writer(path: Path) -> subprocess.Popen:
  ff = imageio_ffmpeg.get_ffmpeg_exe()
  cmd = [
      ff, "-y",
      "-f", "rawvideo", "-pix_fmt", "rgb24",
      "-s", f"{OUT_W}x{OUT_H}", "-r", str(OUT_FPS),
      "-i", "-",
      "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
      "-preset", "veryfast", "-crf", "24",
      "-movflags", "+faststart",
      str(path),
  ]
  return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)


def main() -> None:
  DEMO.mkdir(parents=True, exist_ok=True)
  ci = cv2.VideoCapture(str(INJ_SRC))
  cv_ = cv2.VideoCapture(str(VAN_SRC))
  fps_i = float(ci.get(cv2.CAP_PROP_FPS) or 60.0)
  fps_v = float(cv_.get(cv2.CAP_PROP_FPS) or 60.0)
  n_i = int(ci.get(cv2.CAP_PROP_FRAME_COUNT))
  n_v = int(cv_.get(cv2.CAP_PROP_FRAME_COUNT))

  fi0 = int(round(INJ_START_S * fps_i))
  fv0 = int(round(VAN_START_S * fps_v))
  fv0 = refine_van_start(ci, cv_, fi0, fv0, radius=48)
  delta = fv0 - fi0
  print(f"content start: inject f{fi0} ({fi0/fps_i:.2f}s)  vanilla f{fv0} ({fv0/fps_v:.2f}s)  Δ={delta}", flush=True)

  # remaining length limited by shorter tail
  remain = min(n_i - fi0, n_v - fv0)
  print(f"export {remain} src frames ({remain/fps_i:.1f}s) → {remain//2} out @30fps", flush=True)

  paths = {
      "vanilla": DEMO / "yaab-wipe-vanilla.mp4",
      "graded": DEMO / "yaab-wipe-graded.mp4",
      "inject": DEMO / "yaab-wipe-inject.mp4",
  }
  writers = {k: open_writer(p) for k, p in paths.items()}

  skip_to(ci, fi0)
  skip_to(cv_, fv0)

  written = 0
  for src_off in range(remain):
    ok_i, inj_bgr = ci.read()
    ok_v, van_bgr = cv_.read()
    if not ok_i or not ok_v:
      break
    if src_off % 2 != 0:
      continue
    inj = cv2.resize(cv2.cvtColor(inj_bgr, cv2.COLOR_BGR2RGB), (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
    van = cv2.resize(cv2.cvtColor(van_bgr, cv2.COLOR_BGR2RGB), (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
    grd = apply_grade(van)
    for key, fr in (("vanilla", van), ("graded", grd), ("inject", inj)):
      writers[key].stdin.write(fr.tobytes())
    written += 1
    if written % 300 == 0:
      print(f"  {written} ({written/OUT_FPS:.1f}s)", flush=True)

  for w in writers.values():
    w.stdin.close()
    w.wait()
  ci.release()
  cv_.release()

  # quick verify first / mid frame corr
  def corr_at(f: int) -> float:
    a = cv2.VideoCapture(str(paths["vanilla"]))
    b = cv2.VideoCapture(str(paths["inject"]))
    a.set(cv2.CAP_PROP_POS_FRAMES, f)
    b.set(cv2.CAP_PROP_POS_FRAMES, f)
    ok1, ia = a.read()
    ok2, ib = b.read()
    a.release()
    b.release()
    if not ok1 or not ok2:
      return -1.0
    sa = to_sig(ia)
    sb = to_sig(ib)
    return float((sa * sb).mean() / (sa.std() * sb.std() + 1e-6))

  print(f"verify corr t0={corr_at(0):.3f} t30={corr_at(min(900, written-1)):.3f}", flush=True)
  for k, p in paths.items():
    print(f"  {p.name} {p.stat().st_size/1e6:.1f}MB", flush=True)

  html_path = DEMO / "yaab-triple-wipe.html"
  html_path.write_text(
      HTML.format(
          br=BR, co=CO, sa=SA, ga=GA,
          inj_s=INJ_START_S, van_s=VAN_START_S, delta=delta,
          dur=written / OUT_FPS,
      ),
      encoding="utf-8",
  )
  print("wrote", html_path, flush=True)


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>YAAB 三联同屏滑条 · 原版 / 调色 / 注入</title>
  <style>
    :root {{
      --bg: #0c0d10; --panel: #15171c; --text: #e9ebf0; --muted: #9aa3b2;
      --accent: #e8b84a; --line: #f4f6fa;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0; min-height: 100%;
      background: radial-gradient(1100px 520px at 50% -8%, #1a2230 0%, var(--bg) 52%);
      color: var(--text);
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 22px 16px 40px; }}
    h1 {{ margin: 0 0 6px; font-size: 1.35rem; font-weight: 650; }}
    .sub {{ margin: 0 0 16px; color: var(--muted); font-size: 0.9rem; line-height: 1.5; }}
    .stage-wrap {{
      background: var(--panel); border: 1px solid #2a2f3a; border-radius: 12px;
      padding: 12px; box-shadow: 0 18px 50px rgba(0,0,0,.35);
    }}
    .stage {{
      position: relative; width: 100%; aspect-ratio: 16/9;
      overflow: hidden; border-radius: 8px; background: #000;
      user-select: none; touch-action: none; cursor: ew-resize;
    }}
    .stage video {{
      position: absolute; inset: 0; width: 100%; height: 100%;
      object-fit: contain; pointer-events: none; background: #000;
    }}
    #v-van {{ z-index: 1; }}
    #v-grd {{ z-index: 2; }}
    #v-inj {{ z-index: 3; }}
    .divider {{
      position: absolute; top: 0; bottom: 0; width: 3px; margin-left: -1.5px;
      background: var(--line); z-index: 8;
      box-shadow: 0 0 0 1px rgba(0,0,0,.4); pointer-events: none;
    }}
    .divider::after {{
      content: ""; position: absolute; top: 50%; left: 50%;
      width: 34px; height: 34px; margin: -17px 0 0 -17px; border-radius: 50%;
      background: var(--line); box-shadow: 0 2px 10px rgba(0,0,0,.45);
    }}
    .tag {{
      position: absolute; top: 12px; z-index: 9; padding: 5px 9px; border-radius: 6px;
      font-size: .75rem; font-weight: 650; pointer-events: none;
      backdrop-filter: blur(6px);
    }}
    .tag-van {{ left: 12px; background: rgba(230,232,236,.92); color: #111; }}
    .tag-grd {{ left: 50%; transform: translateX(-50%); background: rgba(180,200,255,.92); color: #0a1020; }}
    .tag-inj {{ right: 12px; background: rgba(94,200,255,.92); color: #041018; }}
    .controls {{
      display: flex; flex-wrap: wrap; gap: 12px 16px; align-items: center; margin-top: 14px;
    }}
    button {{
      appearance: none; border: 1px solid #3a4150; background: #222833; color: var(--text);
      border-radius: 8px; padding: 8px 14px; font: inherit; cursor: pointer;
    }}
    button:hover {{ border-color: var(--accent); }}
    .row {{ flex: 1 1 200px; display: flex; align-items: center; gap: 10px; min-width: 180px; }}
    .row label {{ color: var(--muted); font-size: .85rem; white-space: nowrap; }}
    input[type=range] {{ width: 100%; accent-color: var(--accent); }}
    .time {{ font-variant-numeric: tabular-nums; color: var(--muted); font-size: .85rem; min-width: 7.5rem; }}
    .hint {{ margin-top: 12px; color: var(--muted); font-size: .82rem; }}
    .err {{ display:none; margin-top:10px; padding:10px 12px; border-radius:8px; background:#3a1f1f; color:#ffc9c9; font-size:.88rem; }}
  </style>
</head>
<body>
  <main>
    <h1>YAAB 三联同屏滑条对比</h1>
    <p class="sub">
      已截去启动段（注入 {inj_s:.0f}s / 原版 {van_s:.0f}s 起）· Δ={delta}f · 约 {dur:.0f}s<br />
      左→右：<b>原版</b> | <b>全局调色拟合</b> | <b>注入</b>
      （br{br:+.3f} con{co:.2f} sat{sa:.2f} gam{ga:.2f}）· 拖两条竖线或下方滑条 · 空格播放
    </p>
    <div class="stage-wrap">
      <div class="stage" id="stage">
        <video id="v-van" muted playsinline preload="auto" src="yaab-wipe-vanilla.mp4"></video>
        <video id="v-grd" muted playsinline preload="auto" src="yaab-wipe-graded.mp4"></video>
        <video id="v-inj" muted playsinline preload="auto" src="yaab-wipe-inject.mp4"></video>
        <div class="divider" id="d1"></div>
        <div class="divider" id="d2"></div>
        <span class="tag tag-van">原版</span>
        <span class="tag tag-grd">调色拟合</span>
        <span class="tag tag-inj">注入</span>
      </div>
      <div class="controls">
        <button type="button" id="btn-play">播放</button>
        <button type="button" id="btn-restart">重头</button>
        <div class="row"><label for="w1">左界</label><input id="w1" type="range" min="5" max="90" value="33"></div>
        <div class="row"><label for="w2">右界</label><input id="w2" type="range" min="10" max="95" value="66"></div>
        <div class="row"><label for="seek">进度</label><input id="seek" type="range" min="0" max="1000" value="0"></div>
        <span class="time" id="time">0:00 / 0:00</span>
      </div>
      <div class="err" id="err"></div>
    </div>
    <p class="hint">demo 目录：<code>python -m http.server 8765</code> →
      <code>http://127.0.0.1:8765/yaab-triple-wipe.html</code></p>
  </main>
  <script>
    const van = document.getElementById("v-van");
    const grd = document.getElementById("v-grd");
    const inj = document.getElementById("v-inj");
    const vids = [van, grd, inj];
    const stage = document.getElementById("stage");
    const d1 = document.getElementById("d1");
    const d2 = document.getElementById("d2");
    const w1 = document.getElementById("w1");
    const w2 = document.getElementById("w2");
    const seek = document.getElementById("seek");
    const btnPlay = document.getElementById("btn-play");
    const btnRestart = document.getElementById("btn-restart");
    const timeEl = document.getElementById("time");
    const errEl = document.getElementById("err");
    let playing = false, scrubbing = false, drag = null;

    function clamp(a, lo, hi) {{ return Math.min(hi, Math.max(lo, a)); }}
    function fmt(t) {{
      if (!Number.isFinite(t)) return "0:00";
      const s = Math.floor(t % 60).toString().padStart(2, "0");
      return `${{Math.floor(t / 60)}}:${{s}}`;
    }}
    function applyWipe(p1, p2) {{
      p1 = clamp(p1, 2, 96); p2 = clamp(p2, p1 + 2, 98);
      w1.value = String(Math.round(p1));
      w2.value = String(Math.round(p2));
      // left: vanilla 0..p1 ; mid: graded p1..p2 ; right: inject p2..100
      van.style.clipPath = `inset(0 ${{100 - p1}}% 0 0)`;
      grd.style.clipPath = `inset(0 ${{100 - p2}}% 0 ${{p1}}%)`;
      inj.style.clipPath = `inset(0 0 0 ${{p2}}%)`;
      d1.style.left = p1 + "%";
      d2.style.left = p2 + "%";
      // move mid label
      document.querySelector(".tag-grd").style.left = ((p1 + p2) / 2) + "%";
    }}
    function syncAll(t) {{
      for (const v of vids) if (Math.abs(v.currentTime - t) > 0.04) v.currentTime = t;
    }}
    function tick() {{
      const t = van.currentTime, d = van.duration || 0;
      if (!scrubbing && d > 0) seek.value = String(Math.round((t / d) * 1000));
      timeEl.textContent = `${{fmt(t)}} / ${{fmt(d)}}`;
      for (const v of [grd, inj]) if (Math.abs(v.currentTime - t) > 0.08) v.currentTime = t;
    }}
    async function playAll() {{
      try {{
        syncAll(van.currentTime);
        await Promise.all(vids.map(v => v.play()));
        playing = true; btnPlay.textContent = "暂停";
      }} catch (e) {{
        errEl.style.display = "block";
        errEl.textContent = "无法播放，请用本地 http.server 打开。";
      }}
    }}
    function pauseAll() {{
      vids.forEach(v => v.pause());
      playing = false; btnPlay.textContent = "播放";
    }}
    btnPlay.onclick = () => playing ? pauseAll() : playAll();
    btnRestart.onclick = () => {{ syncAll(0); tick(); }};
    w1.oninput = () => applyWipe(+w1.value, Math.max(+w2.value, +w1.value + 2));
    w2.oninput = () => applyWipe(Math.min(+w1.value, +w2.value - 2), +w2.value);
    seek.onpointerdown = () => {{ scrubbing = true; }};
    seek.onpointerup = () => {{ scrubbing = false; }};
    seek.oninput = () => {{
      const d = van.duration || 0; if (!d) return;
      syncAll((+seek.value / 1000) * d); tick();
    }};
    van.addEventListener("timeupdate", tick);
    van.addEventListener("ended", pauseAll);
    vids.forEach(v => v.addEventListener("error", () => {{
      errEl.style.display = "block";
      errEl.textContent = "视频加载失败: " + v.src;
    }}));

    function pct(ev) {{
      const r = stage.getBoundingClientRect();
      const x = (ev.clientX ?? ev.touches?.[0]?.clientX) - r.left;
      return clamp((x / r.width) * 100, 0, 100);
    }}
    stage.addEventListener("pointerdown", (ev) => {{
      const p = pct(ev);
      const p1 = +w1.value, p2 = +w2.value;
      drag = Math.abs(p - p1) <= Math.abs(p - p2) ? "1" : "2";
      stage.setPointerCapture(ev.pointerId);
      if (drag === "1") applyWipe(p, p2); else applyWipe(p1, p);
    }});
    stage.addEventListener("pointermove", (ev) => {{
      if (!drag) return;
      const p = pct(ev);
      if (drag === "1") applyWipe(p, +w2.value); else applyWipe(+w1.value, p);
    }});
    stage.addEventListener("pointerup", () => {{ drag = null; }});
    window.addEventListener("keydown", (ev) => {{
      if (ev.code === "Space") {{ ev.preventDefault(); playing ? pauseAll() : playAll(); }}
    }});

    applyWipe(33, 66);
    Promise.all(vids.map(v => new Promise(r => v.addEventListener("loadedmetadata", r, {{ once: true }}))))
      .then(tick);
  </script>
</body>
</html>
"""


if __name__ == "__main__":
  main()
