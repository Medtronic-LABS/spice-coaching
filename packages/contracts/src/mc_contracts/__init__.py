"""mc_contracts — shared enums, API schemas, and internal service contracts.

Allowed: Pydantic models, enums, constants.
Not allowed: SQLAlchemy, repositories, business logic, provider clients.
"""

from mc_contracts.modules import (
    CardMediaAnchor,
    CardMediaItem,
    ModuleAttachmentFileRef,
    ModuleAttachmentKind,
    ModuleAttachmentRef,
    ModuleAttachmentYoutubeRef,
    ModuleMediaKind,
)

__all__ = [
    "CardMediaAnchor",
    "CardMediaItem",
    "ModuleAttachmentFileRef",
    "ModuleAttachmentKind",
    "ModuleAttachmentRef",
    "ModuleAttachmentYoutubeRef",
    "ModuleMediaKind",
]
