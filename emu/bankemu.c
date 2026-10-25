/* bankemu: run the full 2 MiB Samsung FALCON image (M-A8000SGZA) on emu8051.
 *
 * Needs the emu8051 core (MIT): https://github.com/jarikomppa/emu8051
 * and the interrupt-latch patch (see emu/patches/).
 *
 * Main difference from a plain 8051 run: code banking.
 * P1[4:0] is the bank number (32 banks of 64 KiB). P1[7:5] are board straps.
 * Code in any bank addresses 64 KiB. A P1 write moves the code window.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <util.h>
#include <unistd.h>
#include "emu8051.h"

#define MEMSZ 65536
#define NBANKS 32

static struct em8051 cpu;
static unsigned char *image, *banks[NBANKS], extdat[MEMSZ], upper[128];
static unsigned long long ticks_run, ops_run, bank_switches, resets, isr_hits;
static unsigned long long bank_hist[NBANKS];
static unsigned long gap_hist[MEMSZ];
static unsigned long long gplo = 0, gphi = 445000;
static unsigned char covered[NBANKS][MEMSZ];
static uint16_t ring[512];
static int ring_pos;
static FILE *conslog; static unsigned long long t_sleep, t_firstline; static int line_n;
static char linebuf[256]; static int linelen;
static unsigned long cons_bytes;
static int policy = 3; static int dbg_q; static int dbg1b;
static unsigned long long erased_reports;
static int trace_start; static unsigned long long trace_from = 0, trace_n = 40;

static int trace_sw;
static unsigned long long sw_log;
static void set_bank(int b)
{
    b &= 0x1F;
    if (trace_sw && sw_log < 24 && cpu.mCodeMem != banks[b]) {
        sw_log++;
        printf("  -> op=%llu switch at pc=0x%04X  bank %d -> %d  (P1=0x%02X)\n",
               ops_run, cpu.mPC, (int)((cpu.mCodeMem - image) / MEMSZ), b, cpu.mSFR[REG_P1]);
    }
    if (cpu.mCodeMem != banks[b]) {
        cpu.mCodeMem = banks[b];
        bank_switches++;
    }
    bank_hist[b]++;
}

static unsigned long xr_count[MEMSZ], xw_count2[MEMSZ];
/* map of the shared-memory window 0xA000..0xBFFF */
#define WN 0x2000
static unsigned long ar[WN], aw[WN];
static unsigned char aval[WN][32];
static uint16_t apc[WN]; static unsigned char apc_set[WN];
static int xtrace; static int watch_addr = -1; static int watch_n;
/* SEEDR=addr:len:val: return val on read while the cell is still zero */
static unsigned seedr_a, seedr_l; static int seedr_v = -1;
/* EVENTS="opcode:0xADDR=0xVAL;...": inject events from the peer subsystem */
static unsigned long long ev_ops[64]; static uint16_t ev_addr[64]; static uint8_t ev_val[64];
static int ev_n, ev_i; static int pty_on; static int pty_fd = -1;
/* peer subsystem model: answers the 0xFDF6/0xFDF7 mailbox */
static int peer_on;
static uint8_t peer_cmd, peer_busy;
struct stub { uint16_t a; uint8_t v; };
static struct stub stubs[64]; static int nstubs;
static int stub_lookup(uint16_t a, uint8_t *v)
{
    for (int i = 0; i < nstubs; i++) if (stubs[i].a == a) { *v = stubs[i].v; return 1; }
    return 0;
}
static uint8_t xread_cb(struct em8051 *c, uint16_t a)
{
    xr_count[a]++;
    if ((int)a == watch_addr && watch_n < 12) {
        watch_n++;
        printf("  [WATCH R] 0x%04X = 0x%02X  pc=0x%04X bank=%d op=%llu\n",
               a, c->mExtData[a], cpu.mPC, (int)((cpu.mCodeMem - image) / MEMSZ), ops_run);
    }
    if (xtrace && a >= 0xA000 && a < 0xC000) {
        unsigned i = a - 0xA000;
        ar[i]++; aval[i][0] = 0; (void)aval;
        if (!apc_set[i]) { apc[i] = cpu.mPC; apc_set[i] = 1; }
    }
    uint8_t sv;
    if (stub_lookup(a, &sv)) return sv;
    if (seedr_v >= 0 && a >= seedr_a && a < seedr_a + seedr_l && c->mExtData[a] == 0)
        return (uint8_t)seedr_v;
    if (peer_on && a == 0xFDF7) {
        if (peer_busy) { peer_busy = 0; return 0x81; }  /* ack from the peer */
        return 0x41;
    }
    if (a >= 0xE000) {
        if (policy == 1) return 0xFF;
        if (a == 0xF072) return 0x0C;   /* bit2/bit3: UART TX ready */
        if (a == 0xF036) return 0x04;   /* second channel */
        /* REGISTER MODEL: a read returns the last written value, as on hardware */
        if (xw_count2[a]) return c->mExtData[a];
        return 0x00;
    }
    return c->mExtData[a];
}

static void xwrite_cb(struct em8051 *c, uint16_t a, uint8_t v)
{
    c->mExtData[a] = v;
    xw_count2[a]++;
    if ((int)a == watch_addr && watch_n < 12) {
        watch_n++;
        printf("  [WATCH W] 0x%04X <- 0x%02X  pc=0x%04X bank=%d op=%llu\n",
               a, v, cpu.mPC, (int)((cpu.mCodeMem - image) / MEMSZ), ops_run);
    }
    if (xtrace && a >= 0xA000 && a < 0xC000) aw[a - 0xA000]++;
    if (peer_on) {
        if (a == 0xFDF6) peer_cmd = v;
        if (a == 0xFDF7 && (v & 0x40)) peer_busy = 1;
    }
    if (a == 0xF073 || a == 0xF037) {
        if (pty_fd >= 0) { ssize_t w = write(pty_fd, &v, 1); (void)w; }
        fputc(v, conslog);
        fflush(conslog);
        cons_bytes++;
        if (v == 0x0A || linelen >= 200) {
            linebuf[linelen] = 0;
            if (linelen > 1) {
                if (!line_n) t_firstline = ticks_run;
                printf("[%8.1f ms] %s\n", (double)(ticks_run - t_firstline) / 1000.0, linebuf);
                line_n++;
            }
            linelen = 0;
        } else if (v != 0x0D) {
            if (linelen < 200) linebuf[linelen++] = (char)v;
        }
    }
}

static int dbg_sfr, sfr_log;
static void sfr_dbg(struct em8051 *c, uint8_t reg)
{
    if (!dbg_sfr) return;
    if ((reg == 0xA8 || reg == 0x89 || reg == 0x88) && sfr_log < 30) {
        sfr_log++;
        printf("  [SFR] IE=0x%02X TMOD=0x%02X TCON=0x%02X  (write 0x%02X)\n",
               c->mSFR[REG_IE], c->mSFR[REG_TMOD], c->mSFR[REG_TCON], reg);
    }
}

static void p1_write(struct em8051 *c, uint8_t reg)
{
    (void)reg;
    set_bank(c->mSFR[REG_P1]);
}

static void trace_erased(uint16_t pc, unsigned long long op)
{
    printf("\n[!] op=%llu PC=0x%04X: entered erased flash. Previous 22:\n", op, pc);
    for (int i = 22; i > 0; i--) {
        uint16_t a = ring[(ring_pos - i) & 511];
        int b = 0;
        char s[64] = {0};
        decode(&cpu, a, s);
        (void)b;
        printf("    0x%04X  %-26s %02X %02X %02X\n", a, s,
               cpu.mCodeMem[a], cpu.mCodeMem[(a + 1) & 0xFFFF], cpu.mCodeMem[(a + 2) & 0xFFFF]);
    }
}

int main(int argc, char **argv)
{
    const char *path = argc > 1 ? argv[1] : "../fw1014.bin";
    unsigned long long limit = argc > 2 ? strtoull(argv[2], 0, 0) : 200000000ULL;

    if (getenv("POLICY")) policy = atoi(getenv("POLICY"));
    peer_on = getenv("PEER") != NULL;
    xtrace = getenv("XTRACE") != NULL;
    if (getenv("SEEDR")) {
        unsigned a, l, v;
        if (sscanf(getenv("SEEDR"), "0x%x:0x%x:0x%x", &a, &l, &v) == 3) {
            seedr_a = a; seedr_l = l; seedr_v = (int)v;
        }
    }
    if (getenv("EVENTS")) {
        char buf[1024]; snprintf(buf, sizeof buf, "%s", getenv("EVENTS"));
        for (char *t = strtok(buf, ";"); t && ev_n < 64; t = strtok(NULL, ";")) {
            unsigned long long o; unsigned a, v;
            if (sscanf(t, "%llu:reset", &o) == 1) {
                ev_ops[ev_n] = o; ev_addr[ev_n] = 0xFFFF; ev_val[ev_n] = 0; ev_n++;
                continue;
            }
            if (sscanf(t, "%llu:0x%x=0x%x", &o, &a, &v) == 3) {
                ev_ops[ev_n] = o; ev_addr[ev_n] = a; ev_val[ev_n] = (uint8_t)v; ev_n++;
            }
        }
    }
    if (getenv("WATCH")) watch_addr = (int)strtol(getenv("WATCH"), 0, 0);
    if (getenv("STUBS")) {
        char buf[512]; snprintf(buf, sizeof buf, "%s", getenv("STUBS"));
        for (char *t = strtok(buf, ","); t && nstubs < 64; t = strtok(NULL, ",")) {
            unsigned int a, v;
            if (sscanf(t, "0x%x=0x%x", &a, &v) == 2) { stubs[nstubs].a = a; stubs[nstubs].v = v; nstubs++; }
        }
    }
    trace_start = getenv("TRACE_START") != NULL;
    trace_sw = getenv("TRACE_SW") != NULL;
    if (getenv("TRACE_FROM")) trace_from = strtoull(getenv("TRACE_FROM"), 0, 0);
    if (getenv("TRACE_N")) trace_n = strtoull(getenv("TRACE_N"), 0, 0);

    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); return 1; }
    image = calloc(1, MEMSZ * NBANKS);
    if (fread(image, 1, MEMSZ * NBANKS, f) != MEMSZ * NBANKS) { fprintf(stderr, "short image\n"); return 1; }
    fclose(f);
    for (int i = 0; i < NBANKS; i++) banks[i] = image + i * MEMSZ;

    memset(&cpu, 0, sizeof cpu);
    cpu.mCodeMem = banks[0];
    cpu.mCodeMemMaxIdx = MEMSZ - 1;
    cpu.mExtData = extdat;
    cpu.mExtDataMaxIdx = MEMSZ - 1;
    cpu.mUpperData = upper;
    reset(&cpu, false);
    memset(extdat, 0, MEMSZ);
    if (getenv("SEED")) {   /* SEED=addr:len:val: fill an XDATA region */
        unsigned a, l, v;
        if (sscanf(getenv("SEED"), "0x%x:0x%x:0x%x", &a, &l, &v) == 3)
            for (unsigned i = 0; i < l && a + i < MEMSZ; i++) extdat[a + i] = (unsigned char)v;
    }

    cpu.xread = xread_cb;
    cpu.xwrite = xwrite_cb;
    cpu.sfrwrite[REG_P1] = p1_write;
    dbg_sfr = getenv("DEBUG_SFR") != NULL;
    if (dbg_sfr) {
        cpu.sfrwrite[REG_IE] = sfr_dbg;
        cpu.sfrwrite[REG_TMOD] = sfr_dbg;
        cpu.sfrwrite[REG_TCON] = sfr_dbg;
    }

    if (getenv("PTY")) {
        int m; if (openpty(&pty_fd, &m, NULL, NULL, NULL) == 0) {
            char *nm = ttyname(m);
            fprintf(stderr, "[pty] monitor UART: %s\n", nm ? nm : "?");
        }
    }
    conslog = fopen("console.log", "w");
    if (!conslog) { fprintf(stderr, "cannot create console.log\n"); return 1; }

    int cur_bank = 0;
    unsigned long long next_report = 0;

    while (ticks_run < limit) {
        uint16_t pc = cpu.mPC;
        int b = (int)((cpu.mCodeMem - image) / MEMSZ);
        if (tick(&cpu)) {
            ops_run++;
            covered[b][pc] = 1;
            ring[ring_pos++ & 511] = pc;
            if (pc == 0x3000) isr_hits++;
            if (pc == 0x8181 && !t_sleep) { t_sleep = ticks_run; }
            if (ticks_run > gplo && ticks_run < gphi) gap_hist[pc]++;
            if (getenv("GAP") && ticks_run % 250000 == 0 && ticks_run > 490000 && ticks_run < 3800000) {
                char b[64]={0}; decode(&cpu, cpu.mPC, b);
                printf("    t=%5.0f ms  bank=%2d pc=0x%04X  %s\n", (double)ticks_run/1000.0,
                       (int)((cpu.mCodeMem - image)/MEMSZ), cpu.mPC, b);
            }
            if (getenv("DEBUG_Q") && pc == 0x5655 && dbg_q < 24) {
                dbg_q++;
                printf("  [Q] A=[%02X %02X] B=[%02X %02X]  R6=%02X R7=%02X\n",
                       cpu.mLowerData[0x47], cpu.mLowerData[0x48],
                       cpu.mLowerData[0x4D], cpu.mLowerData[0x4E],
                       cpu.mLowerData[0x06], cpu.mLowerData[0x07]);
            }
            if (getenv("DEBUG_ERR") && pc == 0x1B41 && dbg1b < 3) {
                dbg1b++;
                printf("    [err-path] A=0x%02X R1=0x%02X R2=0x%02X ram[AE34]=0x%02X  mem[AD36+7*idx]=0x%02X\n",
                       cpu.mSFR[REG_ACC], cpu.mLowerData[0x01], cpu.mLowerData[0x02],
                       extdat[0xAE34], extdat[0xAD36 + 7 * extdat[0xAE34]]);
            }
            if (pc <= 3) {
                if (getenv("DEBUG_RESET") && resets < 2 && ops_run > 1000) {
                    printf("\n[RESET] op=%llu bank=%d: previous 26:\n", ops_run,
                           (int)((cpu.mCodeMem - image) / MEMSZ));
                    for (int i = 26; i > 0; i--) {
                        uint16_t a = ring[(ring_pos - i) & 511];
                        char t[64] = {0}; decode(&cpu, a, t);
                        printf("    0x%04X  %-24s\n", a, t);
                    }
                }
                resets++;
            }
            if (trace_start && ops_run >= trace_from && ops_run < trace_from + trace_n) {
                char s2[64] = {0}; decode(&cpu, cpu.mPC, s2);
                printf("  #%-3llu bank=%2d pc=0x%04X  %-24s P1=0x%02X\n", ops_run, b, pc, s2, cpu.mSFR[REG_P1]);
            }
        }
        ticks_run++;

        if (getenv("PERIODIC") && !(ops_run % 2000000)) {
            printf("    [t=%llu] IRAM[47..4E]=%02X %02X %02X %02X %02X %02X %02X %02X IE=0x%02X\n",
                   ops_run, cpu.mLowerData[0x47], cpu.mLowerData[0x48], cpu.mLowerData[0x49],
                   cpu.mLowerData[0x4A], cpu.mLowerData[0x4B], cpu.mLowerData[0x4C],
                   cpu.mLowerData[0x4D], cpu.mLowerData[0x4E], cpu.mSFR[REG_IE]);
            printf("      IE=0x%02X intActive=%d TCON=0x%02X isr=%llu PC=0x%04X\n",
                   cpu.mSFR[REG_IE], cpu.mInterruptActive, cpu.mSFR[REG_TCON], isr_hits, cpu.mPC);
        }
        while (ev_i < ev_n && ops_run >= ev_ops[ev_i]) {
            if (ev_addr[ev_i] == 0xFFFF) {
                printf("  [EVENT] op=%llu warm reset (wake line)\n", ops_run);
                reset(&cpu, false);
                ev_i++;
                continue;
            }
            int found = 0;
            for (int k = 0; k < nstubs; k++)
                if (stubs[k].a == ev_addr[ev_i]) { stubs[k].v = ev_val[ev_i]; found = 1; }
            if (!found && nstubs < 64) {
                stubs[nstubs].a = ev_addr[ev_i]; stubs[nstubs].v = ev_val[ev_i]; nstubs++;
            }
            printf("  [EVENT] op=%llu 0x%04X := 0x%02X\n", ops_run, ev_addr[ev_i], ev_val[ev_i]);
            ev_i++;
        }
        if ((getenv("DEBUG_ERASED") || getenv("HALT_ERASED")) && erased_reports < 3 && cpu.mCodeMem[pc] == 0xFF && ops_run > 1000) {
            int k = 0;
            while (k < 16 && cpu.mCodeMem[(pc + k) & 0xFFFF] == 0xFF) k++;
            if (k == 16) {
                if (getenv("HALT_ERASED")) {
                    printf("[HALT] %.1f ms: PC=0x%04X bank=%d entered erased flash\n",
                           (double)(ticks_run - t_firstline) / 1000.0, pc,
                           (int)((cpu.mCodeMem - image) / MEMSZ));
                    break;
                }
                printf("\n[!] op=%llu PC=0x%04X bank=%d: erased flash. Previous 26:\n",
                       ops_run, pc, (int)((cpu.mCodeMem - image) / MEMSZ));
                for (int i = 26; i > 0; i--) {
                    uint16_t a = ring[(ring_pos - i) & 511];
                    char t[64] = {0}; decode(&cpu, a, t);
                    printf("    0x%04X  %-24s\n", a, t);
                }
                erased_reports++;
            }
        }
        (void)cur_bank;
        (void)next_report;
    }
    fclose(conslog);

    unsigned long long cov = 0;
    for (int i = 0; i < NBANKS; i++)
        for (int j = 0; j < MEMSZ; j++) cov += covered[i][j];

    printf("\n== %s: ops=%llu pc=0x%04X bank=%d switches=%llu resets=%llu cov=%llu console=%lu bytes ==\n",
           path, ops_run, cpu.mPC, (int)((cpu.mCodeMem - image) / MEMSZ),
           bank_switches, resets, cov, cons_bytes);
    if (xtrace) {
        printf("-- window 0xA000..0xBFFF: read-only addresses (external inputs) --\n");
        int shown = 0;
        for (int i = 0; i < WN && shown < 24; i++) {
            if (!ar[i] || aw[i]) continue;
            printf("  0x%04X  R x%-8lu  first read @pc=0x%04X:", 0xA000 + i, ar[i], apc[i]);
            for (int k = 0; k < 10; k++) {
                char b[64] = {0}; unsigned len = decode(&cpu, (uint16_t)(apc[i] + k), b);
                printf(" | %s", b); (void)len;
                break;
            }
            printf("\n");
            shown++;
        }
        printf("-- window: written addresses (initialized by the firmware) --\n");
        shown = 0;
        for (int i = 0; i < WN && shown < 12; i++) {
            if (!aw[i]) continue;
            printf("  0x%04X  R x%-8lu W x%-8lu\n", 0xA000 + i, ar[i], aw[i]);
            shown++;
        }
    }
    if (getenv("GAP")) {
        printf("-- top instructions in the 490..3780 ms window --\n");
        for (int k = 0; k < 10; k++) {
            unsigned long best = 0; int bp = -1;
            for (int i = 0; i < MEMSZ; i++) if (gap_hist[i] > best) { best = gap_hist[i]; bp = i; }
            if (bp < 0 || !best) break;
            char b[64] = {0}; decode(&cpu, (uint16_t)bp, b);
            printf("   %8lu x 0x%04X %s\n", best, bp, b);
            gap_hist[bp] = 0;
        }
    }
    if (t_sleep)
        printf("sleep loop entry: %.1f ms after the first log line\n",
               (double)(t_sleep - t_firstline) / 1000.0);
    printf("ISR(0x3000) entries: %llu\n", isr_hits);
    printf("-- top XDATA reads (what it polls) --\n");
    for (int k = 0; k < 10; k++) {
        int best = -1; unsigned long bv = 0;
        for (int i = 0; i < MEMSZ; i++) if (xr_count[i] > bv) { bv = xr_count[i]; best = i; }
        if (best < 0 || !bv) break;
        printf("  0x%04X  R x%-9lu  W x%lu\n", best, bv, xw_count2[best]);
        xr_count[best] = 0;
    }
    printf("-- banks used --\n");
    for (int i = 0; i < NBANKS; i++)
        if (bank_hist[i]) printf("  bank %2d: %10llu opcodes\n", i, bank_hist[i]);
    return 0;
}
