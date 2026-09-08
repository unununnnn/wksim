function probe_model_reference_readiness
% Bounded private load/update only. Never simulate, generate code, or save model.
out = fileparts(pwd);
model = 'Exp1_MinModelTemp';
r = struct('status','blocked','stages',{{}},'environment',struct(), 'parameters',{{}}, 'random_sources',{{}}, 'dependencies',{{}});
cleanup = onCleanup(@() bdclose('all'));
r.environment.version = version;
r.environment.release = version('-release');
r.environment.matlabroot = matlabroot;
r.environment.startup_path = path;
evalin('base','restoredefaultpath');
addpath(pwd);
r.environment.path = path;
r.environment.products = ver;
features = {'SIMULINK','Aerospace_Blockset','Aerospace_Toolbox','Real-Time_Workshop'};
for i=1:numel(features)
    r.environment.licenses.(matlab.lang.makeValidName(features{i})) = license('test',features{i});
end
saveResult;
try
    Simulink.fileGenControl('set','CacheFolder',fullfile(out,'cache'),'CodeGenFolder',fullfile(out,'codegen'),'createDir',true);
    stage('capability','Simulink.fileGenControl private cache/codegen folders','ok',[]);
catch ex
    stage('capability','Simulink.fileGenControl','failed',ex); return;
end
try
    load_system(fullfile(pwd,[model '.slx']));
    stage('load_system','load_system(private SLX)','ok',[]);
    r.saved_simulation_mode=get_param(model,'SimulationMode');
    set_param(model,'SimulationMode','normal');
    r.execution_override=struct('SimulationMode','normal','scope','in-memory only; source and staged SLX unchanged');
catch ex
    stage('load_system','load_system(private SLX)','failed',ex); return;
end
% Run the unchanged adjacent init explicitly: the original InitFcn swallows errors.
% Update will also run its original InitFcn. No values are supplied by this probe.
try
    evalin('base',sprintf('run(''%s'')',strrep(fullfile(pwd,[model '_init.m']),'''','''''')));
    stage('initialization','run unchanged private init in base workspace','ok',[]);
catch ex
    stage('initialization','run unchanged private init in base workspace','failed',ex);
end
try
    snapshot;
    stage('parameters_before_update','snapshot masks/seeds/dependencies','ok',[]);
catch ex
    stage('parameters_before_update','snapshot masks/seeds/dependencies','failed',ex);
end
try
    set_param(model,'SimulationCommand','update');
    stage('update','set_param(model, SimulationCommand, update)','ok',[]);
    r.status = 'ready';
catch ex
    stage('update','set_param(model, SimulationCommand, update)','failed',ex);
end
try
    snapshot;
    stage('parameters_after_update','snapshot masks/seeds/dependencies','ok',[]);
catch ex
    stage('parameters_after_update','snapshot masks/seeds/dependencies','failed',ex);
    r.status='blocked';
end
if any(cellfun(@(s) strcmp(s.status,'failed'),r.stages))
    r.status='blocked';
end
saveResult;
bdclose(model);
stage('close','bdclose without save','ok',[]);

    function stage(name,command,status,ex)
        s=struct('name',name,'command',command,'status',status,'identifier','','message','','report','');
        if ~isempty(ex)
            s.identifier=ex.identifier; s.message=ex.message; s.report=getReport(ex,'extended','hyperlinks','off');
            fprintf(2,'%s\n',s.report);
        end
        r.stages{end+1}=s; saveResult;
    end
    function saveResult
        f=fopen(fullfile(out,'readiness.json'),'w');
        fprintf(f,'%s',jsonencode(r,PrettyPrint=true)); fclose(f);
    end
    function snapshot
        vars=evalin('base','whos'); r.workspace=struct();
        for j=1:numel(vars)
            n=vars(j).name;
            if startsWith(n,'Model') || strcmp(n,'FaultParamAPI')
                r.workspace.(n)=evalin('base',n);
            end
        end
        r.parameters={}; r.random_sources={}; r.dependencies={}; r.model_parameter_bindings={};
        blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');
        for j=1:numel(blocks)
            b=blocks{j};
            dp=get_param(b,'DialogParameters');
            if ~isstruct(dp), dp=struct(); end
            keys=fieldnames(dp);
            for k=1:numel(keys)
                expression=get_param(b,keys{k});
                if ischar(expression) && ~isempty(regexp(expression,'Model(Param|Init)_','once'))
                    item=struct('block',b,'parameter',keys{k},'expression',expression,'resolved',false,'value',[],'error','');
                    try
                        item.value=slResolve(expression,b); item.resolved=true;
                    catch ex
                        item.error=getReport(ex,'extended','hyperlinks','off');
                    end
                    r.model_parameter_bindings{end+1}=item;
                end
            end
            ref=get_param(b,'ReferenceBlock');
            if ~isempty(ref)
                lib=strtok(ref,'/');
                r.dependencies{end+1}=struct('block',b,'reference',ref,'resolved_path',which(lib));
            end
            names=get_param(b,'MaskNames'); values=get_param(b,'MaskValues');
            mask=Simulink.Mask.get(b);
            for k=1:numel(names)
                mp=mask.getParameter(names{k});
                item=struct('block',b,'name',names{k},'expression',values{k},'evaluate',mp.Evaluate,'enabled',mp.Enabled,'resolved',false,'value',[],'identifier','','error','');
                try
                    if strcmp(mp.Evaluate,'off')
                        item.value=values{k};
                    else
                        item.value=slResolve(values{k},b);
                    end
                    item.resolved=true;
                catch ex
                    item.identifier=ex.identifier; item.error=ex.message;
                end
                r.parameters{end+1}=item;
            end
            if strcmp(get_param(b,'BlockType'),'UniformRandomNumber')
                item=struct('block',b,'sid',get_param(b,'SID'));
                for key={'Minimum','Maximum','Seed','SampleTime'}
                    item.(key{1})=get_param(b,key{1});
                end
                r.random_sources{end+1}=item;
            end
        end
        r.solver=struct('Solver',get_param(model,'Solver'),'FixedStep',get_param(model,'FixedStep'),'SimulationMode',get_param(model,'SimulationMode'));
        saveResult;
    end
end
