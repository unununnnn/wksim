"""Explicit selection of the three implemented position-control adapters.

Only the selected algorithm is imported. Trial protocols and admission remain
owned by the experiment; selecting an algorithm grants no flight capability.
These are external position controllers, not replacements for firmware rate PID.
"""


def _definition(name):
    if name == 'pid':
        from .position_pid import PIDConfig, PositionPID
        return PIDConfig, PositionPID
    if name == 'ude':
        from .position_ude import UDEConfig, PositionUDE
        return UDEConfig, PositionUDE
    if name == 'ne':
        from .position_ne import NEConfig, PositionNE
        return NEConfig, PositionNE
    raise ValueError(f'unsupported external position controller: {name!r}')


def controller_config(name, mass_kg, parameters):
    config_type, _ = _definition(name)
    return config_type(mass_kg, **parameters)


def select_controller(name, config):
    """Each selected adapter validates its typed config and starts cold."""
    _, implementation = _definition(name)
    return implementation(config)


def controller_implementation(name):
    """Return the actual selected implementation identity for run evidence."""
    _, implementation = _definition(name)
    return implementation.__module__ + '.' + implementation.__qualname__
