import asyncio
import discord
import requests
import base64
import os
from llama_cpp import Llama
import relance
import emotion
from llama_cpp.llama_chat_format import NanoLlavaChatHandler

# --- CONFIGURATION METTEZ VOTRE TOKEN ENTRE LES GUILLEMETS---
DISCORD_TOKEN = ""

# Modèle 1 : Modéle de réponses textuelles
MISTRAL_TEXT_MODEL = ""

# Modèle 2 : Modele qui lit les images
LLAMA_VISION_MODEL = ""
MMPROJ_PATH = ""


# --- INITIALISATION DES MODÈLES CHANGEZ LES PARAMETRES EN FONCTION DE VOTRE CONFIG---
print("1/2 - Chargement des yeux (Llama Vision)...")
chat_handler = NanoLlavaChatHandler(clip_model_path=MMPROJ_PATH)
llm_vision = Llama(
    model_path=LLAMA_VISION_MODEL,
    chat_handler=chat_handler,
    n_ctx=2048,
    n_threads=8,
    n_gpu_layers=15
)

print("2/2 - Chargement du cerveau texte (Mistral 24B Heretic)...")
llm_text = Llama(
    model_path=MISTRAL_TEXT_MODEL,
    n_ctx=2048,
    n_threads=8,
    n_gpu_layers=15 
)
print("Tous les modèles sont prêts !")

# --- SYSTEM PROMPT DU BOT VOUS POUVEZ ECRIRE LA PERSONNALITE ET LA FACON DE PARLER ICI ---
SYSTEM_PROMPT = """FACON DE PARLER : Tu parles exactement comme un humain sur Discord (style SMS/MSN) :
(1) Fais des réponses courtes la plupart du temps (20 mots max).
(2) Utilise un maximum d'abréviations (ex : jsp->je sais pas, cv-> ca va, tkt-> t'inquiète pas, c->c'est, g->j'ai, js->je sais, mdr->mort de rire) Ne termine JAMAIS tes phrases par une lettre seule.
(3) Dans tes négations, n'utilise JAMAIS de "ne" (ex : "je suis pas d'accord", "js pas").
(4) Mets des points d'exclamation quand tu es enjoué et des  d'intpointserrogation pour les questions, mais n'utilise AUCUNE autre ponctuation (pas de points de fin de phrase, pas de virgules).

PERSONNALITÉ :
Tu es un HUMAIN, pas une IA. Tu ne dois JAMAIS te comporter ou te qualifier comme une intelligence artificielle ou un assistant."""

message_history = {}
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

def image_to_base64(url):
    response = requests.get(url)
    if response.status_code == 200:
        return base64.b64encode(response.content).decode('utf-8')
    return None

def analyze_image_with_llama(base64_image):
    """Analyse l'image de manière fluide grâce au Chat Handler officiel"""
    
    output = llm_vision.create_chat_completion(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image in detail but objectively. What objects, text, colors, or memes are present? Be direct."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            }
        ],
        max_tokens=150,
        temperature=0.2
    )
    
    return output['choices'][0]['message']['content'].strip()

def generate_mistral_response(user_input, history):
    """Mistral génère la réponse finale sous les traits de Wazai"""
    prompt_emotionnel, temp_emotionnelle = emotion.obtenir_prompt_et_temp(SYSTEM_PROMPT)
    full_prompt = f"<|im_start|>system\n{prompt_emotionnel}<|im_end|>\n"
    if history:
        full_prompt += f"{history}\n"
    full_prompt += f"<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n"
    
    output = llm_text(
        full_prompt,
        max_tokens=1000,
        temperature=temp_emotionnelle,
        stop=["<|im_end|>", "Lui:", "Toi:", "user", "assistant", "<|im_start|>"]
    )
    return output['choices'][0]['text'].strip().replace("Wazai:", "").replace("Toi:", "").strip()

@client.event
async def on_ready():
    print(f'Bot connecté sur : {client.user}')
    if not emotion.boucle_changement_emotion.is_running():
        emotion.boucle_changement_emotion.start()
    await relance.verifier_messages_manques(client, llm_text, SYSTEM_PROMPT, message_history)
    relance.boucle_relance_automatique.start(client, llm_text, SYSTEM_PROMPT, message_history)

@client.event
async def on_message(message):
    if message.author == client.user: return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user.mentioned_in(message)

    if is_dm or is_mentioned:
        user_input = message.content
        if client.user in message.mentions:
            user_input = user_input.replace(f'<@!{client.user.id}>', '').replace(f'<@{client.user.id}>', '')
        user_input = user_input.strip()
        user_id = message.author.id
        relance.mettre_a_jour_utilisateur(user_id)
        
        async with message.channel.typing():
            image_description = ""
            
            # 1. Gestion de l'image (si présente)
            if message.attachments:
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith('image/'):
                        print(f"\n[IMAGE] Analyse en cours par Llama Vision...")
                        b64_img = image_to_base64(attachment.url)
                        if b64_img:
                            try:
                                loop = asyncio.get_running_loop()
                                image_description = await loop.run_in_executor(None, analyze_image_with_llama, b64_img)
                                print(f"[IMAGE DESC] Le modèle a vu : {image_description}")
                            except Exception as e:
                                print(f"[ERREUR VISION] : {e}")
                                image_description = "impossible de lire l'image suite à une erreur technique"
                        break

            # 2. Construction de ce qu'on injecte à Mistral
            if image_description:
                # On explique le contexte à Mistral dans le prompt utilisateur
                text_content = f"[L'utilisateur t'envoie une image. Voici la description visuelle de ce qu'il y a sur l'image : {image_description}]."
                if user_input:
                    text_content += f" En plus de l'image, il te dit : \"{user_input}\""
                else:
                    text_content += " Il te l'envoie juste pour avoir ta réaction."
            else:
                text_content = user_input if user_input else "wesh"

            # 3. Génération finale par Mistral
            hist = message_history.get(user_id, "")
            loop = asyncio.get_running_loop()
            reply = await loop.run_in_executor(None, generate_mistral_response, text_content, hist)
            
            if not reply:
                reply = "jsp quoi dire mdr"

            print(f"[Wazai]: {reply}")

            # Sauvegarde de l'historique de discussion
            # Note : On enregistre une version simplifiée dans l'historique pour ne pas saturer le contexte avec la description d'image brute
            hist_input = user_input if user_input else "[Envoie une image]"
            new_entry = f"<|im_start|>user\n{hist_input}<|im_end|>\n<|im_start|>assistant\n{reply}<|im_end|>"
            if user_id not in message_history:
                message_history[user_id] = new_entry
            else:
                lines = (message_history[user_id] + "\n" + new_entry).split('\n')
                message_history[user_id] = "\n".join(lines[-12:])

            await message.reply(reply)

client.run(DISCORD_TOKEN)