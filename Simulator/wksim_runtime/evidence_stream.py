"""Bounded single-producer UTF-8 evidence stream; explicit experiment only.

write() never waits for disk/queue capacity. The daemon writer owns its raw
file descriptor; close() has one deadline. Failure never becomes completion.
"""
import math
import os
import queue
import threading
import time


class EvidenceStreamError(RuntimeError):
    pass


def _ordinary_scheduler():
    """Demote this writer thread before it can touch the evidence queue or fd."""
    names=('SCHED_OTHER','sched_param','sched_setscheduler','sched_getscheduler','sched_getparam')
    if not all(hasattr(os,name) for name in names):
        return dict(available=False)
    os.sched_setscheduler(0,os.SCHED_OTHER,os.sched_param(0))
    policy=os.sched_getscheduler(0)
    priority=os.sched_getparam(0).sched_priority
    if policy!=os.SCHED_OTHER or priority!=0:
        raise EvidenceStreamError('evidence writer did not enter ordinary scheduling')
    return dict(available=True,policy='SCHED_OTHER',priority=0,
                actual_policy=policy,actual_priority=priority)


class _Queue(queue.Queue):
    def __init__(self, capacity):
        self.highwater=0
        super().__init__(capacity)
    def _put(self, item):
        super()._put(item)
        self.highwater=max(self.highwater,len(self.queue))


class AsyncEvidenceStream:
    def __init__(self,path,block_size=65536,queue_blocks=8,close_timeout=5,
                 *,_writer=None,_opener=None,_closer=None,_scheduler=None):
        for value,name in ((block_size,'block_size'),(queue_blocks,'queue_blocks')):
            if type(value) is not int or value<1:raise ValueError(name+' must be a positive integer')
        if type(close_timeout) not in (int,float) or not math.isfinite(close_timeout) or close_timeout<0:
            raise ValueError('close_timeout must be finite and nonnegative')
        self._block_size=block_size;self._capacity=block_size*queue_blocks
        self._close_timeout=float(close_timeout)
        self._queue=_Queue(queue_blocks);self._pending=bytearray()
        self._done=threading.Event();self._scheduler_ready=threading.Event()
        self._submitted=self._written=0
        self._worker_error=self._main_error=self._close_outcome=None
        self._writer_scheduler=None
        self._closed=False
        self._io_calls=self._max_io_ns=0
        self._writer=_writer or os.write;self._closer=_closer or os.close
        self._scheduler=_scheduler or _ordinary_scheduler
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)
        fd=(_opener or os.open)(os.fspath(path),flags,0o600)
        try:
            self._thread=threading.Thread(target=self._run,args=(fd,),name='wksim-evidence-writer',daemon=True)
            self._thread.start()
        except BaseException:
            self._closer(fd)
            raise
        # Construction happens before the model RPC loop.  Do not accept the
        # first tick until the writer has either proved ordinary scheduling or
        # failed; otherwise a scheduler error could surface one commit late.
        if not self._scheduler_ready.wait(timeout=self._close_timeout):
            self._main_error=EvidenceStreamError(
                'evidence writer scheduler setup timed out')
            self._done.set()
            self._thread.join(timeout=self._close_timeout)
            raise self._main_error
        try:self.check()
        except BaseException:
            self._thread.join(timeout=self._close_timeout)
            raise

    def _run(self,fd):
        try:
            # pthread creation inherits the creator's policy.  Parent-side
            # SCHED_RESET_ON_FORK does not cover this thread, so demotion must
            # be the first writer-thread operation and must fail closed.
            self._writer_scheduler=self._scheduler()
            self._scheduler_ready.set()
            while True:
                try:block=self._queue.get(timeout=.02)
                except queue.Empty:
                    if self._done.is_set():break
                    continue
                if block is None:break
                remaining=memoryview(block)
                while remaining:
                    started=time.monotonic_ns()
                    try:count=self._writer(fd,remaining)
                    finally:
                        self._max_io_ns=max(self._max_io_ns,time.monotonic_ns()-started)
                        self._io_calls+=1
                    if type(count) is not int or not 0<count<=len(remaining):
                        raise EvidenceStreamError('writer returned an invalid byte count')
                    self._written+=count
                    remaining=remaining[count:]
        except BaseException as error:
            self._worker_error=error
            self._scheduler_ready.set()
        finally:
            try:self._closer(fd)
            except BaseException as error:
                if self._worker_error is None:self._worker_error=error

    def check(self):
        error=self._main_error or self._worker_error
        if error is None and self._close_outcome is not None and self._close_outcome is not True:
            error=self._close_outcome
        if error is not None:raise error

    def write(self,text):
        if self._closed:raise ValueError('evidence stream is closed')
        self.check()
        if not isinstance(text,str):raise TypeError('evidence records must be str')
        if len(text)>self._capacity:
            self._main_error=EvidenceStreamError('single write exceeds stream capacity')
            raise self._main_error
        data=text.encode('utf-8')
        if len(data)>self._capacity:
            self._main_error=EvidenceStreamError('single write exceeds stream capacity')
            raise self._main_error
        self._pending.extend(data);self._submitted+=len(data)
        while len(self._pending)>=self._block_size:
            try:self._queue.put_nowait(bytes(self._pending[:self._block_size]))
            except queue.Full:
                self._main_error=EvidenceStreamError('evidence queue is full; refusing to drop or block')
                raise self._main_error
            del self._pending[:self._block_size]
        return len(text)

    def close(self):
        if self._close_outcome is not None:
            if self._close_outcome is not True:raise self._close_outcome
            return
        self._closed=True
        deadline=time.monotonic()+self._close_timeout
        error=None
        try:
            if self._pending and self._main_error is None:
                block=bytes(self._pending)
                while True:
                    self.check()
                    try:
                        self._queue.put(block,timeout=max(0,min(.02,deadline-time.monotonic())))
                        self._pending.clear();break
                    except queue.Full:
                        if time.monotonic()>=deadline:
                            raise EvidenceStreamError('evidence close timed out before queuing accepted tail')
        except BaseException as exc:error=exc
        finally:
            # After this signal no producer can submit more data. Even a
            # timed-out writer can retire when its blocked OS write returns.
            self._done.set()
            try:self._queue.put_nowait(None)
            except queue.Full:pass
        self._thread.join(timeout=max(0,deadline-time.monotonic()))
        error=self._main_error or self._worker_error or error
        if error is None and self._thread.is_alive():
            error=EvidenceStreamError('evidence close timed out; writer has not retired')
        if error is None and self._written!=self._submitted:
            error=EvidenceStreamError('evidence close did not write all submitted bytes')
        self._close_outcome=error if error is not None else True
        if error is not None:raise error

    def summary(self):
        error=self._main_error or self._worker_error
        if error is None and self._close_outcome is not None and self._close_outcome is not True:
            error=self._close_outcome
        alive=self._thread.is_alive()
        return dict(submitted_bytes=self._submitted,written_bytes=self._written,
                    queue_highwater=self._queue.highwater,alive=alive,closed=self._closed,
                    error=None if error is None else repr(error),io_calls=self._io_calls,
                    max_io_wall_ns=self._max_io_ns,writer_scheduler=self._writer_scheduler,
                    complete=self._close_outcome is True and not alive and error is None
                             and self._written==self._submitted)

    def __enter__(self):return self
    def __exit__(self,*exc):self.close();return False
