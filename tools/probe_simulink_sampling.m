function probe_simulink_sampling
% Analytic logging fixture only; never load or simulate the vehicle model.
out=pwd;
evalin('base','restoredefaultpath');
name='wksim_sampling_fixture';
cleanup=onCleanup(@() bdclose('all'));
r=struct('status','failed','scope','normal ODE4 input and major-output logging fixture', ...
    'version',version,'release',version('-release'));
try
    Simulink.fileGenControl('set','CacheFolder',fullfile(out,'cache'), ...
        'CodeGenFolder',fullfile(out,'codegen'),'createDir',true);
    new_system(name);
    set_param(name,'SimulationMode','normal','Solver','ode4','FixedStep','0.001', ...
        'StartTime','0','StopTime','0.006','LoadExternalInput','on', ...
        'ExternalInput','fixture_input','SaveTime','on','TimeSaveName','tout', ...
        'SaveOutput','on','OutputSaveName','yout','SaveFormat','Dataset', ...
        'ReturnWorkspaceOutputs','on');
    add_block('simulink/Sources/In1',[name '/Input']);
    add_block('simulink/Sinks/Out1',[name '/Direct'],'Port','1');
    add_block('simulink/Discrete/Unit Delay',[name '/Delay'],'SampleTime','0.001','InitialCondition','0');
    add_block('simulink/Sinks/Out1',[name '/Delayed'],'Port','2');
    add_block('simulink/Continuous/Integrator',[name '/State'],'InitialCondition','1');
    add_block('simulink/Math Operations/Gain',[name '/Rate'],'Gain','100');
    add_block('simulink/Sinks/Out1',[name '/Continuous'],'Port','3');
    add_block('simulink/Continuous/Integrator',[name '/InputIntegral'],'InitialCondition','0');
    add_block('simulink/Sinks/Out1',[name '/IntegratedInput'],'Port','4');
    add_line(name,'Input/1','Direct/1'); add_line(name,'Input/1','Delay/1');
    add_line(name,'Delay/1','Delayed/1'); add_line(name,'State/1','Rate/1');
    add_line(name,'Rate/1','State/1'); add_line(name,'State/1','Continuous/1');
    add_line(name,'Input/1','InputIntegral/1'); add_line(name,'InputIntegral/1','IntegratedInput/1');
    values=[1;1;2;2;-1;-1;0];
    times=(0:6)'*.001;
    assignin('base','fixture_input',[times values]);
    r.input=struct('times',times,'values',values,'sample_time',get_param([name '/Input'],'SampleTime'), ...
        'interpolate',get_param([name '/Input'],'Interpolate'));
    r.contract=struct('step_s',.001,'samples',7,'end_time_s',.006, ...
        'logging_absolute_roundoff_limit',1e-12, ...
        'continuous_equation','dx/dt=100*x, x(0)=1', ...
        'expected_major_output','x(k)=R(0.1)^k, R(z)=1+z+z^2/2+z^3/6+z^4/24', ...
        'expected_delayed_output',[0;values(1:end-1)], ...
        'vehicle_precision_budget',false);
    save_system(name,fullfile(out,[name '.slx']));
    z=.1; step_factor=1+z+z^2/2+z^3/6+z^4/24;
    r.cases={};
    for kind={'inherited_interpolated','discrete_zoh'}
        if strcmp(kind{1},'discrete_zoh')
            set_param([name '/Input'],'SampleTime','0.001','Interpolate','off');
            integral=[0;cumsum(values(1:end-1))*.001];
        else
            integral=[0;cumsum((values(1:end-1)+values(2:end))/2)*.001];
        end
        expected={values,[0;values(1:end-1)],step_factor.^(0:6)',integral};
        actual=sim(name);
        channels=cell(1,4);
        for index=1:4
            channel=actual.yout.get(index);
            channels{index}=struct('name',channel.Name,'time',channel.Values.Time,'data',channel.Values.Data);
        end
        r.cases{end+1}=struct('name',kind{1},'channels',{channels},'tout',actual.tout, ...
            'sample_time',get_param([name '/Input'],'SampleTime'), ...
            'interpolate',get_param([name '/Input'],'Interpolate'),'expected',{expected});
        for index=1:4
            assert(numel(channels{index}.time)==7 && max(abs(channels{index}.time-times))<=1e-12, ...
                'wksim:sampling:time','Major log samples differ from frozen grid');
            assert(max(abs(channels{index}.data(:)-expected{index}))<=1e-12, ...
                'wksim:sampling:value','Logging semantics differ from analytic fixture');
        end
    end
    r.status='pass';
catch ex
    r.error=struct('identifier',ex.identifier,'message',ex.message,'report',getReport(ex,'extended','hyperlinks','off'));
end
f=fopen(fullfile(out,'sampling.json'),'w'); fprintf(f,'%s',jsonencode(r,PrettyPrint=true)); fclose(f);
assert(strcmp(r.status,'pass'),'wksim:sampling:failed','See retained sampling.json');
end
