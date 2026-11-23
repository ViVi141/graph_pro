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

    // Soft photographic penumbra (2.85 texels, 24-tap IGN Vogel Disk -> silky smooth shadow edges instead of 2013 hard stencils)
    float radius = 2.85f * nf[6].y;

    // 4-tap outer early-out (identical fast path for fully lit / fully shadowed interiors)
    float sum = 0.0f;
    [unroll]
    for (int k = 0; k < 4; k++)
    {
        float2 ofs = VogelDisk(20 + k, 24, phi) * radius;
        sum += t_shadow.SampleCmpLevelZero(s_shadow, smUV + ofs, smZ);
    }

    float shadow;
    if (sum > 0.001f && sum < 3.999f)
    {
        [unroll]
        for (int j = 0; j < 20; j++)
        {
            float2 ofs = VogelDisk(j, 24, phi) * radius;
            sum += t_shadow.SampleCmpLevelZero(s_shadow, smUV + ofs, smZ);
        }
        shadow = sum * (1.0f / 24.0f);
    }
    else
    {
        shadow = (sum >= 3.999f) ? 1.0f : 0.0f;
    }

    // -------------------------------------------------------------------------
    // Pre-Lighting Screen-Space Contact Shadows (SSCS)
    // Runs ONLY in near cascade (1.2m..35m) on pixels still receiving sunlight.
    // Attenuates ONLY direct sunlight (ambient sky light remains 100% intact).
    // Uses fwidth(depth) smoothness mask so thin alpha-tested grass cards don't
    // self-shadow, while solid ground/curbs/buildings/vehicles stay grounded.
    // -------------------------------------------------------------------------
    float depthGrad = max(abs(ddx(depth)), abs(ddy(depth))) / max(depth, 0.5f);
    float solidSurfaceMask = 1.0f - smoothstep(0.012f, 0.045f, depthGrad);

    if (shadow > 0.05f && depth > 1.2f && depth < 35.0f && solidSurfaceMask > 0.02f)
    {
        float3 rawSun = -pp[47].xyz; // Shadowmap Z increases away from sun -> -row2 points toward sun
        float  sunLen = length(rawSun);
        if (sunLen > 1e-5f)
        {
            float3 sunDirView = rawSun / sunLen;

            // Fade in past 1st-person weapon viewmodel (1.2..2.5m), fade out 22..35m
            float nearFade = smoothstep(1.2f, 2.5f, depth);
            float farFade  = 1.0f - smoothstep(22.0f, 35.0f, depth);
            float distFade = nearFade * farFade * solidSurfaceMask;

            // Adaptive ray length & thickness proportional to view distance
            float rayLen    = clamp(depth * 0.045f, 0.25f, 1.10f);
            float stepSize  = rayLen / 10.0f;
            float minBias   = 0.025f + depth * 0.0040f; // Enough bias to skip micro grass-blade self-hits
            float maxThick  = 0.16f  + depth * 0.022f;

            float contactOcc = 0.0f;
            float t = (0.30f + 0.70f * noise) * stepSize;

            [unroll]
            for (int s = 0; s < 10; s++)
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
                            float thickW = 1.0f - smoothstep(maxThick * 0.45f, maxThick, dz);
                            float rayW   = 1.0f - ((float)s / 10.0f) * 0.35f;
                            contactOcc   = max(contactOcc, thickW * rayW);
                        }
                    }
                }
                t += stepSize;
            }

            // Cap at 0.72 so contact shadows ground solid surfaces naturally without sooty blotches
            shadow *= (1.0f - contactOcc * 0.72f * distFade);
        }
    }

#if CASCADE_BLEND
    float alpha = saturate((depth - pp[49].x) * pp[49].z);
    return float4(shadow, 0.0f, 0.0f, alpha);
#else
    return float4(shadow, 0.0f, 0.0f, 1.0f);
#endif
}
