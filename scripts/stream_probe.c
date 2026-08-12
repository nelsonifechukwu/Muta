/* scripts/stream_probe.c -- Task A3 (S0.3): eviction-semantics probe.
 *
 * The whole weight-streaming design (docs/STREAMING_PLAN.md) rests on one
 * claim: madvise(MADV_DONTNEED) followed by posix_fadvise(POSIX_FADV_DONTNEED)
 * actually uncharges cgroup v2 memory.current for a page-cache-backed
 * MAP_SHARED mapping -- the way llama.cpp mmaps GGUF weight files. This
 * program measures that claim directly, plus a plan-B fallback (an atomic
 * MAP_FIXED remap) and a WILLNEED prefetch path, against the real 4B model.
 *
 * Compiles on Linux (full path: posix_fadvise, cgroup v2 memory.current /
 * memory.stat, /proc/self/smaps_rollup) and macOS (those steps print
 * SKIPPED -- Darwin has no posix_fadvise and no cgroup accounting; mincore's
 * vector type is `char *` on Darwin vs `unsigned char *` on Linux).
 *
 * Usage: stream_probe <file> [region_mib=256]
 *
 * Regions are page-aligned and non-overlapping, fixed at file offsets
 * A=512 MiB, B=1024 MiB, C=1536 MiB, each region_mib long (so region_mib
 * must be <= 512 to avoid overlap). The whole file is mmap'd once
 * (PROT_READ, MAP_SHARED), matching llama.cpp's own mmap strategy.
 */

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#ifdef __APPLE__
typedef char mincore_vec_t;
#else
typedef unsigned char mincore_vec_t;
#endif

static long g_page_size;

/* ---------------------------------------------------------------- timing */

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1e6;
}

/* ------------------------------------------------ cgroup / smaps helpers
 * Linux only; return -1 (n/a) on macOS or when the path is unavailable. */

static long long read_cgroup_memory_current(void) {
#ifdef __APPLE__
    return -1;
#else
    FILE *f = fopen("/sys/fs/cgroup/memory.current", "r");
    if (!f) return -1;
    long long v = -1;
    if (fscanf(f, "%lld", &v) != 1) v = -1;
    fclose(f);
    return v;
#endif
}

static long long read_cgroup_memory_stat_file(void) {
#ifdef __APPLE__
    return -1;
#else
    FILE *f = fopen("/sys/fs/cgroup/memory.stat", "r");
    if (!f) return -1;
    char key[64];
    long long val;
    long long out = -1;
    while (fscanf(f, "%63s %lld", key, &val) == 2) {
        if (strcmp(key, "file") == 0) {
            out = val;
            break;
        }
    }
    fclose(f);
    return out;
#endif
}

static long long read_smaps_rollup_rss_kb(void) {
#ifdef __APPLE__
    return -1;
#else
    FILE *f = fopen("/proc/self/smaps_rollup", "r");
    if (!f) return -1;
    char line[256];
    long long kb = -1;
    while (fgets(line, sizeof line, f)) {
        if (strncmp(line, "Rss:", 4) == 0) {
            sscanf(line + 4, "%lld", &kb);
            break;
        }
    }
    fclose(f);
    return kb;
#endif
}

/* ---------------------------------------------------------------- mincore */

/* Resident percentage [0,100] of [addr, addr+len). -1.0 on mincore() error. */
static double mincore_percent(void *addr, size_t len) {
    long npages = (long)((len + (size_t)g_page_size - 1) / (size_t)g_page_size);
    mincore_vec_t *vec = malloc((size_t)npages * sizeof(mincore_vec_t));
    if (!vec) {
        perror("malloc(mincore vec)");
        exit(1);
    }
    int rc = mincore(addr, len, vec);
    if (rc != 0) {
        perror("mincore");
        free(vec);
        return -1.0;
    }
    long resident = 0;
    for (long i = 0; i < npages; i++) {
        if (vec[i] & 1) resident++;
    }
    free(vec);
    return npages ? (100.0 * (double)resident / (double)npages) : 0.0;
}

/* -------------------------------------------------------- touch a region */

/* Reads one byte per page. The volatile sink prevents the compiler from
 * eliding the loop; the accumulated value itself is not otherwise used. */
static void touch_region(void *addr, size_t len) {
    volatile unsigned char sink = 0;
    unsigned char *p = (unsigned char *)addr;
    for (size_t off = 0; off < len; off += (size_t)g_page_size) {
        sink ^= p[off];
    }
    (void)sink;
}

/* ------------------------------------------------------------- row table */

typedef struct {
    char name[48];
    long long before_cur;  /* cgroup memory.current before the step's action, -1 = n/a */
    long long after_cur;   /* cgroup memory.current after,  -1 = n/a */
    double mincore_pct;    /* resident %% of the region after the step, -1 = n/a */
    double elapsed_ms;     /* wall time of the step's measured action */
    long long rss_kb;      /* /proc/self/smaps_rollup Rss after the step, -1 = n/a */
    long long stat_file;   /* cgroup memory.stat "file" after the step, -1 = n/a */
    double pre_mincore_pct; /* resident %% right before the step's action; -1 = not recorded
                              * (only step 5 sets this, to show its warm-guard precondition). */
} row_t;

#define MAX_ROWS 16
static row_t g_rows[MAX_ROWS];
static int g_nrows = 0;

static int record_row(const char *name, long long before_cur, long long after_cur,
                       double mincore_pct, double elapsed_ms) {
    if (g_nrows >= MAX_ROWS) {
        fprintf(stderr, "record_row: table full\n");
        exit(1);
    }
    int idx = g_nrows++;
    row_t *r = &g_rows[idx];
    snprintf(r->name, sizeof r->name, "%s", name);
    r->before_cur = before_cur;
    r->after_cur = after_cur;
    r->mincore_pct = mincore_pct;
    r->elapsed_ms = elapsed_ms;
    r->rss_kb = read_smaps_rollup_rss_kb();
    r->stat_file = read_cgroup_memory_stat_file();
    r->pre_mincore_pct = -1.0;
    return idx;
}

static void fmt_ll(char *buf, size_t bufsz, long long v) {
    if (v < 0)
        snprintf(buf, bufsz, "n/a");
    else
        snprintf(buf, bufsz, "%lld", v);
}

static void print_table(void) {
    printf("\n=== results (bytes unless noted) ===\n");
    printf("%-42s %15s %15s %15s %9s %10s %10s %14s\n", "step", "before(B)",
           "after(B)", "delta(B)", "mincore%", "ms", "rss(KB)", "cg_file(B)");
    for (int i = 0; i < g_nrows; i++) {
        row_t *r = &g_rows[i];
        char before_s[24], after_s[24], delta_s[24], mc_s[16], rss_s[24], statf_s[24];
        fmt_ll(before_s, sizeof before_s, r->before_cur);
        fmt_ll(after_s, sizeof after_s, r->after_cur);
        if (r->before_cur < 0 || r->after_cur < 0)
            snprintf(delta_s, sizeof delta_s, "n/a");
        else
            snprintf(delta_s, sizeof delta_s, "%+lld", r->after_cur - r->before_cur);
        if (r->mincore_pct < 0)
            snprintf(mc_s, sizeof mc_s, "n/a");
        else
            snprintf(mc_s, sizeof mc_s, "%.1f", r->mincore_pct);
        fmt_ll(rss_s, sizeof rss_s, r->rss_kb);
        fmt_ll(statf_s, sizeof statf_s, r->stat_file);
        printf("%-42s %15s %15s %15s %9s %10.1f %10s %14s\n", r->name, before_s,
               after_s, delta_s, mc_s, r->elapsed_ms, rss_s, statf_s);
    }
}

/* ------------------------------------------------------- WILLNEED thread */

typedef struct {
    void *addr;
    size_t len;
    double call_elapsed_ms;
    int rc; /* errno-style: 0 == success */
} willneed_arg_t;

static void *willneed_thread(void *arg_) {
    willneed_arg_t *arg = (willneed_arg_t *)arg_;
    double t0 = now_ms();
    int rc = madvise(arg->addr, arg->len, MADV_WILLNEED);
    double t1 = now_ms();
    arg->rc = (rc == 0) ? 0 : errno;
    arg->call_elapsed_ms = t1 - t0;
    return NULL;
}

/* Step 4b discriminator: does a single big WILLNEED get capped by a
 * per-call readahead limit (force_page_cache_ra chunks against
 * bdi->io_pages/ra_pages), one that resets on every fresh madvise() call?
 * If so, repeated small calls should out-prefetch one big call. */
typedef struct {
    void *addr;
    size_t len;
    size_t chunk;
    double total_elapsed_ms; /* wall time of the whole chunk loop */
    int rc;                  /* first non-zero errno seen across all calls, else 0 */
} willneed_chunked_arg_t;

static void *willneed_chunked_thread(void *arg_) {
    willneed_chunked_arg_t *arg = (willneed_chunked_arg_t *)arg_;
    double t0 = now_ms();
    arg->rc = 0;
    for (size_t off = 0; off < arg->len; off += arg->chunk) {
        size_t remaining = arg->len - off;
        size_t this_len = (arg->chunk < remaining) ? arg->chunk : remaining;
        int rc = madvise((char *)arg->addr + off, this_len, MADV_WILLNEED);
        if (rc != 0 && arg->rc == 0) arg->rc = errno;
    }
    double t1 = now_ms();
    arg->total_elapsed_ms = t1 - t0;
    return NULL;
}

/* --------------------------------------------------------------- main */

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <file> [region_mib=256]\n", argv[0]);
        return 2;
    }
    const char *path = argv[1];
    long region_mib = (argc >= 3) ? strtol(argv[2], NULL, 10) : 256;
    if (region_mib <= 0) {
        fprintf(stderr, "region_mib must be > 0\n");
        return 2;
    }
    size_t region_len = (size_t)region_mib * 1024 * 1024;

    g_page_size = sysconf(_SC_PAGESIZE);
    if (g_page_size <= 0) g_page_size = 4096;

    if (region_len % (size_t)g_page_size != 0) {
        fprintf(stderr, "region_mib*1MiB must be a multiple of the page size (%ld)\n",
                g_page_size);
        return 2;
    }

    const size_t off_a = 512UL * 1024 * 1024;
    const size_t off_b = 1024UL * 1024 * 1024;
    const size_t off_c = 1536UL * 1024 * 1024;

    if (region_len > (off_b - off_a)) {
        fprintf(stderr,
                "region_mib=%ld would make regions overlap (max %zu MiB given "
                "fixed offsets 512/1024/1536 MiB)\n",
                region_mib, (off_b - off_a) / 1024 / 1024);
        return 2;
    }

    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        perror("open");
        return 1;
    }

    struct stat st;
    if (fstat(fd, &st) != 0) {
        perror("fstat");
        return 1;
    }
    size_t filesz = (size_t)st.st_size;

    if (off_c + region_len > filesz) {
        fprintf(stderr,
                "file too small for region_mib=%ld (need >= %zu bytes, have %zu)\n",
                region_mib, off_c + region_len, filesz);
        return 2;
    }

    printf("stream_probe: file=%s size=%zu bytes region_mib=%ld page_size=%ld\n", path,
           filesz, region_mib, g_page_size);
    printf("stream_probe: A=+%zuMiB B=+%zuMiB C=+%zuMiB, region=%zuMiB each\n",
           off_a / 1024 / 1024, off_b / 1024 / 1024, off_c / 1024 / 1024,
           region_len / 1024 / 1024);
#ifdef __APPLE__
    printf("stream_probe: platform=Darwin -- fadvise/cgroup steps print SKIPPED\n");
#else
    printf("stream_probe: platform=Linux\n");
#endif

    void *base = mmap(NULL, filesz, PROT_READ, MAP_SHARED, fd, 0);
    if (base == MAP_FAILED) {
        perror("mmap(whole file)");
        return 1;
    }

    unsigned char *A = (unsigned char *)base + off_a;
    unsigned char *B = (unsigned char *)base + off_b;
    unsigned char *C = (unsigned char *)base + off_c;

    /* ---- Step 1: touch A ---- */
    {
        long long before = read_cgroup_memory_current();
        double t0 = now_ms();
        touch_region(A, region_len);
        double t1 = now_ms();
        long long after = read_cgroup_memory_current();
        double mc = mincore_percent(A, region_len);
        record_row("1. touch A", before, after, mc, t1 - t0);
        double dt_s = (t1 - t0) / 1000.0;
        double mbps = dt_s > 0.0 ? ((double)region_len / 1024.0 / 1024.0) / dt_s : 0.0;
        printf("  [fault bandwidth: %.1f MiB/s]\n", mbps);
    }

    /* ---- Step 2: madvise(A, MADV_DONTNEED) alone ---- */
    {
        long long before = read_cgroup_memory_current();
        double t0 = now_ms();
        int rc = madvise(A, region_len, MADV_DONTNEED);
        double t1 = now_ms();
        if (rc != 0) perror("madvise(A, DONTNEED)");
        long long after = read_cgroup_memory_current();
        double mc = mincore_percent(A, region_len);
        record_row("2. madvise(A,DONTNEED) alone", before, after, mc, t1 - t0);
    }

    /* ---- Step 3: posix_fadvise(A, DONTNEED) after step 2 -- THE KEY MEASUREMENT ---- */
    int idx3;
    {
        long long before = read_cgroup_memory_current();
        double t0 = now_ms();
#ifdef __APPLE__
        printf("  [posix_fadvise: SKIPPED on macOS -- no such call on Darwin]\n");
        double t1 = t0;
#else
        int rc = posix_fadvise(fd, (off_t)off_a, (off_t)region_len, POSIX_FADV_DONTNEED);
        double t1 = now_ms();
        if (rc != 0) fprintf(stderr, "posix_fadvise(A): %s\n", strerror(rc));
#endif
        long long after = read_cgroup_memory_current();
        double mc = mincore_percent(A, region_len);
        idx3 = record_row("3. fadvise(A,DONTNEED) [KEY]", before, after, mc, t1 - t0);
    }

    /* ---- Step 3b: ordering control on region B ---- */
    {
        /* 3b-i: touch B */
        long long before = read_cgroup_memory_current();
        double t0 = now_ms();
        touch_region(B, region_len);
        double t1 = now_ms();
        long long after = read_cgroup_memory_current();
        double mc = mincore_percent(B, region_len);
        record_row("3b-i. touch B", before, after, mc, t1 - t0);
    }
    {
        /* 3b-ii: fadvise(B) WITHOUT madvise first -- expect ~0 or partial:
         * mapped pages are skipped by invalidate_mapping_pages(). */
        long long before = read_cgroup_memory_current();
        double t0 = now_ms();
#ifdef __APPLE__
        printf("  [posix_fadvise: SKIPPED on macOS]\n");
        double t1 = t0;
#else
        int rc = posix_fadvise(fd, (off_t)off_b, (off_t)region_len, POSIX_FADV_DONTNEED);
        double t1 = now_ms();
        if (rc != 0) fprintf(stderr, "posix_fadvise(B) no-madvise-first: %s\n", strerror(rc));
#endif
        long long after = read_cgroup_memory_current();
        double mc = mincore_percent(B, region_len);
        record_row("3b-ii. fadvise(B) no madvise first", before, after, mc, t1 - t0);
    }
    {
        /* 3b-iii: madvise(B, DONTNEED) -- drop the PTEs now */
        long long before = read_cgroup_memory_current();
        double t0 = now_ms();
        int rc = madvise(B, region_len, MADV_DONTNEED);
        double t1 = now_ms();
        if (rc != 0) perror("madvise(B, DONTNEED)");
        long long after = read_cgroup_memory_current();
        double mc = mincore_percent(B, region_len);
        record_row("3b-iii. madvise(B,DONTNEED)", before, after, mc, t1 - t0);
    }
    {
        /* 3b-iv: fadvise(B, DONTNEED) again, now that PTEs are gone --
         * expect Delta ~= -region, proving the ordering requirement. */
        long long before = read_cgroup_memory_current();
        double t0 = now_ms();
#ifdef __APPLE__
        printf("  [posix_fadvise: SKIPPED on macOS]\n");
        double t1 = t0;
#else
        int rc = posix_fadvise(fd, (off_t)off_b, (off_t)region_len, POSIX_FADV_DONTNEED);
        double t1 = now_ms();
        if (rc != 0) fprintf(stderr, "posix_fadvise(B) after madvise: %s\n", strerror(rc));
#endif
        long long after = read_cgroup_memory_current();
        double mc = mincore_percent(B, region_len);
        record_row("3b-iv. fadvise(B,DONTNEED) after madvise", before, after, mc, t1 - t0);
    }

    /* ---- Step 4: madvise(C, WILLNEED) from a second thread; main thread
     * polls mincore every 50 ms until >=95% or a 10 s timeout. ---- */
    {
        long long before = read_cgroup_memory_current();
        willneed_arg_t arg = {.addr = C, .len = region_len, .call_elapsed_ms = 0, .rc = 0};
        double t0 = now_ms();
        pthread_t th;
        if (pthread_create(&th, NULL, willneed_thread, &arg) != 0) {
            perror("pthread_create");
            return 1;
        }
        const double timeout_ms = 10000.0;
        double t_reach95 = -1.0;
        double mc = mincore_percent(C, region_len);
        for (;;) {
            mc = mincore_percent(C, region_len);
            double elapsed = now_ms() - t0;
            if (mc >= 95.0) {
                t_reach95 = elapsed;
                break;
            }
            if (elapsed >= timeout_ms) break;
            struct timespec ts = {.tv_sec = 0, .tv_nsec = 50L * 1000 * 1000};
            nanosleep(&ts, NULL);
        }
        pthread_join(th, NULL);
        double t1 = now_ms();
        long long after = read_cgroup_memory_current();
        double mc_final = mincore_percent(C, region_len);
        record_row("4. madvise(C,WILLNEED)+poll", before, after, mc_final, t1 - t0);
        if (arg.rc != 0) fprintf(stderr, "madvise(C, WILLNEED) failed: %s\n", strerror(arg.rc));

        if (t_reach95 >= 0.0) {
            double bw = t_reach95 > 0.0
                            ? ((double)region_len / 1024.0 / 1024.0) / (t_reach95 / 1000.0)
                            : 0.0;
            bool blocked = arg.call_elapsed_ms >= 0.8 * t_reach95;
            printf("  [madvise(WILLNEED) call: %.2f ms; mincore>=95%% reached after: "
                   "%.2f ms; prefetch bandwidth: %.1f MiB/s; call %s]\n",
                   arg.call_elapsed_ms, t_reach95, bw,
                   blocked ? "BLOCKED (call time ~= time-to-95%)"
                           : "did NOT block (returned promptly, readahead continued async)");
        } else {
            printf("  [madvise(WILLNEED) call: %.2f ms; mincore never reached 95%% within "
                   "%.0f ms timeout (last seen %.1f%%); does not block the go/no-go, "
                   "decided by steps 3/5 only -- see step 4b for the chunked discriminator]\n",
                   arg.call_elapsed_ms, timeout_ms, mc);
        }
    }

    /* ---- Step 4b: chunked-WILLNEED discriminator. Does one big WILLNEED
     * (step 4) stall because of a per-call readahead cap that resets on
     * every fresh madvise() call? Evict C to a clean cold baseline, then
     * issue WILLNEED in CHUNK-sized pieces across the whole region from a
     * second thread while polling mincore exactly like step 4. ---- */
    {
        const size_t CHUNK = 2UL * 1024 * 1024;

        madvise(C, region_len, MADV_DONTNEED);
#ifndef __APPLE__
        {
            int rc = posix_fadvise(fd, (off_t)off_c, (off_t)region_len, POSIX_FADV_DONTNEED);
            if (rc != 0) fprintf(stderr, "posix_fadvise(C) pre-4b evict: %s\n", strerror(rc));
        }
#endif
        double mc_start = mincore_percent(C, region_len);

        long long before = read_cgroup_memory_current();
        willneed_chunked_arg_t arg = {
            .addr = C, .len = region_len, .chunk = CHUNK, .total_elapsed_ms = 0, .rc = 0};
        double t0 = now_ms();
        pthread_t th;
        if (pthread_create(&th, NULL, willneed_chunked_thread, &arg) != 0) {
            perror("pthread_create (4b)");
            return 1;
        }
        const double timeout_ms = 10000.0;
        double t_reach95 = -1.0;
        double mc = mc_start;
        for (;;) {
            mc = mincore_percent(C, region_len);
            double elapsed = now_ms() - t0;
            if (mc >= 95.0) {
                t_reach95 = elapsed;
                break;
            }
            if (elapsed >= timeout_ms) break;
            struct timespec ts = {.tv_sec = 0, .tv_nsec = 50L * 1000 * 1000};
            nanosleep(&ts, NULL);
        }
        pthread_join(th, NULL);
        double t1 = now_ms();
        long long after = read_cgroup_memory_current();
        double mc_final = mincore_percent(C, region_len);
        record_row("4b. chunked WILLNEED(2MiB)+poll", before, after, mc_final, t1 - t0);
        if (arg.rc != 0)
            fprintf(stderr, "chunked madvise(C, WILLNEED) failed: %s\n", strerror(arg.rc));

        size_t nchunks = (region_len + CHUNK - 1) / CHUNK;
        if (t_reach95 >= 0.0) {
            double bw = t_reach95 > 0.0
                            ? ((double)region_len / 1024.0 / 1024.0) / (t_reach95 / 1000.0)
                            : 0.0;
            printf("  [chunked WILLNEED: %zu calls of %zuMiB (started from %.1f%% resident); "
                   "total call time %.2f ms; mincore>=95%% reached after: %.2f ms; "
                   "prefetch bandwidth: %.1f MiB/s]\n",
                   nchunks, CHUNK / 1024 / 1024, mc_start, arg.total_elapsed_ms, t_reach95, bw);
        } else {
            printf("  [chunked WILLNEED: %zu calls of %zuMiB (started from %.1f%% resident); "
                   "total call time %.2f ms; mincore never reached 95%% within %.0f ms "
                   "timeout (last seen %.1f%%); does not block the go/no-go, decided by "
                   "steps 3/5 only]\n",
                   nchunks, CHUNK / 1024 / 1024, mc_start, arg.total_elapsed_ms, timeout_ms, mc);
        }
    }

    /* Ensure region C is resident before step 5's plan-B validation --
     * step 4b above may already have warmed it; if not, fall back to an
     * explicit touch, so step 5 always measures the fallback's real
     * eviction behavior against a genuinely resident region rather than a
     * confound (docs/WORKLOG.md Phase 5 / Task A3 fix). */
    if (mincore_percent(C, region_len) < 95.0) {
        touch_region(C, region_len);
    }
    double mc_pre5 = mincore_percent(C, region_len);

    /* ---- Step 5: plan-B evict validation on region C (now resident):
     * MAP_FIXED remap over the same mapping/offset, then fadvise. ---- */
    int idx5;
    {
        long long before = read_cgroup_memory_current();
        double t0 = now_ms();
        void *remapped =
            mmap(C, region_len, PROT_READ, MAP_SHARED | MAP_FIXED, fd, (off_t)off_c);
        if (remapped == MAP_FAILED) {
            perror("mmap(MAP_FIXED remap C)");
            return 1;
        }
        if (remapped != (void *)C) {
            fprintf(stderr, "mmap(MAP_FIXED) returned %p, expected %p\n", remapped,
                    (void *)C);
            return 1;
        }
#ifdef __APPLE__
        printf("  [posix_fadvise: SKIPPED on macOS]\n");
#else
        int rc = posix_fadvise(fd, (off_t)off_c, (off_t)region_len, POSIX_FADV_DONTNEED);
        if (rc != 0) fprintf(stderr, "posix_fadvise(C) after MAP_FIXED remap: %s\n",
                              strerror(rc));
#endif
        double t1 = now_ms();
        long long after = read_cgroup_memory_current();
        double mc = mincore_percent(C, region_len);
        idx5 = record_row("5. MAP_FIXED remap C + fadvise", before, after, mc, t1 - t0);
        g_rows[idx5].pre_mincore_pct = mc_pre5;
    }

    print_table();

    /* ---- Verdict ---- */
    printf("\n=== VERDICT ===\n");
    long long b3 = g_rows[idx3].before_cur, a3 = g_rows[idx3].after_cur;
    long long b5 = g_rows[idx5].before_cur, a5 = g_rows[idx5].after_cur;

    if (b3 < 0 || a3 < 0) {
        printf("VERDICT: N/A -- cgroup v2 memory.current is unavailable on this platform "
               "(Darwin has no equivalent accounting). Informational run only; the "
               "primary/fallback determination requires the Linux container run.\n");
    } else {
        double frac3 = (double)(b3 - a3) / (double)region_len;
        printf("step 3 uncharge: %lld -> %lld bytes (%.1f%% of region reclaimed)\n", b3, a3,
               frac3 * 100.0);

        double frac5 = -1.0;
        bool have5 = (b5 >= 0 && a5 >= 0);
        if (have5) {
            frac5 = (double)(b5 - a5) / (double)region_len;
            printf("step 5 uncharge: %lld -> %lld bytes (%.1f%% of region reclaimed; "
                   "pre-step residency %.1f%%)\n",
                   b5, a5, frac5 * 100.0, g_rows[idx5].pre_mincore_pct);
        } else {
            printf("step 5 uncharge: data unavailable\n");
        }

        if (frac3 >= 0.90) {
            printf("VERDICT: PRIMARY -- madvise(MADV_DONTNEED) then "
                   "posix_fadvise(POSIX_FADV_DONTNEED), in that order, uncharges cgroup v2 "
                   "memory.current.\n");
        } else if (have5 && frac5 >= 0.90) {
            printf("VERDICT: FALLBACK -- MAP_FIXED remap + posix_fadvise uncharges "
                   "cgroup v2 memory.current (the plain madvise+fadvise ordering did "
                   "not reach 90%%).\n");
        } else if (have5) {
            printf("VERDICT: NONE -- neither primitive uncharges >=90%% of the region "
                   "under cgroup v2 memory.current. BLOCKED: the streaming design's "
                   "core eviction assumption does not hold as tested.\n");
        } else {
            printf("VERDICT: NONE -- step 3 did not reach 90%% and step 5 data is "
                   "unavailable.\n");
        }
    }

    munmap(base, filesz);
    close(fd);
    return 0;
}
