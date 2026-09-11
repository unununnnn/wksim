"""Compile the ACTUAL candidate WorkQueue::Add/SignalWorkerThread/Run bodies plus its tracing
helper against minimal POSIX semaphore/queue/platform shims; a bounded smoke test, not a flight test.

Scope is deliberately narrow: the three WorkQueue method bodies and the anonymous-namespace
tracing helpers (wksim_wait_trace/wksim_wall_ns) are extracted VERBATIM (byte-exact, with
source sha256 + 1-based line-range provenance) from the candidate WorkQueue.cpp and compiled
into a single translation unit. Everything else — the WorkQueue/WorkItem class scaffolding, the
FIFO queue, the semaphore/log/lockstep/time layer — is a labeled SHIM and claims no production
behavior. No flight, WorkQueueManager, module or manager integration is exercised.

Two sequential batches run on the same WorkQueue. Both WorkItems delete themselves inside Run()
and sleep >2ms so the diagnostic fires; the second also stops the queue. A condition variable in
the labeled lockstep shim establishes the first unregister as the batch boundary before the
second Add. Verified: trace off emits nothing; trace on logs both COPIED item names (a use-after-
free would trip AddressSanitizer), each batch unregisters, the second batch gets a newer ready
timestamp, WKSIM_PX4_QUEUE follows unregister and work_unlock, and the run completes without
deadlock. Compiled with AddressSanitizer when available.

Runs in WSL where g++ and the candidate tree live. Usage:
  python3 -B tools/check_px4_workqueue_trace.py <candidate_src> --output <new_dir>
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

SOURCE_REL = 'platforms/common/px4_work_queue/WorkQueue.cpp'
METHOD_SIGS = {'Add': 'void WorkQueue::Add(',
               'SignalWorkerThread': 'void WorkQueue::SignalWorkerThread(',
               'Run': 'void WorkQueue::Run('}

# --- Labeled shims + minimal class scaffolding (NOT production code). The production method
# --- bodies extracted from WorkQueue.cpp are inserted between these markers verbatim. ---
CPP_PREFIX = r'''
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
'''

CPP_DRIVER = r'''

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
'''


def extract_blocks(text):
    """Slice the verbatim helper block and the three method bodies; 1-based line provenance."""
    lines = text.splitlines()
    blocks = {}
    hstart = next(i for i, l in enumerate(lines) if l.strip() == 'namespace {')
    hend = next(i for i in range(hstart + 1, len(lines)) if lines[i].startswith('} // namespace'))
    blocks['helpers'] = dict(start=hstart + 1, end=hend + 1, text='\n'.join(lines[hstart:hend + 1]))
    for name, sig in METHOD_SIGS.items():
        mstart = next(i for i, l in enumerate(lines) if l.startswith(sig))
        mend = next(i for i in range(mstart + 1, len(lines)) if lines[i] == '}')
        blocks[name] = dict(start=mstart + 1, end=mend + 1, text='\n'.join(lines[mstart:mend + 1]))
    # Sanity: the slices must be the intended production logic, not drift.
    assert 'wksim_wait_trace' in blocks['helpers']['text'] and 'wksim_wall_ns' in blocks['helpers']['text']
    assert '_q.push' in blocks['Add']['text'] and 'SignalWorkerThread();' in blocks['Add']['text']
    assert 'px4_sem_getvalue' in blocks['SignalWorkerThread']['text']
    run = blocks['Run']['text']
    assert 'WKSIM_PX4_WORK' in run and 'WKSIM_PX4_QUEUE' in run and 'item_name' in run
    # The queue record must be emitted only AFTER the lockstep unregister and work_unlock.
    i_unreg = run.index('px4_lockstep_unregister_component')
    i_reset = run.index('_lockstep_component = -1', i_unreg)
    i_unlock = run.index('work_unlock();', i_unreg)
    i_queue = run.index('WKSIM_PX4_QUEUE')
    assert i_unreg < i_reset < i_unlock < i_queue, (
        'component reset and queue unlock must follow unregister and precede queue trace')
    # The item trace must use the copied name buffer, never the (possibly deleted) item, after Run().
    i_run_call = run.index('work->Run();')
    tail = run[i_run_call + len('work->Run();'):]  # text strictly after the Run() call itself
    assert 'work->' not in tail, 'no item access is allowed after Run() returns'
    assert 'item_name' in tail, 'item trace must use the copied name'
    return blocks


def parse_traces(stderr):
    work, queue = [], []
    for line in stderr.splitlines():
        if line.startswith('WKSIM_PX4_WORK '):
            work.append(json.loads(line[len('WKSIM_PX4_WORK '):]))
        elif line.startswith('WKSIM_PX4_QUEUE '):
            queue.append(json.loads(line[len('WKSIM_PX4_QUEUE '):]))
    return dict(work=work, queue=queue)


def build_cpp(blocks):
    return (CPP_PREFIX
            + '\n// ---- BEGIN verbatim production extract (see result.json for provenance) ----\n'
            + blocks['helpers']['text'] + '\n'
            + '\nnamespace px4 {\n'
            + blocks['Add']['text'] + '\n\n'
            + blocks['SignalWorkerThread']['text'] + '\n\n'
            + blocks['Run']['text'] + '\n'
            + '} // namespace px4\n'
            + '// ---- END verbatim production extract ----\n'
            + CPP_DRIVER)


def check(source, out):
    source, out = Path(source), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    src = source / SOURCE_REL
    raw = src.read_bytes()
    blocks = extract_blocks(raw.decode('utf-8'))
    (out / 'test.cpp').write_text(build_cpp(blocks))
    command = ['g++', '-std=c++17', '-pthread', '-g', '-DENABLE_LOCKSTEP_SCHEDULER',
               '-fsanitize=address', '-o', str(out / 'test'), str(out / 'test.cpp')]
    built = subprocess.run(command, capture_output=True, text=True)
    (out / 'build.log').write_text(built.stdout + built.stderr)
    built.check_returncode()
    modes = []
    for label, flag in (('off', None), ('invalid', '0'), ('on', '1')):
        env = dict(os.environ)
        env.pop('WKSIM_PX4_COMPONENT_TIMING', None)
        if flag is not None:
            env['WKSIM_PX4_COMPONENT_TIMING'] = flag
        run = subprocess.run([str(out / 'test')], env=env, capture_output=True, text=True, timeout=15)
        (out / (label + '.stdout')).write_text(run.stdout)
        (out / (label + '.stderr')).write_text(run.stderr)
        assert run.returncode == 0, label + ' exited ' + str(run.returncode)  # no deadlock/ASan abort
        assert 'AddressSanitizer' not in run.stderr, label + ' tripped AddressSanitizer (use-after-free/leak)'
        done = json.loads(run.stdout)
        traces = parse_traces(run.stderr)
        if label == 'on':
            assert done['complete'] and done['unregister_calls'] == 2
            assert [row['item'] for row in traces['work']] == ['batch_one', 'batch_two']
            assert all(row['duration_ns'] > 2_000_000 and row['queue'] == 'wq_smoke'
                       for row in traces['work'])
            assert len(traces['queue']) == 2
            assert all(row['items'] == 1 and row['duration_ns'] > 2_000_000
                       for row in traces['queue'])
            assert [row['component'] for row in traces['queue']] == [1, 2]
            assert traces['queue'][1]['ready_mono_ns'] > traces['queue'][0]['ready_mono_ns']
        else:  # trace disabled: no production trace output at all
            assert done['complete'] and done['unregister_calls'] == 2
            assert not traces['work'] and not traces['queue']
        modes.append(dict(mode=label, unregister_calls=done['unregister_calls'],
                          work_traces=len(traces['work']), queue_traces=len(traces['queue']),
                          queue_ready_mono_ns=[row['ready_mono_ns'] for row in traces['queue']]))
    def sha(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    result = dict(status='pass', scope=__doc__, modes=modes, compiler_command=command,
                  sanitizer='address',
                  source=str(src), source_sha256=hashlib.sha256(raw).hexdigest(),
                  extracted_provenance={k: dict(lines=[v['start'], v['end']],
                                                sha256=hashlib.sha256(v['text'].encode()).hexdigest())
                                        for k, v in blocks.items()},
                  checker_sha256=sha(Path(__file__)))
    (out / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ('status', 'modes')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    check(a.source.resolve(), a.output.resolve())
