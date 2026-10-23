/* Compile the SDK VFS once in this translation unit so the extension shares
 * its descriptor table. The SDK checkout itself remains unchanged. */
#include PORT_PPU_FS_SOURCE
#include <limits.h>

static void port_fs_read_with_offset(ppu_context* c)
{
    int fd=(int)(uint32_t)c->gpr[3];
    uint64_t offset=c->gpr[4], count=c->gpr[6];
    uint32_t buf=(uint32_t)c->gpr[5], out=(uint32_t)c->gpr[7];
    int32_t error=0;
    if (out && ppu_vm_size && (uint64_t)out+8>ppu_vm_size) {
        c->gpr[3]=(uint64_t)(int64_t)(int32_t)0x8001000Du; return;
    }
    if (out) vm_write64(out,0);
    if (fd<3 || fd>=FS_MAX || !g_files[fd]) error=(int32_t)0x8001002Au;
    else if (offset>INT64_MAX) error=(int32_t)0x80010002u;
    else if ((count && !buf) || (uint64_t)buf+count < count ||
             (ppu_vm_size && (uint64_t)buf+count>ppu_vm_size)) error=(int32_t)0x8001000Du;
    else if (count) {
        fs_prefault(buf,count);
        ssize_t n;
        do { n=pread(fileno(g_files[fd]),vm_base+buf,(size_t)count,(off_t)offset); }
        while(n<0 && errno==EINTR);
        if(n<0) error=(int32_t)CELL_FS_EIO;
        else if(out) vm_write64(out,(uint64_t)n);
        static int logged=0;
        if(logged++<8) fprintf(stderr,"[port-fs] pread fd=%d offset=%llu requested=%llu -> %lld\n",
            fd,(unsigned long long)offset,(unsigned long long)count,(long long)n);
    }
    c->gpr[3]=(uint64_t)(int64_t)error;
}
extern "C" void port_fs_register_extensions(void)
{
    ps3_hle_register_ctx(0x0D5B4A14u,"cellFsReadWithOffset",port_fs_read_with_offset);
}
