// GraphPro 3D Architectural Glass PBR Shader (replaces Arma 3 PSSSSMGlass)
// Fixes Arma 3's upside-down / garbled 2009 static env_land_co.paa photo reflection (t2 mip 0)
// with physically accurate Schlick Fresnel (IOR 1.5, F0=0.04) + right-side-up 3D Sky/Horizon/Ground IBL
// + softened t2 (mip 4.5) ambient tint, while preserving 100% of Arma 3's alpha, shadows, SSAO, and fog.

Texture2D    t0  : register(t0);  // Glass Albedo/Tint + Alpha
Texture2D    t1  : register(t1);  // Fresnel LUT
Texture2D    t2  : register(t2);  // Static Environment Map
Texture2D    t15 : register(t15); // SSSM Screen-Space Shadow
Texture2D    t16 : register(t16); // SSAO + Caustics

SamplerState s0  : register(s0);
SamplerState s1  : register(s1);
SamplerState s2  : register(s2);
SamplerState s15 : register(s15);

cbuffer PSCB_NonFrequent : register(b0) { float4 cb0[18]; };
cbuffer PSCB_Special1    : register(b1) { float4 cb1[3];  };
cbuffer PSCB_Object1     : register(b5) { float4 cb5[14]; };
cbuffer PSCB_Object2     : register(b6) { float4 cb6[10]; };

cbuffer GP_Tune : register(b12)
{
    float4 gp_p0; // x=exposure, y=contrast, z=vibrance, w=sharpness
    float4 gp_p1; // x=rtgiBounce, y=rtgiAo, z=treeSss, w=glassRefl
};

// Exact input signature matching Arma 3 PSSSSMGlass (v0..v11, centroid for MSAA)
struct PSIn
{
    float4 pos            : SV_POSITION;          // v0
    centroid float4 tc6   : TEXCOORD6;            // v1 (.xyz = vertex indirect)
    centroid float4 tc7   : TEXCOORD7;            // v2 (.xyz = vertex spec, .w = shadow mask)
    centroid float4 tc4   : TEXCOORD4;            // v3 (unused, keeps slot v3!)
    centroid float4 tc5   : TEXCOORD5;            // v4 (.w = viewZ)
    centroid float4 col0  : COLOR0;               // v5 (unused, keeps slot v5!)
    centroid float4 col1  : COLOR1;               // v6 (.xyz = worldPos, .w = waterDepth)
    centroid float3 tc10  : TEXCOORD10;           // v7.xyz (point/spot lights)
    centroid float  tc11  : TEXCOORD11;           // v7.w
    centroid float4 tc0   : TEXCOORD0;            // v8 (.xy = diffuse UV)
    centroid float4 tc1   : TEXCOORD1;            // v9 (.xyz = relPos -> V = normalize(-v9.xyz))
    centroid float4 tc2   : TEXCOORD2;            // v10 (.xyz = world normal N)
    centroid float4 tc3   : TEXCOORD3;            // v11 (.z = N.y up, .w = NdotL)
};

float4 main(PSIn i) : SV_Target
{
    float4 baseSample = t0.Sample(s0, i.tc0.xy);
    float4 baseCol    = baseSample * cb6[1];
    if (baseCol.a < 0.003922f)
        discard;

    float3 V = normalize(-i.tc1.xyz + 1e-6f);
    float3 N = normalize(i.tc2.xyz + 1e-6f);
    float  NdotV = max(abs(dot(N, V)), 1e-4f);
    float3 R = reflect(-V, N);

    // Physical Glass Schlick Fresnel (IOR 1.5 -> F0 = 0.04, steep reflection at grazing angles)
    float x = saturate(1.0f - NdotV);
    float x2 = x * x;
    float fresnelSchlick = 0.04f + 0.96f * (x2 * x2 * x);
    float fresnelLut = t1.Sample(s1, float2(saturate(dot(N, R)), 0.5f)).w;
    float fresnel = lerp(fresnelSchlick, fresnelLut, 0.30f);

    // Clean, always-right-side-up 3D Sky/Horizon/Ground IBL (eliminates garbled upside-down 2009 fake photo!)
    float3 skyAmb = cb5[1].xyz;
    float3 midAmb = cb5[9].xyz;
    float3 gndAmb = cb5[2].xyz;
    float3 procSky = (R.y >= 0.0f)
        ? lerp(midAmb * 1.15f, skyAmb * 1.65f, pow(saturate(R.y), 0.75f))
        : lerp(midAmb * 0.95f, gndAmb * 0.65f, saturate(-R.y));

    // Softly blurred mip 4.5 of t2 for subtle environment color tone only (zero sharp upside-down artifacts!)
    float2 envUV = R.xy * float2(0.5f, -0.5f) + 0.5f;
    float3 envTint = t2.SampleLevel(s2, envUV, 4.5f).rgb * cb1[2].xyz * cb6[0].xyz;

    float glassScale = (gp_p1.w > 1e-4f) ? gp_p1.w : 1.00f;
    float3 reflCol = (lerp(procSky * 0.85f, envTint * 1.4f, 0.25f) + i.tc7.xyz) * fresnel * glassScale;

    // Hemisphere ambient + diffuse (exact Arma 3 convention)
    float NdotL_pos = max(i.tc3.w, 0.0f);
    float NdotL_neg = max(-i.tc3.w, 0.0f);
    float3 hemi = (i.tc3.z >= 0.0f)
        ? lerp(midAmb, skyAmb, saturate(i.tc3.z))
        : lerp(gndAmb, midAmb, saturate(i.tc3.z + 1.0f));
    float3 ambient = hemi + cb5[8].xyz + i.tc6.xyz + cb5[5].xyz * NdotL_neg;
    float3 directDiff = NdotL_pos * cb5[4].xyz;

    // SSSM Shadow + SSAO + Underwater extinction
    float shFade = saturate((i.tc5.w - cb6[2].w) / max(cb6[2].w, 1e-5f));
    float sssm   = t15.SampleLevel(s15, i.pos.xy * cb0[5].xy, 1.0f).x;
    float shadow = saturate(1.0f + cb6[2].x * (lerp(sssm, 1.0f, shFade) * i.tc7.w - 1.0f));

    float alpha = max(saturate(baseCol.a), cb5[0].w);
    float uwDepth = max(cb5[12].z - i.col1.w, 0.0f);
    float3 uwExt     = exp(-uwDepth * cb0[15].xyz);
    float3 uwDiffExt = exp(-uwDepth * cb0[16].xyz);

    directDiff *= uwDiffExt;
    ambient    *= uwExt;
    reflCol    *= uwDiffExt;

    int2 ssaoCoord = int2(i.pos.xy * cb0[12].xy);
    float4 ssaoTex = t16.Load(int3(ssaoCoord, 0));
    float aoFactor = lerp(1.0f, ssaoTex.x, alpha);
    directDiff += (directDiff * cb0[10].w) * ssaoTex.yzw * alpha;

    float3 totalDiff = ambient * aoFactor + i.tc10.xyz + directDiff * shadow;
    float3 color = (baseCol.rgb * totalDiff) * alpha + reflCol * (0.45f + 0.55f * shadow);

    // Physical distance & height fog (exact Arma 3 convention)
    int fogMode = asint(cb5[11].x);
    if (fogMode == 1 || fogMode == 3)
    {
        float dist = length(i.col1.xyz - cb6[9].xyz);
        float linFog = saturate((cb5[12].x - dist) * cb5[12].y);
        float h0 = min(i.col1.y, cb6[9].y);
        float dh = abs(i.col1.y - cb6[9].y);
        float kFog = (dh / max(dist, 1e-5f)) * cb5[10].x;
        float intFog = (kFog == 0.0f) ? dist : (1.0f - exp(-dist * kFog)) / kFog;
        float fExp = min(exp(-intFog * exp(-h0 * cb5[10].x) * cb5[10].y), 1.0f);
        color = lerp(cb0[1].xyz * alpha, color, linFog * fExp);
    }

    return float4(color, alpha);
}
