import ast,base64,json,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parent
assert not (root/'loss-receipt.json').exists()
tree=ast.parse((root/'run_checks.py').read_text())
pre=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='pre')
checks=[]
for distro in ['Ubuntu-22.04','RflySim-20.04']:
 r=subprocess.run(['wsl.exe','-d',distro,'-u','root','--','python3','-'],input=pre,capture_output=True,text=True,timeout=45)
 assert r.returncode==0,r.stderr
 c=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1]);assert not c['found'],c
 checks.append(c)
(root/'loss-prechecks.json').write_bytes((json.dumps(checks,indent=2)+'\n').encode())
payload={'prior':json.loads((root/'receipt.json').read_bytes()),'checks':checks,'test_source':base64.b64encode((root/'force_kernel_loss.c').read_bytes()).decode(),'consumer':base64.b64encode((root.parent/'ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py').read_bytes()).decode()}
linux="import base64,hashlib,json,os,pathlib,signal,struct,subprocess,time\nprior=payload['prior'];root=pathlib.Path(prior['directory'])\nboot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nassert all(c['boot_id']==boot and 0<=time.time()-c['checked_unix']<=60 and not c['found'] for c in payload['checks'])\nassert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in prior['source_sha256'].items())\noutdir=root/'forced-kernel-loss';outdir.mkdir(exist_ok=False)\nsrc=base64.b64decode(payload['test_source']);(outdir/'force_kernel_loss.c').write_bytes(src)\nconsumer=base64.b64decode(payload['consumer']);(outdir/'consumer.py').write_bytes(consumer)\nout={'boot_id':boot,'directory':str(outdir),'test_source_sha256':hashlib.sha256(src).hexdigest(),'consumer_sha256':hashlib.sha256(consumer).hexdigest(),'source_sha256':prior['source_sha256'],'test_only_reader_stall':True,'commands':[]}\ncommands=[['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread','-I'+str(root),'-o',str(outdir/'force_loss'),str(outdir/'force_kernel_loss.c')],[str(outdir/'force_loss'),str(outdir)],['python3',str(outdir/'consumer.py'),'--raw',str(outdir/'forced-loss.raw'),'--metadata',str(outdir/'forced-loss.meta.json'),'--output',str(outdir/'must-reject.json')]]\nfor i,argv in enumerate(commands):\n p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)\n row={'argv':argv,'pid':p.pid}\n try:stdout,stderr=p.communicate(timeout=15)\n except subprocess.TimeoutExpired:\n  os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate();row['timed_out']=True\n row.update(exit_code=p.returncode,stdout=stdout,stderr=stderr)\n try:os.killpg(p.pid,0);row['pgid_empty']=False\n except ProcessLookupError:row['pgid_empty']=True\n out['commands'].append(row)\n if not row['pgid_empty'] or (i<2 and p.returncode):break\nraw=outdir/'forced-loss.raw'\nif raw.exists():\n data=raw.read_bytes();pos=0;lost=[];records=0\n while pos<len(data):\n  if len(data)-pos<8:raise RuntimeError('short record header')\n  kind,misc,size=struct.unpack_from('<IHH',data,pos)\n  if size<8 or pos+size>len(data):raise RuntimeError('bad record bounds')\n  if kind==2:lost.append({'offset':pos,'size':size,'lost':struct.unpack_from('<Q',data,pos+16)[0] if size>=24 else None})\n  pos+=size;records+=1\n out['raw_summary']={'bytes':len(data),'records':records,'lost_records':lost,'sha256':hashlib.sha256(data).hexdigest()}\nout['boot_after']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()\nout['files']={p.name:base64.b64encode(p.read_bytes()).decode() for p in outdir.iterdir() if p.name.endswith(('.raw','.json'))}\n(outdir/'receipt.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))\n"
script='import base64,json\npayload=json.loads(base64.b64decode('+repr(base64.b64encode(json.dumps(payload).encode()).decode())+'))\n'+linux
r=subprocess.run(['wsl.exe','-d','Ubuntu-22.04','-u','root','--','python3','-'],input=script,capture_output=True,text=True,timeout=55)
assert r.returncode==0,(r.stdout,r.stderr)
out=json.loads([x for x in r.stdout.splitlines() if x.startswith('{')][-1])
(root/'loss-receipt.json').write_bytes((json.dumps(out,indent=2)+'\n').encode())
capture=root/'forced-kernel-loss';capture.mkdir(exist_ok=False)
for name,raw in out['files'].items():
 assert pathlib.PurePath(name).name==name
 (capture/name).write_bytes(base64.b64decode(raw))
print(json.dumps({'commands':out['commands'],'raw_summary':out.get('raw_summary')}))
