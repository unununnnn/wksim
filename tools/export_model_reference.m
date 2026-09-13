function export_model_reference
% One fresh-process, frozen-input normal simulation. Output doubles never use JSON.
out=fileparts(pwd); model='Exp1_MinModelTemp';
c=jsondecode(fileread(fullfile(out,'contract.json')));
m=jsondecode(fileread(fullfile(out,'manifest.json')));
r=struct('status','invalid_run_not_pass','case',m.case,'epoch',m.epoch, ...
    'contract_sha256',m.contract_sha256,'version',version,'release',version('-release'));
cleanup=onCleanup(@() bdclose('all'));
try
    assert(strcmp(version,'9.13.0.2049777 (R2022b)'));
    evalin('base','restoredefaultpath'); addpath(pwd);
    Simulink.fileGenControl('set','CacheFolder',fullfile(out,'cache'), ...
        'CodeGenFolder',fullfile(out,'codegen'),'createDir',true);
    load_system(fullfile(pwd,[model '.slx']));
    evalin('base',sprintf('run(''%s'')',strrep(fullfile(pwd,[model '_init.m']),'''','''''')));
    a=readmatrix(fullfile(out,'input.csv'),'NumHeaderLines',1);
    assert(isequal(size(a),[501 33]) && all(isfinite(a(:))));
    assert(isequal(a(:,1),(0:500)') && all(abs(a(:,2)-(0:500)'*.001)<=1e-12));
    inp=Simulink.SimulationData.Dataset;
    inp=inp.addElement(timeseries(a(:,3:18),a(:,2)),'inPWMs');
    inp=inp.addElement(timeseries(a(:,19:33),a(:,2)),'TerrainIn15d');
    assignin('base','conformance_input',inp);
    set_param(model,'SimulationMode','normal','Solver','ode4','FixedStep','0.001', ...
        'StartTime','0','StopTime','0.5','LoadExternalInput','on', ...
        'ExternalInput','conformance_input','SaveTime','on','TimeSaveName','tout', ...
        'SaveOutput','on','OutputSaveName','yout','SaveFormat','Dataset', ...
        'ReturnWorkspaceOutputs','on','LimitDataPoints','off','Decimation','1');
    r.inports={};
    for name={'inPWMs','TerrainIn15d'}
        b=[model '/' name{1}];
        set_param(b,'SampleTime','0.001','Interpolate','off');
        r.inports{end+1}=struct('name',name{1},'port',get_param(b,'Port'), ...
            'width',get_param(b,'PortDimensions'),'SampleTime',get_param(b,'SampleTime'), ...
            'Interpolate',get_param(b,'Interpolate'));
        assert(strcmp(get_param(b,'SampleTime'),'0.001') && strcmp(get_param(b,'Interpolate'),'off'));
    end
    assert(strcmp(r.inports{1}.port,'1') && strcmp(r.inports{2}.port,'2'));
    assert(str2double(r.inports{1}.width)==16 && str2double(r.inports{2}.width)==15);
    set_param(model,'SimulationCommand','update');
    r.pre_sim=verify;
    r.configuration=struct;
    for name={'SimulationMode','Solver','FixedStep','StartTime','StopTime','LoadExternalInput', ...
            'ExternalInput','SaveTime','TimeSaveName','SaveOutput','OutputSaveName','SaveFormat', ...
            'ReturnWorkspaceOutputs','LimitDataPoints','Decimation'}
        r.configuration.(name{1})=get_param(model,name{1});
    end
    r.configuration.inputs=r.inports;
    f=fopen(fullfile(out,'derived-configuration.json'),'w');
    fprintf(f,'%s',jsonencode(r.configuration,PrettyPrint=true)); fclose(f);
    md=java.security.MessageDigest.getInstance('SHA-256');
    f=fopen(fullfile(out,'derived-configuration.json'),'r'); raw=fread(f,Inf,'*uint8'); fclose(f);
    md.update(raw); bytes=typecast(md.digest(),'uint8');
    r.configuration_sha256=lower(reshape(dec2hex(bytes,2)',1,[]));
    saveResult;
    actual=sim(model);
    r.post_sim=verify;
    assert(actual.yout.numElements==3);
    assert(numel(actual.tout)==501 && all(abs(actual.tout(:)-(0:500)'*.001)<=1e-12));
    r.channels={};
    for name={'Sensor30','GPS30','Vehicle60'}
        key=name{1}; root=c.sampling.source_port_mapping.(key);
        b=[model '/' root]; port=str2double(get_param(b,'Port'));
        assert(strcmp(get_param(b,'BlockType'),'Outport'));
        expected=struct('Sensor30',1,'GPS30',2,'Vehicle60',3);
        assert(port==expected.(key));
        ch=actual.yout.get(port); ts=ch.Values;
        width=c.sampling.array_lengths.(key); rows=zeros(501,width+1);
        assert(isa(ts,'timeseries') && numel(ts.Time)==501);
        assert(all(abs(ts.Time(:)-(0:500)'*.001)<=1e-12) && all(diff(ts.Time)>0));
        for k=1:501
            v=getdatasamples(ts,k);
            assert(isa(v,'double') && isreal(v) && numel(v)==width && all(isfinite(v(:))));
            rows(k,:)=[ts.Time(k) v(:)'];
        end
        f=fopen(fullfile(out,[key '.f64']),'w','ieee-le');
        assert(f~=-1); n=fwrite(f,rows','double'); fclose(f); assert(n==numel(rows));
        r.channels{end+1}=struct('array',key,'root',root,'port',port, ...
            'dataset_name',ch.Name,'samples',501,'width',width,'encoding','row-major little-endian binary64: time then values');
    end
    f=fopen(fullfile(out,'applied-input.f64'),'w','ieee-le'); fwrite(f,a','double'); fclose(f);
    r.status='complete';
catch ex
    r.error=struct('identifier',ex.identifier,'message',ex.message,'report',getReport(ex,'extended','hyperlinks','off'));
    fprintf(2,'%s\n',r.error.report);
end
saveResult;
assert(strcmp(r.status,'complete'),'wksim:reference:invalid','See reference.json');

    function s=verify
        s=struct('parameters',{{}},'random_sources',{{}},'dependencies',{{}});
        bindings=jsondecode(fileread(fullfile(out,'parameter-bindings.json')));
        assert(numel(bindings)==22);
        for j=1:numel(bindings)
            item=bindings(j); v=evalin('base',item.name); e=c.parameters.(item.name);
            assert(numel(v)==numel(e) && isequal(v(:),e(:)));
            for k=1:numel(item.bindings)
                b=item.bindings(k); expression=get_param(b.block,b.parameter);
                assert(strcmp(expression,b.expression)); value=slResolve(expression,b.block);
                assert(numel(value)==numel(e) && isequal(value(:),e(:)));
            end
            s.parameters{end+1}=item;
        end
        assert(evalin('base','ModelParam_uavMotNumbs')==4);
        fault=evalin('base','FaultParamAPI.FaultInParams'); e=zeros(32,1); e(3)=1;
        assert(isequal(fault(:),e));
        assert(strcmp(get_param([model '/SensorOutput'],'Param_GlobalNoiseGainSwitch'),'0'));
        old=jsondecode(fileread(fullfile(out,'readiness.json')));
        for j=1:numel(old.parameters)
            p=old.parameters(j);
            if strcmp(p.name,'i_rand') || strcmp(p.name,'i_pow')
                assert(strcmp(get_param(p.block,p.name),p.expression));
                mask=Simulink.Mask.get(p.block); mp=mask.getParameter(p.name);
                assert(strcmp(mp.Enabled,p.enabled));
            end
        end
        assert(evalin('base','exist(''ModelParam_noisePowerIMU'',''var'')')==0);
        for j=1:numel(c.random.sources)
            p=c.random.sources(j); observed=struct('block',p.block,'sid',get_param(p.block,'SID'));
            assert(strcmp(observed.sid,p.sid));
            for key={'Minimum','Maximum','Seed','SampleTime'}
                observed.(key{1})=get_param(p.block,key{1}); assert(strcmp(observed.(key{1}),p.(key{1})));
            end
            s.random_sources{end+1}=observed;
        end
        blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');
        paths={};
        for j=1:numel(blocks)
            ref=get_param(blocks{j},'ReferenceBlock');
            if ~isempty(ref), paths{end+1}=which(strtok(ref,'/')); end
        end
        expected=jsondecode(fileread(fullfile(out,'dependencies.json')));
        assert(isequal(sort(unique(paths)),sort({expected.path})));
        s.dependencies=sort(unique(paths));
        assert(strcmp(get_param(model,'Solver'),'ode4') && strcmp(get_param(model,'FixedStep'),'0.001') ...
            && strcmp(get_param(model,'SimulationMode'),'normal'));
    end
    function saveResult
        f=fopen(fullfile(out,'reference.json'),'w'); fprintf(f,'%s',jsonencode(r,PrettyPrint=true)); fclose(f);
    end
end
