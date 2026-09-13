"""Replay text buffering against a memory sink; locate underlying writes without disk I/O."""
import argparse
import io
import json
from pathlib import Path
import platform
import sys


class RawSink(io.RawIOBase):
    def __init__(self):
        super().__init__();self.position=0;self.call=0;self.writes=[]
    def writable(self):return True
    def seekable(self):return True
    def tell(self):return self.position
    def write(self,data):
        self.writes.append(dict(call=self.call,bytes=len(data),before=self.position))
        self.position+=len(data)
        return len(data)


def replay(directory):
    directory=Path(directory)
    measurements=[json.loads(line) for line in (directory/'write-timing.jsonl').read_text().splitlines()]
    result=dict(python=sys.version,platform=platform.platform(),streams={},
        scope='Controlled CPython text/buffered write replay; matching offsets constrain whether a slow call flushed, not its OS cause')
    for name in sorted({r['stream'] for r in measurements}):
        selected={r['call']:r for r in measurements if r['stream']==name}
        raw=RawSink()
        line_buffered=name=='lifecycle'
        stream=io.TextIOWrapper(io.BufferedWriter(raw,buffer_size=io.DEFAULT_BUFFER_SIZE if line_buffered else 65536),
                               encoding='utf-8',newline=None,line_buffering=line_buffered)
        rows=[];characters=0
        filename='scene-lifecycle.jsonl' if line_buffered else name+'.jsonl'
        with (directory/filename).open(encoding='utf-8',newline='') as source:
            for ordinal,line in enumerate(source,1):
                raw.call=ordinal;before=raw.position;old_count=len(raw.writes)
                stream.write(line);characters+=len(line)
                if ordinal in selected:
                    measured=selected[ordinal]
                    rows.append(dict(call=ordinal,tick=measured['tick'],wall_ns=measured['wall_ns'],
                        raw_before=before,raw_after=raw.position,observed_raw_after=measured['raw_file_offset'],
                        offset_matches=raw.position==measured['raw_file_offset'],
                        characters_match=characters==measured['submitted_characters'] and len(line)==measured['characters'],
                        underlying_writes=raw.writes[old_count:]))
        raw.call=ordinal+1;stream.close()
        result['streams'][name]=dict(calls=ordinal,characters=characters,slow_calls=rows)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=replay(args.directory)
    with args.output.open('x') as output:json.dump(result,output,indent=2)
    print(json.dumps(result['streams'],indent=2))
