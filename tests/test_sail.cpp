#include "sail_bridge.cpp"
#include <cassert>
#include <sys/mman.h>
#include <tuple>
extern "C" { uint8_t* vm_base=nullptr; const char* ppu_vfs_root=nullptr; }
static uint32_t next_ea=0x100000;
static std::map<uint32_t,void(*)(ppu_context*)> hle;
static std::vector<std::array<uint64_t,4>> events;
static bool fail_alloc=false;
static uint64_t read64(uint32_t ea) {uint64_t v;memcpy(&v,vm_base+ea,8);return __builtin_bswap64(v);}
extern "C" void* sys_heap_malloc(uint32_t,uint32_t n) {
    auto ea=next_ea;next_ea+=(n+255)&~255u;return (void*)(uintptr_t)ea;
}
extern "C" int32_t sys_heap_free(uint32_t,void*) {return 0;}
extern "C" void ps3_hle_register_ctx(uint32_t nid,const char*,void(*f)(ppu_context*)) {hle[nid]=f;}
extern "C" uint64_t ppu_guest_call(uint32_t cb,uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t,uint64_t,uint64_t,uint64_t) {
    if(cb==0x1000)events.push_back({a,b,c,d});
    if(cb==0x2000) {
        if(fail_alloc)return uint64_t(int64_t(-1));
        for(unsigned i=0;i<c;i++)port_sail::w32(d+i*4,(uintptr_t)sys_heap_malloc(0,b));
    }
    return 0;
}
static uint32_t invoke(uint32_t nid,std::initializer_list<uint64_t> args) {
    ppu_context ctx{};unsigned r=3;for(auto a:args)ctx.gpr[r++]=a;
    assert(hle.count(nid));hle[nid](&ctx);return ctx.gpr[3];
}
int main(int argc,char** argv) {
    assert(argc==2);ppu_vfs_root=argv[1];
    vm_base=(uint8_t*)mmap(nullptr,0xE0000000ull,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_NORESERVE,-1,0);
    assert(vm_base!=MAP_FAILED);port_register_sail();
    using namespace port_sail;
    constexpr uint32_t p=0x10000,a=0x11000,funcs=0x12000,fmt=0x13000,uri=0x14000,out=0x15000,info=0x16000;
    assert(invoke(0x23654375,{0,0,0x1000})==InvalidArg);
    assert(invoke(0x23654375,{p,0,0x1000,0x9999})==0);
    assert(invoke(0x23654375,{p,0,0x1000})==InvalidState);
    w32(funcs+12,0x2000);
    assert(invoke(0x1C983864,{a,funcs,0x1234})==0);
    assert(invoke(0x18BCD21B,{p,0,a})==0);
    memset(vm_base+fmt,0xFF,32);vm_base[fmt]=0;
    assert(invoke(0x2E3CCB5E,{a,fmt})==0);
    assert(invoke(0xE535B0D3,{p,0,55})==InvalidState);
    assert(invoke(0xBDF21B0F,{p,0xFEDCBA9876543210ull})==0);
    assert(events.empty()); // boot cannot call guest inline
    assert(invoke(0xBDF21B0F,{p,0})==Using);
    port_sail_poll();assert(events.size()==3);
    assert(events.back()[1]==0x200000001ull && events.back()[3]==0xFEDCBA9876543210ull);
    strcpy((char*)vm_base+uri,"x-cell-fs:///dev_bdvd/../outside.pam");
    assert(invoke(0xD7938B8D,{p,0,0,uri,out})==InvalidArg);
    strcpy((char*)vm_base+uri,"x-cell-fs:///dev_bdvd/PS3_GAME/test.pam");
    assert(invoke(0xD7938B8D,{p,0,0,uri,out})==0);auto d=r32(out);assert(d!=0);
    assert(invoke(0x7C8DFF3B,{p,d})==0);
    assert(invoke(0x752F8585,{p})==1);
    fail_alloc=true;
    assert(invoke(0x34ECC1B9,{p,123})==0);port_sail_poll();assert(player(p)->state==2);
    assert(adapter(a)->buffers.empty() && !adapter(a)->table_ea);
    fail_alloc=false;
    assert(invoke(0x34ECC1B9,{p,123})==0);port_sail_poll();assert(player(p)->state==4);
    assert(r32(a+28+8)==64*4);assert(player(p)->video.height==48);
    assert(invoke(0xE535B0D3,{p,0,456})==0);port_sail_poll();assert(player(p)->state==6);
    uint64_t previous_pts=0;unsigned delivered=0;
    auto deadline=Clock::now()+std::chrono::seconds(5);
    while(Clock::now()<deadline && player(p)->state==6) {
        uint32_t r=invoke(0x018281A8,{a,info,0,info+32,2});
        if(r>=256 && r<0x10000) {
            assert(valid(r32(info),64*48*4));assert(r32(info+4)==player(p)->session);
            assert(read64(info+16)>=previous_pts);previous_pts=read64(info+16);delivered++;
            assert(vm_base[r32(info)]==255); // decoder produced an opaque ARGB pixel
            if(delivered==1) {
                assert(invoke(0xD1D55A90,{p,1})==0);
                assert(invoke(0xAAFA17B8,{p})==1);
                size_t before=events.size();
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
                assert(invoke(0x018281A8,{a,info,0,0,2})==36);
                assert(invoke(0xD1D55A90,{p,0})==0);
                assert(events.size()==before); // pause notifications are deferred too
            }
        }
        port_sail_poll();std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    assert(delivered==6);assert(player(p)->state==4 && !player(p)->decoder);
    bool eos=false;for(auto& e:events)eos|=e[1]==0x800000000ull;assert(eos);
    assert(invoke(0x018281A8,{a,info,0,0,2})==48);
    // Stop is a genuine cancellation, not a synthetic EOS notification.
    assert(invoke(0xE535B0D3,{p,0,0xABC})==0);port_sail_poll();
    auto event_count=events.size();
    assert(invoke(0xEBA8D4EC,{p,0xDEF})==0);port_sail_poll();
    assert(player(p)->state==4 && !player(p)->decoder);
    for(size_t i=event_count;i<events.size();i++)assert(events[i][1]!=0x800000000ull);
    assert(events.back()[1]==0x20000000Bull && events.back()[3]==0xDEF);
    assert(invoke(0x85BEFFCC,{p,999})==0);port_sail_poll();assert(player(p)->state==2);
    assert(invoke(0x9897FBD1,{p,d})==0);assert(invoke(0xFC839BD4,{p,d})==0);
    assert(invoke(0x18B4629D,{p})==0);assert(invoke(0x76488BB1,{a})==0);
    // Cancellation must unblock a full four-frame queue without a hung join.
    Decoder decoder;assert(decoder.start(std::string(argv[1])+"/PS3_GAME/test.pam","argb",64*48*4));
    std::this_thread::sleep_for(std::chrono::milliseconds(200));auto start=Clock::now();decoder.stop();
    assert(Clock::now()-start<std::chrono::seconds(2));
    Decoder broken;assert(broken.start(std::string(argv[1])+"/PS3_GAME/missing.pam","argb",64*48*4));
    int code=0;deadline=Clock::now()+std::chrono::seconds(3);
    while(!broken.done(code) && Clock::now()<deadline)std::this_thread::sleep_for(std::chrono::milliseconds(10));
    assert(broken.done(code) && code!=0);
    munmap(vm_base,0xE0000000ull);puts("cellSail lifecycle, callbacks, frames, EOS, validation, cancellation: PASS");
}
