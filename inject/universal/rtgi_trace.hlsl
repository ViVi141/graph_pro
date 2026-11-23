// GraphPro Ultimate Pass 1 (Half-Res): 32-Ray Horizon-Tracked Screen-Space Ray-Traced GI (RTGI) + Multi-Meter GTAO
// Prevents thin-wall/pillar light leaking via 4-step horizon elevation tracking along 8 IGN-rotated rays (8x4 = 32 taps).
// Inputs:  t0 = Full-Res Linear HDR Scene, t2 = Exact Linear View-Space Depth (meters), b13 = PSCB_PostProcess
// Output:  R16G16B16A16_FLOAT Half-Res RT -> rgb = Indirect Radiance Bounce (Linear HDR), a = Horizon Ambient Occlusion [0..1]

Texture2D    t_scene : register(t0);
Texture2D    t_depth : register(t2);
SamplerState s_lin   : register(s0);

cbuffer PSCB_PostProcess : register(b13)
{
    float4 c[84];
};

struct PSIn
{
    float4 pos : SV_Position;
    float2 uv  : TEXCOORD0;
};

float Luma(float3 col)
{
    return dot(col, float3(0.2126f, 0.7152f, 0.0722f));
}

float IGN(float2 p)
{
    return frac(52.9829189f * frac(dot(p, float2(0.06711056f, 0.00583715f))));
}

float3 ViewPosFromDepth(float2 uv, float depth, float2 fovScale)
{
    float2 ndc = uv * float2(2.0f, -2.0f) + float2(-1.0f, 1.0f);
    return float3(ndc * fovScale * depth, depth);
}

float4 main(PSIn i) : SV_Target
{
    uint tw, th;
    t_depth.GetDimensions(tw, th);
    float2 res = max(float2(tw, th), float2(1.0f, 1.0f));
    float2 ts  = 1.0f / res;
    float  aspect = res.x / res.y;
    float2 fovScale = (c[44].x > 0.05f && c[44].y > 0.05f && c[44].x < 4.0f && c[44].y < 4.0f)
        ? c[44].xy
        : float2(0.65f * aspect, 0.65f);

    float dC = t_depth.SampleLevel(s_lin, i.uv, 0).x;
    if (dC <= 1.0f || dC >= 950.0f)
        return float4(0.0f, 0.0f, 0.0f, 1.0f);

    // Minimum-gradient 3D normal reconstruction (zero silhouette halos)
    float dL = t_depth.SampleLevel(s_lin, i.uv + float2(-ts.x,  0.0f), 0).x;
    float dR = t_depth.SampleLevel(s_lin, i.uv + float2( ts.x,  0.0f), 0).x;
    float dU = t_depth.SampleLevel(s_lin, i.uv + float2( 0.0f, -ts.y), 0).x;
    float dD = t_depth.SampleLevel(s_lin, i.uv + float2( 0.0f,  ts.y), 0).x;

    float3 pC = ViewPosFromDepth(i.uv, dC, fovScale);
    float3 pL = ViewPosFromDepth(i.uv + float2(-ts.x,  0.0f), dL, fovScale);
    float3 pR = ViewPosFromDepth(i.uv + float2( ts.x,  0.0f), dR, fovScale);
    float3 pU = ViewPosFromDepth(i.uv + float2( 0.0f, -ts.y), dU, fovScale);
    float3 pD = ViewPosFromDepth(i.uv + float2( 0.0f,  ts.y), dD, fovScale);

    float3 dPdx = (abs(dR - dC) < abs(dL - dC)) ? (pR - pC) : (pC - pL);
    float3 dPdy = (abs(dD - dC) < abs(dU - dC)) ? (pD - pC) : (pC - pU);
    float3 N = normalize(cross(dPdy, dPdx) + 1e-6f);
    if (dot(N, -pC) < 0.0f) N = -N;

    // Smoothness mask protects alpha-tested grass cards from over-occlusion
    float minGradX   = min(abs(dR - dC), abs(dL - dC));
    float minGradY   = min(abs(dD - dC), abs(dU - dC));
    float depthRough = max(minGradX, minGradY) / max(dC, 0.5f);
    float solidMask  = 1.0f - smoothstep(0.014f, 0.050f, depthRough);

    float distFade = smoothstep(1.0f, 2.2f, dC) * (1.0f - smoothstep(220.0f, 550.0f, dC));
    if (distFade <= 0.005f)
        return float4(0.0f, 0.0f, 0.0f, 1.0f);

    float maxRadiusPx  = clamp(280.0f / max(dC, 2.2f), 16.0f, 130.0f);
    float maxWorldDist = clamp(dC * 0.28f, 3.2f, 11.5f);

    float noise   = IGN(i.pos.xy);
    float basePhi = noise * 6.2831853f;
    float jitter  = frac(noise * 7.13f);

    float3 giAccum = 0.0f;
    float  aoAccum = 0.0f;

    // 8 azimuthal directions x 4 progressive raymarch steps = 32 depth-tested visibility rays!
    // Horizon elevation tracking (maxSinH) ensures a foreground wall/pillar blocks light from behind it!
    [unroll]
    for (int dirIdx = 0; dirIdx < 8; dirIdx++)
    {
        float theta = ((float)dirIdx / 8.0f) * 6.2831853f + basePhi;
        float s, co;
        sincos(theta, s, co);
        float2 rayDirUV = float2(co, s) * ts;

        float maxSinH = 0.08f; // Tangent bias avoids flat-plane self-occlusion
        float rayAO   = 0.0f;
        float3 rayGI  = 0.0f;

        [unroll]
        for (int stepIdx = 0; stepIdx < 4; stepIdx++)
        {
            // Quadratic step spacing: dense near contact creases, wide for multi-meter GI bounce
            float fracT = ((float)stepIdx + 0.35f + 0.65f * jitter) / 4.0f;
            float rPx   = (fracT * fracT) * maxRadiusPx + 2.5f;
            float2 sUV  = i.uv + rayDirUV * rPx;

            if (sUV.x > 0.002f && sUV.x < 0.998f && sUV.y > 0.002f && sUV.y < 0.998f)
            {
                float dQ = t_depth.SampleLevel(s_lin, sUV, 0).x;
                if (dQ > 1.0f && dQ < 950.0f)
                {
                    float3 pQ   = ViewPosFromDepth(sUV, dQ, fovScale);
                    float3 v    = pQ - pC;
                    float  d2   = dot(v, v);
                    float  dist = sqrt(max(d2, 1e-6f));

                    if (dist > 0.10f && dist < maxWorldDist)
                    {
                        float3 L = v / dist;
                        float sinH = dot(N, L);

                        // ONLY samples rising ABOVE the previous horizon are visible (blocks thin-wall leaking!)
                        if (sinH > maxSinH)
                        {
                            float deltaH = sinH - maxSinH;
                            maxSinH = sinH;

                            float rangeW = 1.0f - smoothstep(maxWorldDist * 0.50f, maxWorldDist, dist);
                            float aoW    = 1.0f - smoothstep(0.5f, 4.5f, dist);
                            rayAO += deltaH * aoW;

                            // Gather linear HDR radiance from visible occluder surface
                            float3 radQ = max(t_scene.SampleLevel(s_lin, sUV, 0).rgb, 0.0f);
                            float  radL = Luma(radQ);
                            if (radL > 3.2f) radQ *= (3.2f / radL);

                            float bounceW = deltaH * rangeW / (1.0f + d2 * 0.10f);
                            rayGI += radQ * bounceW;
                        }
                    }
                }
            }
        }

        aoAccum += rayAO;
        giAccum += rayGI;
    }

    float3 giFinal = (giAccum * (1.0f / 8.0f)) * distFade * solidMask;
    float  aoFinal = 1.0f - saturate((aoAccum * (1.0f / 8.0f)) * 1.45f) * 0.72f * distFade * solidMask;

    return float4(giFinal, aoFinal);
}
