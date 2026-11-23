import unittest
from dataclasses import dataclass, field


# ============================================================
# Code de production (sera déplacé dans src/zentry/ au refactor)
# ============================================================

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


class Harness:
    def __init__(self, llm, prompt_systeme, outils=()):
        self.llm = llm
        self.prompt_systeme = prompt_systeme
        self.outils = list(outils)

    def executer(self, texte):
        messages = [
            Message(role="system", contenu=self.prompt_systeme),
            Message(role="user", contenu=texte),
        ]
        specs = [outil.spec for outil in self.outils]
        outils_par_nom = {outil.spec.nom: outil for outil in self.outils}

        while True:
            reponse = self.llm.discuter(messages=messages, outils=specs)

            if not reponse.appels:
                return reponse.texte

            messages.append(Message(role="assistant", contenu=reponse.texte, appels=reponse.appels))
            for appel in reponse.appels:
                outil = outils_par_nom.get(appel.nom)
                if outil is None:
                    disponibles = ", ".join(outils_par_nom)
                    resultat = (
                        f"Erreur : l'outil '{appel.nom}' n'existe pas. "
                        f"Outils disponibles : {disponibles}."
                    )
                else:
                    try:                                              # ← nouveau
                        resultat = outil.executer(**appel.arguments)
                    except Exception as erreur:                       # ← nouveau
                        resultat = f"Erreur lors de l'exécution de '{appel.nom}' : {erreur}"
                messages.append(Message(role="tool", contenu=resultat, nom_outil=appel.nom))


# ============================================================
# Doublures de test (seront déplacées dans tests/fakes.py au refactor)
# ============================================================

class FakeLLM:
    """Faux modèle : renvoie, dans l'ordre, des réponses écrites à l'avance."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.messages_recus = []          # ce que le harness a envoyé, appel par appel
        self.outils_recus = []            # les outils proposés au modèle, appel par appel

    def discuter(self, messages, outils):
        self.messages_recus.append(list(messages))
        self.outils_recus.append(list(outils))
        if not self.reponses:
            raise AssertionError("FakeLLM : le harness a appelé le modèle plus de fois que prévu")
        return self.reponses.pop(0)


class OutilFactice:
    """Faux outil : il a une description (spec) et renvoie un résultat fixe."""

    def __init__(self, nom, resultat="ok", erreur=None):
        self.spec = SpecOutil(
            nom=nom,
            description=f"Outil factice {nom}",
            parametres={"type": "object", "properties": {}},
        )
        self.resultat = resultat
        self.appels = []     
        self.erreur = erreur             # les arguments reçus à chaque exécution

    def executer(self, **arguments):
        self.appels.append(arguments)
        if self.erreur is not None:
            raise self.erreur
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
        # Arrange
        llm = FakeLLM([ReponseLLM(texte="ok")])
        harness = Harness(llm=llm, prompt_systeme="Tu es un pirate.")

        # Act
        harness.executer("Salut")

        # Assert : le modèle a reçu exactement ces deux messages, dans cet ordre
        self.assertEqual(
            llm.messages_recus[0],
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
        self.assertEqual(llm.outils_recus[0], [heure.spec, meteo.spec])

    def test_execute_l_outil_demande_par_le_modele_avec_ses_arguments(self):
        # Arrange
        heure = OutilFactice("heure")
        meteo = OutilFactice("meteo")
        llm = FakeLLM([
            ReponseLLM(appels=[AppelOutil(nom="meteo", arguments={"ville": "Paris"})]),
            ReponseLLM(texte="Il fait beau à Paris."),
        ])
        harness = Harness(llm=llm, prompt_systeme="Tu es utile.", outils=[heure, meteo])

        # Act
        harness.executer("Quel temps fait-il à Paris ?")

        # Assert : seul l'outil demandé a été exécuté, avec les bons arguments
        self.assertEqual(meteo.appels, [{"ville": "Paris"}])
        self.assertEqual(heure.appels, [])

    def test_renvoie_le_resultat_de_l_outil_au_modele_puis_sa_reponse_finale(self):
        # Arrange
        meteo = OutilFactice("meteo", resultat="Ensoleillé, 18°C")
        appel = AppelOutil(nom="meteo", arguments={"ville": "Paris"})
        llm = FakeLLM([
            ReponseLLM(appels=[appel]),
            ReponseLLM(texte="Il fait beau à Paris : 18°C."),
        ])
        harness = Harness(llm=llm, prompt_systeme="Tu es utile.", outils=[meteo])

        # Act
        reponse = harness.executer("Quel temps fait-il à Paris ?")

        # Assert 1 : le harness renvoie la réponse FINALE du modèle
        self.assertEqual(reponse, "Il fait beau à Paris : 18°C.")

        # Assert 2 : au 2e appel, le modèle a reçu sa demande d'outil puis le résultat
        self.assertEqual(
            llm.messages_recus[1],
            [
                Message(role="system", contenu="Tu es utile."),
                Message(role="user", contenu="Quel temps fait-il à Paris ?"),
                Message(role="assistant", contenu="", appels=[appel]),
                Message(role="tool", contenu="Ensoleillé, 18°C", nom_outil="meteo"),
            ],
        )
class TestHarnessGardeFous(unittest.TestCase):

    def test_un_outil_inconnu_renvoie_une_erreur_au_modele_sans_planter(self):
        # Arrange : le modèle demande un outil qui n'existe pas
        meteo = OutilFactice("meteo")
        llm = FakeLLM([
            ReponseLLM(appels=[AppelOutil(nom="teleporter", arguments={})]),
            ReponseLLM(texte="Désolé, je ne peux pas faire ça."),
        ])
        harness = Harness(llm=llm, prompt_systeme="Tu es utile.", outils=[meteo])

        # Act
        reponse = harness.executer("Téléporte-moi à Paris")

        # Assert 1 : pas de plantage, le modèle a pu donner sa réponse finale
        self.assertEqual(reponse, "Désolé, je ne peux pas faire ça.")

        # Assert 2 : le modèle a reçu un message d'erreur pour cet outil
        message_outil = llm.messages_recus[1][-1]
        self.assertEqual(message_outil.role, "tool")
        self.assertEqual(message_outil.nom_outil, "teleporter")
        self.assertIn("erreur", message_outil.contenu.lower())
        self.assertIn("teleporter", message_outil.contenu)

    def test_l_erreur_d_outil_inconnu_liste_les_outils_disponibles(self):
            # Arrange
            heure = OutilFactice("heure")
            meteo = OutilFactice("meteo")
            llm = FakeLLM([
                ReponseLLM(appels=[AppelOutil(nom="meteoo", arguments={})]),
                ReponseLLM(texte="ok"),
            ])
            harness = Harness(llm=llm, prompt_systeme="Tu es utile.", outils=[heure, meteo])

            # Act
            harness.executer("Quel temps fait-il ?")

            # Assert : le message d'erreur cite chaque outil disponible
            message_outil = llm.messages_recus[1][-1]
            self.assertIn("heure", message_outil.contenu)
            self.assertIn("meteo", message_outil.contenu)

    def test_un_outil_qui_leve_une_exception_renvoie_l_erreur_au_modele(self):
            # Arrange : l'outil météo plante (API hors service)
            meteo = OutilFactice("meteo", erreur=ConnectionError("API météo injoignable"))
            llm = FakeLLM([
                ReponseLLM(appels=[AppelOutil(nom="meteo", arguments={"ville": "Paris"})]),
                ReponseLLM(texte="Le service météo est indisponible, réessaie plus tard."),
            ])
            harness = Harness(llm=llm, prompt_systeme="Tu es utile.", outils=[meteo])

            # Act
            reponse = harness.executer("Quel temps fait-il à Paris ?")

            # Assert 1 : pas de plantage, le modèle a pu répondre
            self.assertEqual(reponse, "Le service météo est indisponible, réessaie plus tard.")

            # Assert 2 : le modèle a reçu l'erreur, avec son explication
            message_outil = llm.messages_recus[1][-1]
            self.assertEqual(message_outil.role, "tool")
            self.assertEqual(message_outil.nom_outil, "meteo")
            self.assertIn("erreur", message_outil.contenu.lower())
            self.assertIn("API météo injoignable", message_outil.contenu)


if __name__ == "__main__":
    unittest.main()