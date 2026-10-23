// GraphPro present pass
//   mode 0 : contact shadows composited over the finished frame
//   mode 1 : gray occlusion debug
//   mode 2 : passthrough / disabled (CPU side; this shader not drawn)
//   mode 3 : contact + depth thumbnail
//   mode 4 : red occlusion debug
//
// Single RT only (no MRT hist) — dual RT was a black-sky suspect on Arma.
// Sky/cloud reject: runtime skyThr (g_p1.w) + GROUND_D_MAX.
struct VSOut
{
    float4 pos : SV_Position;
    float2 uv  : TEXCOORD0;
};

VSOut VSMain(uint id : SV_VertexID)
{
    VSOut o;
    float2 p = float2((id << 1) & 2, id & 2);
    o.pos = float4(p * float2(2.0, -2.0) + float2(-1.0, 1.0), 0.0f, 1.0f);
    o.uv  = p;
    return o;
}

cbuffer GPParams : register(b0)
{
    float4 g_p0;   // x = strength, y = radius metres, z = projection scale, w = mode
    float4 g_p1;   // xy = texel size, z = unused, w = skyThr
    float4 g_p2;   // xyz = light dir, w = steps
    float4 g_p3;   // x = luma0, y = luma1, z = unused, w = unused
};

SamplerState       g_smp     : register(s0);
Texture2D<float4>  g_color   : register(t0);
Texture2D<float>   g_depth   : register(t1);
Texture2DMS<float> g_depthMS : register(t1);

#define NEAR_M 0.1
#define GROUND_D_MAX 0.80
#define CONTACT_Z_MAX 20.0

float Zof(float d)
{
    return NEAR_M / max(1.0 - d, 0.0000001);
}

bool IsSkyOrFar(float d)
{
    float skyThr = g_p1.w;
    if (skyThr < 0.5) skyThr = 0.992;
    if (d >= skyThr) return true;
    if (d >= GROUND_D_MAX) return true;
    if (d >= 0.995) return true;
    return false;
}

bool IsGroundContactCandidate(float d0)
{
    if (IsSkyOrFar(d0)) return false;
    float z = Zof(d0);
    if (z > CONTACT_Z_MAX) return false;
    return true;
}

float ContactShadowRadius(float2 uv, float d0, float radScale)
{
    float z0 = Zof(d0);
    float2 L = g_p2.xy;
    float llen = length(L);
    if (llen < 1e-4) return 0.0;
    L /= llen;

    float radM = max(g_p0.y * radScale, 0.05);
    float pixR = clamp(radM * g_p0.z / z0, 2.0, 48.0);
    float2 ts = g_p1.xy;
    int steps = (int)clamp(g_p2.w, 4.0, 12.0);
    float occ = 0.0;

    [loop] for (int s = 1; s <= 12; s++)
    {
        if (s > steps) break;
        float t = (float)s / (float)steps;
        float2 ouv = uv + L * (pixR * t) * ts;
        if (any(ouv < 0.0) || any(ouv > 1.0)) break;
        float d1 = g_depth.SampleLevel(g_smp, ouv, 0).r;
        if (IsSkyOrFar(d1)) continue;
        float z1 = Zof(d1);
        float dz = z0 - z1;
        if (dz <= 0.02) continue;
        float maxDz = radM * (0.35 + 0.65 * t);
        if (dz > maxDz) continue;
        float w = (1.0 - t) * (1.0 - t);
        float cand = w * saturate(dz / max(maxDz, 1e-3));
        occ += cand * (1.0 - occ);
    }
    return saturate(occ);
}

float ContactOcclusion(float2 uv, float d0)
{
    float fine = ContactShadowRadius(uv, d0, 0.40);
    float coarse = ContactShadowRadius(uv, d0, 1.00);
    return max(fine, coarse);
}

float4 PSComposite(VSOut i) : SV_Target
{
    float2 uv = i.uv;
    float4 col = g_color.SampleLevel(g_smp, uv, 0);
    float  d0  = g_depth.SampleLevel(g_smp, uv, 0).r;

    // Hard sky gate before any contact math.
    if (!IsGroundContactCandidate(d0))
        return col;

    float occ = ContactOcclusion(uv, d0);
    float sh = saturate(1.0 - occ);

    if (g_p0.w > 0.5 && g_p0.w < 1.5)
        return float4(sh, sh, sh, 1.0);
    if (g_p0.w > 3.5 && g_p0.w < 4.5)
        return float4(lerp(col.rgb, float3(1, 0.15, 0.1), occ * 0.85), 1.0);

    float luma = dot(col.rgb, float3(0.2126, 0.7152, 0.0722));
    float t0 = g_p3.x;
    float t1 = max(g_p3.y, t0 + 1e-3);
    float protect = saturate((luma - t0) / (t1 - t0));
    float k = 1.0 - occ * saturate(g_p0.x) * protect;
    return float4(col.rgb * k, 1.0);
}

float4 PSDepth(VSOut i) : SV_Target
{
    float v = saturate((1.0 - g_depth.SampleLevel(g_smp, i.uv, 0).r) * 125.0);
    float2 e = min(i.uv, 1.0 - i.uv);
    if (min(e.x, e.y) < 0.004) return float4(1.0, 0.12, 0.12, 1.0);
    return float4(v, v, v, 1.0);
}

float4 PSDepthMS(VSOut i) : SV_Target
{
    uint w = 0, h = 0, n = 0;
    g_depthMS.GetDimensions(w, h, n);
    int2 p = int2(saturate(i.uv) * float2(w, h));
    p = clamp(p, int2(0, 0), int2((int)w - 1, (int)h - 1));
    float v = saturate((1.0 - g_depthMS.Load(p, 0)) * 125.0);
    float2 e = min(i.uv, 1.0 - i.uv);
    if (min(e.x, e.y) < 0.004) return float4(1.0, 0.12, 0.12, 1.0);
    return float4(v, v, v, 1.0);
}
