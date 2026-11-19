"""Exact comparison of bilinear level sets inside a single original cell.

Both sides of an overlap review keep the same original cells but may carry
different corrected elevations. A group pair is recorded only when the two
local level sets on a shared cell meet in a set with positive length -- a
non-degenerate continuous curve or an axis-aligned segment, including a whole
cell edge and a public region of positive area. Isolated common points never
form a pair.

The level set of a cell is the zero set of

    f(x, y) = a + b*x + c*y + d*x*y

with ``a`` the south-west corner relative to the level and the other corners
shifted by the same amount. Within the unit square:

* ``a == b == c == d == 0`` is the whole closed cell;
* ``d == 0`` is one affine line;
* ``d != 0`` and ``b*c - a*d == 0`` is a vertical and a horizontal line;
* otherwise it is a hyperbola; each sign of ``d*x + c`` is one monotone branch.

Two distinct irreducible curves can only share a positive-length arc when they
share an irreducible component, so component identity -- written in a canonical
form -- is all this module has to decide. A component is recorded only when its
intersection with the square has positive length; a corner-only touch or an
isolated point contributes nothing.
"""

from fractions import Fraction
from functools import reduce
from math import gcd, lcm


WHOLE = ('whole',)


def coefficients(corners, level: Fraction):
    lower_left, lower_right, upper_left, upper_right = (
        Fraction(value) - Fraction(level) for value in corners
    )
    a = lower_left
    b = lower_right - lower_left
    c = upper_left - lower_left
    d = upper_right - lower_right - upper_left + lower_left
    return a, b, c, d


def _normalize(values) -> tuple[Fraction, ...]:
    denominator = 1
    for value in values:
        denominator = lcm(denominator, value.denominator)
    integers = [int(value * denominator) for value in values]
    divisor = reduce(gcd, (abs(value) for value in integers), 0)
    if divisor == 0:
        return tuple(Fraction(0) for _ in values)
    integers = [value // divisor for value in integers]
    for value in integers:
        if value != 0:
            if value < 0:
                integers = [-item for item in integers]
            break
    return tuple(Fraction(value) for value in integers)


def _line_is_positive(b: Fraction, c: Fraction, a: Fraction) -> bool:
    """Whether the line b*x + c*y + a = 0 meets the square in an arc."""
    if b == 0 and c == 0:
        return False
    if c == 0:
        return 0 <= -a / b <= 1
    if b == 0:
        return 0 <= -a / c <= 1
    points = set()
    for x in (Fraction(0), Fraction(1)):
        y = -(a + b * x) / c
        if 0 <= y <= 1:
            points.add((x, y))
    for y in (Fraction(0), Fraction(1)):
        x = -(a + c * y) / b
        if 0 <= x <= 1:
            points.add((x, y))
    return len(points) >= 2


def _branch_points(piece) -> set:
    points = set()
    for contact in piece:
        points.add(contact.start)
        points.add(contact.end)
    return points


def _branch_is_positive(piece) -> bool:
    for contact in piece:
        if not contact.is_point:
            return True
    return len(_branch_points(piece)) >= 2


def _line_key(b, c, a):
    return ('line',) + _normalize((b, c, a))


def part_components(corners, level: Fraction, part) -> frozenset:
    """Positive-length irreducible components of one clipped cell piece."""
    a, b, c, d = coefficients(corners, level)
    if a == 0 and b == 0 and c == 0 and d == 0:
        return frozenset((WHOLE,))
    if d == 0:
        if b == 0 and c == 0:
            return frozenset()
        return frozenset((_line_key(b, c, a),)) if _line_is_positive(b, c, a) else frozenset()
    if b * c - a * d == 0:
        keys = set()
        if _line_is_positive(d, Fraction(0), c):
            keys.add(_line_key(d, Fraction(0), c))
        if _line_is_positive(Fraction(0), d, b):
            keys.add(_line_key(Fraction(0), d, b))
        return frozenset(keys)
    if not _branch_is_positive(part):
        return frozenset()
    polynomial = _normalize((a, b, c, d))
    canonical_c, canonical_d = polynomial[2], polynomial[3]
    side = canonical_d * part[0].start[0] + canonical_c > 0
    return frozenset((('conic',) + polynomial + (side,),))


def cell_components(corners, level: Fraction, parts) -> frozenset:
    """Union over the pieces of one cell held by a single group."""
    keys = set()
    for part in parts:
        keys |= part_components(corners, level, part)
    return frozenset(keys)


def shares_positive_length(left: frozenset, right: frozenset) -> bool:
    if not left or not right:
        return False
    if WHOLE in left or WHOLE in right:
        return True
    return bool(left & right)
