// GraphPro Ultimate Pass 3 (Full-Res): Joint-Bilateral RTGI Upsample + Physical Atmospheric Scattering + AgX + CAS
// Replaces Arma 3 PSPostProcessGlowNewFinalFilmic (5860 / 42670B06).
// Inputs:
//   t0 = Full-Res Linear HDR Scene
//   t1 = Physical HDR Bloom
//   t2 = Exact Linear View-Space Depth (meters, zero-copy from SSSM)
//   t3 = Half-Res Denoised RTGI (rgb = 3D indirect bounce, a = multi-meter horizon GTAO)
//   b13 = PSCB_PostProcess

Texture2D    t_scene : register(t0);
Texture2D    t_glow  : register(t1);
Texture2D    t_depth : register(t2);
Texture2D    t_rtgi  : register(t3);
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

float4 main(PSIn i) : SV_Target
{
    uint tw, th;
    t_scene.GetDimensions(tw, th);
    float2 res = max(float2(tw, th), float2(1.0f, 1.0f));
    float2 ts  = 1.0f / res;
    float  aspect = res.x / res.y;

    // 1. Center + 4-tap FidelityFX CAS (clean texture micro-detail without grass crunch)
    float3 cE = max(t_scene.Sample(s_scene, i.uv).rgb, 0.0f);
    float3 cN = max(t_scene.Sample(s_scene, i.uv + float2( 0.0f, -ts.y)).rgb, 0.0f);
    float3 cS = max(t_scene.Sample(s_scene, i.uv + float2( 0.0f,  ts.y)).rgb, 0.0f);
    float3 cW = max(t_scene.Sample(s_scene, i.uv + float2(-ts.x,  0.0f)).rgb, 0.0f);
    float3 cR = max(t_scene.Sample(s_scene, i.uv + float2( ts.x,  0.0f)).rgb, 0.0f);
    float3 sceneClean = ApplyCAS(cE, cN, cW, cR, cS, 0.34f);

    float dC = t_depth.SampleLevel(s_scene, i.uv, 0).x;

    // -------------------------------------------------------------------------
    // 2. Joint-Bilateral Upsample of Denoised Half-Res RTGI + Multi-Meter GTAO
    // -------------------------------------------------------------------------
    if (dC > 1.0f && dC < 950.0f)
    {
        float2 halfStep = ts * 2.0f;
        float4 giSum = 0.0f;
        float  wSum  = 0.0f;
        float  invSigma = 1.0f / max(dC * 0.055f, 0.10f);

        static const float2 kOfs[4] = {
            float2(-0.5f, -0.5f), float2( 0.5f, -0.5f),
            float2(-0.5f,  0.5f), float2( 0.5f,  0.5f)
        };
        [unroll]
        for (int k = 0; k < 4; k++)
        {
            float2 sUV = i.uv + kOfs[k] * halfStep;
            float  sD  = t_depth.SampleLevel(s_scene, sUV, 0).x;
            float  dz  = abs(sD - dC) * invSigma;
            float  w   = exp(-dz * dz * 2.0f) + 1e-4f;
            giSum += t_rtgi.SampleLevel(s_scene, sUV, 0) * w;
            wSum  += w;
        }
        float4 rtgi = giSum / max(wSum, 1e-4f);
        float3 giBounce = rtgi.rgb;
        float  giAO     = saturate(rtgi.a);

        // Physically combine denoised GTAO + colored indirect bounce light in linear HDR!
        float  sceneL = Luma(sceneClean);
        float3 recvAlbedo = lerp(float3(0.42f, 0.42f, 0.42f), sceneClean / max(sceneL, 0.08f), 0.50f);
        // Shadowed surfaces receive richer visible bounce fill; directly sunlit surfaces stay crisp
        float  shadowBoost = lerp(1.55f, 0.50f, smoothstep(0.08f, 0.85f, sceneL));
        sceneClean = sceneClean * giAO + giBounce * recvAlbedo * (1.85f * shadowBoost);

        // ---------------------------------------------------------------------
        // 3. Depth-Driven Physical Atmospheric Perspective (Rayleigh + Mie Aerial Depth)
        // Replaces Arma 3's flat 2013 grey distance fog with crisp Mediterranean aerial blue
        // and subtle warm sun-direction Mie forward scattering on distant hills/towns (>140m)!
        // ---------------------------------------------------------------------
        float aeroDist = max(dC - 130.0f, 0.0f);
        if (aeroDist > 0.0f)
        {
            float rayleighAmt = (1.0f - exp(-aeroDist / 1750.0f)) * 0.42f;
            // Sample upper sky dome color so atmospheric perspective matches current weather/time of day!
            float3 skyRef = max(t_scene.SampleLevel(s_scene, float2(i.uv.x, 0.08f), 0).rgb, 0.0f);
            float  skyL   = Luma(skyRef);
            // Rich aerial blue-tinted scatter (desaturated gracefully in overcast/sunset via skyRef)
            float3 scatterCol = lerp(skyRef, skyRef * float3(0.84f, 0.96f, 1.18f), 0.65f);
            scatterCol = max(scatterCol, float3(0.04f, 0.06f, 0.09f) * max(skyL, 0.15f));

            // Optional Mie forward-scattering golden glow if sun direction is present in cb13[47]
            float3 rawSun = -c[47].xyz;
            float  sunLen = length(rawSun);
            if (sunLen > 1e-4f)
            {
                float2 fovScale = (c[44].x > 0.05f && c[44].y > 0.05f && c[44].x < 4.0f)
                    ? c[44].xy : float2(0.65f * aspect, 0.65f);
                float2 ndc = i.uv * float2(2.0f, -2.0f) + float2(-1.0f, 1.0f);
                float3 viewDir = normalize(float3(ndc * fovScale, 1.0f));
                float  cosSun  = saturate(dot(viewDir, rawSun / sunLen));
                float  mie     = pow(cosSun, 6.0f) * 0.35f;
                scatterCol += float3(1.15f, 0.96f, 0.72f) * (mie * max(skyL, 0.2f));
            }

            sceneClean = lerp(sceneClean, scatterCol, rayleighAmt);
        }
    }

    // 4. Combine with Physical HDR Bloom
    float3 glowRaw = t_glow.Sample(s_glow, i.uv).rgb;
    float3 glow    = pow(max(glowRaw, 1e-6f), c[37].w) * 0.28f;

    float3 scene = sceneClean * c[37].z;
    float  luma  = Luma(scene);
    float  w     = saturate(1.0f - 1.8f * luma) * c[37].y;

    float3 hdr = max(scene * c[37].x + glow * w, 0.0f) * 1.85f;

    // 5. Daylight Split-Toning + AgX Filmic Tonemap
    float hdrLuma    = Luma(hdr);
    float shadowMask = 1.0f - smoothstep(0.04f, 0.50f, hdrLuma);
    float sunMask    = smoothstep(0.35f, 1.55f, hdrLuma);
    float3 splitTint = lerp(float3(1.0f, 1.0f, 1.0f), float3(0.90f, 0.96f, 1.09f), shadowMask * 0.55f);
    splitTint        = lerp(splitTint, float3(1.05f, 1.01f, 0.94f), sunMask * 0.50f);
    hdr *= splitTint;

    float3 srgb = agxTonemap(hdr);
    srgb = pow(max(srgb, 1e-6f), 1.27f);
    float3 sCurve = srgb * srgb * (3.0f - 2.0f * srgb);
    srgb = lerp(srgb, sCurve, 0.13f);

    // 6. Photorealistic Vibrance + ±0.5/255 IGN Dithering
    float g   = Luma(srgb);
    float mxC = max(srgb.r, max(srgb.g, srgb.b));
    float mnC = min(srgb.r, min(srgb.g, srgb.b));
    float curSat = (mxC - mnC) / max(mxC, 1e-4f);
    float hiProtect = 1.0f - smoothstep(0.75f, 0.99f, g);
    float loProtect = smoothstep(0.02f, 0.10f, g);
    float vibBoost  = (0.30f * (1.0f - curSat * 0.65f)) * hiProtect * loProtect;
    srgb = saturate(lerp(float3(g, g, g), srgb, 1.0f + vibBoost));

    float3 lin    = pow(max(srgb, 1e-6f), 2.2f);
    float3 outCol = pow(max(lin, 0.0f), c[1].w);

    float dither = (IGN(i.pos.xy) - 0.5f) / 255.0f;
    return float4(saturate(outCol + dither), 1.0f);
}
