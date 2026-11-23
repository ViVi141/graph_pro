// GraphPro Universal - AgX Punchy v3 Night Tonemap
// Replaces Arma 3 PSPostProcessGlowNewFinalNightFilmic (5732 / 92DDC7B8).
// Preserves exact alpha channel (o0.w = scene.a) and deep uncrushed night blacks
// while keeping flashlights, tracer rounds, and explosions vibrant and unclipped.

Texture2D    t_scene : register(t0);
Texture2D    t_glow  : register(t1);
SamplerState s_scene : register(s0);
SamplerState s_glow  : register(s1);

cbuffer PSCB_PostProcess : register(b13)
{
    float4 c[84];
    // c[1].w   = 1 / gamma (~0.4545)
    // c[37].x  = scene multiplier
    // c[37].y  = glow multiplier
    // c[37].z  = exposure
    // c[37].w  = glow power
    // c[83].w  = filmic pre-exposure
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
    const float minEv = -11.0f; // Extra shadow toe stop for night visibility
    const float maxEv =   4.0f;

    val = mul(AGX_INSET, max(val, 1e-6f));
    val = clamp(log2(val), minEv, maxEv);
    val = (val - minEv) / (maxEv - minEv);
    val = agxDefaultContrastApprox(val);
    val = mul(AGX_OUTSET, val);
    return saturate(val);
}

float IGN(float2 p)
{
    return frac(52.9829189f * frac(dot(p, float2(0.06711056f, 0.00583715f))));
}

float4 main(PSIn i) : SV_Target
{
    float4 sceneRaw = t_scene.Sample(s_scene, i.uv);
    float3 glowRaw  = t_glow.Sample(s_glow, i.uv).rgb;

    float3 glow  = pow(max(glowRaw, 1e-6f), c[37].w) * c[37].y * 0.55f;
    float3 scene = sceneRaw.rgb * c[37].z;

    float3 hdr  = max(scene * c[37].x + glow, 0.0f) * max(c[83].w, 1.0f) * 1.35f;
    float3 srgb = agxTonemap(hdr);
    srgb = pow(max(srgb, 1e-6f), 1.18f);

    // Subtle saturation protection for night lights/tracers without coloring dark noise
    float g = dot(srgb, float3(0.2126f, 0.7152f, 0.0722f));
    float hiProtect = 1.0f - smoothstep(0.72f, 0.98f, g);
    float loProtect = smoothstep(0.03f, 0.15f, g);
    float sat = 1.0f + 0.12f * hiProtect * loProtect;
    srgb = saturate(lerp(float3(g, g, g), srgb, sat));

    float3 lin    = pow(max(srgb, 1e-6f), 2.2f);
    float3 outCol = pow(max(lin, 0.0f), c[1].w);

    // ±0.5/255 IGN dithering eliminates 8-bit banding in dark night skies
    float dither = (IGN(i.pos.xy) - 0.5f) / 255.0f;
    return float4(saturate(outCol + dither), sceneRaw.a);
}
