/* Kernel/local PID mapping for one namespace, using Linux UAPI only.
 * No pinned objects, target writes, signals or process creation. The caller owns
 * all returned FDs; closing the raw tracepoint FD detaches sampling immediately.
 * Key zero is reserved for an atomic map-update failure counter.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <linux/bpf.h>
#include <stdint.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <unistd.h>

struct wk_pid_record {
    uint64_t kernel_ids;
    uint32_t local_tid, local_tgid;
    uint64_t observed_boot_ns;
    char comm[16];
};
_Static_assert(sizeof(struct wk_pid_record) == 40, "PID map wire layout");

struct builder { struct bpf_insn instructions[96]; uint32_t count; };
static void emit(struct builder *b, uint8_t code, uint8_t dst, uint8_t src,
                 int16_t off, int32_t imm) {
    b->instructions[b->count++] = (struct bpf_insn){
        .code=code,.dst_reg=dst,.src_reg=src,.off=off,.imm=imm};
}
static void imm64(struct builder *b, uint8_t dst, uint8_t src, uint64_t value) {
    emit(b,BPF_LD|BPF_DW|BPF_IMM,dst,src,0,(int32_t)value);
    emit(b,0,0,0,0,(int32_t)(value>>32));
}
static void constant(struct builder *b, uint8_t dst, int32_t value) {
    emit(b,BPF_ALU64|BPF_MOV|BPF_K,dst,0,0,value);
}
static void stack(struct builder *b, uint8_t dst, int32_t offset) {
    emit(b,BPF_ALU64|BPF_MOV|BPF_X,dst,BPF_REG_10,0,0);
    emit(b,BPF_ALU64|BPF_ADD|BPF_K,dst,0,0,offset);
}
static void call(struct builder *b, int helper) {
    emit(b,BPF_JMP|BPF_CALL,0,0,0,helper);
}
static int bpf_call(enum bpf_cmd command, union bpf_attr *attr) {
    int result=(int)syscall(__NR_bpf,command,attr,sizeof(*attr));
    return result < 0 ? -errno : result;
}

int wk_pid_probe_lookup(int map_fd, uint32_t tid, struct wk_pid_record *record) {
    if(map_fd < 0 || !record) return -EINVAL;
    union bpf_attr attr={0};attr.map_fd=(uint32_t)map_fd;
    attr.key=(uint64_t)(uintptr_t)&tid;attr.value=(uint64_t)(uintptr_t)record;
    return bpf_call(BPF_MAP_LOOKUP_ELEM,&attr);
}

int wk_pid_probe_info(int map_fd, uint32_t out[5]) {
    if(map_fd < 0 || !out) return -EINVAL;
    struct bpf_map_info info={0};
    union bpf_attr attr={0};attr.info.bpf_fd=(uint32_t)map_fd;
    attr.info.info_len=sizeof(info);attr.info.info=(uint64_t)(uintptr_t)&info;
    int result=bpf_call(BPF_OBJ_GET_INFO_BY_FD,&attr);
    if(result < 0) return result;
    out[0]=info.id;out[1]=info.type;out[2]=info.key_size;
    out[3]=info.value_size;out[4]=info.max_entries;
    return 0;
}

int wk_pid_probe_open(uint64_t dev, uint64_t ino, uint32_t max_entries,
                     int out_fds[3], char *verifier, uint32_t verifier_size) {
    if(!out_fds || !verifier || verifier_size < 4096 || !dev || !ino
       || max_entries < 2 || max_entries > 16384) return -EINVAL;
    out_fds[0]=out_fds[1]=out_fds[2]=-1;
    memset(verifier,0,verifier_size);
    int map=-1,prog=-1,link=-1,result=0;
    struct rlimit limit={RLIM_INFINITY,RLIM_INFINITY};
    (void)setrlimit(RLIMIT_MEMLOCK,&limit);
    union bpf_attr attr={0};
    attr.map_type=BPF_MAP_TYPE_HASH;attr.key_size=4;
    attr.value_size=sizeof(struct wk_pid_record);attr.max_entries=max_entries;
    memcpy(attr.map_name,"wk_pid_binding",15);
    map=bpf_call(BPF_MAP_CREATE,&attr);
    if(map<0) { result=map;goto fail; }
    uint32_t zero=0;struct wk_pid_record zero_record={0};
    memset(&attr,0,sizeof(attr));attr.map_fd=(uint32_t)map;
    attr.key=(uint64_t)(uintptr_t)&zero;attr.value=(uint64_t)(uintptr_t)&zero_record;
    result=bpf_call(BPF_MAP_UPDATE_ELEM,&attr);
    if(result<0) goto fail;

    struct builder b={0};
    imm64(&b,BPF_REG_1,0,dev);imm64(&b,BPF_REG_2,0,ino);
    stack(&b,BPF_REG_3,-8);constant(&b,BPF_REG_4,8);
    call(&b,BPF_FUNC_get_ns_current_pid_tgid);
    uint32_t bad_namespace=b.count;
    emit(&b,BPF_JMP|BPF_JNE|BPF_K,BPF_REG_0,0,0,0);
    emit(&b,BPF_LDX|BPF_W|BPF_MEM,BPF_REG_6,BPF_REG_10,-8,0);
    uint32_t idle=b.count;emit(&b,BPF_JMP|BPF_JEQ|BPF_K,BPF_REG_6,0,0,0);
    emit(&b,BPF_STX|BPF_W|BPF_MEM,BPF_REG_10,BPF_REG_6,-12,0);
    call(&b,BPF_FUNC_get_current_pid_tgid);
    emit(&b,BPF_STX|BPF_DW|BPF_MEM,BPF_REG_10,BPF_REG_0,-64,0);
    emit(&b,BPF_LDX|BPF_DW|BPF_MEM,BPF_REG_6,BPF_REG_10,-8,0);
    emit(&b,BPF_STX|BPF_DW|BPF_MEM,BPF_REG_10,BPF_REG_6,-56,0);
    call(&b,BPF_FUNC_ktime_get_boot_ns);
    emit(&b,BPF_STX|BPF_DW|BPF_MEM,BPF_REG_10,BPF_REG_0,-48,0);
    stack(&b,BPF_REG_1,-40);constant(&b,BPF_REG_2,16);
    call(&b,BPF_FUNC_get_current_comm);
    imm64(&b,BPF_REG_1,BPF_PSEUDO_MAP_FD,(uint64_t)map);
    stack(&b,BPF_REG_2,-12);stack(&b,BPF_REG_3,-64);constant(&b,BPF_REG_4,BPF_ANY);
    call(&b,BPF_FUNC_map_update_elem);
    uint32_t stored=b.count;emit(&b,BPF_JMP|BPF_JEQ|BPF_K,BPF_REG_0,0,0,0);
    /* Record every update failure. Never silently accept a full hash map. */
    emit(&b,BPF_ST|BPF_W|BPF_MEM,BPF_REG_10,0,-12,0);
    imm64(&b,BPF_REG_1,BPF_PSEUDO_MAP_FD,(uint64_t)map);
    stack(&b,BPF_REG_2,-12);call(&b,BPF_FUNC_map_lookup_elem);
    uint32_t missing_counter=b.count;emit(&b,BPF_JMP|BPF_JEQ|BPF_K,BPF_REG_0,0,0,0);
    constant(&b,BPF_REG_1,1);
    emit(&b,BPF_STX|BPF_DW|BPF_XADD,BPF_REG_0,BPF_REG_1,0,0);
    uint32_t end=b.count;constant(&b,BPF_REG_0,0);emit(&b,BPF_JMP|BPF_EXIT,0,0,0,0);
    b.instructions[bad_namespace].off=(int16_t)(end-bad_namespace-1);
    b.instructions[idle].off=(int16_t)(end-idle-1);
    b.instructions[stored].off=(int16_t)(end-stored-1);
    b.instructions[missing_counter].off=(int16_t)(end-missing_counter-1);
    const char license[]="GPL";
    memset(&attr,0,sizeof(attr));attr.prog_type=BPF_PROG_TYPE_RAW_TRACEPOINT;
    attr.insn_cnt=b.count;attr.insns=(uint64_t)(uintptr_t)b.instructions;
    attr.license=(uint64_t)(uintptr_t)license;
    attr.log_buf=(uint64_t)(uintptr_t)verifier;attr.log_size=verifier_size;attr.log_level=1;
    memcpy(attr.prog_name,"wk_pid_binding",15);
    prog=bpf_call(BPF_PROG_LOAD,&attr);
    if(prog<0) { result=prog;goto fail; }
    const char tracepoint[]="sched_switch";
    memset(&attr,0,sizeof(attr));attr.raw_tracepoint.name=(uint64_t)(uintptr_t)tracepoint;
    attr.raw_tracepoint.prog_fd=(uint32_t)prog;
    link=bpf_call(BPF_RAW_TRACEPOINT_OPEN,&attr);
    if(link<0) { result=link;goto fail; }
    out_fds[0]=map;out_fds[1]=prog;out_fds[2]=link;
    return 0;
fail:
    if(link>=0) close(link);
    if(prog>=0) close(prog);
    if(map>=0) close(map);
    return result;
}
