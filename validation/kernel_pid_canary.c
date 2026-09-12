/* Self-only BPF capability probe. No SITL, ptrace, signals, or pinned BPF objects.
 * Uses Linux UAPI instructions directly, so clang/libbpf are not prerequisites.
 * A map entry requires BOTH the selected PID namespace and this process's TID.
 * Helpers: Linux v6.6 include/uapi/linux/bpf.h.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <linux/bpf.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static struct bpf_insn program[64];
static size_t count;
static void emit(uint8_t code, uint8_t dst, uint8_t src, int16_t off, int32_t imm) {
    program[count++] = (struct bpf_insn){.code=code,.dst_reg=dst,.src_reg=src,.off=off,.imm=imm};
}
static void imm64(uint8_t dst, uint8_t src, uint64_t value) {
    emit(BPF_LD|BPF_DW|BPF_IMM, dst, src, 0, (int32_t)value);
    emit(0,0,0,0,(int32_t)(value>>32));
}
static void mov(uint8_t dst, uint8_t src) { emit(BPF_ALU64|BPF_MOV|BPF_X,dst,src,0,0); }
static void constant(uint8_t dst, int32_t value) { emit(BPF_ALU64|BPF_MOV|BPF_K,dst,0,0,value); }
static void stack(uint8_t dst, int32_t offset) {
    mov(dst,BPF_REG_10); emit(BPF_ALU64|BPF_ADD|BPF_K,dst,0,0,offset);
}
static void call(int helper) { emit(BPF_JMP|BPF_CALL,0,0,0,helper); }
static int bpf_call(enum bpf_cmd command, union bpf_attr *attr) {
    return (int)syscall(__NR_bpf,command,attr,sizeof(*attr));
}
struct record { uint64_t kernel_ids; uint32_t local_tid,local_tgid; uint64_t observed_ns; };
_Static_assert(sizeof(struct record)==24,"map layout");

int main(void) {
    int map=-1,prog=-1,link=-1,result=1;
    uint32_t tid=(uint32_t)syscall(SYS_gettid);
    struct stat ns;
    struct record record={0};
    char verifier[65536]={0};
    const char license[]="GPL";
    const char tracepoint[]="sched_switch";
    struct rlimit limit={RLIM_INFINITY,RLIM_INFINITY};
    if (stat("/proc/self/ns/pid",&ns)<0) { perror("pid namespace stat"); return 1; }
    /* Older kernels account BPF memory against RLIMIT_MEMLOCK. Failure is safe:
       MAP_CREATE/PROG_LOAD still enforce the actual kernel limits. */
    (void)setrlimit(RLIMIT_MEMLOCK,&limit);
    union bpf_attr attr={0};
    attr.map_type=BPF_MAP_TYPE_HASH;attr.key_size=4;attr.value_size=sizeof(record);attr.max_entries=1;
    map=bpf_call(BPF_MAP_CREATE,&attr);
    if(map<0) { perror("BPF_MAP_CREATE"); goto done; }
    imm64(BPF_REG_1,0,(uint64_t)ns.st_dev);
    imm64(BPF_REG_2,0,(uint64_t)ns.st_ino);
    stack(BPF_REG_3,-8);constant(BPF_REG_4,8);
    call(BPF_FUNC_get_ns_current_pid_tgid);
    size_t bad_namespace=count; emit(BPF_JMP|BPF_JNE|BPF_K,BPF_REG_0,0,0,0);
    emit(BPF_LDX|BPF_W|BPF_MEM,BPF_REG_6,BPF_REG_10,-8,0);
    size_t other_thread=count; emit(BPF_JMP|BPF_JNE|BPF_K,BPF_REG_6,0,0,(int32_t)tid);
    emit(BPF_STX|BPF_W|BPF_MEM,BPF_REG_10,BPF_REG_6,-12,0);
    call(BPF_FUNC_get_current_pid_tgid);
    emit(BPF_STX|BPF_DW|BPF_MEM,BPF_REG_10,BPF_REG_0,-40,0);
    emit(BPF_LDX|BPF_DW|BPF_MEM,BPF_REG_6,BPF_REG_10,-8,0);
    emit(BPF_STX|BPF_DW|BPF_MEM,BPF_REG_10,BPF_REG_6,-32,0);
    call(BPF_FUNC_ktime_get_ns);
    emit(BPF_STX|BPF_DW|BPF_MEM,BPF_REG_10,BPF_REG_0,-24,0);
    imm64(BPF_REG_1,BPF_PSEUDO_MAP_FD,(uint64_t)map);
    stack(BPF_REG_2,-12);stack(BPF_REG_3,-40);constant(BPF_REG_4,BPF_ANY);
    call(BPF_FUNC_map_update_elem);
    size_t exit_index=count; constant(BPF_REG_0,0);emit(BPF_JMP|BPF_EXIT,0,0,0,0);
    program[bad_namespace].off=(int16_t)(exit_index-bad_namespace-1);
    program[other_thread].off=(int16_t)(exit_index-other_thread-1);
    memset(&attr,0,sizeof(attr));attr.prog_type=BPF_PROG_TYPE_RAW_TRACEPOINT;
    attr.insn_cnt=(uint32_t)count;attr.insns=(uint64_t)(uintptr_t)program;
    attr.license=(uint64_t)(uintptr_t)license;attr.log_buf=(uint64_t)(uintptr_t)verifier;
    attr.log_size=sizeof(verifier);attr.log_level=1;
    prog=bpf_call(BPF_PROG_LOAD,&attr);
    if(prog<0) { perror("BPF_PROG_LOAD");fputs(verifier,stderr);goto done; }
    fputs(verifier,stderr);
    memset(&attr,0,sizeof(attr));attr.raw_tracepoint.name=(uint64_t)(uintptr_t)tracepoint;
    attr.raw_tracepoint.prog_fd=(uint32_t)prog;
    link=bpf_call(BPF_RAW_TRACEPOINT_OPEN,&attr);
    if(link<0) { perror("BPF_RAW_TRACEPOINT_OPEN");goto done; }
    for(int attempt=0;attempt<100;attempt++) {
        struct timespec delay={0,1000000};nanosleep(&delay,NULL);
        memset(&attr,0,sizeof(attr));attr.map_fd=(uint32_t)map;
        attr.key=(uint64_t)(uintptr_t)&tid;attr.value=(uint64_t)(uintptr_t)&record;
        if(bpf_call(BPF_MAP_LOOKUP_ELEM,&attr)==0) {
            if(record.local_tid!=tid || record.local_tgid!=(uint32_t)getpid()
               || !record.observed_ns || !(uint32_t)record.kernel_ids
               || !(uint32_t)(record.kernel_ids>>32)) {
                fputs("BPF self identity mismatch\n",stderr);goto done;
            }
            result=0;break;
        }
        if(errno!=ENOENT) { perror("BPF_MAP_LOOKUP_ELEM");goto done; }
    }
    if(result) fputs("No self scheduler mapping in bounded window\n",stderr);
done:
    if(link>=0 && close(link)<0) { perror("close link");result=1; }
    if(prog>=0 && close(prog)<0) { perror("close program");result=1; }
    if(map>=0 && close(map)<0) { perror("close map");result=1; }
    printf("{\"status\":\"%s\",\"scope\":\"self-only kernel helper canary\","
           "\"pid_ns_dev\":%"PRIu64",\"pid_ns_inode\":%"PRIu64","
           "\"local_tid\":%u,\"local_tgid\":%u,\"kernel_tid\":%u,\"kernel_tgid\":%u,"
           "\"observed_monotonic_ns\":%"PRIu64",\"all_fds_close_attempted\":true}\n",
           result?"fail":"pass",(uint64_t)ns.st_dev,(uint64_t)ns.st_ino,
           record.local_tid,record.local_tgid,(uint32_t)record.kernel_ids,
           (uint32_t)(record.kernel_ids>>32),record.observed_ns);
    return result;
}
