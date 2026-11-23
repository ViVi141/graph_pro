// GraphPro Route B - True Linear-HDR Screen-Space Global Illumination (SSGI) + Multi-Scale GTAO + AgX + CAS
// Replaces Arma 3 PSPostProcessGlowNewFinalFilmic (5860 / 42670B06).
// Receives Arma 3's exact linear view-space depth buffer (in meters) at t2 via zero-copy proxy forwarding
// from PSPostProcessSSSM*, enabling REAL 3D indirect light bounce + multi-meter horizon AO in linear HDR
// BEFORE Tonemapping and BEFORE HUD/UI (zero sky/HUD corruption, zero Present hook).

Texture2D    t_scene : register(t0);
Texture2D    t_glow  : register(t1);
Texture2D    t_depth : register(t2); // Linear view-space depth (meters), zero-copy forwarded from SSSM
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

float IGN(float2 p)
{
    return frac(52.9829189f * frac(dot(p, float2(0.06711056f, 0.00583715f))));
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

float3 ApplyCAS(float3 e, float3 b, float3 d, float3 f, float3 h, float sharpness)
{
    float3 mnRGB = min(e, min(min(b, d), min(f, h)));
    float3 mxRGB = max(e, max(max(b, d), max(f, h)));
    float3 rcpM  = rcp(max(mxRGB, 1e-4f));
    float3 amp   = sqrt(saturate(min(mnRGB, 2.0f - mxRGB) * rcpM));
    float  peak  = -rcp(lerp(8.0f, 5.0f, sharpness));
    float3 w     = amp * peak;
    return max(((b + d + f + h) * w + e) * rcp(1.0f + 4.0f * w), 0.0f);
}

float3 ViewPosFromDepth(float2 uv, float depth, float2 fovScale)
{
    float2 ndc = uv * float2(2.0f, -2.0f) + float2(-1.0f, 1.0f);
    return float3(ndc * fovScale * depth, depth);
}

float4 main(PSIn i) : SV_Target
{
    uint tw, th;
    t_scene.GetDimensions(tw, th);
    float2 res = max(float2(tw, th), float2(1.0f, 1.0f));
    float2 ts  = 1.0f / res;
    float  aspect = res.x / res.y;
    float2 fovScale = float2(0.65f * aspect, 0.65f);

    // 1. Center + 4-tap FidelityFX CAS
    float3 cE = max(t_scene.Sample(s_scene, i.uv).rgb, 0.0f);
    float3 cN = max(t_scene.Sample(s_scene, i.uv + float2( 0.0f, -ts.y)).rgb, 0.0f);
    float3 cS = max(t_scene.Sample(s_scene, i.uv + float2( 0.0f,  ts.y)).rgb, 0.0f);
    float3 cW = max(t_scene.Sample(s_scene, i.uv + float2(-ts.x,  0.0f)).rgb, 0.0f);
    float3 cR = max(t_scene.Sample(s_scene, i.uv + float2( ts.x,  0.0f)).rgb, 0.0f);
    float3 sceneClean = ApplyCAS(cE, cN, cW, cR, cS, 0.30f);

    // -------------------------------------------------------------------------
    // 2. TRUE LINEAR-HDR SCREEN-SPACE GLOBAL ILLUMINATION (SSGI) + MULTI-SCALE GTAO
    // -------------------------------------------------------------------------
    float dC = t_depth.SampleLevel(s_scene, i.uv, 0).x;

    // Graceful bypass on sky (> 900m), 1st-person viewmodel (< 1.1m), or if depth SRV not bound (0.0)
    if (dC > 1.1f && dC < 900.0f)
    {
        float dL = t_depth.SampleLevel(s_scene, i.uv + float2(-ts.x,  0.0f), 0).x;
        float dR = t_depth.SampleLevel(s_scene, i.uv + float2( ts.x,  0.0f), 0).x;
        float dU = t_depth.SampleLevel(s_scene, i.uv + float2( 0.0f, -ts.y), 0).x;
        float dD = t_depth.SampleLevel(s_scene, i.uv + float2( 0.0f,  ts.y), 0).x;

        float3 pC = ViewPosFromDepth(i.uv, dC, fovScale);
        float3 pL = ViewPosFromDepth(i.uv + float2(-ts.x,  0.0f), dL, fovScale);
        float3 pR = ViewPosFromDepth(i.uv + float2( ts.x,  0.0f), dR, fovScale);
        float3 pU = ViewPosFromDepth(i.uv + float2( 0.0f, -ts.y), dU, fovScale);
        float3 pD = ViewPosFromDepth(i.uv + float2( 0.0f,  ts.y), dD, fovScale);

        // Minimum-gradient normal reconstruction (zero halo at depth silhouettes!)
        float3 dPdx = (abs(dR - dC) < abs(dL - dC)) ? (pR - pC) : (pC - pL);
        float3 dPdy = (abs(dD - dC) < abs(dU - dC)) ? (pD - pC) : (pC - pU);
        float3 N = normalize(cross(dPdy, dPdx) + 1e-6f);
        if (dot(N, -pC) < 0.0f) N = -N;

        // Smoothness mask protects thin alpha-tested grass blades from over-occlusion
        float minGradX = min(abs(dR - dC), abs(dL - dC));
        float minGradY = min(abs(dD - dC), abs(dU - dC));
        float depthRough = max(minGradX, minGradY) / max(dC, 0.5f);
        float solidMask  = 1.0f - smoothstep(0.015f, 0.055f, depthRough);

        // Distance fade (in from 1.1..2.2m past 1st-person gun, out from 180..450m)
        float distFade = smoothstep(1.1f, 2.2f, dC) * (1.0f - smoothstep(180.0f, 450.0f, dC));

        // Screen-space sampling radius scaled by 1/depth (large bounce radius on buildings/vehicles!)
        float maxRadiusPx = clamp(240.0f / max(dC, 2.5f), 14.0f, 110.0f);
        float maxWorldDist = clamp(dC * 0.22f, 2.8f, 9.5f);

        float noise = IGN(i.pos.xy);
        float basePhi = noise * 6.2831853f;

        float3 giBounce = 0.0f;
        float  giAO     = 0.0f;
        float  wTotal   = 0.0f;

        // 16-tap Golden-Angle Vogel Hemisphere Gather (wide multi-meter bounce + horizon AO)
        [unroll]
        for (int k = 0; k < 16; k++)
        {
            float fracR = sqrt(((float)k + 0.5f) / 16.0f);
            float theta = (float)k * 2.39996323f + basePhi;
            float s, co;
            sincos(theta, s, co);

            float2 ofsUV = float2(co, s) * (fracR * maxRadiusPx) * ts;
            float2 sUV   = i.uv + ofsUV;

            if (sUV.x > 0.002f && sUV.x < 0.998f && sUV.y > 0.002f && sUV.y < 0.998f)
            {
                float dQ = t_depth.SampleLevel(s_scene, sUV, 0).x;
                if (dQ > 1.1f && dQ < 900.0f)
                {
                    float3 pQ  = ViewPosFromDepth(sUV, dQ, fovScale);
                    float3 v   = pQ - pC;
                    float  d2  = dot(v, v);
                    float  dist = sqrt(max(d2, 1e-6f));

                    if (dist > 0.12f && dist < maxWorldDist)
                    {
                        float3 L = v / dist;
                        float NdotL = max(dot(N, L) - 0.08f, 0.0f);
                        float rangeW = 1.0f - smoothstep(maxWorldDist * 0.55f, maxWorldDist, dist);

                        // Multi-meter Horizon Ambient Occlusion (grounds vehicles, eaves, balconies, wall-road corners!)
                        float aoRange = 1.0f - smoothstep(0.6f, 3.8f, dist);
                        giAO += NdotL * aoRange;

                        // Indirect Radiance Bounce (color bleeding from sunlit walls, terracotta roofs, tarmac & grass!)
                        float3 radQ = max(t_scene.SampleLevel(s_scene, sUV, 0).rgb, 0.0f);
                        // Clamp extreme sun glints so single hot pixels don't cause firefly noise
                        float  radL = Luma(radQ);
                        if (radL > 3.5f) radQ *= (3.5f / radL);

                        float bounceW = NdotL * rangeW / (1.0f + d2 * 0.14f);
                        giBounce += radQ * bounceW;
                    }
                }
                wTotal += 1.0f;
            }
        }

        float invW = 1.0f / max(wTotal, 1.0f);
        giBounce *= invW;
        giAO      = saturate(giAO * invW * 2.85f);

        // Apply multi-scale GTAO (deepens corners/under-vehicle/eaves) + warm colored indirect bounce light!
        float aoFactor = lerp(1.0f, 1.0f - giAO * 0.68f, distFade * solidMask);
        float sceneL   = Luma(sceneClean);
        // Approximate receiving surface albedo tint (darker in crevices so bounce fills shadows realistically!)
        float3 recvTint = lerp(float3(0.35f, 0.35f, 0.35f), sceneClean / max(sceneL, 0.08f), 0.55f);
        // Shadowed surfaces receive proportionally stronger visible indirect fill than directly sunlit walls
        float shadowBoost = lerp(1.35f, 0.55f, smoothstep(0.10f, 0.85f, sceneL));

        sceneClean = sceneClean * aoFactor + giBounce * recvTint * (1.25f * shadowBoost * distFade * solidMask);
    }

    // 3. Combine with Physical HDR Bloom
    float3 glowRaw = t_glow.Sample(s_glow, i.uv).rgb;
    float3 glow    = pow(max(glowRaw, 1e-6f), c[37].w) * 0.28f;

    float3 scene = sceneClean * c[37].z;
    float  luma  = Luma(scene);
    float  w     = saturate(1.0f - 1.8f * luma) * c[37].y;

    float3 hdr = max(scene * c[37].x + glow * w, 0.0f) * 1.85f;

    // 4. Subtle Daylight Split-Toning + AgX Filmic Tonemap
    float hdrLuma    = Luma(hdr);
    float shadowMask = 1.0f - smoothstep(0.04f, 0.50f, hdrLuma);
    float sunMask    = smoothstep(0.35f, 1.55f, hdrLuma);
    float3 splitTint = lerp(float3(1.0f, 1.0f, 1.0f), float3(0.91f, 0.97f, 1.08f), shadowMask * 0.55f);
    splitTint        = lerp(splitTint, float3(1.04f, 1.01f, 0.95f), sunMask * 0.50f);
    hdr *= splitTint;

    float3 srgb = agxTonemap(hdr);
    srgb = pow(max(srgb, 1e-6f), 1.26f);
    float3 sCurve = srgb * srgb * (3.0f - 2.0f * srgb);
    srgb = lerp(srgb, sCurve, 0.12f);

    // 5. Natural Vibrance + IGN Dithering
    float g   = Luma(srgb);
    float mxC = max(srgb.r, max(srgb.g, srgb.b));
    float mnC = min(srgb.r, min(srgb.g, srgb.b));
    float curSat = (mxC - mnC) / max(mxC, 1e-4f);
    float hiProtect = 1.0f - smoothstep(0.75f, 0.99f, g);
    float loProtect = smoothstep(0.02f, 0.10f, g);
    float vibBoost  = (0.28f * (1.0f - curSat * 0.65f)) * hiProtect * loProtect;
    srgb = saturate(lerp(float3(g, g, g), srgb, 1.0f + vibBoost));

    float3 lin    = pow(max(srgb, 1e-6f), 2.2f);
    float3 outCol = pow(max(lin, 0.0f), c[1].w);

    float dither = (IGN(i.pos.xy) - 0.5f) / 255.0f;
    return float4(saturate(outCol + dither), 1.0f);
}
