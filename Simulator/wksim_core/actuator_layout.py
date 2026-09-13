"""Convert declared PWM channels to named signed or positive actuators."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PWMActuator:
    name: str
    channel: int
    signed: bool
    minimum: int = 1000
    neutral: int = 1500
    maximum: int = 2000
    reversed: bool = False

    def __post_init__(self):
        if (not isinstance(self.name,str) or not self.name or type(self.channel) is not int
                or not 0<=self.channel<16 or type(self.signed) is not bool or type(self.reversed) is not bool
                or any(type(x) is not int for x in (self.minimum,self.neutral,self.maximum))
                or not 0<self.minimum<self.neutral<self.maximum or (self.reversed and not self.signed)):
            raise ValueError('Invalid explicit PWM actuator declaration')

    def decode(self,pwm):
        if type(pwm) is not int:raise ValueError('PWM must be an integer')
        if pwm==0:return 0. # Disabled output is neutral, never reverse propulsion.
        if not self.minimum<=pwm<=self.maximum:raise ValueError('PWM outside declared actuator range')
        if not self.signed:return (pwm-self.minimum)/(self.maximum-self.minimum)
        scale=self.maximum-self.neutral if pwm>=self.neutral else self.neutral-self.minimum
        return (pwm-self.neutral)/scale*(-1 if self.reversed else 1)


def decode_layout(layout,pwm):
    if (len(pwm)!=16 or not layout or len({x.name for x in layout})!=len(layout)
            or len({x.channel for x in layout})!=len(layout)):
        raise ValueError('Expected a unique named actuator layout and 16 PWM channels')
    return {item.name:item.decode(pwm[item.channel]) for item in layout}


ACKERMANN = (PWMActuator('steering',0,True),PWMActuator('throttle',2,True))
QUAD_X = tuple(PWMActuator(name,i,False) for i,name in enumerate(('front_right','rear_left','front_left','rear_right')))
