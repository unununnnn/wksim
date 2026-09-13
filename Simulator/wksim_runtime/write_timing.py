"""Opt-in timing of actual evidence writes; payloads and synchronous I/O stay unchanged."""
import json
import time


class WriteTiming:
    def __init__(self, sink, epoch, tick, *, wall=time.monotonic_ns, cpu=time.thread_time_ns):
        self.sink, self.epoch, self.tick = sink, epoch, tick
        self.wall, self.cpu = wall, cpu
        self.counts, self.characters, self.slow, self.maximum = {}, {}, {}, {}

    def write(self, stream, name, text):
        start, cpu_start = self.wall(), self.cpu()
        error = None
        try:
            return stream.write(text)
        except BaseException as exc:
            error = repr(exc)
            raise
        finally:
            finish, cpu_finish = self.wall(), self.cpu()
            elapsed = finish-start
            self.counts[name] = self.counts.get(name, 0)+1
            self.characters[name] = self.characters.get(name, 0)+len(text)
            self.maximum[name] = max(self.maximum.get(name, 0), elapsed)
            if elapsed > 1_000_000 or error is not None:
                self.slow[name] = self.slow.get(name, 0)+1
                raw_position = None
                raw = getattr(getattr(stream, 'buffer', None), 'raw', None)
                if raw is not None:
                    try: raw_position = raw.tell()  # Raw file offset; never flush the text/buffered layers.
                    except (OSError, ValueError): pass
                self.sink.write(json.dumps(dict(kind='evidence_write_timing', epoch=self.epoch,
                    tick=self.tick(), stream=name, call=self.counts[name], characters=len(text),
                    submitted_characters=self.characters[name], raw_file_offset=raw_position,
                    wall_start_ns=start, wall_end_ns=finish, wall_ns=elapsed,
                    thread_cpu_ns=cpu_finish-cpu_start, error=error), separators=(',', ':'))+'\n')

    def summary(self):
        return dict(calls=self.counts, submitted_characters=self.characters,
                    slow_writes=self.slow, max_wall_ns=self.maximum,
                    scope='Actual write call timing, not a disk/OS causal attribution; no dropped or modified payloads')
