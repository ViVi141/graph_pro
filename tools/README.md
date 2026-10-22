# tools 说明

都是 Python / PowerShell 小工具，按用途分组。

## 解包与反汇编

| 文件 | 作用 |
|---|---|
| pbo_shdc_probe.py | 解析 bin.pbo，导出 9 个 .shdc 着色器缓存 |
| shdc_inventory.py / shdc_csv.py | 统计 shdc 里的命名条目，导出 CSV |
| shdc_extract_dxbc.py | 按名字从 shdc 里抽出单个 DXBC |
| match_tonemap.py | 把候选反汇编与参考 tonemap 做指令级相似度比对 |

反汇编用 Windows SDK 的 fxc：
  fxc /dumpbin /nologo xxx.dxbc

## 注入器验证

| 文件 | 作用 |
|---|---|
| smoke_test.py | 用真实 D3D11 设备验证代理 DLL 的替换逻辑（不启动游戏） |
| strip_test2.py | 验证 D3DStripShader 对字节码的影响 |

## 图像对比

| 文件 | 作用 |
|---|---|
| crop.py / crops.py | 从实拍帧裁切细节区域 |
| cmp_cfg.py / config_ab.py | 配置改动前后对比 |
| cmp_spec.py / cmp_spec2.py | 镜面注入前后对比 |
| region_diff.py | 按区域统计像素差 |
| grade_compare.py / grade_compare2.py / grade_stats.py | 调色变体对比与统计 |
| sharp_hist.py | 锐度指标（拉普拉斯方差）历史对比 |
| tonemap_demo.py | 生成 tonemap 曲线示意对比图 |
| capture_loop.ps1 | 外部定时抓帧（备用采集） |
| pe_imports.py | 解析 exe 导入表（确认渲染 API 依赖） |
