
from dataclasses import dataclass, field
from enum import Enum


@dataclass
class Evenement:
    type: str
    conversation_id: str
    donnees: dict = field(default_factory=dict)
class Risque(Enum):
    LECTURE = "lecture"       # sans danger : s'exécute directement
    ECRITURE = "ecriture"     # modifie quelque chose : demande une confirmation
    SENSIBLE = "sensible"     # argent, envoi de messages... : confirmation obligatoire


@dataclass
class AppelOutil:
    nom: str
    arguments: dict


@dataclass
class Message:
    role: str
    contenu: str
    appels: list[AppelOutil] = field(default_factory=list)
    nom_outil: str | None = None


@dataclass
class ReponseLLM:
    texte: str = ""
    appels: list[AppelOutil] = field(default_factory=list)


@dataclass
class SpecOutil:
    nom: str
    description: str
    parametres: dict

