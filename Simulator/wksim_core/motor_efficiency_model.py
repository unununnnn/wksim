"""Separate, pinned-source rotor-0 aerodynamic efficiency candidate, local use.

No production model pins or generated vendor files in the repository are edited.
The only selectable factors are the frozen .97 event and normal 1.0 state.
"""
import ctypes as C
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .model import ARCHIVE, EXPECTED_HASH, Model, extract_source
from .model_parameters import RAW_HASHES, WRAPPER_HASH, sha

SCHEMA = 'wksim.rotor-efficiency-model.v1'
SEED_FIELDS = (('RandSeed', 3), ('RandSeed_g', 3), ('RandSeed_j', 3),
               ('RandSeed_l', 1), ('RandSeed_p', 1), ('RandSeed_ld', 3), ('RandSeed_ji', 3))


def replace_once(raw, before, after):
    if raw.count(before) != 1:
        raise ValueError('Ambiguous generated source seam: '+before[:70])
    return raw.replace(before, after)


def patched_sources(cpp, header):
    if sha(cpp) != RAW_HASHES['Exp1_MinModelTemp.cpp'] or sha(header) != RAW_HASHES['Exp1_MinModelTemp.h']:
        raise ValueError('Unreviewed generated source')
    source = cpp.decode('latin1').replace('\r\n', '\n')
    source = '#include "motor_efficiency_native.h"\n'+source
    source = replace_once(source,
        'rtb_Sum_e2_idx_0 = Exp1_MinModelTemp_P.ModelParam_rotorCt *',
        'rtb_Sum_e2_idx_0 = wk_motor_eta[rtb_Sum_i] * Exp1_MinModelTemp_P.ModelParam_rotorCt *')
    source = replace_once(source,
        'rtb_Switch_o += -(Exp1_MinModelTemp_P.ModelParam_rotorCm *',
        'const double wk_torque_before = rtb_Switch_o;\n      rtb_Switch_o += -(wk_motor_eta[rtb_Sum_i] * Exp1_MinModelTemp_P.ModelParam_rotorCm *')
    marker = "      // '<S120>:1:67' Fb=Fb+[0;0;-PropT];"
    source = replace_once(source, marker,
        '      wk_efficiency_sample(rtb_Sum_i, (&Exp1_MinModelTemp_M)->Timing.t[0],\n'
        '        rtmIsMajorTimeStep((&Exp1_MinModelTemp_M)), rtb_UniformRandomNumber4_idx_0,\n'
        '        Exp1_MinModelTemp_P.ModelParam_rotorCt, Exp1_MinModelTemp_P.ModelParam_rotorCm,\n'
        '        rtb_Sum_e2_idx_0, rtb_Switch_o-wk_torque_before, rtb_sincos_o1_j_idx_2);\n'+marker)
    head = header.decode('latin1').replace('\r\n', '\n')
    values = ['Exp1_MinModelTemp_DW.'+name+(f'[{i}]' if count>1 else '')
              for name,count in SEED_FIELDS for i in range(count)]
    method = '  void wk_random_state(uint32_T* out) const {\n'
    method += ''.join(f'    out[{i}] = {value};\n' for i,value in enumerate(values))+'  }\n\n'
    head = replace_once(head, '  // private data and function members', method+'  // private data and function members')
    return source.encode('latin1'), head.encode('latin1')


def build(archive=ARCHIVE):
    extracted = extract_source(archive)
    root = Path(tempfile.mkdtemp(prefix='wksim-efficiency-model-',dir='/root'))
    for name in RAW_HASHES:
        shutil.copy2(extracted/name, root/name)
    for name, expected in RAW_HASHES.items():
        if sha((root/name).read_bytes()) != expected:
            raise ValueError('Source member differs: '+name)
    cpp, header = root/'Exp1_MinModelTemp.cpp', root/'Exp1_MinModelTemp.h'
    original_cpp, original_h = cpp.read_bytes(), header.read_bytes()
    (root/'original.cpp').write_bytes(original_cpp); (root/'original.h').write_bytes(original_h)
    changed_cpp, changed_h = patched_sources(original_cpp, original_h)
    cpp.write_bytes(changed_cpp); header.write_bytes(changed_h)
    core = Path(__file__).parent
    if sha((core/'model.cpp').read_bytes()) != WRAPPER_HASH:
        raise ValueError('Baseline wrapper changed')
    shutil.copy2(core/'model.cpp', root/'base_wrapper.cpp')
    for name in ('motor_efficiency_native.h','motor_efficiency_native.cpp'):
        shutil.copy2(core/name, root/name)
    library = root/'libwksim_efficiency.so'
    argv = ['g++','-std=c++17','-O2','-fno-fast-math','-fPIC','-shared','-Wl,--no-undefined',
            '-I',str(root),str(cpp),str(root/'motor_efficiency_native.cpp'),'-o',str(library)]
    result = subprocess.run(argv, text=True, capture_output=True, timeout=60)
    (root/'build.stdout.log').write_text(result.stdout); (root/'build.stderr.log').write_text(result.stderr)
    if result.returncode:
        raise RuntimeError('Efficiency build failed: '+str(root/'build.stderr.log'))
    names=[*RAW_HASHES,'original.cpp','original.h','base_wrapper.cpp','motor_efficiency_native.h',
           'motor_efficiency_native.cpp',library.name]
    manifest=dict(schema=SCHEMA, archive=str(archive), archive_sha256=EXPECTED_HASH, library=str(library),
        files_sha256={name:sha((root/name).read_bytes()) for name in names},
        builder_sha256=sha(Path(__file__).read_bytes()), argv=argv,
        compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
        random_state_fields=SEED_FIELDS, physical_semantics='rotor0 thrust and reaction torque times eta; motor and gyro unchanged',
        production_admitted=False, flown=False, redistribution='local supplied source use only')
    (root/'efficiency-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return library


class EfficiencyModel(Model):
    _used_pid = None

    def __init__(self, library):
        library=Path(library).resolve(strict=True)
        manifest=json.loads((library.parent/'efficiency-build.json').read_text())
        if manifest['schema']!=SCHEMA or manifest['library']!=str(library):
            raise ValueError('Wrong efficiency model identity')
        names={*RAW_HASHES,'original.cpp','original.h','base_wrapper.cpp','motor_efficiency_native.h',
               'motor_efficiency_native.cpp','libwksim_efficiency.so'}
        if (set(manifest['files_sha256'])!=names or manifest['archive_sha256']!=EXPECTED_HASH
                or manifest['builder_sha256']!=sha(Path(__file__).read_bytes())):
            raise ValueError('Incomplete or changed efficiency build recipe')
        for name, expected in manifest['files_sha256'].items():
            if Path(name).name!=name or sha((library.parent/name).read_bytes())!=expected:
                raise ValueError('Efficiency artifact differs: '+name)
        cpp,head=patched_sources((library.parent/'original.cpp').read_bytes(),(library.parent/'original.h').read_bytes())
        if cpp!=(library.parent/'Exp1_MinModelTemp.cpp').read_bytes() or head!=(library.parent/'Exp1_MinModelTemp.h').read_bytes():
            raise ValueError('Efficiency patch differs')
        for name in ('motor_efficiency_native.cpp','motor_efficiency_native.h'):
            if (library.parent/name).read_bytes()!=Path(__file__).with_name(name).read_bytes():
                raise ValueError('Native efficiency wrapper changed')
        if sha((library.parent/'base_wrapper.cpp').read_bytes())!=WRAPPER_HASH:
            raise ValueError('Baseline bridge changed')
        self.manifest=manifest
        self.library_sha256=manifest['files_sha256']['libwksim_efficiency.so']
        if EfficiencyModel._used_pid==os.getpid():
            raise RuntimeError('Efficiency model requires a new process for every lifetime')
        EfficiencyModel._used_pid=os.getpid()
        super().__init__(library)
        for name, args, result in (
            ('set_efficiency',[C.c_void_p,C.c_int,C.c_double],C.c_int),
            ('get_efficiency',[C.c_void_p,C.POINTER(C.c_double),C.c_int],C.c_int),
            ('random_state',[C.c_void_p,C.POINTER(C.c_uint32),C.c_int],C.c_int),
            ('efficiency_stages',[C.c_void_p,C.POINTER(C.c_double),C.c_int],C.c_int),
            ('tick',[C.c_void_p],C.c_uint64)):
            fn=getattr(self.library,'wk_model_'+name); fn.argtypes=args; fn.restype=result
        self.initial_random_state=self.random_state()

    def efficiency(self):
        output=(C.c_double*4)()
        if self.library.wk_model_get_efficiency(self.handle,output,4): raise RuntimeError('Efficiency readback failed')
        return list(output)

    def set_efficiency(self, eta):
        if type(eta) not in (int,float) or eta not in (1.,.97): raise ValueError('Select frozen eta 1 or .97')
        if self.library.wk_model_set_efficiency(self.handle,0,eta): raise RuntimeError('Efficiency write failed')
        if self.efficiency()!=[float(eta),1.,1.,1.]: raise RuntimeError('Efficiency readback mismatch')

    def random_state(self):
        output=(C.c_uint32*17)()
        if self.library.wk_model_random_state(self.handle,output,17): raise RuntimeError('Random state readback failed')
        return list(output)

    def step(self, commands, steps=1):
        if type(steps) is not int or steps!=1: raise ValueError('Efficiency event boundary requires individual 1 ms steps')
        output=super().step(commands,1)
        if self.library.wk_model_tick(self.handle)!=self.ticks: raise RuntimeError('Native tick mismatch')
        stages=(C.c_double*160)()
        if self.library.wk_model_efficiency_stages(self.handle,stages,160)!=16:
            raise RuntimeError('Missing ODE4 substage evidence')
        self.stages=[list(stages[i:i+10]) for i in range(0,160,10)]
        return output


if __name__=='__main__':
    print(build())
