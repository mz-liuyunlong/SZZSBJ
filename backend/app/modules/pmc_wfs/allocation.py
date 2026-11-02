"""Deterministic whole-box allocation, preserving mixed cases and tail quantities."""

from decimal import Decimal

from app.core.api import ApiError
from app.modules.pmc_domestic.packing_rules import fingerprint
from app.modules.pmc_wfs.creation_schemas import (
    AllocationPreview,
    AllocationTicket,
    BoxRange,
)


def allocate(command, sources, occupied):
    boxes = []
    for order, box_set in sorted(sources, key=lambda source: source[0].pk):
        if not box_set.completed_at:
            raise ApiError(code="WFS_PACKING_NOT_COMPLETED", status_code=409)
        if sum(line.boxes * line.units_per_box for line in box_set.lines) != box_set.total_qty:
            raise ApiError(code="WFS_PACKING_TOTAL_MISMATCH", status_code=409)
        boxes.extend(
            (order, box_set.version, line, ordinal)
            for line in sorted(box_set.lines, key=lambda line: line.line_no)
            for ordinal in range(1, line.boxes + 1)
            if (line.id, ordinal) not in occupied
        )
    if command.shipping_boxes > len(boxes):
        raise ApiError(code="WFS_INSUFFICIENT_BOXES", status_code=409)
    cursor, tickets = 0, []
    for number, count in enumerate(command.shipment_boxes, 1):
        ranges = []
        for order, version, line, ordinal in boxes[cursor : cursor + count]:
            if ranges and ranges[-1].line_id == line.id and ranges[-1].end + 1 == ordinal:
                r = ranges[-1]
                r.end, r.boxes, r.units = ordinal, r.boxes + 1, r.units + line.units_per_box
            else:
                ranges.append(
                    BoxRange(
                        order_id=order.id,
                        pk=order.pk,
                        sku=order.sku,
                        box_version=version,
                        line_id=line.id,
                        line_no=line.line_no,
                        start=ordinal,
                        end=ordinal,
                        boxes=1,
                        units_per_box=line.units_per_box,
                        units=line.units_per_box,
                        length_cm=format(Decimal(str(line.length_cm)).normalize(), "f"),
                        width_cm=format(Decimal(str(line.width_cm)).normalize(), "f"),
                        height_cm=format(Decimal(str(line.height_cm)).normalize(), "f"),
                        gross_weight_kg=format(Decimal(str(line.gross_weight_kg)).normalize(), "f"),
                    )
                )
        tickets.append(
            AllocationTicket(
                number=number,
                boxes=count,
                units=sum(r.units for r in ranges),
                ranges=ranges,
            )
        )
        cursor += count
    data = dict(
        order_id=command.order_id,
        order_version=command.expected_version,
        box_version=command.expected_box_version,
        selections=[
            dict(order_id=o.id, expected_version=o.version, expected_box_version=b.version)
            for o, b in sorted(sources, key=lambda source: str(source[0].id))
        ],
        available_boxes=len(boxes),
        remaining_boxes=len(boxes) - cursor,
        tickets=tickets,
    )
    result = AllocationPreview(**data, preview_hash="")
    result.preview_hash = fingerprint(result.model_dump(mode="json", exclude={"preview_hash"}))
    return result
