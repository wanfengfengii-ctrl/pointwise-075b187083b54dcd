from fractions import Fraction

from sheet.edge_contacts import BoundaryContact, contact_sort_key, edge_zero_set


_ZERO = Fraction(0)
_ONE = Fraction(1)
_VERTICES = ((_ZERO, _ZERO), (_ONE, _ZERO), (_ZERO, _ONE), (_ONE, _ONE))
_EDGES = ((0, 1), (0, 2), (1, 3), (2, 3))


LocalPieces = tuple[tuple[BoundaryContact, ...], ...]


def boundary_contacts(values: tuple[Fraction, ...]) -> tuple[BoundaryContact, ...]:
    contacts = set()
    for first, last in _EDGES:
        contact = edge_zero_set(_VERTICES[first], _VERTICES[last], values[first], values[last])
        if contact is not None:
            contacts.add(contact)
    spans = tuple(contact for contact in contacts if not contact.is_point)
    distinct = (
        contact for contact in contacts
        if not contact.is_point or not any(span.contains_point(contact.start) for span in spans)
    )
    return tuple(sorted(distinct, key=contact_sort_key))


def classify_cell(
    corners: tuple[Fraction, Fraction, Fraction, Fraction], level: Fraction,
) -> LocalPieces:
    """Return the boundary contacts of each connected piece in the unit square."""
    values = tuple(Fraction(value) - Fraction(level) for value in corners)
    lower_left, lower_right, upper_left, upper_right = values
    contacts = boundary_contacts(values)
    if not contacts:
        return ()

    a = lower_left
    b = lower_right - a
    c = upper_left - a
    d = upper_right - lower_right - upper_left + a
    if d == 0 or b * c == a * d:
        # An affine zero set is convex. In the factored case the zero set is
        # a vertical and a horizontal line, which meet if both enter the cell.
        return (contacts,)

    # The zero set satisfies (d*x+c)*(d*y+b) = b*c-a*d. Each sign of
    # d*x+c gives a monotone graph whose intersection with the square is
    # connected. Its boundary contacts therefore identify that entire piece.
    branches: dict[bool, list[BoundaryContact]] = {}
    for contact in contacts:
        x, _ = contact.start
        positive = d * x + c > 0
        branches.setdefault(positive, []).append(contact)
    pieces = (tuple(branch) for branch in branches.values())
    return tuple(sorted(pieces, key=lambda piece: tuple(map(contact_sort_key, piece))))
