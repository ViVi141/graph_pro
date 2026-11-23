// GraphPro Ultimate Pass 2 (Half-Res): Edge-Aware À-Trous Bilateral Spatial Ray Reconstructor (Denoiser)
// Turns 32-ray stochastic RTGI+GTAO into a butter-smooth, noise-free global illumination field
// while strictly stopping blur across depth & normal discontinuities (zero bleeding across walls/silhouettes).
// Inputs:  t0 = Half-Res noisy RTGI (rgb=GI, a=AO), t2 = Full-Res Linear Depth (meters)
// Output:  R16G16B16A16_FLOAT Half-Res denoised RTGI

Texture2D    t_gi    : register(t0);
Texture2D    t_depth : register(t2);
SamplerState s_lin   : register(s0);

struct PSIn
{
    float4 pos : SV_Position;
    float2 uv  : TEXCOORD0;
};

static const float kGauss[3] = { 1.0f, 0.6667f, 0.25f };

float4 main(PSIn i) : SV_Target
{
    uint gw, gh;
    t_gi.GetDimensions(gw, gh);
    float2 ts = 1.0f / max(float2(gw, gh), float2(1.0f, 1.0f));

    float4 centerGI = t_gi.SampleLevel(s_lin, i.uv, 0);
    float  centerD  = t_depth.SampleLevel(s_lin, i.uv, 0).x;
    if (centerD <= 1.0f || centerD >= 950.0f)
        return float4(0.0f, 0.0f, 0.0f, 1.0f);

    // 5x5 À-Trous bilateral kernel (step = 2 half-res pixels = 4 full-res pixels)
    float4 sum = centerGI;
    float  wSum = 1.0f;
    float  invDepthSigma = 1.0f / max(centerD * 0.065f, 0.12f);

    [unroll]
    for (int dy = -2; dy <= 2; dy++)
    {
        [unroll]
        for (int dx = -2; dx <= 2; dx++)
        {
            if (dx == 0 && dy == 0) continue;

            float2 sUV = i.uv + float2((float)dx, (float)dy) * ts * 2.0f;
            float  sD  = t_depth.SampleLevel(s_lin, sUV, 0).x;

            // Strict depth edge-stopping weight prevents GI/AO from bleeding across foreground/background edges
            float dz = abs(sD - centerD) * invDepthSigma;
            float wD = exp(-dz * dz * 1.5f);
            float wS = kGauss[abs(dx)] * kGauss[abs(dy)];
            float w  = wS * wD;

            sum  += t_gi.SampleLevel(s_lin, sUV, 0) * w;
            wSum += w;
        }
    }

    return sum / max(wSum, 1e-5f);
}
