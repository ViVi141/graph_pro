# 第一次实拍对比：管线打通，取景待修

日期：2026-10-22

## 结论

**引擎内后处理 → 截图 → 量化对比，这条链路已经跑通。**

- 任务：`GP Shot 2`（`Documents\Arma 3\missions\GP_Shot2.Altis`）
- 出图：`Documents\Arma 3\Screenshots\gp_r_*.png`（1920×1080 PNG）
- 对比图：`demo/grade-compare-real.png`

## 踩过的三个坑（都定位了）

| 现象 | 根因 | 解法 |
|---|---|---|
| RPT 刷「缺少 ;」 | 天气命令要前导过渡时间：`<秒> setOvercast <值>` | `0 setOvercast 0.30;` |
| 截图命令报 Invalid file extension | `screenshot` 只认自己的命名规则，且目录 `Documents\Arma 3\Screenshots\` 必须先存在 | 用 `.png` + 预先建目录 |
| 画面永远是海面 | `player` 在 init 里是 objNull（任务以 spectator 启动），相机对象也不会接管视角 | `waitUntil {!isNull player}` 超时后 `createUnit` + `selectPlayer` |

## 数据（同一实景，四种调色）

| 变体 | 亮度 | 高光溢出 | 死黑 | 饱和度 | 对比 σ |
|---|---|---|---|---|---|
| 原样 | 156 | 0.0% | 0.0% | 9.7% | 25 |
| 低对比胶片 | 207 | 4.4% | 0.0% | 2.7% | 28 |
| 冷调高对比 | 217 | 10.2% | 0.0% | 4.0% | 29 |
| 暖调日落 | 217 | 9.5% | 0.0% | 5.9% | 29 |

（参数是刻意夸张的验证值，不代表最终风格。）

## 还差一步

`selectPlayer` 成功后视角仍停在第三人称/ spectator。已在 init 里补：

```sqf
player switchCamera "INTERNAL";
player setDir ((_tx - _bx) atan2 (_ty - _by));
```

下次运行即为第一人称、正对城镇的取景。

## 待办

- [ ] 跑一次确认第一人称取景（约 35 秒）
- [ ] 把调色参数换成克制的真实值（低对比胶片那组过曝了）
- [ ] 回到主线：材质（rvmat）/ 着色器替换
