// memprobe2: prefetch primitives on a page-cache-hot mmap after MAP_FIXED remap:
//  (a) madvise(WILLNEED) — does it populate PTEs (RSS up)? speed?
//  (b) mlock/munlock speed and RSS effect
//  (c) touch with QOS_CLASS_BACKGROUND threads (E-cores) while N compute threads spin
//  (d) TLB-shootdown cost: time a tight compute loop on 4 threads while another thread does MAP_FIXED remaps
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
#include <stdatomic.h>
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
typedef struct { const uint8_t *p; size_t n; size_t pg; int bg; } targ;
static void *touch_thread(void *a_){ targ *a=a_;
#ifdef __APPLE__
    if (a->bg) pthread_set_qos_class_self_np(QOS_CLASS_BACKGROUND, 0);
#endif
    uint64_t s=0; for(size_t o=0;o<a->n;o+=a->pg) s+=a->p[o]; sink+=s; return NULL; }
static atomic_int stop_spin;
static atomic_llong spin_iters;
static void *spin_thread(void *a_){ (void)a_; volatile double x=1.0; long long it=0; while(!atomic_load(&stop_spin)){ for(int i=0;i<100000;i++) x=x*1.0000001+0.0000001; it++; } atomic_fetch_add(&spin_iters,it); sink+= (uint64_t)x; return NULL; }
static void *sum_thread(void *a_){ targ *a=a_; const uint64_t *q=(const uint64_t*)a->p; size_t m=a->n/8; uint64_t s=0; for(size_t i=0;i<m;i+=8) s+=q[i]+q[i+1]+q[i+2]+q[i+3]+q[i+4]+q[i+5]+q[i+6]+q[i+7]; sink+=s; return NULL; }
static double touch(const uint8_t *p,size_t n,size_t pg,int nth,int bg){ pthread_t th[16]; targ a[16]; size_t chunk=(n/nth)&~(pg-1); double t0=now();
    for(int i=0;i<nth;i++){a[i].p=p+i*chunk;a[i].n=(i==nth-1)?n-i*chunk:chunk;a[i].pg=pg;a[i].bg=bg;pthread_create(&th[i],NULL,touch_thread,&a[i]);}
    for(int i=0;i<nth;i++)pthread_join(th[i],NULL); return now()-t0; }
static double sum(const uint8_t *p,size_t n,int nth){ pthread_t th[16]; targ a[16]; size_t chunk=(n/nth)&~(size_t)63; double t0=now();
    for(int i=0;i<nth;i++){a[i].p=p+i*chunk;a[i].n=(i==nth-1)?n-i*chunk:chunk;pthread_create(&th[i],NULL,sum_thread,&a[i]);}
    for(int i=0;i<nth;i++)pthread_join(th[i],NULL); return now()-t0; }
int main(int argc,char**argv){
    int fd=open(argv[1],O_RDONLY); struct stat st; fstat(fd,&st); size_t n=st.st_size; if(argc>2){size_t w=strtoull(argv[2],0,0); if(w<n)n=w;}
    size_t pg=sysconf(_SC_PAGESIZE); n&=~(pg-1);
    uint8_t *p=mmap(NULL,n,PROT_READ,MAP_SHARED,fd,0);
    printf("bytes=%.0f MB\n", n/1048576.0);
    double dt=sum(p,n,4); printf("warm pass: %.1f ms %.2f GB/s rss=%.0f\n", dt*1e3, n/dt/1e9, rss_mb());
    dt=sum(p,n,4); printf("warm pass2: %.1f ms %.2f GB/s rss=%.0f\n", dt*1e3, n/dt/1e9, rss_mb());
    // (a) WILLNEED after remap
    mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0); printf("after remap rss=%.0f\n", rss_mb());
    double t0=now(); int r=madvise(p,n,MADV_WILLNEED); dt=now()-t0; printf("(a) madvise(WILLNEED) whole: ret=%d %.1f ms (%.2f GB/s) rss=%.0f MB\n", r, dt*1e3, n/dt/1e9, rss_mb());
    dt=sum(p,n,4); printf("    read after WILLNEED: %.1f ms %.2f GB/s rss=%.0f\n", dt*1e3, n/dt/1e9, rss_mb());
    // per-64MB WILLNEED
    mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0); t0=now(); for(size_t o=0;o<n;o+=64u<<20){ size_t l=(o+(64u<<20)<=n)?(64u<<20):n-o; madvise(p+o,l,MADV_WILLNEED);} dt=now()-t0; printf("(a2) WILLNEED in 64MB chunks: %.1f ms (%.2f GB/s) rss=%.0f\n", dt*1e3, n/dt/1e9, rss_mb());
    // (b) mlock
    mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0); t0=now(); r=mlock(p,n); dt=now()-t0; printf("(b) mlock whole: ret=%d %.1f ms (%.2f GB/s) rss=%.0f MB\n", r, dt*1e3, n/dt/1e9, rss_mb());
    dt=sum(p,n,4); printf("    read after mlock: %.1f ms %.2f GB/s\n", dt*1e3, n/dt/1e9);
    t0=now(); r=munlock(p,n); dt=now()-t0; printf("    munlock: ret=%d %.1f ms rss=%.0f\n", r, dt*1e3, rss_mb());
    t0=now(); mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0); dt=now()-t0; printf("    remap after munlock: %.1f ms rss=%.0f\n", dt*1e3, rss_mb());
    // (c) touch by BACKGROUND-QoS threads (E-cores) with 4 spinning compute threads
    for(int nth=1; nth<=4; nth*=2){
      mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0);
      atomic_store(&stop_spin,0); atomic_store(&spin_iters,0); pthread_t sp[4]; for(int i=0;i<4;i++) pthread_create(&sp[i],NULL,spin_thread,NULL);
      usleep(100000); long long base=atomic_load(&spin_iters); double tb=now();
      dt=touch(p,n,pg,nth,1);
      double te=now(); long long it=atomic_load(&spin_iters)-base; atomic_store(&stop_spin,1); for(int i=0;i<4;i++) pthread_join(sp[i],NULL);
      printf("(c) BG-QoS touch %d thr with 4 spinners: %.1f ms (%.2f GB/s) rss=%.0f | spinner rate %.0f it/s\n", nth, dt*1e3, n/dt/1e9, rss_mb(), it/(te-tb));
    }
    // spinner baseline rate
    { atomic_store(&stop_spin,0); atomic_store(&spin_iters,0); pthread_t sp[4]; for(int i=0;i<4;i++) pthread_create(&sp[i],NULL,spin_thread,NULL); usleep(100000); long long base=atomic_load(&spin_iters); double tb=now(); usleep(500000); double te=now(); long long it=atomic_load(&spin_iters)-base; atomic_store(&stop_spin,1); for(int i=0;i<4;i++) pthread_join(sp[i],NULL); printf("    spinner baseline rate %.0f it/s\n", it/(te-tb)); }
    // (c2) touch by default-QoS threads with 4 spinners
    for(int nth=1; nth<=4; nth*=2){ mmap(p,n,PROT_READ,MAP_SHARED|MAP_FIXED,fd,0);
      atomic_store(&stop_spin,0); atomic_store(&spin_iters,0); pthread_t sp[4]; for(int i=0;i<4;i++) pthread_create(&sp[i],NULL,spin_thread,NULL); usleep(100000); long long base=atomic_load(&spin_iters); double tb=now();
      dt=touch(p,n,pg,nth,0); double te=now(); long long it=atomic_load(&spin_iters)-base; atomic_store(&stop_spin,1); for(int i=0;i<4;i++) pthread_join(sp[i],NULL);
      printf("(c2) default-QoS touch %d thr with 4 spinners: %.1f ms (%.2f GB/s) | spinner rate %.0f it/s\n", nth, dt*1e3, n/dt/1e9, it/(te-tb)); }
    // (d) shootdown cost: 4 spinners while remapping 64MB slices 200 times
    { atomic_store(&stop_spin,0); atomic_store(&spin_iters,0); pthread_t sp[4]; for(int i=0;i<4;i++) pthread_create(&sp[i],NULL,spin_thread,NULL); usleep(100000); long long base=atomic_load(&spin_iters); double tb=now();
      for(int k=0;k<200;k++){ size_t o=(k%32)*(64u<<20); if(o+(64u<<20)>n) continue; mmap(p+o,64u<<20,PROT_READ,MAP_SHARED|MAP_FIXED,fd,o);} double te=now(); long long it=atomic_load(&spin_iters)-base; atomic_store(&stop_spin,1); for(int i=0;i<4;i++) pthread_join(sp[i],NULL);
      printf("(d) 200 x 64MB MAP_FIXED remaps in %.1f ms (%.3f ms each) | spinner rate during %.0f it/s\n", (te-tb)*1e3, (te-tb)*1e3/200, it/(te-tb)); }
    return 0;
}
