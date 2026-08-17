// memprobe: measure (1) soft-fault bandwidth of a page-cache-hot file mmap (touch 1 byte/page),
// (2) full-read bandwidth (sum all bytes via mmap), (3) pread() into a reusable buffer,
// (4) cold read via F_NOCACHE (macOS) / O_DIRECT (Linux), (5) memcpy bandwidth,
// (6) whether munmap+MAP_FIXED remap drops RSS and how fast re-touch is,
// (7) madvise(MADV_DONTNEED) effect on RSS (macOS: expected no-op for file-backed).
// Usage: memprobe <file> [bytes_to_use]
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/resource.h>
#include <pthread.h>
#ifdef __APPLE__
#include <mach/mach.h>
#endif

static double now(void){ struct timeval tv; gettimeofday(&tv,NULL); return tv.tv_sec + tv.tv_usec*1e-6; }
static double rss_mb(void){
#ifdef __APPLE__
    struct mach_task_basic_info info; mach_msg_type_number_t cnt = MACH_TASK_BASIC_INFO_COUNT;
    if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&info, &cnt) != KERN_SUCCESS) return -1;
    return info.resident_size / 1048576.0;
#else
    FILE *f = fopen("/proc/self/statm","r"); long a,b; if(!f) return -1; if (fscanf(f,"%ld %ld",&a,&b)!=2) b=0; fclose(f); return b*sysconf(_SC_PAGESIZE)/1048576.0;
#endif
}
static volatile uint64_t sink;

typedef struct { const uint8_t *p; size_t n; size_t pg; int stride_pages; } touch_arg;
static void *touch_thread(void *a_){ touch_arg *a=a_; uint64_t s=0; for(size_t o=0;o<a->n;o+=a->pg) s+=a->p[o]; sink+=s; return NULL; }
typedef struct { const uint8_t *p; size_t n; } sum_arg;
static void *sum_thread(void *a_){ sum_arg *a=a_; const uint64_t *q=(const uint64_t*)a->p; size_t m=a->n/8; uint64_t s=0; for(size_t i=0;i<m;i+=8) s+=q[i]+q[i+1]+q[i+2]+q[i+3]+q[i+4]+q[i+5]+q[i+6]+q[i+7]; sink+=s; return NULL; }

static void run_touch(const uint8_t *p, size_t n, size_t pg, int nth, const char *label){
    pthread_t th[64]; touch_arg args[64]; size_t chunk = (n/nth) & ~(pg-1);
    double t0=now();
    for(int i=0;i<nth;i++){ args[i].p=p+i*chunk; args[i].n=(i==nth-1)? n-i*chunk : chunk; args[i].pg=pg; pthread_create(&th[i],NULL,touch_thread,&args[i]); }
    for(int i=0;i<nth;i++) pthread_join(th[i],NULL);
    double dt=now()-t0;
    printf("  %-44s %d thr: %7.1f ms  %8.2f GB/s (page-touch)  rss=%.0f MB\n", label, nth, dt*1e3, n/dt/1e9, rss_mb());
}
static void run_sum(const uint8_t *p, size_t n, int nth, const char *label){
    pthread_t th[64]; sum_arg args[64]; size_t chunk = (n/nth) & ~(size_t)63;
    double t0=now();
    for(int i=0;i<nth;i++){ args[i].p=p+i*chunk; args[i].n=(i==nth-1)? n-i*chunk : chunk; pthread_create(&th[i],NULL,sum_thread,&args[i]); }
    for(int i=0;i<nth;i++) pthread_join(th[i],NULL);
    double dt=now()-t0;
    printf("  %-44s %d thr: %7.1f ms  %8.2f GB/s (full read)   rss=%.0f MB\n", label, nth, dt*1e3, n/dt/1e9, rss_mb());
}

int main(int argc, char **argv){
    if(argc<2){ fprintf(stderr,"usage: %s file [bytes]\n",argv[0]); return 1; }
    int fd=open(argv[1],O_RDONLY); if(fd<0){perror("open");return 1;}
    struct stat st; fstat(fd,&st); size_t n = st.st_size; if(argc>2) { size_t want=strtoull(argv[2],0,0); if(want<n) n=want; }
    size_t pg = sysconf(_SC_PAGESIZE); n &= ~(pg-1);
    printf("file=%s bytes=%zu (%.0f MB) pagesize=%zu rss0=%.0f MB\n", argv[1], n, n/1048576.0, pg, rss_mb());

    // (5) memcpy bandwidth, 512 MB
    { size_t m=512u<<20; uint8_t *a=malloc(m),*b=malloc(m); memset(a,1,m); memset(b,2,m);
      double t0=now(); for(int r=0;r<4;r++) memcpy(b,a,m); double dt=now()-t0;
      printf("  memcpy 512MB x4: %.2f GB/s (copy bw, counts bytes copied)\n", 4.0*m/dt/1e9); free(a); free(b); }

    // warm the page cache fully via mmap read
    uint8_t *p = mmap(NULL,n,PROT_READ,MAP_SHARED,fd,0); if(p==MAP_FAILED){perror("mmap");return 1;}
    printf("[warm] first full read (may include disk):\n"); run_sum(p,n,4,"mmap sum, cold-ish");
    run_sum(p,n,1,"mmap sum, warm");
    run_sum(p,n,4,"mmap sum, warm");
    run_sum(p,n,8,"mmap sum, warm");
    printf("  rss after warm = %.0f MB\n", rss_mb());

    // (7) madvise DONTNEED on the whole mapping
    { double t0=now(); int r=madvise(p,n,MADV_DONTNEED); double dt=now()-t0; printf("  madvise(DONTNEED) whole: ret=%d %.2f ms rss=%.0f MB\n", r, dt*1e3, rss_mb()); }
    run_touch(p,n,pg,1,"touch after DONTNEED");
#ifdef MADV_FREE_REUSABLE
    { double t0=now(); int r=madvise(p,n,MADV_FREE_REUSABLE); double dt=now()-t0; printf("  madvise(FREE_REUSABLE) whole: ret=%d %.2f ms rss=%.0f MB\n", r, dt*1e3, rss_mb()); }
    run_touch(p,n,pg,1,"touch after FREE_REUSABLE");
#endif
    // (6) munmap + MAP_FIXED remap => drops PTEs; measure soft-fault re-touch bandwidth
    for(int nth=1; nth<=8; nth*=2){
        double t0=now(); void *q=mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0); double dt=now()-t0;
        if(q!=p){perror("remap");return 1;}
        printf("  MAP_FIXED remap: %.2f ms rss=%.0f MB\n", dt*1e3, rss_mb());
        char lab[64]; snprintf(lab,64,"soft-fault touch (1B/page) after remap"); run_touch(p,n,pg,nth,lab);
    }
    // soft-fault + full read (what a matmul does): remap then sum
    for(int nth=1; nth<=8; nth*=2){
        mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0);
        run_sum(p,n,nth,"soft-fault + full read after remap");
    }
    // per-layer-sized windows: remap 64MB slices repeatedly (simulating a sliding window), 4 threads reading
    { size_t win=64u<<20; if(win>n) win=n; double t0=now(); size_t done=0; int iters=0;
      for(size_t off=0; off+win<=n; off+=win){ mmap(p+off,win,PROT_READ,MAP_SHARED|MAP_FIXED,fd,off); run_sum(p+off,win,4,"  (window)"); done+=win; iters++; if(iters>=6) break; }
      double dt=now()-t0; printf("  sliding 64MB windows (remap+read, incl. prints): %.2f GB/s\n", done/dt/1e9); }

    // (3) pread into reusable 64MB buffer, page cache hot
    { size_t buf=64u<<20; uint8_t *b=malloc(buf); double t0=now(); size_t tot=0; for(size_t off=0; off+buf<=n; off+=buf){ ssize_t r=pread(fd,b,buf,off); if(r<=0)break; tot+=r; sink+=b[0]; } double dt=now()-t0;
      printf("  pread 64MB chunks (page-cache hot), 1 thr: %.2f GB/s rss=%.0f MB\n", tot/dt/1e9, rss_mb()); free(b); }
    // (4) cold read via F_NOCACHE (macOS) — SSD bandwidth
#ifdef __APPLE__
    { int fd2=open(argv[1],O_RDONLY); fcntl(fd2,F_NOCACHE,1); size_t buf=8u<<20; uint8_t *b=malloc(buf+65536); uint8_t *bb=(uint8_t*)(((uintptr_t)b+4095)&~4095ull);
      double t0=now(); size_t tot=0; for(size_t off=0; off+buf<=n && tot < (1024u<<20); off+=buf){ ssize_t r=pread(fd2,bb,buf,off); if(r<=0)break; tot+=r; sink+=bb[0]; } double dt=now()-t0;
      printf("  F_NOCACHE pread 8MB chunks (SSD, uncached), 1 thr: %.2f GB/s over %.0f MB\n", tot/dt/1e9, tot/1048576.0); close(fd2); free(b); }
#else
    { int fd2=open(argv[1],O_RDONLY|O_DIRECT); if(fd2>=0){ size_t buf=8u<<20; void *bb; posix_memalign(&bb,4096,buf); double t0=now(); size_t tot=0; for(size_t off=0; off+buf<=n && tot < (1024u<<20); off+=buf){ ssize_t r=pread(fd2,bb,buf,off); if(r<=0)break; tot+=r; } double dt=now()-t0; printf("  O_DIRECT pread 8MB (SSD): %.2f GB/s\n", tot/dt/1e9); close(fd2);} }
#endif
    struct rusage ru; getrusage(RUSAGE_SELF,&ru); printf("  minflt=%ld majflt=%ld\n", ru.ru_minflt, ru.ru_majflt);
    return 0;
}
