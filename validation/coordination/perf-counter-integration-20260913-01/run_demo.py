import ast,base64,json,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parent
assert not (root/'demo-receipt.json').exists()
tree=ast.parse((root/'run_checks.py').read_text())
pre=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='pre')
checks=[]
for distro in ['Ubuntu-22.04','RflySim-20.04']:
 r=subprocess.run(['wsl.exe','-d',distro,'-u','root','--','python3','-'],input=pre,capture_output=True,text=True,timeout=45)
 assert r.returncode==0,r.stderr
 c=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1]);assert not c['found'],c
 checks.append(c)
(root/'demo-prechecks.json').write_bytes((json.dumps(checks,indent=2)+'\n').encode())
consumer=(root.parent/'ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py').read_bytes()
payload={'prior':json.loads((root/'receipt.json').read_bytes()),'checks':checks,'consumer':base64.b64encode(consumer).decode()}
linux="import base64,hashlib,json,os,pathlib,signal,subprocess,time\nr=payload['prior'];root=pathlib.Path(r['directory'])\nboot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nassert all(c['boot_id']==boot and 0<=time.time()-c['checked_unix']<=60 and not c['found'] for c in payload['checks'])\nassert hashlib.sha256((root/'demo').read_bytes()).hexdigest()==r['binary_sha256']['demo']\nassert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in r['source_sha256'].items())\noutdir=root/'normal-demo';outdir.mkdir(exist_ok=False)\nconsumer=base64.b64decode(payload['consumer']);(outdir/'consumer.py').write_bytes(consumer)\nresult={'boot_id':boot,'directory':str(outdir),'source_sha256':r['source_sha256'],'demo_sha256':r['binary_sha256']['demo'],'consumer_sha256':hashlib.sha256(consumer).hexdigest(),'commands':[]}\ncommands=[[str(root/'demo'),str(outdir)],['python3',str(outdir/'consumer.py'),'--raw',str(outdir/'switch-stream.raw'),'--metadata',str(outdir/'switch-stream.meta.json'),'--output',str(outdir/'decoded.json'),'--require-kernel-counter']]\nfor argv in commands:\n p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)\n row={'argv':argv,'pid':p.pid}\n try:stdout,stderr=p.communicate(timeout=20)\n except subprocess.TimeoutExpired:\n  os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate();row['timeout']=True\n row.update(exit_code=p.returncode,stdout=stdout,stderr=stderr)\n try:os.killpg(p.pid,0);row['pgid_empty']=False\n except ProcessLookupError:row['pgid_empty']=True\n result['commands'].append(row)\n if p.returncode or not row['pgid_empty']:break\nresult['boot_after']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nresult['files']={p.name:base64.b64encode(p.read_bytes()).decode() for p in outdir.iterdir() if p.is_file() and p.name!='consumer.py'}\n(outdir/'receipt.json').write_text(json.dumps(result,indent=2))\nprint(json.dumps(result))\n"
script='import base64,json\npayload=json.loads(base64.b64decode('+repr(base64.b64encode(json.dumps(payload).encode()).decode())+'))\n'+linux
r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','-u','root','--','python3','-'],input=script,capture_output=True,text=True,timeout=55)
assert r.returncode==0,(r.stdout,r.stderr)
out=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1])
(root/'demo-receipt.json').write_bytes((json.dumps(out,indent=2)+'\n').encode())
capture=root/'normal-demo';capture.mkdir(exist_ok=False)
for name,raw in out['files'].items():
 assert pathlib.PurePath(name).name==name
 (capture/name).write_bytes(base64.b64decode(raw))
print(json.dumps({'directory':out['directory'],'commands':out['commands'],'files':list(out['files'])}))
