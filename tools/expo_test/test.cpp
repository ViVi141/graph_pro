#include <cstdio>
int main() {
    const char* p = "D:\\SteamLibrary\\steamapps\\common\\Arma 3\\GP_expo.txt";
    FILE* f = fopen(p, "r");
    if (!f) { printf("fopen FAILED for [%s]\n", p); return 1; }
    unsigned s = 0; float lo = 0.0f, hi = 0.0f;
    int got = fscanf(f, "%u %f %f", &s, &lo, &hi);
    fclose(f);
    printf("got=%d size=%u lo=%.3f hi=%.3f\n", got, s, lo, hi);
    return 0;
}
