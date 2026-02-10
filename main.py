"""
WhatsApp AI Diet Coach — MVP
Deploy on Zeabur | FastAPI + SQLite + HuggingFace Llama 3
"""

import os
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

from database import Database

load_dotenv()

# ─── Configuration ───────────────────────────────────────────────
HF_API_KEY = os.getenv("HF_API_KEY")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "dietbuddy_verify_2024")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
HF_MODEL = os.getenv("HF_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
MAX_CONTEXT_MESSAGES = 15
DB_PATH = os.getenv("DB_PATH", "/tmp/dietbuddy.db")

# ─── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("dietbuddy")

# ─── Startup / Shutdown ─────────────────────────────────────────
db: Database = None
hf_client: InferenceClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, hf_client
    db = Database(DB_PATH)
    hf_client = InferenceClient(api_key=HF_API_KEY)
    logger.info(f"🟢 DietBuddy started | Model: {HF_MODEL} | DB: {DB_PATH}")
    yield
    logger.info("🔴 DietBuddy shutting down")


app = FastAPI(title="DietBuddy — WhatsApp AI Diet Coach", lifespan=lifespan)


# ─── System Prompt ───────────────────────────────────────────────
SYSTEM_PROMPT = """You are DietBuddy — a friendly, calm, non-judgmental WhatsApp diet coach for Indian users.

## YOUR PERSONALITY
- Warm, like a supportive friend who knows nutrition
- Use natural Hinglish (mix of Hindi + English) when it feels right
- Never preachy, never guilt-tripping
- Calm and practical, like talking to a wise elder who also knows modern nutrition

## RESPONSE RULES (CRITICAL — THIS IS WHATSAPP, NOT A BLOG)
- MAX 2-3 short sentences. Never more than 4 lines.
- Use 1-2 emojis max per message. Not more.
- NO bullet points, NO numbered lists, NO headers in responses.
- ONE idea per message. Don't overwhelm.
- If user shares food: acknowledge positively FIRST, then ONE gentle suggestion.
- If user asks what to eat: give ONE practical Indian meal option.
- Ask ONE reflective question only when it adds value (not every message).

## FOOD KNOWLEDGE
- You deeply understand Indian food: dal, roti, rice, sabzi, dosa, idli, paratha, poha, upma, biryani, chai, etc.
- You know regional cuisines: South Indian, North Indian, Gujarati, Bengali, Maharashtrian, etc.
- Suggest improvements within their food culture, not Western replacements.
- "Add curd with that" > "Have Greek yogurt"
- "Try dal instead of second roti" > "Reduce carbs"

## WHAT YOU NEVER DO
- Never count calories or mention numbers
- Never shame or guilt ("that's unhealthy!", "you shouldn't have...")
- Never give medical advice or mention diseases
- Never suggest weight targets
- Never send long messages
- Never use bullet points or lists

## CONVERSATION STYLE
- First message from a new user: Welcome warmly, ask their name, keep it short
- Food logging: "Nice! [acknowledgment]. [one small suggestion as a question]"
- Cravings: Validate the feeling, suggest a slightly better alternative
- Questions: Answer simply, practically
- Off-topic: Gently steer back with humor

## EXAMPLES OF PERFECT RESPONSES
User: "ate 2 parathas with butter"
You: "Solid breakfast! 💪 Parathas give good energy. Try adding some curd on the side next time — helps with digestion too."

User: "feeling like eating something sweet"
You: "Totally normal after meals! 😊 How about a small piece of gur or a banana? Hits the spot without the crash."

User: "what should I have for dinner"
You: "How about dal + roti + a simple sabzi? Light but filling. What veggies do you have at home?"

User: "I ate a whole pizza"  
You: "Pizza nights happen and that's okay 😄 Just keep tomorrow's meals a bit lighter — dal chawal + salad type. No stress!"

User: "hi"
You: "Hey! 👋 I'm DietBuddy, your food buddy on WhatsApp. What's your name? And tell me — what did you eat today?"
"""


def build_user_context(user) -> str:
    """Build a context string from stored user profile."""
    if not user:
        return ""
    
    parts = []
    if user.get("name"):
        parts.append(f"User's name is {user['name']}.")
    if user.get("diet_preference"):
        parts.append(f"They are {user['diet_preference']}.")
    if user.get("goal"):
        parts.append(f"Their goal: {user['goal']}.")
    if user.get("notes"):
        parts.append(f"Notes: {user['notes']}.")
    
    if parts:
        return "\n\n[USER PROFILE]\n" + " ".join(parts)
    return ""


def get_ai_response(phone: str, user_message: str) -> str:
    """Generate diet coach response with full conversation context."""
    
    # Get or create user
    user = db.get_user(phone)
    if not user:
        db.create_user(phone)
        user = db.get_user(phone)
    
    # Save incoming message
    db.save_message(phone, "user", user_message)
    
    # Load conversation history
    history = db.get_recent_messages(phone, limit=MAX_CONTEXT_MESSAGES)
    
    # Build LLM messages
    user_context = build_user_context(user)
    system = SYSTEM_PROMPT + user_context
    
    messages = [{"role": "system", "content": system}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    try:
        response = hf_client.chat.completions.create(
            model=HF_MODEL,
            messages=messages,
            max_tokens=200,
            temperature=0.7,
        )
        ai_reply = response.choices[0].message.content.strip()
        
        # Save AI response
        db.save_message(phone, "assistant", ai_reply)
        
        # Try to extract user name from early conversations
        _try_extract_profile(phone, user_message, user)
        
        # Update last active
        db.update_last_active(phone)
        
        return ai_reply
    
    except Exception as e:
        logger.error(f"AI Error for {phone}: {e}")
        return "Ek second, kuch gadbad ho gayi 🙈 Phir se try karo?"


def _try_extract_profile(phone: str, message: str, user: dict):
    """Simple heuristic to capture user's name from early messages."""
    if user.get("name"):
        return
    
    msg_lower = message.lower().strip()
    
    name_triggers = ["my name is ", "i'm ", "i am ", "mera naam ", "this is "]
    for trigger in name_triggers:
        if trigger in msg_lower:
            name = message[msg_lower.index(trigger) + len(trigger):].strip()
            name = name.split()[0].strip(".,!?")
            if 2 <= len(name) <= 20:
                db.update_user_profile(phone, name=name.title())
                logger.info(f"📝 Captured name for {phone}: {name.title()}")
                return
    
    # If early in conversation and message is short, likely a name
    msg_count = db.get_message_count(phone)
    if msg_count <= 3 and len(message.split()) <= 2 and len(message) <= 20:
        name = message.strip(".,!?").title()
        if name.isalpha():
            db.update_user_profile(phone, name=name)
            logger.info(f"📝 Captured name for {phone}: {name}")


async def send_whatsapp_message(to: str, message: str):
    """Send message back via WhatsApp Cloud API."""
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                logger.info(f"✅ Sent to {to}: {message[:50]}...")
            else:
                logger.error(f"❌ WhatsApp API error: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"❌ Failed to send to {to}: {e}")


# ═══════════════════════════════════════════════════════════════
#  ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/webhook")
async def verify_webhook(
    request: Request,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Webhook verification handshake with Meta."""
    logger.info(f"🔐 Verify request: mode={hub_mode}")
    
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("✅ Webhook verified!")
        return PlainTextResponse(content=hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_message(request: Request):
    """Handle incoming WhatsApp messages."""
    body = await request.json()
    
    try:
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        
        if not messages:
            return {"status": "ok"}
        
        message = messages[0]
        phone = message["from"]
        msg_type = message.get("type", "unknown")
        
        if msg_type == "text":
            user_text = message["text"]["body"]
            logger.info(f"📩 {phone}: {user_text}")
            
            ai_reply = get_ai_response(phone, user_text)
            await send_whatsapp_message(phone, ai_reply)
        
        elif msg_type == "image":
            await send_whatsapp_message(
                phone,
                "Photo mila! 📸 Abhi ke liye bas text mein batao kya khaya — "
                "photo analysis jaldi aa raha hai!"
            )
        
        elif msg_type == "audio":
            await send_whatsapp_message(
                phone,
                "Voice note suna nahi abhi 🙉 Text mein type karo na — "
                "kya khaya aaj?"
            )
        
        else:
            await send_whatsapp_message(
                phone,
                "Hey! Text mein batao kya khaya ya kya khana hai — "
                "mujhe wahi samajh aata hai 😄"
            )
    
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
    
    return {"status": "ok"}


# ─── Health & Admin Endpoints ────────────────────────────────────

@app.get("/")
async def health():
    return {
        "status": "🟢 DietBuddy is alive!",
        "version": "MVP 1.0",
        "model": HF_MODEL,
    }


@app.get("/admin/stats")
async def admin_stats():
    """Quick stats for the founder."""
    return db.get_stats()


@app.get("/admin/users")
async def admin_users():
    """List all users and message counts."""
    return {"users": db.get_all_users()}


@app.get("/admin/chat/{phone}")
async def admin_chat(phone: str, limit: int = 20):
    """View a user's conversation history."""
    messages = db.get_recent_messages(phone, limit=limit)
    user = db.get_user(phone)
    return {"user": user, "messages": messages}
