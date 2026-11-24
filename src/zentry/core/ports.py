from typing import Protocol, runtime_checkable

from .types import AppelOutil, Evenement, Message, ReponseLLM, Risque, SpecOutil


@runtime_checkable
class LLMProvider(Protocol):
    """Un modèle de langage : reçoit la conversation, renvoie une réponse."""

    def discuter(self, messages: list[Message], outils: list[SpecOutil]) -> ReponseLLM: ...


@runtime_checkable
class Outil(Protocol):
    """Une action que l'agent peut déclencher."""

    spec: SpecOutil
    risque: Risque

    def executer(self, **arguments) -> str: ...


@runtime_checkable
class Memoire(Protocol):
    """Stocke l'historique des conversations."""

    def charger(self, conversation_id: str) -> list[Message]: ...

    def sauvegarder(self, conversation_id: str, messages: list[Message]) -> None: ...


@runtime_checkable
class Approbation(Protocol):
    """Demande à l'utilisateur s'il autorise une action risquée."""

    def approuver(self, appel: AppelOutil) -> bool: ...


@runtime_checkable
class Journal(Protocol):
    """Enregistre ce qui se passe pendant l'exécution."""

    def enregistrer(self, evenement: Evenement) -> None: ...