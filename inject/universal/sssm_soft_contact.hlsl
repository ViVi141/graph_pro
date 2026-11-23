// GraphPro Universal - Soft Shadows (IGN Vogel Disk) + Pre-Lighting Screen-Space Contact Shadows
// Replaces Arma 3 PSPostProcessSSSMVeryHigh (10036/C8390391), High (9960/31F14A8E), Normal (7396/3D897E19).
// Compile with:
//   fxc /T ps_5_0 /E main /D CASCADE_BLEND=1 /O2 /Fo GP_sssm_veryhigh.dxbc sssm_soft_contact.hlsl
//   fxc /T ps_5_0 /E main /D CASCADE_BLEND=0 /O2 /Fo GP_sssm_high.dxbc     sssm_soft_contact.hlsl

Texture2D              t_depth  : register(t0);
Texture2D              t_shadow : register(t15);
SamplerState           s_depth  : register(s0);
SamplerComparisonState s_shadow : register(s15);

cbuffer PSCB_NonFrequent : register(b0)
{
    float4 nf[7]; // nf[6].y = invSBTSize (1.0 / shadowMapResolution)
};

cbuffer PSCB_PostProcess : register(b13)
{
    float4 pp[50];
    // pp[44].xy    = PSC_FOV.xy (view-space ray scale)
    // pp[45..47]   = PSC_ShadowmapMatrix (3 rows: viewPos -> shadow UV & Z)
    // pp[49].xyz   = PSC_ShadowmapLayerBorder (x=near, y=far, z=blendScale)
};

struct PSIn
{
    float4 pos : SV_Position;
    float2 uv  : TEXCOORD0;
};

// Jorge Jimenez Interleaved Gradient Noise (blue-noise-like spatial distribution, zero salt-and-pepper grain)
float IGN(float2 pixelPos)
{
    return frac(52.9829189f * frac(dot(pixelPos, float2(0.06711056f, 0.00583715f))));
}

// Golden-angle Vogel disk sample (uniform circular distribution, far cleaner than 2008 Poisson table)
float2 VogelDisk(int idx, int count, float phi)
{
    float r = sqrt(((float)idx + 0.5f) / (float)count);
    float theta = (float)idx * 2.39996323f + phi;
    float s, c;
    sincos(theta, s, c);
    return float2(c, s) * r;
}

float4 main(PSIn i) : SV_Target
{
    float depth = t_depth.SampleLevel(s_depth, i.uv, 0).x;
    if (depth < pp[49].x || depth >= pp[49].y)
        discard;

    // Reconstruct view-space position (exact Arma 3 convention)
    float2 ndc = i.uv * float2(2.0f, -2.0f) + float2(-1.0f, 1.0f);
    float4 viewPos = float4(ndc * pp[44].xy * depth, depth, 1.0f);

    float2 smUV = float2(dot(viewPos, pp[45]), dot(viewPos, pp[46]));
    float  smZ  = dot(viewPos, pp[47]);

    float noise = IGN(i.pos.xy);
    float phi   = noise * 6.2831853f;

    // Slightly softer penumbra than vanilla (1.55 vs 1.30), smooth blue-noise-like edge
    float radius = 1.55f * nf[6].y;

    // 4-tap outer early-out (identical fast path to vanilla for fully lit / fully shadowed pixels)
    float sum = 0.0f;
    [unroll]
    for (int k = 0; k < 4; k++)
    {
        // Outer ring indices (12..15) catch penumbra boundaries reliably
        float2 ofs = VogelDisk(12 + k, 16, phi) * radius;
        sum += t_shadow.SampleCmpLevelZero(s_shadow, smUV + ofs, smZ);
    }

    float shadow;
    if (sum > 0.001f && sum < 3.999f)
    {
        [unroll]
        for (int j = 0; j < 12; j++)
        {
            float2 ofs = VogelDisk(j, 16, phi) * radius;
            sum += t_shadow.SampleCmpLevelZero(s_shadow, smUV + ofs, smZ);
        }
        shadow = sum * 0.0625f;
    }
    else
    {
        shadow = (sum >= 3.999f) ? 1.0f : 0.0f;
    }

    // -------------------------------------------------------------------------
    // Pre-Lighting Screen-Space Contact Shadows (SSCS)
    // Runs ONLY in near cascade (1.2m..35m) on pixels still receiving sunlight.
    // Attenuates ONLY direct sunlight (ambient sky light remains 100% intact).
    // -------------------------------------------------------------------------
    if (shadow > 0.05f && depth > 1.2f && depth < 35.0f)
    {
        float3 rawSun = -pp[47].xyz; // Shadowmap Z increases away from sun -> -row2 points toward sun
        float  sunLen = length(rawSun);
        if (sunLen > 1e-5f)
        {
            float3 sunDirView = rawSun / sunLen;

            // Fade in past 1st-person weapon viewmodel (1.2..2.5m), fade out 22..35m
            float nearFade = smoothstep(1.2f, 2.5f, depth);
            float farFade  = 1.0f - smoothstep(22.0f, 35.0f, depth);
            float distFade = nearFade * farFade;

            // Adaptive ray length & thickness proportional to view distance
            float rayLen    = clamp(depth * 0.060f, 0.35f, 1.40f);
            float stepSize  = rayLen / 12.0f; // 12 steps for crisp grass/curb/building contact grounding
            float minBias   = 0.008f + depth * 0.0018f;
            float maxThick  = 0.14f  + depth * 0.022f;

            float contactOcc = 0.0f;
            float t = (0.25f + 0.75f * noise) * stepSize;

            [unroll]
            for (int s = 0; s < 12; s++)
            {
                float3 sp = viewPos.xyz + sunDirView * t;
                if (sp.z > 0.2f)
                {
                    float2 sNdc = sp.xy / (sp.z * pp[44].xy);
                    float2 sUV  = sNdc * float2(0.5f, -0.5f) + 0.5f;

                    // Stay safely inside screen bounds
                    if (sUV.x > 0.002f && sUV.x < 0.998f && sUV.y > 0.002f && sUV.y < 0.998f)
                    {
                        float sceneD = t_depth.SampleLevel(s_depth, sUV, 0).x;
                        float dz = sp.z - sceneD;
                        if (dz > minBias && dz < maxThick)
                        {
                            // Smooth falloff near edge of thickness window and ray end
                            float thickW = 1.0f - smoothstep(maxThick * 0.5f, maxThick, dz);
                            float rayW   = 1.0f - ((float)s / 12.0f) * 0.30f;
                            contactOcc   = max(contactOcc, thickW * rayW);
                        }
                    }
                }
                t += stepSize;
            }

            // Cap at 0.85 so micro-contact shadows look grounded and dimensional
            shadow *= (1.0f - contactOcc * 0.85f * distFade);
        }
    }

#if CASCADE_BLEND
    float alpha = saturate((depth - pp[49].x) * pp[49].z);
    return float4(shadow, 0.0f, 0.0f, alpha);
#else
    return float4(shadow, 0.0f, 0.0f, 1.0f);
#endif
}
