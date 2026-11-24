import unittest

from zentry.core.harness import Harness
from zentry.core.types import AppelOutil, Evenement, Message, ReponseLLM, Risque, SpecOutil

# ============================================================
# Doublures de test (seront déplacées dans tests/fakes.py au refactor)
# ============================================================
class JournalFactice:
    """Faux journal : garde les événements en mémoire pour pouvoir les vérifier."""

    def __init__(self):
        self.evenements = []

    def enregistrer(self, evenement):
        self.evenements.append(evenement)
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

    def __init__(self, nom, resultat="ok", erreur=None, risque=Risque.LECTURE):
        self.spec = SpecOutil(
            nom=nom,
            description=f"Outil factice {nom}",
            parametres={"type": "object", "properties": {}},
        )
        self.resultat = resultat
        self.erreur = erreur              # si fournie, l'outil lève cette exception
        self.risque = risque
        self.appels = []                  # les arguments reçus à chaque exécution

    def executer(self, **arguments):
        self.appels.append(arguments)
        if self.erreur is not None:
            raise self.erreur
        return self.resultat


class ApprobationFixe:
    """Fausse approbation : répond toujours la même chose et note les demandes."""

    def __init__(self, reponse):
        self.reponse = reponse
        self.demandes = []                # les appels pour lesquels on a demandé l'accord

    def approuver(self, appel):
        self.demandes.append(appel)
        return self.reponse


class MemoireFactice:
    """Fausse mémoire : un simple dictionnaire en RAM, une liste de messages par conversation."""

    def __init__(self):
        self.conversations = {}

    def charger(self, conversation_id):
        return list(self.conversations.get(conversation_id, []))

    def sauvegarder(self, conversation_id, messages):
        self.conversations[conversation_id] = list(messages)


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

    def test_s_arrete_apres_le_nombre_maximum_de_tours(self):
        # Arrange : un modèle qui demande l'outil en boucle, sans jamais conclure
        heure = OutilFactice("heure")
        demande = ReponseLLM(appels=[AppelOutil(nom="heure", arguments={})])
        llm = FakeLLM([demande] * 10)
        harness = Harness(llm=llm, prompt_systeme="Tu es utile.", outils=[heure], max_iterations=3)

        # Act
        reponse = harness.executer("Quelle heure est-il ?")

        # Assert 1 : le modèle n'a été appelé que 3 fois
        self.assertEqual(len(llm.messages_recus), 3)

        # Assert 2 : le harness explique pourquoi il s'est arrêté
        self.assertIn("limite", reponse.lower())


class TestHarnessApprobation(unittest.TestCase):

    def test_un_outil_en_ecriture_demande_une_confirmation_avant_de_s_executer(self):
        # Arrange
        ajouter_note = OutilFactice("ajouter_note", resultat="Note ajoutée", risque=Risque.ECRITURE)
        appel = AppelOutil(nom="ajouter_note", arguments={"texte": "wifi BX-4471"})
        llm = FakeLLM([ReponseLLM(appels=[appel]), ReponseLLM(texte="C'est noté.")])
        approbation = ApprobationFixe(True)
        harness = Harness(
            llm=llm, prompt_systeme="Tu es utile.", outils=[ajouter_note], approbation=approbation
        )

        # Act
        harness.executer("Note le code wifi BX-4471")

        # Assert 1 : on a demandé la confirmation pour cet appel précis
        self.assertEqual(approbation.demandes, [appel])

        # Assert 2 : confirmation accordée, donc l'outil a été exécuté
        self.assertEqual(ajouter_note.appels, [{"texte": "wifi BX-4471"}])

    def test_si_la_confirmation_est_refusee_l_outil_ne_s_execute_pas_et_le_modele_est_informe(self):
        # Arrange
        supprimer = OutilFactice("supprimer_notes", risque=Risque.ECRITURE)
        llm = FakeLLM([
            ReponseLLM(appels=[AppelOutil(nom="supprimer_notes", arguments={})]),
            ReponseLLM(texte="D'accord, je ne supprime rien."),
        ])
        harness = Harness(
            llm=llm, prompt_systeme="Tu es utile.", outils=[supprimer],
            approbation=ApprobationFixe(False),
        )

        # Act
        reponse = harness.executer("Supprime toutes mes notes")

        # Assert 1 : l'outil n'a PAS été exécuté
        self.assertEqual(supprimer.appels, [])

        # Assert 2 : le modèle a été informé du refus
        message_outil = llm.messages_recus[1][-1]
        self.assertEqual(message_outil.role, "tool")
        self.assertEqual(message_outil.nom_outil, "supprimer_notes")
        self.assertIn("refus", message_outil.contenu.lower())

        # Assert 3 : le modèle a pu répondre normalement
        self.assertEqual(reponse, "D'accord, je ne supprime rien.")

    def test_sans_approbation_configuree_un_outil_en_ecriture_est_refuse(self):
        # Arrange : aucun système d'approbation fourni au harness
        supprimer = OutilFactice("supprimer_notes", risque=Risque.ECRITURE)
        llm = FakeLLM([
            ReponseLLM(appels=[AppelOutil(nom="supprimer_notes", arguments={})]),
            ReponseLLM(texte="Je n'ai pas l'autorisation de faire ça."),
        ])
        harness = Harness(llm=llm, prompt_systeme="Tu es utile.", outils=[supprimer])

        # Act
        reponse = harness.executer("Supprime toutes mes notes")

        # Assert 1 : l'outil n'a PAS été exécuté (sûr par défaut)
        self.assertEqual(supprimer.appels, [])

        # Assert 2 : le modèle a été informé du refus, et a pu répondre
        self.assertIn("refus", llm.messages_recus[1][-1].contenu.lower())
        self.assertEqual(reponse, "Je n'ai pas l'autorisation de faire ça.")


class TestHarnessMemoire(unittest.TestCase):

    def test_l_historique_d_une_conversation_est_recharge_a_l_appel_suivant(self):
        # Arrange
        llm = FakeLLM([
            ReponseLLM(texte="Enchanté john !"),
            ReponseLLM(texte="Tu t'appelles john."),
        ])
        harness = Harness(llm=llm, prompt_systeme="Tu es utile.", memoire=MemoireFactice())

        # Act : deux échanges dans la même conversation
        harness.executer("Je m'appelle john", conversation_id="c1")
        harness.executer("Comment je m'appelle ?", conversation_id="c1")

        # Assert : au 2e échange, le modèle a reçu tout le 1er échange
        self.assertEqual(
            llm.messages_recus[1],
            [
                Message(role="system", contenu="Tu es utile."),
                Message(role="user", contenu="Je m'appelle john"),
                Message(role="assistant", contenu="Enchanté john !"),
                Message(role="user", contenu="Comment je m'appelle ?"),
            ],
        )

    def test_deux_conversations_differentes_ne_se_melangent_pas(self):
        # Arrange
        llm = FakeLLM([
            ReponseLLM(texte="Enchanté Manu !"),
            ReponseLLM(texte="Je ne sais pas comment tu t'appelles."),
        ])
        harness = Harness(llm=llm, prompt_systeme="Tu es utile.", memoire=MemoireFactice())

        # Act : un échange dans la conversation "c1", puis un autre dans "c2"
        harness.executer("Je m'appelle Manu", conversation_id="c1")
        harness.executer("Comment je m'appelle ?", conversation_id="c2")

        # Assert : la conversation "c2" ne voit rien de "c1"
        self.assertEqual(
            llm.messages_recus[1],
            [
                Message(role="system", contenu="Tu es utile."),
                Message(role="user", contenu="Comment je m'appelle ?"),
            ],
        )

    def test_la_conversation_est_sauvegardee_quand_la_limite_est_atteinte(self):
        # Arrange : un modèle qui appelle un outil à chaque tour, sans jamais conclure
        appel = AppelOutil(nom="heure", arguments={})
        llm = FakeLLM([ReponseLLM(appels=[appel]), ReponseLLM(appels=[appel])])
        memoire = MemoireFactice()
        harness = Harness(
            llm=llm,
            prompt_systeme="Tu es utile.",
            outils=[OutilFactice("heure", resultat="12h")],
            max_iterations=2,
            memoire=memoire,
        )

        # Act
        harness.executer("Quelle heure est-il ?", conversation_id="c1")

        # Assert : tout l'échange est sauvegardé, sans le prompt système
        self.assertEqual(
            memoire.charger("c1"),
            [
                Message(role="user", contenu="Quelle heure est-il ?"),
                Message(role="assistant", contenu="", appels=[appel]),
                Message(role="tool", contenu="12h", nom_outil="heure"),
                Message(role="assistant", contenu="", appels=[appel]),
                Message(role="tool", contenu="12h", nom_outil="heure"),
            ],
        )


class TestHarnessJournal(unittest.TestCase):

    def test_la_question_recue_est_journalisee(self):
        # Arrange
        journal = JournalFactice()
        llm = FakeLLM([ReponseLLM(texte="Bonjour !")])
        harness = Harness(llm=llm, prompt_systeme="Tu es utile.", journal=journal)

        # Act
        harness.executer("Salut", conversation_id="c1")

        # Assert : le premier événement est la question reçue
        self.assertEqual(
            journal.evenements[0],
            Evenement(type="question_recue", conversation_id="c1", donnees={"texte": "Salut"}),
        )


if __name__ == "__main__":
    unittest.main()