
// SHIM layer only: POSIX semaphore, log, lockstep and time stand-ins plus minimal
// WorkQueue/WorkItem scaffolding. None of this claims production behavior; the ONLY
// production code in this translation unit is the verbatim-extracted block further below.
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <queue>
#include <thread>
#include <semaphore.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

typedef sem_t px4_sem_t;
#define px4_sem_init sem_init
#define px4_sem_destroy sem_destroy
#define px4_sem_wait sem_wait
#define px4_sem_post sem_post
#define px4_sem_getvalue sem_getvalue
#define PX4_DEBUG(...) ((void)0)
#define PX4_INFO_RAW(...) ((void)0)

// Lockstep scheduler C API shim (signatures match src/drivers/drv_hrt.h).
static std::mutex g_unregister_mutex;
static std::condition_variable g_unregister_cv;
static unsigned g_lockstep_unregister_calls = 0;
int px4_lockstep_register_component(void) { static int next = 1; return next++; }
void px4_lockstep_unregister_component(int component) {
    (void)component;
    {
        std::lock_guard<std::mutex> guard(g_unregister_mutex);
        ++g_lockstep_unregister_calls;
    }
    g_unregister_cv.notify_all();
}
bool wait_for_unregister_calls(unsigned expected) {
    std::unique_lock<std::mutex> lock(g_unregister_mutex);
    return g_unregister_cv.wait_for(lock, std::chrono::seconds(5), [&] {
        return g_lockstep_unregister_calls >= expected;
    });
}
unsigned unregister_calls() {
    std::lock_guard<std::mutex> guard(g_unregister_mutex);
    return g_lockstep_unregister_calls;
}

namespace px4 {

struct wq_config_t { const char *name; };  // SHIM: production wq_config_t also carries stacksize/priority.

class WorkItem {  // SHIM base: only the surface the extracted WorkQueue methods touch.
public:
    explicit WorkItem(const char *name) : _name(name) {}
    virtual ~WorkItem() = default;
    const char *ItemName() const { return _name; }
    void RunPreamble() {}      // SHIM: production timestamps first run; not under test here.
    virtual void Run() = 0;
private:
    const char *_name;
};

template <typename T>
class SimpleQueue {            // SHIM FIFO matching the IntrusiveQueue push/pop/empty surface used.
public:
    bool empty() const { return _q.empty(); }
    void push(T item) { _q.push(item); }
    T pop() { T item = _q.front(); _q.pop(); return item; }
private:
    std::queue<T> _q;
};

class WorkQueue {              // SHIM declaration; Add/SignalWorkerThread/Run bodies are verbatim below.
public:
    explicit WorkQueue(const wq_config_t &config) : _config(config) {
        px4_sem_init(&_qlock, 0, 1);
        px4_sem_init(&_process_lock, 0, 0);
        px4_sem_init(&_exit_lock, 0, 1);
    }
    ~WorkQueue() {
        px4_sem_destroy(&_qlock);
        px4_sem_destroy(&_process_lock);
        px4_sem_destroy(&_exit_lock);
    }
    void request_stop() { _should_exit.store(true); }
    void Add(WorkItem *item);
    void SignalWorkerThread();
    void Run();
private:
    bool should_exit() const { return _should_exit.load(); }
    void work_lock() { do {} while (px4_sem_wait(&_qlock) != 0); }
    void work_unlock() { px4_sem_post(&_qlock); }
    SimpleQueue<WorkItem *> _q;
    px4_sem_t _qlock;
    px4_sem_t _process_lock;
    px4_sem_t _exit_lock;
    const wq_config_t &_config;
    std::atomic<bool> _should_exit{false};
    int _lockstep_component{-1};
    long long _trace_batch_ready_ns{0};
};

} // namespace px4

// ---- BEGIN verbatim production extract (see result.json for provenance) ----
namespace {
bool wksim_wait_trace()
{
	static const bool enabled = []() {
		const char *value = std::getenv("WKSIM_PX4_COMPONENT_TIMING");
		return value != nullptr && std::strcmp(value, "1") == 0;
	}();
	return enabled;
}

long long wksim_wall_ns()
{
	struct timespec ts {};
	if (::syscall(SYS_clock_gettime, CLOCK_MONOTONIC, &ts) != 0) { return 0; }
	return static_cast<long long>(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}
} // namespace

namespace px4 {
void WorkQueue::Add(WorkItem *item)
{
	work_lock();

#if defined(ENABLE_LOCKSTEP_SCHEDULER)

	if (_lockstep_component == -1) {
		_lockstep_component = px4_lockstep_register_component();
		if (wksim_wait_trace()) { _trace_batch_ready_ns = wksim_wall_ns(); }
	}

#endif // ENABLE_LOCKSTEP_SCHEDULER

	_q.push(item);
	work_unlock();

	SignalWorkerThread();
}

void WorkQueue::SignalWorkerThread()
{
	int sem_val;

	if (px4_sem_getvalue(&_process_lock, &sem_val) == 0 && sem_val <= 0) {
		px4_sem_post(&_process_lock);
	}
}

void WorkQueue::Run()
{
	const bool trace = wksim_wait_trace();
	while (!should_exit()) {
		// loop as the wait may be interrupted by a signal
		do {} while (px4_sem_wait(&_process_lock) != 0);
		const long long woke_ns = trace ? wksim_wall_ns() : 0;

		work_lock();
		const long long worker_ns = trace ? wksim_wall_ns() : 0;
#if defined(ENABLE_LOCKSTEP_SCHEDULER)
		const int component = _lockstep_component;
		const long long ready_ns = trace ? _trace_batch_ready_ns : 0;
#else
		const int component = 0;
		const long long ready_ns = worker_ns;
#endif
		unsigned items = 0;

		// process queued work
		while (!_q.empty()) {
			WorkItem *work = _q.pop();
			char item_name[96] {};
			if (trace) {
				const char *name = work->ItemName();
				std::snprintf(item_name, sizeof(item_name), "%s", name ? name : "unknown");
				++items;
			}

			work_unlock(); // unlock work queue to run (item may requeue itself)
			const long long item_start_ns = trace ? wksim_wall_ns() : 0;
			work->RunPreamble();
			work->Run();
			if (trace) {
				const long long item_end_ns = wksim_wall_ns();
				if (item_end_ns - item_start_ns > 2000000LL) {
					// No queue lock is held; work may already have deleted itself.
					std::fprintf(stderr, "WKSIM_PX4_WORK {\"start_mono_ns\":%lld,\"end_mono_ns\":%lld,\"duration_ns\":%lld,\"queue\":\"%s\",\"item\":\"%s\",\"component\":%d,\"tid\":%ld}\n",
						item_start_ns, item_end_ns, item_end_ns - item_start_ns, _config.name,
						item_name, component, static_cast<long>(::syscall(SYS_gettid)));
				}
			}
			// Note: after Run() we cannot access work anymore, as it might have been deleted
			work_lock(); // re-lock
		}

#if defined(ENABLE_LOCKSTEP_SCHEDULER)

		if (_q.empty()) {
			px4_lockstep_unregister_component(_lockstep_component);
			_lockstep_component = -1;
		}

#endif // ENABLE_LOCKSTEP_SCHEDULER

		work_unlock();
		if (trace && items > 0 && ready_ns > 0) {
			const long long end_ns = wksim_wall_ns();
			if (end_ns - ready_ns > 2000000LL) {
				// The queue lock and its lockstep registration have both been released.
				std::fprintf(stderr, "WKSIM_PX4_QUEUE {\"ready_mono_ns\":%lld,\"woke_mono_ns\":%lld,\"worker_mono_ns\":%lld,\"end_mono_ns\":%lld,\"duration_ns\":%lld,\"queue\":\"%s\",\"component\":%d,\"tid\":%ld,\"items\":%u}\n",
					ready_ns, woke_ns, worker_ns, end_ns, end_ns - ready_ns, _config.name, component,
					static_cast<long>(::syscall(SYS_gettid)), items);
			}
		}
	}

	PX4_DEBUG("%s: exiting", _config.name);
}
} // namespace px4
// ---- END verbatim production extract ----


// Test WorkItem: sleeps past the 2ms diagnostic threshold and deletes itself inside Run().
// The second batch also stops the queue. After delete, the extracted trace may use only the copy.
class SelfDeletingItem : public px4::WorkItem {
public:
    SelfDeletingItem(const char *name, px4::WorkQueue *wq, bool stop)
        : px4::WorkItem(name), _wq(wq), _stop(stop) {}
    void Run() override {
        std::this_thread::sleep_for(std::chrono::milliseconds(3));  // > 2_000_000 ns threshold
        if (_stop) { _wq->request_stop(); }
        delete this;  // self-delete: nothing below may dereference this item (ASan-verified)
    }
private:
    px4::WorkQueue *_wq;
    bool _stop;
};

int main() {
    px4::wq_config_t config{"wq_smoke"};
    px4::WorkQueue wq(config);
    std::thread worker([&] { wq.Run(); });
    wq.Add(new SelfDeletingItem("batch_one", &wq, false));
    // Explicit batch boundary: unregister happens while Run holds work_lock, and Add below
    // cannot acquire it until Run has also reset _lockstep_component to -1 and unlocked.
    if (!wait_for_unregister_calls(1)) {
        wq.request_stop();
        wq.SignalWorkerThread();
        worker.join();
        return 2;
    }
    wq.Add(new SelfDeletingItem("batch_two", &wq, true));
    worker.join();  // must return: no deadlock
    std::printf("{\"complete\":true,\"unregister_calls\":%u}\n", unregister_calls());
    return 0;
}
