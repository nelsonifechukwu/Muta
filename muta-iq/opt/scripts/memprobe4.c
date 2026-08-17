// memprobe4: does a VM behavior hint change soft-fault+read throughput after MAP_FIXED remap?
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <pthread.h>
static double now(void){ struct timeval tv; gettimeofday(&tv,NULL); return tv.tv_sec + tv.tv_usec*1e-6; }
static volatile uint64_t sink;
typedef struct { const uint8_t *p; size_t n; } sarg;
static void *sum_thread(void *a_){ sarg *a=a_; const uint64_t *q=(const uint64_t*)a->p; size_t m=a->n/8; uint64_t s=0; for(size_t i=0;i<m;i+=8) s+=q[i]+q[i+1]+q[i+2]+q[i+3]+q[i+4]+q[i+5]+q[i+6]+q[i+7]; sink+=s; return NULL; }
static double sumN(const uint8_t *p,size_t n,int nth){ pthread_t th[8]; sarg a[8]; size_t chunk=(n/nth)&~(size_t)63; double t0=now();
    for(int i=0;i<nth;i++){a[i].p=p+i*chunk;a[i].n=(i==nth-1)?n-i*chunk:chunk;pthread_create(&th[i],NULL,sum_thread,&a[i]);}
    for(int i=0;i<nth;i++)pthread_join(th[i],NULL); return now()-t0; }
int main(int argc,char**argv){
    int fd=open(argv[1],O_RDONLY); struct stat st; fstat(fd,&st); size_t n=st.st_size; size_t pg=sysconf(_SC_PAGESIZE); n&=~(pg-1);
    uint8_t *p=mmap(NULL,n,PROT_READ,MAP_SHARED,fd,0);
    double dt=sumN(p,n,4); printf("warm pass: %.1f ms %.2f GB/s\n", dt*1e3, n/dt/1e9);
    dt=sumN(p,n,4); printf("warm pass2: %.1f ms %.2f GB/s\n", dt*1e3, n/dt/1e9);
    int hints[]={ -1, MADV_NORMAL, MADV_SEQUENTIAL, MADV_RANDOM, MADV_WILLNEED };
    const char *names[]={"none","NORMAL","SEQUENTIAL","RANDOM","WILLNEED"};
    for(int rep=0;rep<2;rep++) for(int h=0;h<5;h++){
        mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0);
        double th=0; if(hints[h]>=0){ double t0=now(); madvise(p,n,hints[h]); th=now()-t0; }
        dt=sumN(p,n,4); printf("remap + %-10s (hint %.1f ms): fault+read 4thr %.1f ms %.2f GB/s\n", names[h], th*1e3, dt*1e3, n/dt/1e9);
    }
    // 8 threads faulting
    mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0); dt=sumN(p,n,8); printf("remap + none: fault+read 8thr %.1f ms %.2f GB/s\n", dt*1e3, n/dt/1e9);
    // 64MB unit granularity: remap unit, hint SEQUENTIAL on unit, read unit (4 thr) — closer to the engine
    size_t unit=64u<<20; double tot=0; int k;
    for(k=0;k<16;k++){ size_t off=(size_t)(k+4)*unit; mmap(p+off,unit,PROT_READ,MAP_SHARED|MAP_FIXED,fd,off); tot+=sumN(p+off,unit,4);} printf("per-unit remap+read (no hint): %.2f ms/unit %.1f GB/s\n", tot/16*1e3, 16.0*unit/tot/1e9);
    tot=0; for(k=0;k<16;k++){ size_t off=(size_t)(k+4)*unit; mmap(p+off,unit,PROT_READ,MAP_SHARED|MAP_FIXED,fd,off); madvise(p+off,unit,MADV_SEQUENTIAL); tot+=sumN(p+off,unit,4);} printf("per-unit remap+SEQ+read: %.2f ms/unit %.1f GB/s\n", tot/16*1e3, 16.0*unit/tot/1e9);
    tot=0; for(k=0;k<16;k++){ size_t off=(size_t)(k+4)*unit; tot+=sumN(p+off,unit,4);} printf("per-unit read resident: %.2f ms/unit %.1f GB/s\n", tot/16*1e3, 16.0*unit/tot/1e9);
    return 0; }
