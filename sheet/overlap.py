"""Version 2 overlap packets and their exact per-cell evidence.

The evidence is a self-describing snapshot of every original cell in a sheet's
coverage. It stores the four bilinear corner elevations of each cell and the
V1 decomposition (part numbering and unit-square boundary contacts) derived
from those corners and the survey level. A reviewer can therefore recompute
the complete level set of every cell -- including empty, boundary and
degenerate cells -- and can rebuild the V1 local pieces exactly, using only
the stored survey geometry.
"""

from dataclasses import dataclass
from fractions import Fraction
import json

from grid.rationals import from_rational_pair, to_rational_pair
from sheet.cell_topology import classify_cell
from sheet.edge_contacts import BoundaryContact, Point, contact_sort_key
from survey.layout import CellRange


def _decode_pair(data: object, description: str) -> Fraction:
    try:
        return from_rational_pair(data)
    except ValueError as error:
        raise ValueError(f'invalid rational in {description}') from error


def _decode_point(data: object, description: str) -> Point:
    if not isinstance(data, list) or len(data) != 2:
        raise ValueError(f'{description} needs X and Y values')
    return _decode_pair(data[0], description), _decode_pair(data[1], description)


def _decode_contact(data: object) -> BoundaryContact:
    if not isinstance(data, dict) or data.keys() != {'start', 'end'}:
        raise ValueError('invalid evidence contact fields')
    try:
        return BoundaryContact(
            _decode_point(data['start'], 'contact'),
            _decode_point(data['end'], 'contact'),
        )
    except ValueError as error:
        raise ValueError('invalid evidence contact') from error


@dataclass(frozen=True)
class CellRecord:
    """Exact bilinear data and V1 pieces for one original cell."""

    row: int
    column: int
    corners: tuple[Fraction, Fraction, Fraction, Fraction]
    parts: tuple[tuple[BoundaryContact, ...], ...]

    @property
    def cell(self) -> tuple[int, int]:
        return self.row, self.column


@dataclass(frozen=True)
class OverlapEvidence:
    cells: tuple[CellRecord, ...]

    def records(self) -> dict[tuple[int, int], CellRecord]:
        return {record.cell: record for record in self.cells}


def _classify(corners: tuple[Fraction, Fraction, Fraction, Fraction], level: Fraction):
    return classify_cell(corners, level)


def build_overlap_evidence(
    samples, geometry, level: Fraction, coverage: CellRange,
) -> OverlapEvidence:
    records = []
    for row, column in coverage.cells():
        corners = samples.cell_corners(row, column)
        parts = _classify(corners, level)
        records.append(CellRecord(row, column, corners, parts))
    return OverlapEvidence(tuple(records))


def _encode_contact(contact: BoundaryContact) -> dict:
    return {
        'start': [to_rational_pair(value) for value in contact.start],
        'end': [to_rational_pair(value) for value in contact.end],
    }


def encode_evidence(evidence: OverlapEvidence) -> list:
    payload = []
    for record in sorted(evidence.cells, key=lambda item: (item.row, item.column)):
        payload.append({
            'cell': [record.row, record.column],
            'corners': [to_rational_pair(value) for value in record.corners],
            'parts': [
                [_encode_contact(contact) for contact in part]
                for part in record.parts
            ],
        })
    return payload


def _decode_index(value: object, description: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f'{description} must be a nonnegative integer')
    return value


def decode_evidence(data: object, coverage: CellRange) -> OverlapEvidence:
    if not isinstance(data, list):
        raise ValueError('evidence must be a list of cell records')
    records = []
    seen = set()
    for entry in data:
        if not isinstance(entry, dict) or entry.keys() != {'cell', 'corners', 'parts'}:
            raise ValueError('invalid evidence cell fields')
        cell = entry['cell']
        if not isinstance(cell, list) or len(cell) != 2:
            raise ValueError('an evidence cell needs a row and column')
        row = _decode_index(cell[0], 'evidence row')
        column = _decode_index(cell[1], 'evidence column')
        if not coverage.contains(row, column):
            raise ValueError(f'evidence cell outside coverage: {(row, column)}')
        if (row, column) in seen:
            raise ValueError(f'duplicate evidence cell: {(row, column)}')
        seen.add((row, column))
        raw_corners = entry['corners']
        if not isinstance(raw_corners, list) or len(raw_corners) != 4:
            raise ValueError('an evidence cell needs four corner elevations')
        corners = tuple(_decode_pair(value, 'corner') for value in raw_corners)
        raw_parts = entry['parts']
        if not isinstance(raw_parts, list):
            raise ValueError('an evidence cell needs a list of parts')
        parts = []
        for raw_part in raw_parts:
            if not isinstance(raw_part, list) or not raw_part:
                raise ValueError('an evidence part needs at least one contact')
            parts.append(tuple(sorted(
                (_decode_contact(contact) for contact in raw_part), key=contact_sort_key,
            )))
        records.append(CellRecord(row, column, corners, tuple(parts)))
    expected = set(coverage.cells())
    if seen != expected:
        raise ValueError('evidence does not describe every cell in coverage')
    return OverlapEvidence(tuple(sorted(records, key=lambda item: item.cell)))


def verify_evidence(
    evidence: OverlapEvidence, level: Fraction, coverage: CellRange,
) -> None:
    """Recompute every cell's complete level set and compare with stored parts."""
    if set(record.cell for record in evidence.cells) != set(coverage.cells()):
        raise ValueError('evidence does not describe every cell in coverage')
    for record in sorted(evidence.cells, key=lambda item: item.cell):
        recomputed = _classify(record.corners, level)
        if recomputed != record.parts:
            raise ValueError(f'evidence cannot be explained at cell {record.cell}')


def v1_components(evidence: OverlapEvidence, geometry) -> tuple:
    from sheet.packet import CellComponent

    components = []
    for record in sorted(evidence.cells, key=lambda item: item.cell):
        bounds = geometry.cell_bounds(record.row, record.column)
        for part, piece in enumerate(record.parts):
            components.append(CellComponent(
                record.row, record.column, part, _place_piece(piece, bounds),
            ))
    return tuple(components)


def _place_piece(piece, bounds):
    left, bottom, right, top = bounds
    width, height = right - left, top - bottom

    def place(point: Point) -> Point:
        x, y = point
        return left + x * width, bottom + y * height

    return tuple(BoundaryContact(place(contact.start), place(contact.end)) for contact in piece)


@dataclass(frozen=True)
class OverlapPacket:
    survey_id: str
    revision_id: str
    sheet_id: str
    packet_id: str
    coverage: CellRange
    evidence: OverlapEvidence


def encode_overlap_packet(packet: OverlapPacket) -> str:
    payload = {
        'version': 2,
        'survey_id': packet.survey_id,
        'revision_id': packet.revision_id,
        'sheet_id': packet.sheet_id,
        'packet_id': packet.packet_id,
        'coverage': packet.coverage.coordinates,
        'evidence': encode_evidence(packet.evidence),
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('V2 identity fields must be nonempty text')
    return value


def decode_overlap_packet(raw: str) -> OverlapPacket:
    if not isinstance(raw, str):
        raise ValueError('a packet must be JSON text')
    fields = json.loads(raw)
    expected = {'version', 'survey_id', 'revision_id', 'sheet_id', 'packet_id', 'coverage', 'evidence'}
    if not isinstance(fields, dict) or fields.keys() != expected:
        raise ValueError('invalid V2 packet fields')
    if type(fields['version']) is not int or fields['version'] != 2:
        raise ValueError('not a V2 packet')
    coverage = CellRange.from_bounds(fields['coverage'])
    evidence = decode_evidence(fields['evidence'], coverage)
    return OverlapPacket(
        _identifier(fields['survey_id']), _identifier(fields['revision_id']),
        _identifier(fields['sheet_id']), _identifier(fields['packet_id']),
        coverage, evidence,
    )
