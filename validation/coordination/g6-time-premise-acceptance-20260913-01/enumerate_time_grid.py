"""Independent finite-domain arithmetic check; no model or physical budget."""
from fractions import Fraction
import json
import math
import struct


def enumerate_grid():
    def bits(value):
        return int.from_bytes(struct.pack('>d', value), 'big')

    equal = different = maximum = 0
    maximum_error = Fraction(0)
    maximum_normalized = Fraction(0)
    for tick in range(98685):
        product = tick * .001
        rational = Fraction(tick, 1000)
        rounded = float(rational)
        distance = abs(bits(product) - bits(rounded))
        equal += distance == 0
        different += distance != 0
        maximum = max(maximum, distance)
        error = abs(Fraction.from_float(product) - rational)
        maximum_error = max(maximum_error, error)
        if error:
            spacing = (Fraction.from_float(math.nextafter(product, math.inf))
                       - Fraction.from_float(product))
            maximum_normalized = max(maximum_normalized, error / spacing)
    assert (equal, different, maximum) == (85555, 13130, 1)
    assert maximum_error == Fraction(1, 109951162777600)
    assert maximum_normalized == Fraction(17, 25)
    return dict(domain=[0, 98684], equal=equal, different=different,
                maximum_lattice_distance=maximum,
                maximum_error_seconds=str(maximum_error),
                maximum_error_over_forward_spacing=str(maximum_normalized),
                budget_approved=False, g6_acceptance=False)


if __name__ == '__main__':
    print(json.dumps(enumerate_grid(), indent=2))
