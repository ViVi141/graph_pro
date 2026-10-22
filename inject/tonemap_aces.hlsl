// GraphPro tonemap v5: ACES + calibrated exposure + mild contrast/saturation
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

float3 acesFilm(float3 x)
{
    const float a = 2.51f, b = 0.03f, cc = 2.43f, d = 0.59f, e = 0.14f;
    return saturate((x * (a * x + b)) / (x * (cc * x + d) + e));
}

float4 main(PSIn i) : SV_Target
{
    float3 glowRaw = t_glow.Sample(s_glow, i.uv).rgb;
    float3 glow    = pow(max(glowRaw, 1e-6f), c[37].w) * 0.35f;

    float3 scene = t_scene.Sample(s_scene, i.uv).rgb * c[37].z;
    float  luma  = dot(scene, float3(0.299f, 0.587f, 0.114f));
    float  w     = saturate(1.0f - 2.0f * luma) * c[37].y;

    float3 col = scene * c[37].x + glow * w;
    col = acesFilm(col * 0.45f);
    col = pow(max(col, 0.0f), c[1].w);

    // display-space finishing: gentle contrast + slight saturation
    col = saturate((col - 0.5f) * 1.12f + 0.5f);
    float g = dot(col, float3(0.299f, 0.587f, 0.114f));
    col = saturate(lerp(float3(g, g, g), col, 1.08f));

    return float4(col, 1.0f);
}
