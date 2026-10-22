// GraphPro present pass
//   mode 0 : contact shadows composited over the finished frame
//   mode 1 : AO buffer only (debug)
//   mode 2 : passthrough / disabled
//   mode 3 : contact shadows + depth thumbnail in the corner
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
    float4 g_p1;   // xy = texel size, z = jitter, w = unused
    float4 g_p2;   // xyz = screen-space light dir (toward light), w = contact steps scale
};

SamplerState       g_smp     : register(s0);
Texture2D<float4>  g_color   : register(t0);
Texture2D<float>   g_depth   : register(t1);
Texture2DMS<float> g_depthMS : register(t1);

#define TAU 6.28318530718
#define NEAR_M 0.1

// Arma packs the whole view into 0.992..1.0 of a 24-bit UNORM.
// 1/(1-d) is proportional to view distance; scale it back to metres.
float Zof(float d)
{
    return NEAR_M / max(1.0 - d, 0.0000001);
}

float Hash12(float2 p)
{
    return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453);
}

// Horizon based: per direction keep the largest elevation angle of an
// occluder, then average the 6 directions. Bounded in [0,1] by
// construction, unlike summing 24 taps (which saturated to black).
// Screen-space contact shadow: march toward the light in UV space and look
// for a closer surface. Needs depth + light dir only (no G-buffer normals).
float ContactShadow(float2 uv, float d0)
{
    float z0 = Zof(d0);
    if (z0 > 200.0) return 1.0;                 // far field: 24-bit depth collapses

    float2 L = g_p2.xy;
    float llen = length(L);
    if (llen < 1e-4) return 1.0;
    L /= llen;

    float radM = max(g_p0.y, 0.05);
    float pixR = radM * g_p0.z / z0;
    pixR = clamp(pixR, 2.0, 64.0);
    float2 ts = g_p1.xy;
    int steps = (int)clamp(g_p2.w, 4.0, 16.0);
    float occ = 0.0;

    [loop] for (int s = 1; s <= 16; s++)
    {
        if (s > steps) break;
        float t = (float)s / (float)steps;
        float2 ouv = uv + L * (pixR * t) * ts;
        if (any(ouv < 0.0) || any(ouv > 1.0)) break;
        float z1 = Zof(g_depth.SampleLevel(g_smp, ouv, 0).r);
        float dz = z0 - z1;                      // >0 : sample in front of receiver
        if (dz <= 0.02) continue;
        float maxDz = radM * (0.35 + 0.65 * t);
        if (dz > maxDz) continue;                // reject sky/large discontinuities
        occ = max(occ, saturate(1.0 - t) * saturate(dz / max(maxDz, 1e-3)));
    }
    return saturate(1.0 - occ);
}

float4 PSComposite(VSOut i) : SV_Target
{
    float2 uv = i.uv;
    float4 col = g_color.SampleLevel(g_smp, uv, 0);
    float  d0  = g_depth.SampleLevel(g_smp, uv, 0).r;

    if (d0 >= 0.9999999) return col;
    float sh = ContactShadow(uv, d0);
    // mode 1 / 4 : debug — grayscale / red occlusion
    if (g_p0.w > 0.5 && g_p0.w < 1.5) return float4(sh, sh, sh, 1.0);
    if (g_p0.w > 3.5 && g_p0.w < 4.5) {
        float o = 1.0 - sh;
        return float4(lerp(col.rgb, float3(1, 0.15, 0.1), o * 0.85), 1.0);
    }
    float k = 1.0 - (1.0 - sh) * saturate(g_p0.x);
    return float4(col.rgb * k, 1.0);
}

// ---- debug thumbnail: near = bright, far = dark
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
