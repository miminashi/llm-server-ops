// mi25 P2P (hipMemcpyPeer) checker
// Usage: hip_peer_check [SIZE_MB]  (default 256)
#include <hip/hip_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#define CHK(x) do { \
    hipError_t e = (x); \
    if (e != hipSuccess) { \
        fprintf(stderr, "HIP error %s at %s:%d: %s\n", #x, __FILE__, __LINE__, hipGetErrorString(e)); \
        exit(1); \
    } \
} while (0)

int main(int argc, char** argv) {
    int n = 0;
    CHK(hipGetDeviceCount(&n));
    printf("Device count: %d\n", n);
    for (int i = 0; i < n; i++) {
        hipDeviceProp_t p;
        CHK(hipGetDeviceProperties(&p, i));
        printf("Device %d: %s  pciBusID=%d pciDeviceID=%d totalGlobalMem=%zuMB\n",
               i, p.name, p.pciBusID, p.pciDeviceID, p.totalGlobalMem / (1024ULL*1024ULL));
    }

    printf("\n=== canAccessPeer matrix ===\n");
    printf("     ");
    for (int j = 0; j < n; j++) printf(" D%d", j);
    printf("\n");
    for (int i = 0; i < n; i++) {
        printf("D%d ->", i);
        for (int j = 0; j < n; j++) {
            if (i == j) { printf("  -"); continue; }
            int can = 0;
            CHK(hipDeviceCanAccessPeer(&can, i, j));
            printf("  %d", can);
        }
        printf("\n");
    }

    printf("\n=== EnablePeerAccess ===\n");
    for (int i = 0; i < n; i++) {
        CHK(hipSetDevice(i));
        for (int j = 0; j < n; j++) {
            if (i == j) continue;
            int can = 0;
            CHK(hipDeviceCanAccessPeer(&can, i, j));
            if (!can) { printf("D%d->D%d: cannot access (skip)\n", i, j); continue; }
            hipError_t e = hipDeviceEnablePeerAccess(j, 0);
            if (e == hipSuccess) {
                printf("D%d->D%d: enabled\n", i, j);
            } else if (e == hipErrorPeerAccessAlreadyEnabled) {
                printf("D%d->D%d: already enabled\n", i, j);
                (void)hipGetLastError();
            } else {
                fprintf(stderr, "D%d->D%d: EnablePeerAccess FAILED: %s\n", i, j, hipGetErrorString(e));
            }
        }
    }

    size_t SIZE_MB = (argc > 1) ? (size_t)atoi(argv[1]) : 256;
    size_t bytes = SIZE_MB * 1024ULL * 1024ULL;
    printf("\n=== hipMemcpyPeerAsync bandwidth (buffer=%zu MB, 10 iters averaged) ===\n", SIZE_MB);

    std::vector<void*> buf(n, nullptr);
    for (int i = 0; i < n; i++) {
        CHK(hipSetDevice(i));
        CHK(hipMalloc(&buf[i], bytes));
        CHK(hipMemset(buf[i], 0xa5, bytes));
    }

    hipStream_t stream;
    CHK(hipSetDevice(0));
    CHK(hipStreamCreate(&stream));

    hipEvent_t start, stop;
    CHK(hipEventCreate(&start));
    CHK(hipEventCreate(&stop));

    printf("src\\dst");
    for (int j = 0; j < n; j++) printf("      D%d", j);
    printf("     (GB/s)\n");

    for (int src = 0; src < n; src++) {
        printf("  D%d  ", src);
        for (int dst = 0; dst < n; dst++) {
            if (src == dst) { printf("       -"); continue; }
            for (int k = 0; k < 3; k++) {
                CHK(hipMemcpyPeerAsync(buf[dst], dst, buf[src], src, bytes, stream));
            }
            CHK(hipStreamSynchronize(stream));
            CHK(hipEventRecord(start, stream));
            const int ITERS = 10;
            for (int k = 0; k < ITERS; k++) {
                CHK(hipMemcpyPeerAsync(buf[dst], dst, buf[src], src, bytes, stream));
            }
            CHK(hipEventRecord(stop, stream));
            CHK(hipEventSynchronize(stop));
            float ms = 0;
            CHK(hipEventElapsedTime(&ms, start, stop));
            double gbs = (double)bytes * ITERS / (ms * 1e-3) / (1024.0 * 1024.0 * 1024.0);
            printf(" %7.2f", gbs);
        }
        printf("\n");
    }

    for (int i = 0; i < n; i++) CHK(hipFree(buf[i]));
    CHK(hipEventDestroy(start));
    CHK(hipEventDestroy(stop));
    CHK(hipStreamDestroy(stream));
    return 0;
}
