// GraphPro Grounded SSAO Resolve: rich contact creases under foliage, vehicles, and walls without black crush
Texture2D    t_ao : register(t1);
SamplerState s_ao : register(s1);

struct PSIn
{
    float4 pos : SV_Position;
    float2 uv  : TEXCOORD0;
};

float4 main(PSIn i) : SV_Target
{
    float ao = saturate(t_ao.Sample(s_ao, i.uv).x);
    // Tighten upper transition (0.86) and deepen curve (1.45) so creases genuinely ground objects,
    // while keeping a 0.10 floor so dark corners never turn pitch-black ink.
    ao = smoothstep(0.02f, 0.86f, ao);
    ao = pow(max(ao, 1e-4f), 1.45f);
    ao = lerp(0.10f, 1.0f, ao);
    return float4(ao, ao, ao, ao);
}
