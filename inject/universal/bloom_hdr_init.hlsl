// GraphPro Universal - Physical HDR Bloom Init Downsample 4x
// Replaces Arma 3 PSPostProcessGlowNewBloomInitDownsample4x (5724 / F6B44573).
// Fixes Arma 3's saturate(luma) HDR-clamping bug (which turned bloom into flat milky wall haze)
// using Karis anti-firefly averaging + true HDR soft-knee extraction.

Texture2D    t0 : register(t0);
Texture2D    t1 : register(t1);
Texture2D    t2 : register(t2);
Texture2D    t3 : register(t3);
SamplerState s0 : register(s0);
SamplerState s1 : register(s1);
SamplerState s2 : register(s2);
SamplerState s3 : register(s3);

cbuffer PSCB_PostProcess : register(b13)
{
    float4 c[38];
    // c[37].x = bloom threshold
    // c[37].y = bloom scale
    // c[37].z = bloom power
    // c[37].w = exposure multiplier
};

struct PSIn
{
    float4 pos : SV_Position;
    float4 uv0 : TEXCOORD0;
    float4 uv1 : TEXCOORD1;
    float4 uv2 : TEXCOORD2;
    float4 uv3 : TEXCOORD3;
};

float Luma(float3 col)
{
    return dot(col, float3(0.2126f, 0.7152f, 0.0722f));
}

float4 main(PSIn i) : SV_Target
{
    float4 a = max(t0.Sample(s0, i.uv0.xy), 0.0f) * c[37].w;
    float4 b = max(t1.Sample(s1, i.uv1.xy), 0.0f) * c[37].w;
    float4 d = max(t2.Sample(s2, i.uv2.xy), 0.0f) * c[37].w;
    float4 e = max(t3.Sample(s3, i.uv3.xy), 0.0f) * c[37].w;

    // Karis-weighted average prevents single-pixel specular fireflies from flickering
    float wa = 1.0f / (1.0f + Luma(a.rgb));
    float wb = 1.0f / (1.0f + Luma(b.rgb));
    float wd = 1.0f / (1.0f + Luma(d.rgb));
    float we = 1.0f / (1.0f + Luma(e.rgb));
    float wSum = wa + wb + wd + we;
    float4 avg = (a * wa + b * wb + d * wd + e * we) / max(wSum, 1e-5f);

    float luma = Luma(avg.rgb);

    // True HDR soft-knee threshold (NO saturate(luma) clamp!)
    // Raises threshold slightly above flat walls so only genuine highlights/lights/sun glints bloom
    float thresh = max(c[37].x, 0.65f);
    float knee   = 0.35f;
    float soft   = clamp(luma - thresh + knee, 0.0f, 2.0f * knee);
    soft         = (soft * soft) / (4.0f * knee + 1e-5f);
    float contrib = max(luma - thresh, soft);

    // Soft upper energy rolloff (Reinhard-like cap at ~4.0) so muzzle flashes & flares glow without blowing out
    float energy = (contrib / (1.0f + contrib * 0.25f)) * c[37].y;
    float scale  = energy / max(luma, 1e-4f);

    return max(avg * scale, 0.0f);
}
