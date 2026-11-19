"""Issue a version 2 overlap review across two corrected surveys."""

from collections.abc import Callable

from ledger.issue import commit_overlap_review
from review.contacts import iter_contact_links
from review.groups import build_groups
from review.overlap_selection import (
    OverlapSide, geometry_signature, selected_cells, validate_overlap_side,
)
from sheet.overlap_geometry import cell_components, shares_positive_length
from survey.catalog import SurveyCatalog


def _side(surveys: SurveyCatalog, spec) -> OverlapSide:
    if not isinstance(spec, (tuple, list)) or len(spec) != 3:
        raise ValueError('each side needs (survey_id, sheet_ids, packets)')
    survey_id, sheet_ids, packets = spec
    return validate_overlap_side(surveys, survey_id, sheet_ids, packets)


def _group_components(side: OverlapSide):
    """Groups plus, per group, the positive-length keys per cell it owns."""
    groups = build_groups(side.components, iter_contact_links(side.components))
    keys_per_group = []
    for group in groups:
        by_cell: dict[tuple[int, int], list] = {}
        for component in group:
            record = side.records[component.cell]
            by_cell.setdefault(component.cell, []).append(record.parts[component.part])
        keys_per_group.append({
            cell: cell_components(side.records[cell].corners, side.level, parts)
            for cell, parts in by_cell.items()
        })
    return groups, keys_per_group


def issue_overlap_review(
    surveys: SurveyCatalog,
    reports,
    old,
    new,
    *,
    before_commit: Callable[[], None] | None = None,
):
    old_side = _side(surveys, old)
    new_side = _side(surveys, new)
    old_order = surveys.read(old_side.survey_id)
    new_order = surveys.read(new_side.survey_id)
    if geometry_signature(old_order) != geometry_signature(new_order):
        raise ValueError('the two surveys use different origin, spacing or level')
    if selected_cells(old_order, [name for name, _ in old_side.adopted]) != selected_cells(
        new_order, [name for name, _ in new_side.adopted]
    ):
        raise ValueError('the two selections cover different original cells')

    old_groups, old_keys = _group_components(old_side)
    new_groups, new_keys = _group_components(new_side)
    pairs = sorted(
        (old_index, new_index)
        for old_index, old_cells in enumerate(old_keys)
        for new_index, new_cells in enumerate(new_keys)
        if _paired(old_cells, new_cells)
    )
    return commit_overlap_review(
        reports, old_side, new_side, old_groups, new_groups, tuple(pairs),
        before_commit=before_commit,
    )


def _paired(old_cells, new_cells) -> bool:
    for cell in old_cells.keys() & new_cells.keys():
        if shares_positive_length(old_cells[cell], new_cells[cell]):
            return True
    return False
