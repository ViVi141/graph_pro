// GraphPro replacement for Arma's stretch pass (852x480 -> 1280x720,
// original psLen 5596, crc B682EAC0).
//
// HISTORY / WHY THIS IS NOT "EASU" ANY MORE:
//   v1 tried an edge-adaptive (EASU-style) reconstruction with taps pinned to the
//   nearest source texel centre. That quantised the output into 1.5x1.5 blocks
//   -> visible stair-stepping.
//   v2 fixed the blockiness by using bilinear weights as a base, but still chose
//   a gradient DIRECTION per pixel from a nearest-neighbour 3x3 neighbourhood.
//   That direction is piecewise-constant in ~1.5x1.5 pixel blocks, so the
//   attenuation jumped at block edges and shimmered whenever the camera moved
//   -> "锯齿闪烁".
//   Any per-pixel hard directional decision derived from a nearest-neighbour
//   neighbourhood has this instability. So: no directional decisions at all.
//
// v3 (current): hardware bilinear + contrast-adaptive sharpening with a local
// range clamp (RCAS idea). Fully deterministic, temporally stable, and it can
// never overshoot beyond the local neighbourhood, so it cannot ring or flicker.
// This is a conservative improvement over the original bilinear, not a
// best-in-class upscaler -- that needs temporal data (motion vectors) which this
// engine does not expose.
//
// Binding contract MUST match the original pass or nothing draws:
//   t0 / s0 : scene colour (low resolution source)
//   t1 / s1 : the coordinate LUT the original used. Unused here, kept declared
//             (see keepAlive) so the binding layout is unchanged.
//   cb13    : PSCB_PostProcess (only [38]/[39] were used, by StretchRectCoefs).
//
// Input is LDR: tonemap runs BEFORE this pass (bind-sequence probe: tonemap
// idx 269, stretch idx 275), so sharpening in perceptual space is correct.

Texture2D    t0      : register(t0);
Texture2D    t1      : register(t1);
SamplerState s0      : register(s0);
SamplerState s1      : register(s1);

cbuffer PSCB_PostProcess : register(b13)
{
    float4 c[84];
};

struct PSIn
{
    float4 pos : SV_Position;
    float2 uv  : TEXCOORD0;
};

// Sharpening strength. 0.0 = pure bilinear (safe), 1.0 = strong.
// Kept low deliberately: the clamp already prevents ringing, but too much gain
// on vegetation reads as noise.
static const float kSharpness = 0.35f;

float4 main(PSIn i) : SV_Target
{
    uint srcW = 0, srcH = 0;
    t0.GetDimensions(srcW, srcH);
    if (!srcW || !srcH) { srcW = 852; srcH = 480; }
    float2 t = 1.0f / float2((float)srcW, (float)srcH);   // one source texel in UV

    // Keep the original pass's full binding shape alive (see header).
    float keepAlive = min(t1.SampleLevel(s1, i.uv, 0).r, 0.0f) + min(c[39].x, 0.0f);

    // Centre: hardware bilinear. This is the stable baseline.
    float3 ctr = t0.SampleLevel(s0, i.uv, 0).rgb;

    // Four neighbours at one source texel out. Sampled bilinearly at those
    // offsets, so each one is itself smooth -- no nearest-neighbour decisions.
    float3 n = t0.SampleLevel(s0, i.uv + float2(0.0f, -t.y), 0).rgb;
    float3 s = t0.SampleLevel(s0, i.uv + float2(0.0f,  t.y), 0).rgb;
    float3 e = t0.SampleLevel(s0, i.uv + float2( t.x, 0.0f), 0).rgb;
    float3 w = t0.SampleLevel(s0, i.uv + float2(-t.x, 0.0f), 0).rgb;

    // Local range of the 4-neighbourhood. Sharpening is clamped to this, which
    // is what makes the filter ring-free and temporally stable: an output pixel
    // can never exceed colours that already exist next to it.
    float3 mn = min(min(n, s), min(e, w));
    float3 mx = max(max(n, s), max(e, w));

    // Contrast-adaptive gain: sharpen weakly where the local range is already
    // wide (edges that risk haloing) and more strongly in flat-ish areas where
    // sharpening only adds micro-contrast.
    float3 range = mx - mn;
    float3 gain = 1.0f / (1.0f + range * 8.0f);

    // Unsharp mask around the 4-neighbour average.
    float3 blur   = (n + s + e + w) * 0.25f;
    float3 detail = ctr - blur;

    float3 outc = ctr + detail * (kSharpness * gain);

    // Hard clamp to the neighbourhood range: guarantees no overshoot, hence no
    // white halos and no bright pixels popping in and out between frames.
    outc = clamp(outc, mn, mx);

    return float4(saturate(outc + keepAlive), 1.0f);
}
