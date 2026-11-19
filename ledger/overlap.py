"""Persisted version 2 overlap reports."""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from ledger.report import FrozenReport, decode_report, encode_report
from sheet.packet import CellComponent


@dataclass(frozen=True)
class OverlapReport:
    old: FrozenReport
    new: FrozenReport
    pairs: tuple[tuple[int, int], ...]


def freeze_overlap_report(
    old_side,
    new_side,
    old_groups: Iterable[Iterable[CellComponent]],
    new_groups: Iterable[Iterable[CellComponent]],
    pairs: Iterable[tuple[int, int]],
) -> OverlapReport:
    old = FrozenReport(old_side.survey_id, tuple(sorted(old_side.adopted)),
                       tuple(tuple(g) for g in old_groups))
    new = FrozenReport(new_side.survey_id, tuple(sorted(new_side.adopted)),
                       tuple(tuple(g) for g in new_groups))
    return OverlapReport(old, new, tuple(sorted(set(pairs))))


def encode_overlap_report(report: OverlapReport) -> str:
    return json.dumps({
        'version': 2,
        'old': json.loads(encode_report(report.old)),
        'new': json.loads(encode_report(report.new)),
        'pairs': [list(pair) for pair in report.pairs],
    }, sort_keys=True, separators=(',', ':'))


def decode_overlap_report(raw: str) -> OverlapReport:
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get('version') != 2:
        raise ValueError('not a version 2 overlap report')
    old = decode_report(json.dumps(payload['old']))
    new = decode_report(json.dumps(payload['new']))
    pairs = tuple((int(left), int(right)) for left, right in payload['pairs'])
    return OverlapReport(old, new, pairs)
