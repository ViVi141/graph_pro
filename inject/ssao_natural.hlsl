// GraphPro Natural SSAO Resolve: deepens contact creases without black crush
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
    // Gentle crease enhancement with 0.18 floor to prevent crushed dark foliage/corners
    ao = lerp(0.18f, 1.0f, smoothstep(0.05f, 0.96f, ao));
    return float4(ao, ao, ao, ao);
}
