function resolution = resolve_probe_solver_input(integrator)
%RESOLVE_PROBE_SOLVER_INPUT Follow actual ports to a matrix Product, read-only.
% A subsystem hop enters the direct Outport corresponding to the source port.
% Names never select the leaf. Missing, cyclic, ambiguous or unsupported paths
% remain unavailable. This inspects the loaded model; it does not load or save it.
resolution = struct('status','unavailable','reason','not resolved', ...
    'target_path','','hops',{{}},'upstream',[]);
boundary = integrator;
seen = {};
try
    for hop = 1:16
        boundary_path = getfullname(boundary);
        if any(strcmp(seen, boundary_path))
            error('wk:probe:cycle','cycle in upstream port traversal');
        end
        seen{end+1} = boundary_path; %#ok<AGROW>
        ph = get_param(boundary,'PortHandles');
        if numel(ph.Inport) < 1
            error('wk:probe:port','traversed boundary has no input port');
        end
        line = get_param(ph.Inport(1),'Line');
        source = get_param(line,'SrcBlockHandle');
        source_port = get_param(line,'SrcPortHandle');
        source_path = getfullname(source);
        source_type = get_param(source,'BlockType');
        port_number = get_param(source_port,'PortNumber');
        if ~isnumeric(port_number) || ~isscalar(port_number) || ...
                ~isfinite(port_number) || port_number < 1 || fix(port_number) ~= port_number
            error('wk:probe:port','source output port number is invalid');
        end
        resolution.hops{end+1} = struct('destination',boundary_path, ...
            'source',source_path,'source_type',source_type, ...
            'source_output_port',port_number); %#ok<AGROW>
        if strcmp(source_type,'Product')
            upstream = struct('path',source_path,'BlockType',source_type, ...
                'is_product_block',true);
            for field = {'Inputs','Multiplication','InputSameDT','OutDataTypeStr'}
                try, upstream.(field{1}) = get_param(source,field{1});
                catch, upstream.(field{1}) = 'unavailable'; end
            end
            resolution.target_path = source_path;
            resolution.upstream = upstream;
            resolution.status = 'traced';
            resolution.reason = 'Product resolved by actual port connections';
            return;
        elseif strcmp(source_type,'Reshape')
            reshape_ports = get_param(source,'PortHandles');
            if numel(reshape_ports.Inport) ~= 1 || numel(reshape_ports.Outport) ~= 1
                error('wk:probe:reshape','Reshape does not have one input and one output');
            end
            resolution.hops{end}.output_dimensionality = get_param(source,'OutputDimensionality');
            boundary = source_path;
        elseif strcmp(source_type,'SubSystem')
            ports = find_system(source_path,'SearchDepth',1,'FollowLinks','on', ...
                'LookUnderMasks','all','BlockType','Outport', ...
                'Port',num2str(port_number));
            if numel(ports) ~= 1
                error('wk:probe:ambiguous','source subsystem has no unique matching direct Outport');
            end
            boundary = ports{1};
        else
            error('wk:probe:routing','unsupported upstream block type: %s',source_type);
        end
    end
    resolution.reason = 'upstream traversal exceeded 16 hops';
catch ex
    resolution.status = 'unavailable';
    resolution.reason = ex.message;
end
end
