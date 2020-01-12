from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AorBorBothType:
    """
    :ivar a:
    :ivar b:
    :ivar b:
    """
    class Meta:
        name = "AOrBOrBothType"

    a: Optional[str] = field(
        default=None,
        metadata=dict(
            name="a",
            type="Element",
            required=True
        )
    )
    b: Optional[str] = field(
        default=None,
        metadata=dict(
            name="b",
            type="Element"
        )
    )
    b: Optional[str] = field(
        default=None,
        metadata=dict(
            name="b",
            type="Element"
        )
    )
