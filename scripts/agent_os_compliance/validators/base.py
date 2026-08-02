from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ComplianceContext, Finding


class Validator(ABC):
    name = "validator"

    @abstractmethod
    def validate(self, context: ComplianceContext) -> list[Finding]:
        raise NotImplementedError
