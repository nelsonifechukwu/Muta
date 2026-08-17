// memprobe3: choose the prefetch primitive on Darwin. Layer-sized (64MB) units, page-cache hot.
// For each primitive: time to populate a 64MB unit from a helper thread (default and BG QoS),
// then read bandwidth of that unit with 4 threads (does the primitive install "fast" PTEs?),
// then evict via MAP_FIXED remap directly (no munlock) — check RSS drop.
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
#include <pthread.h>
#ifdef __APPLE__
#include <mach/mach.h>
#include <pthread/qos.h>
#endif
static double now(void){ struct timeval tv; gettimeofday(&tv,NULL); return tv.tv_sec + tv.tv_usec*1e-6; }
static double rss_mb(void){
#ifdef __APPLE__
    struct mach_task_basic_info info; mach_msg_type_number_t cnt = MACH_TASK_BASIC_INFO_COUNT;
    task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&info, &cnt); return info.resident_size/1048576.0;
#else
    FILE *f=fopen("/proc/self/statm","r"); long a,b; fscanf(f,"%ld %ld",&a,&b); fclose(f); return b*sysconf(_SC_PAGESIZE)/1048576.0;
#endif
}
static volatile uint64_t sink;
typedef struct { uint8_t *p; size_t n; size_t pg; int mode; int bg; int fd; size_t off; double dt; } job;
static void *helper(void *a_){ job *a=a_;
#ifdef __APPLE__
    if (a->bg) pthread_set_qos_class_self_np(QOS_CLASS_BACKGROUND, 0);
#endif
    double t0=now();
    if(a->mode==0){ madvise(a->p,a->n,MADV_WILLNEED); }
    else if(a->mode==1){ madvise(a->p,a->n,MADV_WILLNEED); uint64_t s=0; for(size_t o=0;o<a->n;o+=a->pg) s+=a->p[o]; sink+=s; }
    else if(a->mode==2){ mlock(a->p,a->n); }
    else if(a->mode==3){ uint64_t s=0; for(size_t o=0;o<a->n;o+=a->pg) s+=a->p[o]; sink+=s; }
    else if(a->mode==4){ /* pread into buffer then discard: warms cache only, not PTEs */ }
    a->dt=now()-t0; return NULL; }
typedef struct { const uint8_t *p; size_t n; } sarg;
static void *sum_thread(void *a_){ sarg *a=a_; const uint64_t *q=(const uint64_t*)a->p; size_t m=a->n/8; uint64_t s=0; for(size_t i=0;i<m;i+=8) s+=q[i]+q[i+1]+q[i+2]+q[i+3]+q[i+4]+q[i+5]+q[i+6]+q[i+7]; sink+=s; return NULL; }
static double sum4(const uint8_t *p,size_t n){ pthread_t th[4]; sarg a[4]; size_t chunk=(n/4)&~(size_t)63; double t0=now();
    for(int i=0;i<4;i++){a[i].p=p+i*chunk;a[i].n=(i==3)?n-i*chunk:chunk;pthread_create(&th[i],NULL,sum_thread,&a[i]);}
    for(int i=0;i<4;i++)pthread_join(th[i],NULL); return now()-t0; }
int main(int argc,char**argv){
    int fd=open(argv[1],O_RDONLY); struct stat st; fstat(fd,&st); size_t n=st.st_size; size_t pg=sysconf(_SC_PAGESIZE); n&=~(pg-1);
    uint8_t *p=mmap(NULL,n,PROT_READ,MAP_SHARED,fd,0);
    double dt=sum4(p,n); printf("warm pass: %.1f ms %.2f GB/s rss=%.0f\n", dt*1e3, n/dt/1e9, rss_mb());
    dt=sum4(p,n); printf("warm pass2: %.1f ms %.2f GB/s rss=%.0f\n", dt*1e3, n/dt/1e9, rss_mb());
    size_t unit=64u<<20; const char *names[]={"WILLNEED","WILLNEED+touch","mlock","touch"};
    for(int mode=0; mode<4; mode++) for(int bg=0; bg<2; bg++){
        // evict 8 units first
        double tot_pop=0, tot_read=0; int k;
        for(k=0;k<8;k++){ size_t off=(size_t)(k+2)*unit; mmap(p+off,unit,PROT_READ,MAP_SHARED|MAP_FIXED,fd,off); }
        double r0=rss_mb();
        for(k=0;k<8;k++){ size_t off=(size_t)(k+2)*unit; job j={p+off,unit,pg,mode,bg,fd,off,0}; pthread_t th; pthread_create(&th,NULL,helper,&j); pthread_join(th,NULL); tot_pop+=j.dt; }
        double r1=rss_mb();
        for(k=0;k<8;k++){ size_t off=(size_t)(k+2)*unit; tot_read+=sum4(p+off,unit); }
        // evict directly with remap (no munlock)
        double t0=now(); for(k=0;k<8;k++){ size_t off=(size_t)(k+2)*unit; mmap(p+off,unit,PROT_READ,MAP_SHARED|MAP_FIXED,fd,off);} double te=now()-t0; double r2=rss_mb();
        printf("%-16s %s: populate %.2f ms/unit (%.1f GB/s) rss %.0f->%.0f | read-after %.2f ms/unit (%.1f GB/s) | remap-evict %.2f ms/unit rss->%.0f\n",
            names[mode], bg?"BG-QoS ":"default", tot_pop/8*1e3, 8.0*unit/tot_pop/1e9, r0, r1, tot_read/8*1e3, 8.0*unit/tot_read/1e9, te/8*1e3, r2);
        if(mode==2){ for(k=0;k<8;k++){ size_t off=(size_t)(k+2)*unit; munlock(p+off,unit);} }
    }
    // reference: read of never-evicted units
    { double t=0; for(int k=0;k<8;k++){ size_t off=(size_t)(k+12)*unit; t+=sum4(p+off,unit);} printf("reference read of resident units: %.2f ms/unit (%.1f GB/s)\n", t/8*1e3, 8.0*unit/t/1e9); }
    return 0; }
