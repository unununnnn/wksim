"""Named-actuator model host for a real generated quad and a ground bicycle.

Legacy generated ABI details stay in the quad adapter. Firmware/visual selection
is deliberately absent; a model selection does not admit a firmware combination.
"""
import math

from .actuator_layout import QUAD_X,ACKERMANN
from .vehicle_state import VehicleState


class VehicleModel:
    dt_s=.001

    def __init__(self,profile,*,library=None,parameters=None):
        self.profile=profile
        if profile=='quad_x':
            if library is None or parameters is not None:
                raise ValueError('Generated quad requires an explicit library and its own model parameter workflow')
            from .model import Model
            self._model=Model(library)
            self.layout=QUAD_X
            self.vehicle_class='multicopter'
        elif profile=='ackermann_v1':
            if library is not None:raise ValueError('Ground model does not load a quad library')
            from .ackermann import AckermannModel,AckermannParameters
            self._model=AckermannModel(parameters if parameters is not None else AckermannParameters())
            self.layout=ACKERMANN
            self.vehicle_class='ground_vehicle'
        else:
            raise ValueError('Unimplemented model profile: '+str(profile))
        self.actuators=tuple(item.name for item in self.layout)
        self._closed=False

    def step(self,actuators,steps=1):
        if self._closed:raise ValueError('Model is closed')
        if not isinstance(actuators,dict) or set(actuators)!=set(self.actuators):
            raise ValueError('Actuator names differ from the selected vehicle')
        if type(steps) is not int or not 1<=steps<=1000:
            raise ValueError('Expected 1..1000 fixed model steps')
        if any(type(actuators[item.name]) not in (int,float) or not math.isfinite(actuators[item.name])
               or not (-1 if item.signed else 0)<=actuators[item.name]<=1 for item in self.layout):
            raise ValueError('Actuator value outside the selected vehicle domain')
        if self.profile=='quad_x':
            raw=self._model.step([actuators[name] for name in self.actuators]+[0.]*12,steps)
            return VehicleState(raw[2],tuple(raw[6:9]),tuple(raw[3:6]),tuple(raw[12:16]),
                                tuple(raw[64:67]),tuple(raw[61:64]))
        for _ in range(steps):state=self._model.step(**actuators,dt_s=self.dt_s)
        return state

    def close(self):
        if not self._closed and self.profile=='quad_x':self._model.close()
        self._closed=True

    def __enter__(self):return self
    def __exit__(self,*_):self.close()
