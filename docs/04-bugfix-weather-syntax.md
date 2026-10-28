# 修复记录：init.sqf 第 6 行「缺少 ;」

日期：2026-10-22　状态：已修复，待游戏内验证

## 现象

RPT 里刷屏（同一秒 120 次）：

```
Error in expression <Date [2035, 7, 12, 18, 10];
setOvercast 0.30;
setFog [0.10, 0.02, 90];
setRain 0>
  Error position: <0.30; ...>
  Error 缺少 ;
File ...\GP_Shot.Altis\init.sqf..., line 6
```

## 根因

**Arma 3 的天气类命令是"带过渡时间"的命令**，语法是：

```
<过渡秒数> setOvercast <值>
```

裸写 `setOvercast 0.30;` 时，编译器只把 `setOvercast` 当成一个完整表达式，紧跟的数字就成了多余 token → 报"缺少 ;"。

### 证据 1：引擎自带的命令帮助文本

从 `arma3_x64.exe` 里提取到的帮助字符串：

| 命令 | 帮助文本里的示例 | 结论 |
|---|---|---|
| `setOvercast` | `1800 setOvercast 0.5` | 需要前导时间 |
| `setRain` | `60 setRain 1` | 需要前导时间 |
| `setWaves` | `1800 setWaves 0.5` | 需要前导时间 |
| `setTerrainGrid` | `setTerrainGrid 12.5` | 裸参数 |
| `setTimeMultiplier` | `setTimeMultiplier 60` | 裸参数 |

### 证据 2：官方脚本里的 9 处用法，无一例外都带前导时间

```sqf
0 setOvercast (_overcast * 0.01);      // functions_f
3600 setOvercast 0.65;                  // missions_f_gamma
900 setRain 0;                          // missions_f_epa
_delay setOvercast _overcast;           // modules_f
0 setFog [0.15, 0.06, 50];              // missions_f_gamma
```

## 修复

```sqf
setDate [2035, 7, 12, 18, 10];   // 当时档位；现已改为 12:00（见 RESULTS）
0 setOvercast 0.30;
0 setFog [0.10, 0.02, 90];
0 setRain 0;
0 setWaves 0.25;
```

同时：
- 删除 `setWind`（任务 sqm 的 `startWind` 已定义）
- 删除 `setTimeMultiplier 0`（非必要，减少风险面）
- 全文改为 **CRLF** 行尾（与官方脚本、你其他任务一致）

另外 `mission.sqm` 的 `class Intel` 本来就写了 `startWeather/startWind/startWaves/year/month/day/hour/minute`，init 里的命令只是二次保险。

## 附带发现（不影响客户端）

用 `arma3server_x64.exe` 做无头测试时，本机 DS 会拒绝任何任务：

```
Warning Message: You cannot play/edit this mission; it is dependent on
downloadable content that has been deleted. a3_characters_f
```

自带 MP 任务、空任务、`addons[]={}` 都会被拒 → 说明是 DS 环境的 Addon 注册问题（与脚本无关）。
副作用：**暂时没有无头脚本测试通道**，脚本改动只能靠客户端跑一次验证。

## 待办

- [ ] 游戏内跑一次 `GP Shot`，确认 RPT 出现 `[GP] init begin` 且无 Error
- [ ] 确认 `screenshot` 落盘路径（任务内截图，用于四联对比）
