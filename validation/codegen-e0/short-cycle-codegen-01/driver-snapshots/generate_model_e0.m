function generate_model_e0
% Generate standalone C++ code from e0 model via Embedded Coder (ert.tlc).
% Bounded headless execution. Never simulate, save modified model, or call vendor .p scripts.

config_path = fullfile(pwd, 'codegen_config.json');
if ~isfile(config_path)
    fprintf(2, 'Missing codegen_config.json in staged directory: %s\n', pwd);
    exit(1);
end

cfg = jsondecode(fileread(config_path));
model = cfg.model_name;
out_report = cfg.report_output;

r = struct('status', 'blocked', 'stages', {{}}, 'environment', struct(), ...
           'licenses', struct(), 'solver', struct(), 'original_target', struct(), ...
           'artifacts', {{}});

cleanup = onCleanup(@() bdclose('all'));

% 1. Record and isolate MATLAB environment and product versions
r.environment.version = version;
r.environment.release = version('-release');
r.environment.matlabroot = matlabroot;
r.environment.products = ver;
r.environment.startup_path = path;
evalin('base', 'restoredefaultpath');
addpath(pwd);
r.environment.isolated_path = path;

% 2. License testing and checkout verification for required toolboxes
required_feats = cfg.required_licenses;
r.licenses.test = struct();
r.licenses.checkout = struct();
all_licenses_ok = true;

for i = 1:numel(required_feats)
    feat = required_feats{i};
    vname = matlab.lang.makeValidName(feat);
    t_val = license('test', feat);
    [c_val, c_msg] = license('checkout', feat);
    r.licenses.test.(vname) = t_val;
    r.licenses.checkout.(vname) = c_val;
    if t_val ~= 1 || c_val ~= 1
        all_licenses_ok = false;
        fprintf(2, 'License check failed for feature %s: test=%d, checkout=%d (%s)\n', ...
                feat, t_val, c_val, c_msg);
    end
end

saveResult();

if ~all_licenses_ok
    stage('license_verification', 'Verify test and checkout for required toolboxes', 'failed', []);
    r.status = 'license_failed';
    saveResult();
    exit(1);
else
    stage('license_verification', 'Verify test and checkout for required toolboxes', 'ok', []);
end

% 3. Configure Simulink file generation private directories
try
    Simulink.fileGenControl('set', 'CacheFolder', cfg.cache_folder, ...
                            'CodeGenFolder', cfg.codegen_folder, 'createDir', true);
    stage('fileGenControl', 'Set private CacheFolder and CodeGenFolder', 'ok', []);
catch ex
    stage('fileGenControl', 'Set private CacheFolder and CodeGenFolder', 'failed', ex);
    r.status = 'failed';
    saveResult();
    exit(1);
end

% 4. Load model
try
    load_system(fullfile(pwd, [model '.slx']));
    stage('load_system', sprintf('load_system(''%s.slx'')', model), 'ok', []);
catch ex
    stage('load_system', sprintf('load_system(''%s.slx'')', model), 'failed', ex);
    r.status = 'failed';
    saveResult();
    exit(1);
end

% 5. Verify ODE4/0.001s solver configuration and switch SimulationMode to normal in-memory
solver = get_param(model, 'Solver');
fixedStep = get_param(model, 'FixedStep');
r.solver.Solver = solver;
r.solver.FixedStep = fixedStep;
r.solver.SimulationMode = get_param(model, 'SimulationMode');

r.original_target.SystemTargetFile = get_param(model, 'SystemTargetFile');
r.original_target.TargetLang = get_param(model, 'TargetLang');
r.original_target.GenCodeOnly = get_param(model, 'GenCodeOnly');

if ~strcmp(solver, 'ode4') || ~strcmp(fixedStep, '0.001')
    stage('verify_solver', sprintf('Require Solver=ode4, FixedStep=0.001; got Solver=%s, FixedStep=%s', solver, fixedStep), 'failed', []);
    r.status = 'invalid_solver_config';
    saveResult();
    exit(1);
else
    set_param(model, 'SimulationMode', 'normal');
    r.execution_override = struct('SimulationMode', 'normal', 'scope', 'in-memory only; SLX file untouched');
    stage('verify_solver', sprintf('Verified Solver=%s, FixedStep=%s; set SimulationMode normal', solver, fixedStep), 'ok', []);
end

% 6. In-memory target configuration (ERT TLC, C++, GenCodeOnly=on)
% Note: Model is NOT saved back to disk. Changes exist only in memory during this process.
try
    set_param(model, 'SystemTargetFile', cfg.system_target_file);
    set_param(model, 'TargetLang', cfg.target_lang);
    set_param(model, 'GenCodeOnly', cfg.gen_code_only);
    set_param(model, 'PackageGeneratedCodeAndArtifacts', cfg.package_artifacts);
    stage('configure_target', 'Set SystemTargetFile=ert.tlc, TargetLang=C++, GenCodeOnly=on', 'ok', []);
catch ex
    stage('configure_target', 'Set SystemTargetFile=ert.tlc, TargetLang=C++, GenCodeOnly=on', 'failed', ex);
    r.status = 'failed';
    saveResult();
    exit(1);
end

% 7. Run original companion init in base workspace
init_script = fullfile(pwd, [model '_init.m']);
try
    evalin('base', sprintf('run(''%s'')', strrep(init_script, '''', '''''')));
    stage('initialization', sprintf('run(''%s_init.m'') in base workspace', model), 'ok', []);
catch ex
    stage('initialization', sprintf('run(''%s_init.m'') in base workspace', model), 'failed', ex);
    r.status = 'failed';
    saveResult();
    exit(1);
end

% 8. Execute code generation via slbuild
try
    slbuild(model);
    stage('slbuild', sprintf('slbuild(''%s'') for standalone C++ code generation', model), 'ok', []);
catch ex
    stage('slbuild', sprintf('slbuild(''%s'') for standalone C++ code generation', model), 'failed', ex);
    r.status = 'failed';
    saveResult();
    exit(1);
end

% 9. Enumerate and check generated C++ and header files
gen_files = dir(fullfile(cfg.codegen_folder, '**', '*.*'));
cpp_files = 0;
header_files = 0;
has_empty = false;

for k = 1:numel(gen_files)
    if ~gen_files(k).isdir
        [~, fname, fext] = fileparts(gen_files(k).name);
        fext_lower = lower(fext);
        if ismember(fext_lower, {'.cpp', '.cxx', '.cc', '.h', '.hpp'})
            if ismember(fext_lower, {'.cpp', '.cxx', '.cc'})
                cpp_files = cpp_files + 1;
            else
                header_files = header_files + 1;
            end
            if gen_files(k).bytes == 0
                has_empty = true;
            end
            art = struct('name', gen_files(k).name, 'bytes', gen_files(k).bytes, ...
                         'relative_dir', gen_files(k).folder);
            r.artifacts{end+1} = art;
        end
    end
end

if cpp_files > 0 && header_files > 0 && ~has_empty
    r.status = 'generated';
    stage('artifact_verification', sprintf('Found %d C++ and %d header non-empty files', cpp_files, header_files), 'ok', []);
else
    r.status = 'missing_artifacts';
    stage('artifact_verification', sprintf('Expected non-empty C++ and header files, found cpp=%d, h=%d, empty=%d', cpp_files, header_files, has_empty), 'failed', []);
end

% 10. Close model without saving
bdclose(model);
stage('close_model', 'bdclose without saving modified model', 'ok', []);

saveResult();

if strcmp(r.status, 'generated')
    exit(0);
else
    exit(1);
end

    function stage(name, command, status, ex)
        s = struct('name', name, 'command', command, 'status', status, ...
                   'identifier', '', 'message', '', 'report', '');
        if ~isempty(ex)
            s.identifier = ex.identifier;
            s.message = ex.message;
            s.report = getReport(ex, 'extended', 'hyperlinks', 'off');
            fprintf(2, '%s\n', s.report);
        end
        r.stages{end+1} = s;
        saveResult();
    end

    function saveResult()
        f = fopen(out_report, 'w');
        if f ~= -1
            fprintf(f, '%s', jsonencode(r, PrettyPrint=true));
            fclose(f);
        end
    end
end
