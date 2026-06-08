import os
import json
import random
from datetime import datetime, timedelta
from discord.ext import tasks

DATA_FILE = "./utilisateurs.json"

def charger_donnees():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            contenu = f.read().strip()
            if not contenu:
                return {}
            f.seek(0)
            return json.loads(contenu)
    except (json.JSONDecodeError, Exception):
        print("[Attention] Fichier utilisateurs.json corrompu ou vide, réinitialisation...")
        return {}

def sauvegarder_donnees(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def planifier_prochaine_etape(user_id_str, etape_actuelle, data):
    """Calcule le temps d'attente selon l'étape où on en est"""
    maintenant = datetime.now()
    
    if etape_actuelle == 0:
        heures_attente = random.randint(2, 4)
        date_relance = maintenant + timedelta(hours=heures_attente)
        prochaine_etape = 1
    elif etape_actuelle == 1:
        date_relance = maintenant + timedelta(days=1)
        prochaine_etape = 2
    else:
        jours_attente = random.randint(3, 5)
        date_relance = maintenant + timedelta(days=jours_attente)
        prochaine_etape = 3

    data[user_id_str]["date_relance_prevue"] = date_relance.strftime("%Y-%m-%d %H:%M:%S")
    data[user_id_str]["etape"] = prochaine_etape
    data[user_id_str]["relance_faite"] = False

def mettre_a_jour_utilisateur(user_id):
    """L'utilisateur a parlé : on réinitialise tout le cycle à l'étape 0"""
    data = charger_donnees()
    user_id_str = str(user_id)
    
    data[user_id_str] = {
        "derniere_discussion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date_relance_prevue": "",
        "etape": 0,
        "relance_faite": False
    }
    
    planifier_prochaine_etape(user_id_str, 0, data)
    sauvegarder_donnees(data)

def generer_relance_ia(llm_text, system_prompt, history, etape):
    """Demande à Mistral d'inventer une relance adaptée au temps écoulé"""
    
    if etape == 1:
        consigne = "[CONTEXTE SYSTÈME : Tu n'as pas parlé à cette personne depuis quelques heures. En te basant subtilement sur votre historique si pertinent, envoie-lui un petit message de relance spontané, court, style SMS pour continuer la discussion ou relancer le délire. Ne dis rien d'autre, écris juste ton message.]"
    elif etape == 2:
        consigne = "[CONTEXTE SYSTÈME : Tu n'as pas parlé à cette personne depuis hier. En te basant subtilement sur votre historique si pertinent, envoie-lui un message de relance spontané, court, style SMS pour prendre des nouvelles et voir ce qu'elle fait aujourd'hui. Ne dis rien d'autre, écris juste ton message.]"
    else:
        consigne = "[CONTEXTE SYSTÈME : Tu n'as pas parlé à cette personne depuis plusieurs jours. En te basant subtilement sur votre historique si pertinent, envoie-lui un message de relance spontané, court, style SMS pour lui dire qu'elle donne plus de signes de vie ou lui demander ce qu'elle devient. Ne dis rien d'autre, écris juste ton message.]"

    full_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
    if history:
        full_prompt += f"{history}\n"
    full_prompt += f"<|im_start|>user\n{consigne}<|im_end|>\n<|im_start|>assistant\n"
    
    output = llm_text(full_prompt, max_tokens=40, temperature=0.9, stop=["<|im_end|>", "user", "assistant"])
    return output['choices'][0]['text'].strip()

@tasks.loop(minutes=1)
async def boucle_relance_automatique(client, llm_text, system_prompt, message_history):
    await client.wait_until_ready()
    data = charger_donnees()
    maintenant = datetime.now()
    changement = False

    for user_id_str, infos in data.items():
        if infos["relance_faite"]:
            continue
        
        date_prevue = datetime.strptime(infos["date_relance_prevue"], "%Y-%m-%d %H:%M:%S")
        
        if maintenant >= date_prevue:
            try:
                user_id = int(user_id_str)
                user = await client.fetch_user(user_id)
                
                if user:
                    etape_actuelle = infos["etape"]
                    print(f"\n[RELANCE ÉTAPE {etape_actuelle}] Génération pour {user.name}...")
                    hist = message_history.get(user_id, "")
                    
                    message_relance = generer_relance_ia(llm_text, system_prompt, hist, etape_actuelle)
                    if not message_relance:
                        message_relance = "wesh tu deviens quoi ?"
                    
                    await user.send(message_relance)
                    print(f"[RELANCE Envoyée à {user.name}]: {message_relance}")
                    
                    new_entry = f"<|im_start|>user\n[Relance automatique après absence]<|im_end|>\n<|im_start|>assistant\n{message_relance}<|im_end|>"
                    if user_id not in message_history:
                        message_history[user_id] = new_entry
                    else:
                        message_history[user_id] += "\n" + new_entry
                    
                    infos["relance_faite"] = True
                    planifier_prochaine_etape(user_id_str, etape_actuelle, data)
                    changement = True
            except Exception as e:
                print(f"[ERREUR RELANCE] Impossible de relancer {user_id_str} : {e}")

    if changement:
        sauvegarder_donnees(data)

async def verifier_messages_manques(client, llm_text, system_prompt, message_history):
    """Vérifie au démarrage si des utilisateurs ont écrit pendant que le bot était éteint"""
    print("[RÉVEIL] Vérification des messages manqués pendant l'absence...")
    data = charger_donnees()
    changement = False

    for user_id_str in data.keys():
        try:
            user_id = int(user_id_str)
            user = await client.fetch_user(user_id)
            if not user:
                continue

            dm_channel = user.dm_channel
            if dm_channel is None:
                dm_channel = await user.create_dm()
                
            messages = [msg async for msg in dm_channel.history(limit=2)]
            if not messages:
                continue

            dernier_msg = messages[0]

            if dernier_msg.author.id != client.user.id:
                print(f"[RÉVEIL] Message manqué détecté de la part de {user.name} : '{dernier_msg.content}'")
                
                user_input = dernier_msg.content if dernier_msg.content else "[Envoie une image ou un sticker]"
                hist = message_history.get(user_id, "")
                
                consigne_reveil = (
                    f"[CONTEXTE SYSTÈME : Tu viens tout juste de revenir sur ton PC après une absence. "
                    f"L'utilisateur t'avait envoyé un message pendant que tu n'étais pas là. "
                    f"Tu dois impérativement commencer ton message par une petite excuse courte style SMS "
                    f"(ex: dsl g t pas la, dsl je faisais un truc, dsl g t occupé) puis enchaîner directement "
                    f"en répondant à ce qu'il t'a dit. Fais une réponse courte, max 15 mots.]"
                )
                
                full_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                if hist:
                    full_prompt += f"{hist}\n"
                full_prompt += f"<|im_start|>user\n{consigne_reveil}\nEn plus, voici son message : \"{user_input}\"<|im_end|>\n<|im_start|>assistant\n"
                
                output = llm_text(full_prompt, max_tokens=65, temperature=0.85, stop=["<|im_end|>", "user", "assistant"])
                reply = output['choices'][0]['text'].strip()
                
                if not reply:
                    reply = "dsl j'étais pas là cv ?"

                await dm_channel.send(reply)
                print(f"[RÉVEIL Réponse envoyée à {user.name}]: {reply}")

                new_entry = f"<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n{reply}<|im_end|>"
                if user_id not in message_history:
                    message_history[user_id] = new_entry
                else:
                    message_history[user_id] += "\n" + new_entry
                
                infos_utilisateurs = data[user_id_str]
                infos_utilisateurs["derniere_discussion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                changement = True

        except Exception as e:
            print(f"[ERREUR RÉVEIL] Impossible de vérifier les messages pour {user_id_str} : {e}")

    if changement:
        for user_id_str in data.keys():
            if data[user_id_str]["derniere_discussion"] == datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
                planifier_prochaine_etape(user_id_str, 0, data)
        sauvegarder_donnees(data)