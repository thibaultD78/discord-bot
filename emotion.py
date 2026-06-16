import os
import json
import random
from datetime import datetime, timedelta
from discord.ext import tasks

EMOTION_FILE = "./personnality.json"

EMOTIONS_CONFIG = {
    "neutre": {
        "temperature": 0.85,
        "instruction": "Tu es dans ton état normal, détendu et amical."
    },
    "heureux": {
        "temperature": 1.0,
        "instruction": "Tu es d'humeur super enjouée, fêtarde et un peu fofolle ! Utilise encore plus de points d'exclamation, sois hyper expressif, dis des trucs un peu plus délirants et spontanés."
    },
    "triste": {
        "temperature": 0.7,
        "instruction": "Tu es d'humeur un peu triste, mélancolique et fatiguée. Tu essaies de le cacher mais ça se sent : tu es un peu moins expressif, tes réponses sont légèrement plus courtes et tu mets moins de points d'exclamation."
    },
}

def charger_emotion():
    if not os.path.exists(EMOTION_FILE):
        return réinitialiser_humeur()
    try:
        with open(EMOTION_FILE, "r") as f:
            contenu = f.read().strip()
            if not contenu:
                return réinitialiser_humeur()
            f.seek(0)
            return json.loads(contenu)
    except Exception:
        return réinitialiser_humeur()

def sauvegarder_emotion(data):
    with open(EMOTION_FILE, "w") as f:
        json.dump(data, f, indent=4)

def réinitialiser_humeur():
    """Choisit une humeur en fonction de pourcentages de chance précis"""
    humeurs_possibles = ["neutre", "triste", "coquin", "foufou"]
    poids_emotions = [50, 20, 30]
    humeur_choisie = random.choices(humeurs_possibles, weights=poids_emotions, k=1)[0]
    heures_duree = random.randint(4, 16)
    fin_emotion = datetime.now() + timedelta(hours=heures_duree)
    
    data = {
        "humeur_actuelle": humeur_choisie,
        "date_fin": fin_emotion.strftime("%Y-%m-%d %H:%M:%S")
    }
    sauvegarder_emotion(data)
    print(f"[ÉMOTION] Nouvelle humeur activée : {humeur_choisie.upper()} pour les prochaines {heures_duree} heures.")
    return data

def obtenir_prompt_et_temp(system_prompt_de_base):
    """Injecte l'émotion actuelle dans le prompt système et renvoie la température adaptée"""
    data = charger_emotion()
    maintenant = datetime.now()
    date_fin = datetime.strptime(data["date_fin"], "%Y-%m-%d %H:%M:%S")
    
    if maintenant >= date_fin:
        data = réinitialiser_humeur()
        
    humeur = data["humeur_actuelle"]
    config = EMOTIONS_CONFIG[humeur]
    
    prompt_modifie = f"{system_prompt_de_base}\n\n[HUMEUR ACTUELLE : {config['instruction']}]"
    return prompt_modifie, config["temperature"]

@tasks.loop(minutes=10)
async def boucle_changement_emotion():
    data = charger_emotion()
    maintenant = datetime.now()
    date_fin = datetime.strptime(data["date_fin"], "%Y-%m-%d %H:%M:%S")
    
    if maintenant >= date_fin:
        réinitialiser_humeur()