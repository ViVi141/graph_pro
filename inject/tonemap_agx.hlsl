// GraphPro tonemap: AgX (three.js / Blender-style, neutral look)
// Scene-linear sRGB in -> display sRGB out.
// Same PSCB_PostProcess cbuffer layout as the original Arma tonemap pass.
Texture2D    t_scene : register(t0);
Texture2D    t_glow  : register(t1);
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

// Linear sRGB <-> linear Rec.2020 (ITU-R BT.2407 matrices).
static const float3x3 SRGB_TO_REC2020 = float3x3(
    0.6274f, 0.3293f, 0.0433f,
    0.0691f, 0.9195f, 0.0113f,
    0.0164f, 0.0880f, 0.8956f);

static const float3x3 REC2020_TO_SRGB = float3x3(
     1.6605f, -0.5876f, -0.0728f,
    -0.1246f,  1.1329f, -0.0083f,
    -0.0182f, -0.1006f,  1.1187f);

// AgX inset / outset, rows as used by the GLSL column-major originals.
static const float3x3 AGX_INSET = float3x3(
    0.856627153315983f, 0.0951212405381588f, 0.0482516061458583f,
    0.137318972929847f, 0.761241990602591f,  0.101439036467562f,
    0.11189821299995f,  0.0767994186031903f, 0.811302368396859f);

static const float3x3 AGX_OUTSET = float3x3(
     1.1271005818144368f, -0.11060664309660323f, -0.016493938717834573f,
    -0.1413297634984383f,  1.157823702216272f,  -0.016493938717834257f,
    -0.14132976349843826f, -0.11060664309660294f, 1.2519364065950405f);

static const float AGX_MIN_EV = -12.47393f;
static const float AGX_MAX_EV =  4.026069f;

float3 AgXDefaultContrastApprox(float3 x)
{
    float3 x2 = x * x;
    float3 x4 = x2 * x2;
    return 15.5f   * x4 * x2
         - 40.14f  * x4 * x
         + 31.96f  * x4
         - 6.868f  * x2 * x
         + 0.4298f * x2
         + 0.1191f * x
         - 0.00232f;
}

float3 AgXToneMap(float3 color)
{
    // AgX expects scene-linear input. Keep the game's exposure/scale from c[37].
    color = max(color, 0.0f);
    color = mul(SRGB_TO_REC2020, color);
    color = mul(AGX_INSET, color);

    // Log2 allocation, AgX range.
    color = max(color, 1e-10f);
    color = log2(color);
    color = (color - AGX_MIN_EV) / (AGX_MAX_EV - AGX_MIN_EV);
    color = saturate(color);

    // AgX default contrast sigmoid.
    color = AgXDefaultContrastApprox(color);

    color = mul(AGX_OUTSET, color);

    // Back to linear light, then to sRGB primaries.
    color = pow(max(color, 0.0f), 2.2f);
    color = mul(REC2020_TO_SRGB, color);
    return saturate(color);
}

float4 main(PSIn i) : SV_Target
{
    float3 glowRaw = t_glow.Sample(s_glow, i.uv).rgb;
    float3 glow    = pow(max(glowRaw, 1e-6f), c[37].w) * 0.35f;

    float3 scene = t_scene.Sample(s_scene, i.uv).rgb * c[37].z;
    float  luma  = dot(scene, float3(0.299f, 0.587f, 0.114f));
    float  w     = saturate(1.0f - 2.0f * luma) * c[37].y;

    float3 col = scene * c[37].x + glow * w;

    // Fixed AgX tune3: E0.55 / k1.40 / s1.20.
    // Optional scene-adaptive override: the proxy writes g_adapt into c[80].x and
    // the sentinel 1.0 into c[80].w only when the controller is enabled. Exact
    // float compare — stale/unwritten cbuffer memory cannot hit 1.0 by accident.
    // Higher adapt == more highlight pressure, so back the exposure off and
    // soften the curve instead of letting channels clip.
    float E = 0.55f;
    float K = 1.40f;
    float S = 1.20f;
    if (c[80].w == 1.0f) {
        float a = saturate(c[80].x);
        E = lerp(0.55f, 0.42f, a);
        K = lerp(1.40f, 1.25f, a);
        S = lerp(1.20f, 1.10f, a);
    }

    col = AgXToneMap(col * E);
    col = pow(max(col, 0.0f), c[1].w);

    col = saturate((col - 0.5f) * K + 0.5f);
    float g = dot(col, float3(0.299f, 0.587f, 0.114f));
    col = saturate(lerp(float3(g, g, g), col, S));

    return float4(saturate(col), 1.0f);
}
