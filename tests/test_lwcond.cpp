#include "ppu_recomp.h"
#undef vm_read32
#include "ps3emu/nid.h"
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <sys/mman.h>
#include <thread>
#include <unordered_map>
extern "C" {uint8_t* vm_base;int vm_inline_ok=1;uint32_t ppu_hle_inject_base=0x20000000;uint32_t ppu_vm_size=0;}
static std::mutex mem_lock;
static std::unordered_map<uint32_t,uint32_t> mem;
extern "C" uint32_t vm_read32(uint64_t a) {std::lock_guard<std::mutex> g(mem_lock);return mem[(uint32_t)a];}
extern "C" void vm_write32(uint64_t a,uint32_t v) {std::lock_guard<std::mutex> g(mem_lock);mem[(uint32_t)a]=v;uint32_t be=__builtin_bswap32(v);memcpy(vm_base+(uint32_t)a,&be,4);}
/* A guest lwmutex as the SDK keeps it: owner at +0, recursion at +0xC, and a
 * binary semaphore behind it that any thread may release. */
static std::mutex sem_lock; static std::condition_variable sem_cv; static bool sem_free=true;
static void lwm_lock(ppu_context* c) {
 uint32_t lwm=(uint32_t)c->gpr[3];
 if(vm_read32(lwm)==c->thread_id && vm_read32(lwm+0xC)){vm_write32(lwm+0xC,vm_read32(lwm+0xC)+1);c->gpr[3]=0;return;}
 {std::unique_lock<std::mutex> l(sem_lock);sem_cv.wait(l,[]{return sem_free;});sem_free=false;}
 vm_write32(lwm,(uint32_t)c->thread_id);vm_write32(lwm+0xC,1);c->gpr[3]=0;
}
static void lwm_unlock(ppu_context* c) {
 uint32_t lwm=(uint32_t)c->gpr[3],rc=vm_read32(lwm+0xC);
 if(rc>1){vm_write32(lwm+0xC,rc-1);c->gpr[3]=0;return;}
 vm_write32(lwm,0);vm_write32(lwm+0xC,0);
 {std::lock_guard<std::mutex> l(sem_lock);sem_free=true;}sem_cv.notify_all();c->gpr[3]=0;
}
extern "C" void ps3_hle_call(uint32_t nid,ppu_context* c) {
 if(nid==ps3_compute_nid("sys_lwmutex_lock"))lwm_lock(c);
 else if(nid==ps3_compute_nid("sys_lwmutex_unlock"))lwm_unlock(c);
 else assert(!"unexpected HLE call");
}
static std::unordered_map<uint32_t,void(*)(ppu_context*)> hle;
extern "C" void ps3_hle_register_ctx(uint32_t nid,const char*,void(*fn)(ppu_context*)) {hle[nid]=fn;}
extern "C" void port_register_hle_early(void);
static const uint32_t LWM=0x10000100,LWC=0x10000200;
static int64_t call(const char* name,uint32_t tid,uint64_t r3,uint64_t r4=0) {
 ppu_context c{};c.thread_id=tid;c.gpr[3]=r3;c.gpr[4]=r4;hle.at(ps3_compute_nid(name))(&c);return (int32_t)c.gpr[3];
}
static void lock(uint32_t tid) {ppu_context c{};c.thread_id=tid;c.gpr[3]=LWM;lwm_lock(&c);}
static void unlock(uint32_t tid) {ppu_context c{};c.thread_id=tid;c.gpr[3]=LWM;lwm_unlock(&c);}
using clk=std::chrono::steady_clock;
static long ms_since(clk::time_point t) {return (long)std::chrono::duration_cast<std::chrono::milliseconds>(clk::now()-t).count();}
int main() {
 vm_base=(uint8_t*)mmap(nullptr,0x100000000ull,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_NORESERVE,-1,0);assert(vm_base!=MAP_FAILED);
 setenv("PORT_LWCOND_SDK","1",1);port_register_hle_early();assert(hle.empty());
 unsetenv("PORT_LWCOND_SDK");port_register_hle_early();assert(hle.size()==4);
 vm_write32(LWC,LWM);
 /* An unsignalled wait blocks for its whole timeout, releases the lwmutex
  * meanwhile, and hands it back with the caller's recursion count. */
 lock(1);lock(1);
 auto t0=clk::now();
 std::thread other([]{lock(2);unlock(2);});
 assert(call("sys_lwcond_wait",1,LWC,50000)==(int32_t)0x8001000B);
 other.join();
 assert(ms_since(t0)>=45 && vm_read32(LWM)==1 && vm_read32(LWM+0xC)==2);
 unlock(1);unlock(1);
 /* A signal with no waiter is not remembered: the frame event depends on it. */
 call("sys_lwcond_signal",3,LWC);
 lock(1);assert(call("sys_lwcond_wait",1,LWC,20000)==(int32_t)0x8001000B);unlock(1);
 /* signal_all wakes a waiter that would otherwise sleep for 10 s. */
 int64_t r=-1;t0=clk::now();
 std::thread w([&]{lock(1);r=call("sys_lwcond_wait",1,LWC,10000000);assert(vm_read32(LWM)==1);unlock(1);});
 std::this_thread::sleep_for(std::chrono::milliseconds(30));
 lock(2);call("sys_lwcond_signal_all",2,LWC);unlock(2);
 w.join();assert(r==0 && ms_since(t0)<2000);
 /* signal wakes one waiter per call. */
 int64_t ra=-1,rb=-1;
 std::thread a([&]{lock(4);ra=call("sys_lwcond_wait",4,LWC,400000);unlock(4);});
 std::thread b([&]{lock(5);rb=call("sys_lwcond_wait",5,LWC,400000);unlock(5);});
 std::this_thread::sleep_for(std::chrono::milliseconds(50));
 lock(2);call("sys_lwcond_signal",2,LWC);unlock(2);
 a.join();b.join();
 assert((ra==0)+(rb==0)==1 && (ra==(int32_t)0x8001000B)+(rb==(int32_t)0x8001000B)==1);
 puts("PASS: opt-out, timeout releases/restores lwmutex, unremembered signal, signal_all wake, signal wakes one");
}
