// GraphPro AgX Punchy v3 (Calibrated Filmic + Subtle HDR Clarity, Zero-Blowout, Zero-Crush)
// For GraphPro Universal (-Graphics agx). Zero Map/Unmap hooks (0.000 ms CPU overhead).

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
    const float minEv = -10.0f;
    const float maxEv =   4.0f;

    val = mul(AGX_INSET, max(val, 1e-6f));
    val = clamp(log2(val), minEv, maxEv);
    val = (val - minEv) / (maxEv - minEv);
    val = agxDefaultContrastApprox(val);
    val = mul(AGX_OUTSET, val);
    return saturate(val);
}

float4 main(PSIn i) : SV_Target
{
    uint tw, th;
    t_scene.GetDimensions(tw, th);
    float2 ts = 1.0f / max(float2(tw, th), float2(1.0f, 1.0f));

    float3 rawC = t_scene.Sample(s_scene, i.uv).rgb;

    // Subtle 4-tap HDR micro-contrast / clarity (removes Arma's flat midtone haze without haloing)
    float3 blur = 0.25f * (
        t_scene.Sample(s_scene, i.uv + float2( ts.x,  ts.y) * 1.5f).rgb +
        t_scene.Sample(s_scene, i.uv + float2(-ts.x,  ts.y) * 1.5f).rgb +
        t_scene.Sample(s_scene, i.uv + float2( ts.x, -ts.y) * 1.5f).rgb +
        t_scene.Sample(s_scene, i.uv + float2(-ts.x, -ts.y) * 1.5f).rgb
    );
    float lC = dot(rawC, float3(0.2126f, 0.7152f, 0.0722f));
    float lB = dot(blur, float3(0.2126f, 0.7152f, 0.0722f));
    float detail = clamp(lC - lB, -0.15f, 0.15f);
    float edgeMask = 1.0f - saturate(abs(lC - lB) * 3.0f);
    float3 sceneClean = max(rawC + rawC * (detail * 0.45f * edgeMask / max(lC, 0.05f)), 0.0f);

    float3 glowRaw = t_glow.Sample(s_glow, i.uv).rgb;
    float3 glow    = pow(max(glowRaw, 1e-6f), c[37].w) * 0.22f;

    float3 scene = sceneClean * c[37].z;
    float  luma  = dot(scene, float3(0.2126f, 0.7152f, 0.0722f));
    float  w     = saturate(1.0f - 2.0f * luma) * c[37].y;

    float3 hdr = max(scene * c[37].x + glow * w, 0.0f) * 1.65f;
    float3 srgb = agxTonemap(hdr);
    srgb = pow(max(srgb, 1e-6f), 1.24f);

    float g = dot(srgb, float3(0.2126f, 0.7152f, 0.0722f));
    float hiProtect = 1.0f - smoothstep(0.68f, 0.98f, g);
    float loProtect = smoothstep(0.02f, 0.12f, g);
    float sat = 1.0f + 0.18f * hiProtect * loProtect;
    srgb = saturate(lerp(float3(g, g, g), srgb, sat));

    float3 lin = pow(max(srgb, 1e-6f), 2.2f);
    float3 outCol = pow(max(lin, 0.0f), c[1].w);

    return float4(saturate(outCol), 1.0f);
}
