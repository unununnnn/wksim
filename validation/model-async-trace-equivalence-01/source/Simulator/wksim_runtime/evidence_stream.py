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


class _Queue(queue.Queue):
    def __init__(self, capacity):
        self.highwater=0
        super().__init__(capacity)
    def _put(self, item):
        super()._put(item)
        self.highwater=max(self.highwater,len(self.queue))


class AsyncEvidenceStream:
    def __init__(self,path,block_size=65536,queue_blocks=8,close_timeout=5,
                 *,_writer=None,_opener=None,_closer=None):
        for value,name in ((block_size,'block_size'),(queue_blocks,'queue_blocks')):
            if type(value) is not int or value<1:raise ValueError(name+' must be a positive integer')
        if type(close_timeout) not in (int,float) or not math.isfinite(close_timeout) or close_timeout<0:
            raise ValueError('close_timeout must be finite and nonnegative')
        self._block_size=block_size;self._capacity=block_size*queue_blocks
        self._close_timeout=float(close_timeout)
        self._queue=_Queue(queue_blocks);self._pending=bytearray()
        self._done=threading.Event()
        self._submitted=self._written=0
        self._worker_error=self._main_error=self._close_outcome=None
        self._closed=False
        self._io_calls=self._max_io_ns=0
        self._writer=_writer or os.write;self._closer=_closer or os.close
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)
        fd=(_opener or os.open)(os.fspath(path),flags,0o600)
        try:
            self._thread=threading.Thread(target=self._run,args=(fd,),name='wksim-evidence-writer',daemon=True)
            self._thread.start()
        except BaseException:
            self._closer(fd)
            raise

    def _run(self,fd):
        try:
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
                    max_io_wall_ns=self._max_io_ns,
                    complete=self._close_outcome is True and not alive and error is None
                             and self._written==self._submitted)

    def __enter__(self):return self
    def __exit__(self,*exc):self.close();return False
