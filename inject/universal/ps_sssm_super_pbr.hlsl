// GraphPro Route A - Real 3D Forward Material Shader PBR/GGX Upgrade
// Replaces Arma 3 PSSSSMSuper / PSSSSMSuperAToC. The (size, crc32) keys below must
// match GP_replace.txt; update both together when a game update changes them.
//   16264 / 4AC9BAA2, 17992 / D7B6AECA, 17960 / 13052781
// True 3D per-pixel lighting upgrade (NOT post-processing) with ZERO CPU overhead (ctxHook=0):
//   1. GGX Trowbridge-Reitz Microfacet Specular + Smith-GGX Visibility + Schlick Fresnel
//      (replaces Arma 3's 2006 Blinn-Phong min(pow(NdotH, P), 1.0) clamp!)
//   2. View-dependent 3D Roughness-Aware Fresnel + Dual-Hemisphere Sky/Ground IBL Reflection
//   3. Burley/Disney Diffuse + Cavity-Enhanced 3D Hemisphere Ambient (Sky vs Ground bounce)
//   4. Preserves 100% of Arma 3's Detail/Macro textures, Point/Spot Lights, SSSM Shadows, SSAO & Physical Fog.

Texture2D    t0  : register(t0);  // Diffuse / Albedo (CO)
Texture2D    t1  : register(t1);  // Normal Map (NOHQ DXT5nm)
Texture2D    t2  : register(t2);  // Detail Texture (DT)
Texture2D    t3  : register(t3);  // Macro Texture (MC)
Texture2D    t4  : register(t4);  // Ambient Shadow / Cavity (AS)
Texture2D    t5  : register(t5);  // Specular / Gloss Map (SMDI: G=spec, B=gloss)
Texture2D    t6  : register(t6);  // Fresnel LUT
Texture2D    t7  : register(t7);  // Environment Reflection Map
Texture2D    t15 : register(t15); // Screen-Space Shadow Map (SSSM)
Texture2D    t16 : register(t16); // Screen-Space AO + Caustics

SamplerState s0  : register(s0);
SamplerState s1  : register(s1);
SamplerState s2  : register(s2);
SamplerState s3  : register(s3);
SamplerState s4  : register(s4);
SamplerState s5  : register(s5);
SamplerState s6  : register(s6);
SamplerState s7  : register(s7);
SamplerState s15 : register(s15);

cbuffer PSCB_NonFrequent : register(b0)
{
    float4 cb0[18];
    // cb0[1]  = PSC_FogColor
    // cb0[2]  = PSC_WLight (3D Sun direction)
    // cb0[5]  = PSC_InvW_InvH_X_X
    // cb0[7]  = PSC_WaterFogColor
    // cb0[10] = PSC_CausticsPars[1] (.w = caustics scale)
    // cb0[12] = PSC_SSAOCausticsScale
    // cb0[14] = PSC_HazePars
    // cb0[15] = PSC_WaterLightExtinctionCoefs
    // cb0[16] = PSC_WaterDiffuseLightExtinctionCoefs
    // cb0[17] = PSC_WaterFogGradientCoefs
};

cbuffer PSCB_Special1 : register(b1)
{
    float4 cb1[3]; // cb1[2] = PSC_GlassEnvColor
};

cbuffer PSCB_Object1 : register(b5)
{
    float4 cb5[14];
    // cb5[0]  = PSC_DiscretizeAlpha
    // cb5[1]  = PSC_AE (Sky Ambient)
    // cb5[2]  = PSC_GE (Ground Bounce Ambient)
    // cb5[3]  = PSC_DForced
    // cb5[4]  = PSC_Diffuse (Sun Diffuse)
    // cb5[5]  = PSC_LDirectionGround_DiffuseBack
    // cb5[6]  = PSC_Specular (.xyz=color, .w=specPower)
    // cb5[7]  = PSC_MatSpecular
    // cb5[8]  = PSC_Emissive
    // cb5[9]  = PSC_AmbientMid (Horizon Ambient)
    // cb5[10] = PSC_PhysicalFog
    // cb5[11] = int PSC_FogMode (asint(cb5[11].x))
    // cb5[12] = PSC_FogEnd_RCPFogEndMinusFogStart_WaterHeight_ExpCoef
    // cb5[13] = PSC_CamUnderwater
};

cbuffer PSCB_Object2 : register(b6)
{
    float4 cb6[10];
    // cb6[0] = PSC_GlassMatSpecular
    // cb6[1] = PSC_MaxColor
    // cb6[2] = PSC_Shadow_Factor_ZHalf
    // cb6[9] = PSC_CameraWorldPosition
};

cbuffer PSCB_Lights1 : register(b10)
{
    int4   PSC_PointLoopCount;
    int4   PSC_SpotLoopCount;
    float4 PSC_LightDistScale;
    float4 PSC_MatDiffuse;
};

cbuffer PSCB_Lights2 : register(b11)
{
    float4 PSC_LPSData[192];
};

// Exact input signature matching Arma 3 PSSSSMSuper (v0..v11, centroid for MSAA edge safety)
struct PSIn
{
    float4 pos            : SV_POSITION;          // v0
    centroid float4 tc6   : TEXCOORD6;            // v1 (vertex indirect light + alpha)
    centroid float4 tc7   : TEXCOORD7;            // v2 (.w = shadow mask)
    centroid float4 tc4   : TEXCOORD4;            // v3 (.xyz = TBN row2, .w = relPos.z)
    centroid float4 tc5   : TEXCOORD5;            // v4 (.w = viewZ for shadow fade)
    centroid float4 col0  : COLOR0;               // v5 (.xyz = TBN row0, .w = relPos.x)
    centroid float4 col1  : COLOR1;               // v6 (.xyz = worldPos, .w = waterDepth)
    centroid float3 tc10  : TEXCOORD10;           // v7.xyz (unused, keeps register slot v7!)
    centroid float  tc11  : TEXCOORD11;           // v7.w
    centroid float4 tc0   : TEXCOORD0;            // v8 (.xy = diffuse UV, .wz = normal UV)
    centroid float4 tc1   : TEXCOORD1;            // v9 (.xy = detail UV, .wz = macro UV)
    centroid float4 tc2   : TEXCOORD2;            // v10 (.xy = AS UV, .wz = SMDI UV)
    centroid float4 tc3   : TEXCOORD3;            // v11 (.xyz = TBN row1, .w = relPos.y)
};

static const float PI = 3.14159265f;

// Trowbridge-Reitz GGX Normal Distribution
float D_GGX(float NdotH, float a2)
{
    float d = (NdotH * a2 - NdotH) * NdotH + 1.0f;
    return a2 / max(PI * d * d, 1e-5f);
}

// Height-Correlated Smith-GGX Visibility (includes 1 / (4 * NdotL * NdotV))
float V_SmithGGX(float NdotL, float NdotV, float a2)
{
    float gv = NdotL * sqrt(NdotV * (NdotV - NdotV * a2) + a2);
    float gl = NdotV * sqrt(NdotL * (NdotL - NdotL * a2) + a2);
    return 0.5f / max(gv + gl, 1e-4f);
}

// Schlick Fresnel
float F_Schlick(float cosTheta, float F0)
{
    float x = saturate(1.0f - cosTheta);
    float x2 = x * x;
    return F0 + (1.0f - F0) * (x2 * x2 * x);
}

// Roughness-aware Schlick Fresnel for IBL reflections
float F_SchlickRough(float cosTheta, float F0, float roughness)
{
    float x = saturate(1.0f - cosTheta);
    float x2 = x * x;
    return F0 + (max(1.0f - roughness, F0) - F0) * (x2 * x2 * x);
}

float4 main(PSIn i) : SV_Target
{
    // 1. Decode NOHQ Normal Map -> 3D World Normal N
    float4 nRaw = t1.Sample(s1, i.tc0.wz);
    float3 nTS;
    nTS.x = (nRaw.x - nRaw.w + 1.0f) * 2.0f - 1.0f;
    nTS.y = nRaw.y * 2.0f - 1.0f;
    nTS.z = nRaw.z * 2.0f - 1.0f;

    float3 N_raw = float3(
        dot(i.col0.xyz, nTS),
        dot(i.tc3.xyz,  nTS),
        dot(i.tc4.xyz,  nTS)
    );
    float3 N = normalize(N_raw + 1e-6f);

    // 2. View vector V, Sun vector L, Half vector H
    float3 relPos = float3(i.col0.w, i.tc3.w, i.tc4.w);
    float  invDist = rsqrt(max(dot(relPos, relPos), 1e-8f));
    float3 V = -relPos * invDist;
    float3 L = cb0[2].xyz;
    float3 H = normalize(V + L + 1e-6f);

    float NdotV = max(dot(N, V), 1e-4f);
    float NdotL_raw = dot(N, L);
    float NdotL = max(NdotL_raw, 0.0f);
    float NdotH = max(dot(N, H), 0.0f);
    float VdotH = max(dot(V, H), 0.0f);

    // 3. SMDI Specular / Gloss -> Physical PBR Roughness & Metallicity Estimate
    float4 smdi = t5.Sample(s5, i.tc2.wz);
    float specInt   = saturate(smdi.g);
    float specPower = max(smdi.b * cb5[6].w, 1.0f);

    // Map Blinn-Phong specular power to GGX perceptual roughness [0.06..0.92]
    float roughness = clamp(sqrt(2.0f / (specPower + 2.0f)), 0.06f, 0.92f);
    float a  = roughness * roughness;
    float a2 = max(a * a, 1e-4f);

    // 4. Environment Map Reflection (t7) + Procedural 3D Dual-Hemisphere Sky/Ground IBL
    // Arma 3's vanilla t7 is a tiny 2009 2D-projected static photo (env_land_co.paa) that looks distorted/upside-down
    // at sharp mips on building windows. Biasing envMip >= 3.5 turns t7 into a smooth ambient color probe while
    // procEnv provides an always-right-side-up 3D sky-horizon-ground reflection!
    float3 R = reflect(-V, N);
    float2 envUV = R.xy * float2(0.5f, -0.5f) + 0.5f;
    float  envMip = max(pow(1.0f - saturate(specPower * 0.001f), 10.0f) * 8.0f, 3.5f);
    float4 envSample = t7.SampleLevel(s7, envUV, envMip);
    float3 envMapCol = envSample.rgb * exp2((1.0f - envSample.a) * 4.0f) * cb1[2].xyz;

    // 3D Sky/Horizon/Ground IBL along reflection vector R (always physically right-side-up!)
    float3 skyAmb = cb5[1].xyz;
    float3 midAmb = cb5[9].xyz;
    float3 gndAmb = cb5[2].xyz;
    float3 procEnv = (R.y >= 0.0f)
        ? lerp(midAmb, skyAmb * 1.35f, saturate(R.y))
        : lerp(midAmb, gndAmb * 0.80f, saturate(-R.y));
    float3 envCombined = lerp(procEnv * 0.70f, envMapCol * cb6[0].xyz * 1.15f, 0.35f);

    // Original Fresnel LUT blended with physical Roughness-Aware Schlick Fresnel
    float fresnelLut = t6.Sample(s6, float2(saturate(dot(N, R)), 0.5f)).x;
    float F0 = lerp(0.03f, 0.22f, specInt);
    float F_ibl  = F_SchlickRough(NdotV, F0, roughness);
    float F_spec = F_Schlick(VdotH, F0);

    // 5. Ambient Shadow / Cavity Map (t4)
    float4 asSample = t4.Sample(s4, i.tc2.xy);
    float asW = pow(max(asSample.w, 1e-6f), 2.2f);
    float ambShadow = lerp(asW, asSample.y, asSample.x);
    float sunAS     = lerp(asSample.y, asSample.z, asSample.x);
    // Slightly crisper cavity occlusion in crevices (bolts, panel seams, window frames)
    float cavityAO  = pow(saturate(ambShadow), 1.18f);

    // 6. True GGX Direct Sun Specular (NO MORE 1.0 CLAMP!)
    float D = D_GGX(NdotH, a2);
    float G = V_SmithGGX(NdotL, NdotV, a2);
    // Physical GGX peak modulated by SMDI specInt; soft cap at 8.0 so extreme glancing sun glints stay clean
    float ggxSpec = (NdotL > 0.0f) ? min(D * G * F_spec * NdotL * PI, 8.0f) : 0.0f;
    float3 directSpec = ggxSpec * cb5[6].xyz * max(specInt, 0.04f) * (0.65f + 0.55f * fresnelLut);

    // 7. View-Dependent 3D IBL Reflection (quadratic specInt keeps matte polymer/plaster rich while making metal/glass pop!)
    float metalMask = specInt * specInt;
    float iblWeight = F_ibl * lerp(0.05f, 1.50f, metalMask) * cavityAO;
    float3 envRefl = envCombined * iblWeight;

    // 8. 3D Hemisphere Ambient (Sky vs Ground Bounce) with Richer Directional Separation
    float upMask = saturate(N.y);
    float dnMask = saturate(-N.y);
    float3 hemiTop = lerp(midAmb, skyAmb * float3(0.95f, 0.99f, 1.07f), upMask);
    float3 hemiBot = lerp(midAmb, gndAmb * 0.82f, dnMask);
    float3 hemiAmb = (N.y >= 0.0f) ? hemiTop : hemiBot;
    float3 backDiff = cb5[5].xyz * max(-NdotL_raw, 0.0f);
    float3 ambient = (hemiAmb + cb5[8].xyz + backDiff) * cavityAO + i.tc6.xyz;

    // 9. Energy-Conserving Direct Sun Diffuse (Burley/Disney grazing retro-reflection for rough plaster/cloth)
    float fd90 = 0.5f + 2.0f * roughness * VdotH * VdotH;
    float fL = 1.0f + (fd90 - 1.0f) * pow(1.0f - NdotL, 5.0f);
    float fV = 1.0f + (fd90 - 1.0f) * pow(1.0f - NdotV, 5.0f);
    float disneyDiff = NdotL * lerp(1.0f, fL * fV, 0.55f);
    float kD = saturate(1.0f - F_spec * specInt);
    float3 directDiff = (disneyDiff * cb5[4].xyz * kD) + cb5[3].xyz;

    // 10. Dynamic Point & Spot Lights (exact Arma 3 loops, upgraded to GGX specular)
    float3 ptDiff = 0.0f;
    float3 ptAmb  = 0.0f;
    float3 ptSpec = 0.0f;

    int ptCount = PSC_PointLoopCount.x;
    [loop]
    for (int idx = 0; idx < ptCount; idx++)
    {
        int b = idx * 6;
        float3 toL = PSC_LPSData[b].xyz - relPos;
        float dist = length(toL);
        float3 lDir = toL / (dist + 1e-4f);

        float dScaled = max(dist * PSC_LightDistScale.x - PSC_LPSData[b + 4].x, 0.0f);
        float att = saturate(1.0f / (dot(PSC_LPSData[b + 4].yzw, float3(1.0f, dScaled, dScaled * dScaled)) + 1e-4f));
        float fade = 1.0f - saturate((dist * PSC_LightDistScale.x - PSC_LPSData[b + 5].x) * PSC_LPSData[b + 5].y);
        float w = att * fade;

        float3 hL = normalize(V + lDir + 1e-6f);
        float ndl = max(dot(N, lDir), 0.0f);
        float ndh = max(dot(N, hL), 0.0f);
        float vdh = max(dot(V, hL), 0.0f);
        float sp = (ndl > 0.0f) ? min(D_GGX(ndh, a2) * V_SmithGGX(ndl, NdotV, a2) * F_Schlick(vdh, F0) * ndl * PI, 6.0f) : 0.0f;

        ptDiff += (PSC_MatDiffuse.xyz * PSC_LPSData[b + 2].xyz * ndl) * w;
        ptAmb  += PSC_LPSData[b + 3].xyz * w;
        ptSpec += (cb5[7].xyz * PSC_LPSData[b + 2].xyz * (sp * max(specInt, 0.04f))) * w;
    }

    int spEnd = ptCount + PSC_SpotLoopCount.x;
    [loop]
    for (int sIdx = ptCount; sIdx < spEnd; sIdx++)
    {
        int b = sIdx * 6;
        float3 toL = PSC_LPSData[b].xyz - relPos;
        float dist = length(toL);
        float3 lDir = toL / (dist + 1e-4f);

        float spotCos = dot(-PSC_LPSData[b + 1].xyz, lDir);
        float spotW = pow(saturate((spotCos - PSC_LPSData[b + 1].w) * PSC_LPSData[b + 2].w), PSC_LPSData[b + 3].w);

        float dScaled = max(dist * PSC_LightDistScale.x - PSC_LPSData[b + 4].x, 0.0f);
        float att = saturate(1.0f / (dot(PSC_LPSData[b + 4].yzw, float3(1.0f, dScaled, dScaled * dScaled)) + 1e-4f));
        float fade = 1.0f - saturate((dist * PSC_LightDistScale.x - PSC_LPSData[b + 5].x) * PSC_LPSData[b + 5].y);
        float w = att * fade * spotW;

        float3 hL = normalize(V + lDir + 1e-6f);
        float ndl = max(dot(N, lDir), 0.0f);
        float ndh = max(dot(N, hL), 0.0f);
        float vdh = max(dot(V, hL), 0.0f);
        float sp = (ndl > 0.0f) ? min(D_GGX(ndh, a2) * V_SmithGGX(ndl, NdotV, a2) * F_Schlick(vdh, F0) * ndl * PI, 6.0f) : 0.0f;

        ptDiff += (PSC_MatDiffuse.xyz * PSC_LPSData[b + 2].xyz * ndl) * w;
        ptAmb  += PSC_LPSData[b + 3].xyz * w;
        ptSpec += (cb5[7].xyz * PSC_LPSData[b + 2].xyz * (sp * max(specInt, 0.04f))) * w;
    }

    // 11. Albedo (Diffuse + Macro + Detail)
    float4 baseSample = t0.Sample(s0, i.tc0.xy);
    float4 baseCol    = baseSample * cb6[1];
    float4 detailCol  = t2.Sample(s2, i.tc1.xy);
    float4 macroCol   = t3.Sample(s3, i.tc1.wz);

    float3 albedo = lerp(baseCol.rgb, macroCol.rgb, macroCol.a) * detailCol.rgb * 2.0f;
    float  alpha  = max(saturate(baseCol.a * i.tc6.w), cb5[0].w);

    // 12. SSSM Screen-Space Shadow (t15) + SSAO & Caustics (t16) + Underwater Extinction
    float shFade = saturate((i.tc5.w - cb6[2].w) / max(cb6[2].w, 1e-5f));
    float sssm   = t15.SampleLevel(s15, i.pos.xy * cb0[5].xy, 1.0f).x;
    float shComb = lerp(sssm, 1.0f, shFade) - (1.0f - sunAS) * shFade;
    float shadow = saturate(1.0f + cb6[2].x * (shComb * i.tc7.w - 1.0f));

    float uwDepth = max(cb5[12].z - i.col1.w, 0.0f);
    float3 uwExt     = exp(-uwDepth * cb0[15].xyz);
    float3 uwDiffExt = exp(-uwDepth * cb0[16].xyz);

    directDiff *= uwDiffExt;
    ambient    *= uwExt;
    directSpec *= uwDiffExt;

    int2 ssaoCoord = int2(i.pos.xy * cb0[12].xy);
    float4 ssaoTex = t16.Load(int3(ssaoCoord, 0));
    float aoFactor = lerp(1.0f, ssaoTex.x, alpha);
    directDiff += (directDiff * cb0[10].w) * ssaoTex.yzw * alpha;

    // 13. Final PBR Lighting Combine
    float3 totalDiff = ambient * aoFactor + (ptDiff + ptAmb) + directDiff * shadow;
    float3 totalSpec = directSpec * shadow + envRefl * uwExt + ptSpec;
    float3 color = (albedo * totalDiff) * alpha + totalSpec;

    // 14. Physical Atmospheric & Distance Fog (exact Arma 3 behavior)
    int fogMode = asint(cb5[11].x);
    if (fogMode == 1 || fogMode == 3)
    {
        float3 camToPix = i.col1.xyz - cb6[9].xyz;
        float  dist = length(camToPix);
        float  fogEnd = cb5[12].x;
        float  fogRcp = cb5[12].y;
        float  linFog = saturate((fogEnd - dist) * fogRcp);

        // Exponential height fog + haze
        float h0 = min(i.col1.y, cb6[9].y);
        float dh = abs(i.col1.y - cb6[9].y);
        float kFog = (dh / max(dist, 1e-5f)) * cb5[10].x;
        float intFog = (kFog == 0.0f) ? dist : (1.0f - exp(-dist * kFog)) / kFog;
        float fExp = min(exp(-intFog * exp(-h0 * cb5[10].x) * cb5[10].y), 1.0f);

        float kHaze = ((i.col1.y - cb6[9].y) / max(dist, 1e-5f)) * cb0[14].z;
        float intHaze = (kHaze == 0.0f) ? dist : (1.0f - exp(-dist * kHaze)) / kHaze;
        float fHaze = min(exp(-intHaze * exp(-(cb6[9].y - cb0[14].x) * cb0[14].z) * cb0[14].y), 1.0f);

        float fogFactor = linFog * fExp * fHaze;
        color = lerp(cb0[1].xyz * alpha, color, fogFactor);
    }

    return float4(color, alpha);
}
