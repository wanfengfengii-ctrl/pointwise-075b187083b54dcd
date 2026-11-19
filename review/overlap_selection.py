"""Validation of one side of a version 2 overlap review."""

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from grid.geometry import GridGeometry
from review.contacts import contacts_intersect
from sheet.edge_contacts import BoundaryContact
from sheet.overlap import (
    OverlapPacket, decode_overlap_packet, v1_components, verify_evidence,
)
from sheet.packet import CellComponent
from survey.catalog import SurveyOrder
from survey.selection import resolve_selected_sheets


@dataclass(frozen=True)
class OverlapSide:
    survey_id: str
    level: Fraction
    adopted: tuple[tuple[str, str], ...]
    components: tuple[CellComponent, ...]
    records: dict  # cell -> CellRecord (exact corners plus V1 pieces)


def _lies_on_cell_boundary(contact: BoundaryContact, bounds: tuple) -> bool:
    left, bottom, right, top = bounds
    x0, y0 = contact.start
    x1, y1 = contact.end
    if not (left <= x0 <= x1 <= right and bottom <= y0 <= y1 <= top):
        return False
    return x0 == x1 in (left, right) or y0 == y1 in (bottom, top)


def _validate_geometry(packet: OverlapPacket, geometry: GridGeometry) -> None:
    earlier: dict[tuple[int, int], list[BoundaryContact]] = {}
    for component in v1_components(packet.evidence, geometry):
        bounds = geometry.cell_bounds(*component.cell)
        prior = earlier.setdefault(component.cell, [])
        for contact in component.contacts:
            if not _lies_on_cell_boundary(contact, bounds):
                raise ValueError(f'contact outside cell boundary: {component.identity}')
            if any(contacts_intersect(contact, other) for other in prior):
                raise ValueError(f'distinct pieces touch inside cell {component.cell}')
        prior.extend(component.contacts)


def validate_overlap_side(
    surveys, survey_id, sheet_ids: Iterable[str], packets: Iterable[str],
) -> OverlapSide:
    order = surveys.read(survey_id)
    selected = dict(resolve_selected_sheets(order, sheet_ids))
    if isinstance(packets, (str, bytes)) or not isinstance(packets, Iterable):
        raise ValueError('packets must be an iterable of V2 documents')
    supplied = {}
    packet_ids = set()
    for raw in packets:
        packet = decode_overlap_packet(raw)
        if packet.survey_id != order.survey_id:
            raise ValueError(f'packet {packet.packet_id!r} belongs to a different survey')
        if packet.revision_id != order.revision_id:
            raise ValueError(f'packet {packet.packet_id!r} is bound to a different revision')
        if packet.sheet_id not in selected:
            raise ValueError(f'packet supplied for an unselected sheet: {packet.sheet_id!r}')
        if packet.sheet_id in supplied or packet.packet_id in packet_ids:
            raise ValueError(f'duplicate packet for sheet {packet.sheet_id!r}')
        if packet.coverage != selected[packet.sheet_id]:
            raise ValueError(f'packet coverage differs from survey for {packet.sheet_id!r}')
        verify_evidence(packet.evidence, order.level, packet.coverage)
        _validate_geometry(packet, order.geometry)
        supplied[packet.sheet_id] = packet
        packet_ids.add(packet.packet_id)
    missing = selected.keys() - supplied.keys()
    if missing:
        raise ValueError(f'missing selected packets: {sorted(missing)}')
    components = tuple(
        component
        for sheet_id in selected
        for component in v1_components(supplied[sheet_id].evidence, order.geometry)
    )
    shapes = {}
    for sheet_id in selected:
        for record in supplied[sheet_id].evidence.cells:
            shapes[record.cell] = record
    return OverlapSide(
        order.survey_id,
        Fraction(order.level),
        tuple((sheet_id, supplied[sheet_id].packet_id) for sheet_id in selected),
        components,
        shapes,
    )


def selected_cells(order: SurveyOrder, sheet_ids: Iterable[str]) -> frozenset:
    return frozenset(
        cell for _, area in resolve_selected_sheets(order, sheet_ids) for cell in area.cells()
    )


def geometry_signature(order: SurveyOrder) -> tuple:
    return (
        order.geometry.origin_x, order.geometry.origin_y,
        order.geometry.step_x, order.geometry.step_y,
        Fraction(order.level),
    )
