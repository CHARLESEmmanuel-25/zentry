import unittest
from dataclasses import dataclass


# ============================================================
# Code de production (sera déplacé dans src/zentry/ au refactor)
# ============================================================

@dataclass
class ReponseLLM:
    texte: str

@dataclass
class Message:
    role: str
    contenu: str

@dataclass
class SpecOutil:
    nom: str
    description: str
    parametres: dict


class Harness:
    def __init__(self, llm, prompt_systeme, outils=()):
        self.llm = llm
        self.prompt_systeme = prompt_systeme
        self.outils = list(outils)

    def executer(self, texte):
        messages = [
            Message(role="system", contenu=self.prompt_systeme),
            Message(role="user", contenu=texte)
        ]
        specs = [outil.spec for outil in self.outils]
        reponse = self.llm.discuter(messages=messages, outils=specs)
        return reponse.texte


# ============================================================
# Doublure de test (sera déplacée dans tests/fakes.py au refactor)
# ============================================================

class FakeLLM:
    """Faux modèle : renvoie, dans l'ordre, des réponses écrites à l'avance."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.messages_reçus = []
        self.outils_reçus = []

    def discuter(self, messages, outils):
        self.messages_reçus.append(list(messages))
        self.outils_reçus.append(list(outils))
        return self.reponses.pop(0)

class OutilFactice:
    """Faux outil : il a une description (spec) et renvoie un résultat fixe."""

    def __init__(self, nom, resultat="ok"):
        self.spec = SpecOutil(
            nom=nom,
            description=f"Outil factice {nom}",
            parametres={"type": "object", "properties": {}},
        )
        self.resultat = resultat

    def executer(self, **arguments):
        return self.resultat


# ============================================================
# Tests
# ============================================================

class TestHarnessSansOutil(unittest.TestCase):

    def test_renvoie_le_texte_du_modele_quand_aucun_outil_nest_demande(self):
        # Arrange
        llm = FakeLLM([ReponseLLM(texte="Bonjour Manu !")])
        harness = Harness(llm=llm, prompt_systeme="Tu es un assistant utile.")

        # Act
        reponse = harness.executer("Salut")

        # Assert
        self.assertEqual(reponse, "Bonjour Manu !")

    def test_envoie_le_prompt_systeme_puis_la_question_au_modele(self):

        llm = FakeLLM([ReponseLLM(texte="ok")])
        harness = Harness(llm=llm, prompt_systeme="Tu es un pirate.")

        # Act
        harness.executer("Salut")

       
        self.assertEqual(
            llm.messages_reçus[0],
            [
                Message(role="system", contenu="Tu es un pirate."),
                Message(role="user", contenu="Salut"),
            ],
        )

class TestHarnessAvecOutils(unittest.TestCase):

    def test_envoie_la_description_des_outils_au_modele(self):
        # Arrange
        heure = OutilFactice("heure")
        meteo = OutilFactice("meteo")
        llm = FakeLLM([ReponseLLM(texte="ok")])
        harness = Harness(llm=llm, prompt_systeme="Tu es utile.", outils=[heure, meteo])

        # Act
        harness.executer("Quelle heure est-il ?")

        # Assert : le modèle a reçu la spec de chaque outil, dans l'ordre
        self.assertEqual(llm.outils_reçus[0], [heure.spec, meteo.spec])

if __name__ == "__main__":
    unittest.main()