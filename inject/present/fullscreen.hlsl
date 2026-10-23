// GraphPro present pass
//   mode 0 : contact shadows composited over the finished frame
//   mode 1 : gray occlusion debug
//   mode 2 : passthrough / disabled
//   mode 3 : contact + depth thumbnail
//   mode 4 : red occlusion debug
//
// Sky fix: Arma clouds often sit at d≈0.95..0.99 while clear sky is 1.0.
// Contact is ONLY applied on near ground (low d). Everything else is passthrough.
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
    float4 g_p1;   // xy = texel size, z = jitter, w = skyThr (unused for reject now)
    float4 g_p2;   // xyz = light dir, w = steps
};

SamplerState       g_smp     : register(s0);
Texture2D<float4>  g_color   : register(t0);
Texture2D<float>   g_depth   : register(t1);
Texture2DMS<float> g_depthMS : register(t1);

#define NEAR_M 0.1
// Hard ceiling: never touch pixels that could be cloud/sky/far hills silhouette.
#define GROUND_D_MAX 0.88
#define CONTACT_Z_MAX 25.0

float Zof(float d)
{
    return NEAR_M / max(1.0 - d, 0.0000001);
}

bool IsGroundContactCandidate(float d0)
{
    if (d0 >= GROUND_D_MAX) return false;
    if (d0 >= 0.995) return false;
    float z = Zof(d0);
    if (z > CONTACT_Z_MAX) return false;
    return true;
}

float ContactShadow(float2 uv, float d0)
{
    float z0 = Zof(d0);
    float2 L = g_p2.xy;
    float llen = length(L);
    if (llen < 1e-4) return 1.0;
    L /= llen;

    float radM = max(g_p0.y, 0.05);
    float pixR = clamp(radM * g_p0.z / z0, 2.0, 40.0);
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
        // Never treat cloud/sky samples as occluders.
        if (d1 >= GROUND_D_MAX) continue;
        float z1 = Zof(d1);
        float dz = z0 - z1;
        if (dz <= 0.02) continue;
        float maxDz = radM * (0.35 + 0.65 * t);
        if (dz > maxDz) continue;
        occ = max(occ, saturate(1.0 - t) * saturate(dz / max(maxDz, 1e-3)));
    }
    return saturate(1.0 - occ);
}

float4 PSComposite(VSOut i) : SV_Target
{
    float2 uv = i.uv;
    float4 col = g_color.SampleLevel(g_smp, uv, 0);
    float  d0  = g_depth.SampleLevel(g_smp, uv, 0).r;

    // Default: leave sky/clouds/far completely alone.
    if (!IsGroundContactCandidate(d0)) return col;

    float sh = ContactShadow(uv, d0);
    if (g_p0.w > 0.5 && g_p0.w < 1.5) return float4(sh, sh, sh, 1.0);
    if (g_p0.w > 3.5 && g_p0.w < 4.5) {
        float o = 1.0 - sh;
        return float4(lerp(col.rgb, float3(1, 0.15, 0.1), o * 0.85), 1.0);
    }
    float k = 1.0 - (1.0 - sh) * saturate(g_p0.x);
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
