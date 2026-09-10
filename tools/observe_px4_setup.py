"""Opt-in receiver/setup observer; original callbacks and decisions run once.

No replacement freshness, extra clock reads, publishers, or control commands.
Fields are decoded receipt observations, not a claim of original wire CDR.
"""
import atexit
import hashlib
import inspect
import json
from pathlib import Path
import sys


def install(path, node_cls=None, link_cls=None):
    if node_cls is None:
        from prometheus_control.node import ControlNode as node_cls
    if link_cls is None:
        from prometheus_control.native_px4 import PX4Link as link_cls
    stream=Path(path).open('x',encoding='utf-8',buffering=1)
    setup,event,receive,fresh=node_cls.on_setup,node_cls.event,link_cls.receive,link_cls.fresh
    contexts={};closed=False
    def write(row):stream.write(json.dumps(row,allow_nan=False,separators=(',',':'))+'\n')
    identities={}
    for name,method in (('node',setup),('link',receive)):
        file=Path(inspect.getfile(method))
        identities[name]=dict(path=str(file),sha256=hashlib.sha256(file.read_bytes()).hexdigest())
    write(dict(kind='observer_source',scope=__doc__,sources=identities))
    def context(node):
        return dict(run_id=getattr(getattr(node,'session',None),'run_id',None),
            control_epoch=getattr(getattr(node,'session',None),'epoch',None),
            scene_epoch=getattr(getattr(node,'scene',None),'epoch',None),
            request_id=getattr(node,'request_context',None))
    def observed_receive(link,key,message):
        value=receive(link,key,message)
        if key=='land':
            write(dict(kind='land_receipt',**context(link.node),accepted=link.latest.get(key) is message,
                received_monotonic_s=link.received.get(key),callback_monotonic_s=link.last_clock,
                timestamp_us=int(message.timestamp),landed=bool(message.landed)))
        return value
    def observed_fresh(link,*keys):
        value=fresh(link,*keys)
        row=contexts.get(id(link.node))
        if row is not None:
            now=link.last_clock
            row['freshness'].append(dict(keys=list(keys),result=value,evaluated_monotonic_s=now,
                stale_seconds=link.stale_seconds,clock_invalid=link.clock_invalid,
                ages_s={key:now-link.received[key] if key in link.received else None for key in keys}))
        return value
    def observed_event(node,name,*,error=False,**fields):
        row=contexts.get(id(node))
        if row is not None:row['events'].append(dict(event=name,error=error,reason=fields.get('reason')))
        return event(node,name,error=error,**fields)
    def observed_setup(node,message):
        row=dict(kind='setup_decision',**context(node),cmd=int(message.cmd),
            processor_home_missing=node.processor.home is None,
            state_armed=bool(node.state.armed),state_odom_valid=bool(node.state.odom_valid),freshness=[],events=[])
        previous=contexts.get(id(node));contexts[id(node)]=row
        try:return setup(node,message)
        finally:
            if previous is None:contexts.pop(id(node),None)
            else:contexts[id(node)]=previous
            write(row)  # No I/O inserted between the original setup checks.
    def close():
        nonlocal closed
        if not closed:
            node_cls.on_setup,node_cls.event=setup,event
            link_cls.receive,link_cls.fresh=receive,fresh
            stream.close();closed=True
    node_cls.on_setup,node_cls.event=observed_setup,observed_event
    link_cls.receive,link_cls.fresh=observed_receive,observed_fresh
    atexit.register(close)
    return close


if __name__=='__main__':
    output=Path(sys.argv[1]);expected=Path(sys.argv[2]).resolve()
    import prometheus_control
    if Path(prometheus_control.__file__).resolve().parent!=expected:
        raise RuntimeError('Observer resolved a different Control installation')
    sys.argv=[sys.argv[0],*sys.argv[3:]]
    install(output)
    from prometheus_control.node import main
    main()
