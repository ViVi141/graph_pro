// GraphPro Universal - Photorealistic Next-Gen Filmic Pipeline (AgX Punchy v4 + FidelityFX CAS + Daylight Split-Tone)
// Replaces Arma 3 PSPostProcessGlowNewFinalFilmic (5860 / 42670B06). Zero CPU overhead (ctxHook=0).
// Goals:
//   1. True sunlit-vs-shadow dynamic contrast (kills Arma 3's 2013 flat grey-beige look)
//   2. Physical daylight split-toning (cool sky-lit shadows + warm sunlit highlights)
//   3. Multi-scale HDR local contrast (sculpts foliage, terrain, buildings)
//   4. AMD FidelityFX CAS (Contrast Adaptive Sharpening, zero haloing)
//   5. Vibrance with strict highlight/black protection + IGN 8-bit debanding

Texture2D    t_scene : register(t0);
Texture2D    t_glow  : register(t1);
SamplerState s_scene : register(s0);
SamplerState s_glow  : register(s1);

cbuffer PSCB_PostProcess : register(b13)
{
    float4 c[84];
};

struct PSIn
{
    float4 pos : SV_Position;
    float2 uv  : TEXCOORD0;
};

static const float3x3 AGX_INSET = float3x3(
    0.842479062253094f, 0.0784335999999992f, 0.0792237451477643f,
    0.0423282422610123f, 0.878468636469772f, 0.0791661274605434f,
    0.0423756549057051f, 0.0784336f,          0.879142973793104f
);

static const float3x3 AGX_OUTSET = float3x3(
     1.19687900512017f,  -0.0980208811401368f, -0.0990297440797205f,
    -0.0528968517574562f, 1.15190312990417f,   -0.0989611768448433f,
    -0.0529716355144438f, -0.0980434501171241f, 1.15107367264116f
);

float Luma(float3 col)
{
    return dot(col, float3(0.2126f, 0.7152f, 0.0722f));
}

float3 agxDefaultContrastApprox(float3 x)
{
    float3 x2 = x * x;
    float3 x4 = x2 * x2;
    return + 15.5f     * x4 * x2
           - 40.14f    * x4 * x
           + 31.96f    * x4
           - 6.868f    * x2 * x
           + 0.4298f   * x2
           + 0.1191f   * x
           - 0.00232f;
}

float3 agxTonemap(float3 val)
{
    const float minEv = -9.5f;
    const float maxEv =  4.25f;

    val = mul(AGX_INSET, max(val, 1e-6f));
    val = clamp(log2(val), minEv, maxEv);
    val = (val - minEv) / (maxEv - minEv);
    val = agxDefaultContrastApprox(val);
    val = mul(AGX_OUTSET, val);
    return saturate(val);
}

// AMD FidelityFX CAS (Contrast Adaptive Sharpening) operating on 5-tap cross in linear HDR
float3 ApplyCAS(float3 e, float3 b, float3 d, float3 f, float3 h, float sharpness)
{
    float3 mnRGB = min(e, min(min(b, d), min(f, h)));
    float3 mxRGB = max(e, max(max(b, d), max(f, h)));

    // Adaptive weight: attenuates sharpening on already high-contrast edges (zero haloing)
    float3 rcpM = rcp(max(mxRGB, 1e-4f));
    float3 amp  = saturate(min(mnRGB, 2.0f - mxRGB) * rcpM);
    amp = sqrt(amp);

    float peak = -rcp(lerp(8.0f, 5.0f, sharpness));
    float3 w   = amp * peak;
    float3 rcpW = rcp(1.0f + 4.0f * w);

    return max(((b + d + f + h) * w + e) * rcpW, 0.0f);
}

float4 main(PSIn i) : SV_Target
{
    uint tw, th;
    t_scene.GetDimensions(tw, th);
    float2 ts = 1.0f / max(float2(tw, th), float2(1.0f, 1.0f));

    // 1. Center + 4-tap cross for AMD FidelityFX CAS (1.0px)
    float3 cE = max(t_scene.Sample(s_scene, i.uv).rgb, 0.0f);
    float3 cN = max(t_scene.Sample(s_scene, i.uv + float2( 0.0f, -ts.y)).rgb, 0.0f);
    float3 cS = max(t_scene.Sample(s_scene, i.uv + float2( 0.0f,  ts.y)).rgb, 0.0f);
    float3 cW = max(t_scene.Sample(s_scene, i.uv + float2(-ts.x,  0.0f)).rgb, 0.0f);
    float3 cR = max(t_scene.Sample(s_scene, i.uv + float2( ts.x,  0.0f)).rgb, 0.0f);

    float3 sharp = ApplyCAS(cE, cN, cW, cR, cS, 0.46f);

    // 2. Wide-radius HDR Local Contrast / Clarity (4-tap diagonal @ 3.2px)
    // Removes Arma 3's flat midtone haze and sculpts foliage, rocks, buildings, and weapon details
    float3 blur = 0.25f * (
        max(t_scene.Sample(s_scene, i.uv + float2( ts.x,  ts.y) * 3.2f).rgb, 0.0f) +
        max(t_scene.Sample(s_scene, i.uv + float2(-ts.x,  ts.y) * 3.2f).rgb, 0.0f) +
        max(t_scene.Sample(s_scene, i.uv + float2( ts.x, -ts.y) * 3.2f).rgb, 0.0f) +
        max(t_scene.Sample(s_scene, i.uv + float2(-ts.x, -ts.y) * 3.2f).rgb, 0.0f)
    );
    float lC = Luma(sharp);
    float lB = Luma(blur);
    float detail = clamp(lC - lB, -0.18f, 0.18f);
    float edgeMask = 1.0f - saturate(abs(lC - lB) * 2.5f);
    float3 sceneClean = max(sharp + sharp * (detail * 0.52f * edgeMask / max(lC, 0.05f)), 0.0f);

    // 3. Combine with Physical HDR Bloom (from our upgraded BloomInitDownsample4x)
    float3 glowRaw = t_glow.Sample(s_glow, i.uv).rgb;
    float3 glow    = pow(max(glowRaw, 1e-6f), c[37].w) * 0.28f;

    float3 scene = sceneClean * c[37].z;
    float  luma  = Luma(scene);
    float  w     = saturate(1.0f - 1.8f * luma) * c[37].y;

    float3 hdr = max(scene * c[37].x + glow * w, 0.0f) * 1.90f;

    // 4. Pre-tonemap Shadow Depth & Physical Daylight Split-Toning
    // Deepens washed-out 2013 ambient grey into rich cool sky-lit shadows while keeping sunlit highlights warm & luminous
    float hdrLuma = Luma(hdr);
    float shadowMask = 1.0f - smoothstep(0.04f, 0.55f, hdrLuma);
    float sunMask    = smoothstep(0.35f, 1.60f, hdrLuma);

    // Cool sky fill in shadows (9500K sky dome), warm golden daylight on sunlit surfaces (5600K sun)
    float3 coolTint = float3(0.89f, 0.96f, 1.11f);
    float3 warmTint = float3(1.05f, 1.01f, 0.94f);
    float3 splitTint = lerp(float3(1.0f, 1.0f, 1.0f), coolTint, shadowMask * 0.65f);
    splitTint        = lerp(splitTint, warmTint, sunMask * 0.55f);
    hdr *= splitTint;

    // Subtle HDR toe deepening (adds real 3D weight to shadowed foliage/crevices without crushing to 0)
    float toeCurve = lerp(0.90f, 1.08f, smoothstep(0.02f, 0.65f, hdrLuma));
    hdr *= toeCurve;

    // 5. AgX Filmic Tonemap + Punchy Contrast S-Curve
    float3 srgb = agxTonemap(hdr);
    srgb = pow(max(srgb, 1e-6f), 1.29f);

    // Gentle S-curve in sRGB to pop midtone separation without clipping highlights or crushing blacks
    float3 sCurve = srgb * srgb * (3.0f - 2.0f * srgb);
    srgb = lerp(srgb, sCurve, 0.14f);

    // 6. Photorealistic Vibrance (boosts pale 2013 foliage/sky more than already-vivid colors)
    float g = Luma(srgb);
    float mxC = max(srgb.r, max(srgb.g, srgb.b));
    float mnC = min(srgb.r, min(srgb.g, srgb.b));
    float curSat = (mxC - mnC) / max(mxC, 1e-4f);
    float hiProtect = 1.0f - smoothstep(0.75f, 0.99f, g);
    float loProtect = smoothstep(0.02f, 0.10f, g);
    float vibBoost  = (0.34f * (1.0f - curSat * 0.65f)) * hiProtect * loProtect;
    srgb = saturate(lerp(float3(g, g, g), srgb, 1.0f + vibBoost));

    // 7. Linearize & apply Arma 3 display gamma + ±0.5/255 IGN dithering
    float3 lin = pow(max(srgb, 1e-6f), 2.2f);
    float3 outCol = pow(max(lin, 0.0f), c[1].w);

    float dither = (frac(52.9829189f * frac(dot(i.pos.xy, float2(0.06711056f, 0.00583715f)))) - 0.5f) / 255.0f;
    return float4(saturate(outCol + dither), 1.0f);
}
