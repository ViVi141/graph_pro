// GraphPro 3D Foliage Backlit Subsurface Scattering (SSS) Shader (replaces Arma 3 PSSSSMTreeAdv & PSSSSMTreeAdvAToC)
// Upgrades 2013 flat tree crowns with physically inspired backlit leaf translucency (warm sunlit green glow
// when looking toward the sun through leaves) + crisp leaf specular sheen, preserving exact alpha-test/AToC,
// SSSM shadows, SSAO, and physical distance/height fog.

Texture2D    t0  : register(t0);  // Leaf Diffuse + Alpha
Texture2D    t1  : register(t1);  // Normal Map (NOHQ DXT5nm)
Texture2D    t2  : register(t2);  // Macro / Crown Detail + AO (.w)
Texture2D    t15 : register(t15); // SSSM Screen-Space Shadow
Texture2D    t16 : register(t16); // SSAO + Caustics

SamplerState s0  : register(s0);
SamplerState s1  : register(s1);
SamplerState s2  : register(s2);
SamplerState s15 : register(s15);

cbuffer PSCB_NonFrequent : register(b0) { float4 cb0[18]; };
cbuffer PSCB_Tree        : register(b3) { float4 cb3[7];  };
cbuffer PSCB_Object1     : register(b5) { float4 cb5[14]; };
cbuffer PSCB_Object2     : register(b6) { float4 cb6[10]; };

cbuffer GP_Tune : register(b12)
{
    float4 gp_p0; // x=exposure, y=contrast, z=vibrance, w=sharpness
    float4 gp_p1; // x=rtgiBounce, y=rtgiAo, z=treeSss, w=glassRefl
};

// Exact input signature matching Arma 3 PSSSSMTreeAdv (v0..v11, centroid for MSAA)
struct PSIn
{
    float4 pos            : SV_POSITION;          // v0
    centroid float4 tc6   : TEXCOORD6;            // v1 (.xyz = vertex amb, .w = vertex alpha)
    centroid float4 tc7   : TEXCOORD7;            // v2 (.xyz = sun dir L_ts, .w = shadow mask)
    centroid float4 tc4   : TEXCOORD4;            // v3 (.xyz = up dir Up_ts)
    centroid float4 tc5   : TEXCOORD5;            // v4 (.w = viewZ)
    centroid float4 col0  : COLOR0;               // v5 (unused, keeps slot v5!)
    centroid float4 col1  : COLOR1;               // v6 (.xyz = worldPos, .w = waterDepth)
    centroid float3 tc10  : TEXCOORD10;           // v7.xyz (point/spot lights)
    centroid float  tc11  : TEXCOORD11;           // v7.w
    centroid float4 tc0   : TEXCOORD0;            // v8 (.xy = diffuse UV, .wz = normal UV)
    centroid float4 tc1   : TEXCOORD1;            // v9 (.xy = macro UV, .z = sun shadow scale)
    centroid float4 tc2   : TEXCOORD2;            // v10 (.xyz = view dir V_ts)
    centroid float4 tc3   : TEXCOORD3;            // v11 (.xyz = half dir H_ts)
};

float3 HemiAmb(float upVal)
{
    float3 sky = cb5[1].xyz;
    float3 mid = cb5[9].xyz;
    float3 gnd = cb5[2].xyz;
    float u = upVal * 2.0f - 1.0f;
    return (u >= 0.0f) ? lerp(mid, sky, saturate(u)) : lerp(gnd, mid, saturate(upVal * 2.0f));
}

float4 main(PSIn i) : SV_Target
{
    // 1. SSSM Shadow
    float shFade = saturate((i.tc5.w - cb6[2].w) / max(cb6[2].w, 1e-5f));
    float2 ssUV  = (i.pos.xy + 0.5f) * cb0[5].xy;
    float sssm   = t15.SampleLevel(s15, ssUV, 1.0f).x;
    float shadow = saturate(1.0f + cb6[2].x * (lerp(sssm, 1.0f, shFade) * i.tc7.w - 1.0f));

    // 2. Textures & Alpha
    float4 baseCol = t0.Sample(s0, i.tc0.xy) * cb6[1];
    float4 nRaw    = t1.Sample(s1, i.tc0.wz);
    float4 macCol  = t2.Sample(s2, i.tc1.xy);

    float outAlpha = ((baseCol.a * i.tc6.w * cb3[1].x) > 0.5f) ? 1.0f : 0.0f;
    float crownAO  = saturate(macCol.a * cb3[3].z + cb3[3].w);
    float3 albedo  = baseCol.rgb * macCol.rgb * 4.5947f;

    // 3. Normal & Tangent-Space Lighting Vectors
    float3 nTS;
    nTS.x = (nRaw.x - nRaw.w + 1.0f) * 2.0f - 1.0f;
    nTS.y = nRaw.y * 2.0f - 1.0f;
    nTS.z = nRaw.z * 2.0f - 1.0f;
    float3 N = normalize(nTS + 1e-6f);

    float3 L = normalize(i.tc7.xyz + 1e-6f);
    float3 V = normalize(i.tc2.xyz + 1e-6f);
    float3 H = normalize(i.tc3.xyz + 1e-6f);

    float NdotL = dot(N, i.tc7.xyz);
    float NdotV = dot(i.tc2.xyz, N);
    float NdotH = dot(i.tc3.xyz, N);
    float NdotUp = dot(N, i.tc4.xyz) * 0.5f + 0.5f;

    // Grazing leaf Fresnel rim
    float absV = abs(NdotV);
    float leafFres = saturate(1.0f - absV * 0.80f);
    leafFres = leafFres * leafFres;
    leafFres = leafFres * leafFres;

    // 4. Front-lit Diffuse + Specular + Back-lit Translucency
    float3 ambFront = HemiAmb(NdotUp) * crownAO;
    float  sunMask  = crownAO * i.tc1.z;
    float3 diffFront = saturate(NdotL * cb3[2].z + cb3[2].w) * cb5[4].xyz * sunMask * shadow;

    float specPow = (NdotL >= 0.0f && NdotH >= 0.0f) ? min(pow(max(NdotH, 1e-5f), cb5[6].w), 1.0f) : 0.0f;
    float3 specFront = specPow * cb5[6].xyz * leafFres * shadow * macCol.a;

    // Vanilla back-side translucency + NEW 3D View-Dependent Backlit Subsurface Scattering (SSS)!
    float3 ambBack  = HemiAmb(1.0f - NdotUp) * crownAO * cb3[4].xyz;
    float3 diffBack = saturate(NdotL * cb3[3].x + cb3[3].y) * sunMask * cb5[4].xyz * shadow * cb3[5].xyz;

    // Real 3D Backlit Leaf SSS: glows warm sunlit green when sun is behind foliage!
    float sssStrength = (gp_p1.z > 1e-4f) ? gp_p1.z : 0.55f;
    float backDot = saturate(dot(-V, L));
    float sssLobe = pow(backDot, 3.0f) * 0.75f + pow(backDot, 1.5f) * 0.25f;
    float3 sssGlow = cb5[4].xyz * float3(1.05f, 1.18f, 0.65f) * (sssLobe * shadow * sunMask * sssStrength);

    float3 transColor = albedo * (diffBack + ambBack + sssGlow);

    // Reflected sky sheen on waxy leaves
    float3 R = 2.0f * NdotV * N - i.tc2.xyz;
    float RdotUp = dot(i.tc4.xyz, R) * 0.5f + 0.5f;
    float3 reflCol = HemiAmb(RdotUp) * cb3[6].xyz * leafFres * crownAO;

    // 5. Underwater extinction + SSAO + Final Combine
    float uwDepth = max(cb5[12].z - i.col1.w, 0.0f);
    float3 uwExt     = exp(-uwDepth * cb0[15].xyz);
    float3 uwDiffExt = exp(-uwDepth * cb0[16].xyz);

    int2 ssaoCoord = int2(i.pos.xy * cb0[12].xy);
    float4 ssaoTex = t16.Load(int3(ssaoCoord, 0));

    float3 litDiff = diffFront * uwDiffExt;
    litDiff += (litDiff * cb0[10].w) * ssaoTex.yzw;
    float3 totDiff = (ambFront * uwExt) * ssaoTex.x + (i.tc6.xyz + i.tc10.xyz) + litDiff;
    float3 totAdd  = (specFront + transColor) * uwDiffExt + reflCol * uwExt;
    float3 color   = totDiff * albedo + totAdd;

    // 6. Physical distance & height fog
    float dist = length(i.col1.xyz - cb6[9].xyz);
    float linFog = saturate((cb5[12].x - dist) * cb5[12].y);
    float h0 = min(i.col1.y, cb6[9].y);
    float dh = abs(i.col1.y - cb6[9].y);
    float kFog = (dh / max(dist, 1e-5f)) * cb5[10].x;
    float intFog = (kFog == 0.0f) ? dist : (1.0f - exp(-dist * kFog)) / kFog;
    float fExp = min(exp(-intFog * exp(-h0 * cb5[10].x) * cb5[10].y), 1.0f);
    color = lerp(cb0[1].xyz, color, linFog * fExp);

    return float4(color, outAlpha);
}
