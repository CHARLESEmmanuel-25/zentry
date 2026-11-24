from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from .types import AppelOutil, Evenement, Message, Risque, SpecOutil

if TYPE_CHECKING:
    from .ports import Approbation, Journal, LLMProvider, Memoire, Outil


class Harness:
    def __init__(
        self,
        llm: LLMProvider,
        prompt_systeme: str,
        outils: Iterable[Outil] = (),
        max_iterations: int = 10,
        approbation: Approbation | None = None,
        memoire: Memoire | None = None,
        journal: Journal | None = None,
    ) -> None:
        self.llm = llm
        self.prompt_systeme = prompt_systeme
        self.outils: list[Outil] = list(outils)
        self._specs: list[SpecOutil] = [outil.spec for outil in self.outils]
        self._outils_par_nom: dict[str, Outil] = {outil.spec.nom: outil for outil in self.outils}
        self.max_iterations = max_iterations
        self.journal = journal
        self.approbation = approbation
        self.memoire = memoire

    def executer(self, texte: str, conversation_id: str = "defaut") -> str:
        self._journaliser("question_recue", conversation_id, texte=texte)
        messages = self._construire_messages(texte, conversation_id)

        for _ in range(self.max_iterations):
            reponse = self.llm.discuter(messages=messages, outils=self._specs)

            messages.append(Message(role="assistant", contenu=reponse.texte, appels=reponse.appels))

            if not reponse.appels:
                self._sauvegarder(conversation_id, messages)
                return reponse.texte

            for appel in reponse.appels:
                resultat = self._traiter_appel(appel)
                messages.append(Message(role="tool", contenu=resultat, nom_outil=appel.nom))

        # Limite atteinte : on garde quand même tout l'échange en mémoire
        self._sauvegarder(conversation_id, messages)
        return (
            f"Je me suis arrêté : limite de {self.max_iterations} tours atteinte "
            "sans réponse finale."
        )

    def _construire_messages(self, texte: str, conversation_id: str) -> list[Message]:
        historique = self.memoire.charger(conversation_id) if self.memoire else []
        messages = [
            Message(role="system", contenu=self.prompt_systeme),
            *historique,
            Message(role="user", contenu=texte),
        ]
        return messages

    def _sauvegarder(self, conversation_id: str, messages: list[Message]) -> None:
        if self.memoire:
            # Le prompt système (toujours en tête) n'est pas sauvegardé :
            # il est recréé à chaque appel par _construire_messages
            sans_prompt_systeme = messages[1:]
            self.memoire.sauvegarder(conversation_id, sans_prompt_systeme)

    def _traiter_appel(self, appel: AppelOutil) -> str:
        """Décide du sort d'un appel d'outil et renvoie le texte à donner au modèle."""
        outil = self._outils_par_nom.get(appel.nom)

        if outil is None:
            disponibles = ", ".join(self._outils_par_nom)
            return (
                f"Erreur : l'outil '{appel.nom}' n'existe pas. "
                f"Outils disponibles : {disponibles}."
            )

        if outil.risque != Risque.LECTURE and not self._est_approuve(appel):
            return f"Action refusée par l'utilisateur : '{appel.nom}' n'a pas été exécuté."

        try:
            return outil.executer(**appel.arguments)
        except Exception as erreur:
            # Une erreur d'outil ne doit jamais faire planter l'agent : on la renvoie au modèle
            return f"Erreur lors de l'exécution de '{appel.nom}' : {erreur}"

    def _journaliser(self, type_evenement: str, conversation_id: str, **donnees: object) -> None:
        if self.journal is not None:
            self.journal.enregistrer(Evenement(type_evenement, conversation_id, donnees))

    def _est_approuve(self, appel: AppelOutil) -> bool:
        # Sûr par défaut : sans système d'approbation, toute action risquée est refusée
        if self.approbation is None:
            return False
        return self.approbation.approuver(appel)