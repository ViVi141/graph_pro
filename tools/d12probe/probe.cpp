#include <windows.h>
#include <d3d12.h>
#include <dxgi1_6.h>
#include <cstdio>

int main() {
    IDXGIFactory4* fac = nullptr;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&fac)))) { printf("factory failed\n"); return 1; }
    IDXGIAdapter1* ad = nullptr;
    for (UINT i = 0; fac->EnumAdapters1(i, &ad) != DXGI_ERROR_NOT_FOUND; i++) {
        DXGI_ADAPTER_DESC1 d{};
        ad->GetDesc1(&d);
        wprintf(L"adapter %u: %s  dedicated %.0f MB  shared %.0f MB\n", i, d.Description,
                d.DedicatedVideoMemory / 1048576.0, d.SharedSystemMemory / 1048576.0);

        ID3D12Device* dev = nullptr;
        if (SUCCEEDED(D3D12CreateDevice(ad, D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&dev))) && dev) {
            D3D12_FEATURE_DATA_D3D12_OPTIONS5 o5{};
            if (SUCCEEDED(dev->CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS5, &o5, sizeof(o5)))) {
                printf("    D3D12 device OK, feature level 11_0");
                printf("  RaytracingTier=%d (1=1.0, 2=1.1, 0=unsupported)\n", (int)o5.RaytracingTier);
            } else {
                printf("    D3D12 device OK, OPTIONS5 query failed\n");
            }
            D3D12_FEATURE_DATA_D3D12_OPTIONS o{};
            if (SUCCEEDED(dev->CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS, &o, sizeof(o))))
                printf("    ResourceBindingTier=%d  TiledResourcesTier=%d\n", (int)o.ResourceBindingTier, (int)o.TiledResourcesTier);
            dev->Release();
        } else {
            printf("    D3D12 device NOT creatable at FL 11_0\n");
        }
        ad->Release();
    }
    fac->Release();
    return 0;
}
