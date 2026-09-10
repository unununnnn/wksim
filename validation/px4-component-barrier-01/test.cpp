
#include <lockstep_scheduler/lockstep_components.h>
#include <atomic>
#include <thread>
#include <chrono>
#include <cstdio>
#include <cstdarg>
#include <sys/syscall.h>
#include <time.h>
static std::atomic<int> clocks{0};
extern "C" long __real_syscall(long,...);
extern "C" long __wrap_syscall(long n,...)
{
    if(n==SYS_clock_gettime) {
        va_list a; va_start(a,n); int id=va_arg(a,int); auto p=va_arg(a,struct timespec*); va_end(a);
        ++clocks; return __real_syscall(n,id,p);
    }
    if(n==SYS_gettid) return __real_syscall(n);
    return -1;
}
int main()
{
    LockstepComponents c;
    c.wait_for_components(); // Empty registry must never wait, including when tracing is enabled.
    int a=c.register_component(),b=c.register_component();
    if(a<=0 || b<=0 || a==b) return 2;
    std::atomic<bool> entered{false},done{false};
    std::thread t([&]{entered=true;c.wait_for_components();done=true;});
    while(!entered) std::this_thread::yield();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    if(done) return 3;
    c.lockstep_progress(a);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    if(done) return 4;
    c.lockstep_progress(b);
    t.join();
    c.unregister_component(a);c.unregister_component(b);
    c.wait_for_components();
    std::printf("{\"complete\":true,\"clock_reads\":%d,\"last_component\":%d}\n",int(clocks),b);
}
