// GraphPro SSAO final pass: smoothstep contrast (keeps bright, deepens creases)
Texture2D    t_ao : register(t1);
SamplerState s_ao : register(s1);

struct PSIn
{
    float4 pos : SV_Position;
    float2 uv  : TEXCOORD0;
};

float4 main(PSIn i) : SV_Target
{
    float ao = t_ao.Sample(s_ao, i.uv).x;
    ao = smoothstep(0.15f, 1.0f, saturate(ao));
    return float4(ao, ao, ao, ao);
}
