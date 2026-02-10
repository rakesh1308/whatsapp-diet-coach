"""
DietBuddy Pro — WhatsApp AI Diet Coach
FastAPI + SQLite + HuggingFace Llama 3
Full-featured: food logging, water tracking, onboarding, time-aware, weekly summaries
"""

import os
import re
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from openai import OpenAI

from database import Database, now_ist
from coach import (
    SYSTEM_PROMPT,
    get_time_context,
    build_user_context,
    build_today_food_context,
    build_water_context,
    detect_food_log,
    detect_water_log,
    detect_summary_request,
    detect_meal_suggestion_request,
    detect_help_request,
)

load_dotenv()

# ─── Configuration ───────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "dietbuddy_verify_2024")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
MODEL = os.getenv("MODEL", "gpt-4o-mini")
MAX_CONTEXT_MESSAGES = 15
DB_PATH = os.getenv("DB_PATH", "/tmp/dietbuddy.db")

# ─── Logging ─────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("dietbuddy")

# ─── Globals ─────────────────────────────────────────────────────
db: Database = None
ai_client: OpenAI = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, ai_client
    db = Database(DB_PATH)
    ai_client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info(f"🟢 DietBuddy Pro started | Model: {MODEL}")
    yield
    logger.info("🔴 DietBuddy Pro shutting down")


app = FastAPI(title="DietBuddy Pro", lifespan=lifespan)


# ═══════════════════════════════════════════════════════════════
#  CORE AI ENGINE
# ═══════════════════════════════════════════════════════════════

def get_ai_response(phone: str, user_message: str) -> str:
    """Generate contextual AI response with full user awareness."""

    # Get or create user
    user = db.get_user(phone)
    if not user:
        db.create_user(phone)
        user = db.get_user(phone)

    # Save incoming message
    db.save_message(phone, "user", user_message)

    # ── Handle special commands before LLM ──
    msg_lower = user_message.lower().strip()

    # Help command
    if detect_help_request(user_message):
        help_text = (
            "Hey! Here's what I can do 😊\n\n"
            "🍽️ Tell me what you ate — I'll track it and give tips\n"
            "💧 Say 'water' — I'll log your hydration\n"
            "🤔 Ask 'what should I eat' — I'll suggest meals\n"
            "📊 Say 'summary' — I'll show your weekly eating patterns\n"
            "📋 Say 'today's log' — I'll recap what you ate today\n\n"
            "Or just chat with me about anything food related!"
        )
        db.save_message(phone, "assistant", help_text)
        db.update_last_active(phone)
        return help_text

    # Water logging
    if detect_water_log(user_message) and not detect_food_log(user_message):
        return _handle_water_log(phone, user_message, user)

    # Weekly summary
    if detect_summary_request(user_message):
        return _handle_summary(phone, user)

    # ── Detect and log food ──
    is_food = detect_food_log(user_message)
    if is_food:
        db.log_food(phone, user_message)
        logger.info(f"🍽️ Food logged for {phone}: {user_message}")

    # ── Build rich context for LLM ──
    history = db.get_recent_messages(phone, limit=MAX_CONTEXT_MESSAGES)
    today_food = db.get_today_food_logs(phone)
    water_today = db.get_today_water(phone)
    water_goal = user.get("water_goal_liters", 3.0) if user else 3.0

    context_parts = [
        SYSTEM_PROMPT,
        get_time_context(),
        build_user_context(user),
        build_today_food_context(today_food),
        build_water_context(water_today, water_goal),
    ]

    # Add food log instruction if food detected
    if is_food:
        context_parts.append(
            "\n[INSTRUCTION: User just logged food. This has been saved. "
            "Acknowledge the meal positively, assess it briefly, and give ONE helpful suggestion. "
            "Keep it short and warm.]"
        )

    # Add meal suggestion context
    if detect_meal_suggestion_request(user_message):
        context_parts.append(
            "\n[INSTRUCTION: User wants a meal suggestion. Consider the time of day, "
            "their diet preference, regional cuisine, and what they've already eaten today. "
            "Suggest ONE specific, practical Indian meal.]"
        )

    system_message = "\n".join(context_parts)

    messages = [{"role": "system", "content": system_message}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    try:
        response = ai_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=1024,
            temperature=0.7,
        )
        ai_reply = response.choices[0].message.content.strip()

        # Clean up common LLM artifacts
        ai_reply = _clean_response(ai_reply)

        # Save AI response
        db.save_message(phone, "assistant", ai_reply)

        # Try profile extraction from user message
        _extract_profile_info(phone, user_message, user)

        db.update_last_active(phone)
        return ai_reply

    except Exception as e:
        logger.error(f"AI Error for {phone}: {e}")
        return "Ek second, thoda issue ho gaya 🙈 Please try again?"


def _handle_water_log(phone: str, message: str, user: dict) -> str:
    """Handle water logging."""
    # Try to extract number of glasses
    glasses = 1
    numbers = re.findall(r'\d+', message)
    if numbers:
        num = int(numbers[0])
        if 1 <= num <= 10:
            glasses = num

    db.log_water(phone, glasses)
    total = db.get_today_water(phone)
    goal = user.get("water_goal_liters", 3.0) if user else 3.0
    goal_glasses = int(goal * 4)

    if total >= goal_glasses:
        reply = f"💧 Logged! You've had {total} glasses today — you've hit your goal! Awesome 👏"
    elif total >= goal_glasses * 0.7:
        reply = f"💧 Nice! {total} glasses done today. Almost at your goal of {goal_glasses}! Keep going 💪"
    else:
        remaining = goal_glasses - total
        reply = f"💧 Logged! {total} glasses so far today. About {remaining} more to hit your goal. You got this!"

    db.save_message(phone, "assistant", reply)
    db.update_last_active(phone)
    return reply


def _handle_summary(phone: str, user: dict) -> str:
    """Handle weekly summary or today's log request."""
    # Check if asking for today
    today_food = db.get_today_food_logs(phone)

    if not today_food:
        reply = "You haven't logged any meals today yet! Batao kya khaya aaj? 😊"
        db.save_message(phone, "assistant", reply)
        return reply

    # Build today's recap
    summary_parts = ["Here's what you've eaten today 📋\n"]
    for log in today_food:
        meal = log.get("meal_type", "meal").replace("_", " ").title()
        food = log.get("food_description", "")
        time = log.get("meal_time", "")
        summary_parts.append(f"• {meal} ({time}): {food}")

    water = db.get_today_water(phone)
    summary_parts.append(f"\n💧 Water: {water} glasses")

    # Now use LLM to give a brief assessment
    today_text = "\n".join(summary_parts)

    assessment_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"{build_user_context(user)}\n\n"
        f"[TODAY'S COMPLETE FOOD LOG]\n{today_text}\n\n"
        f"[INSTRUCTION: Give a brief, warm 2-3 sentence assessment of today's eating. "
        f"Highlight one good thing and one gentle improvement suggestion. "
        f"Don't repeat the food list — the user already sees it above your message.]"
    )

    try:
        response = ai_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": assessment_prompt},
                {"role": "user", "content": "How did I eat today?"},
            ],
            max_tokens=800,
            temperature=0.7,
        )
        assessment = _clean_response(response.choices[0].message.content.strip())
        reply = f"{today_text}\n\n{assessment}"
    except Exception:
        reply = today_text

    db.save_message(phone, "assistant", reply)
    db.update_last_active(phone)
    return reply


def _clean_response(text: str) -> str:
    """Clean common LLM output artifacts."""
    # Remove markdown bold
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    # Remove markdown headers
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    # Remove excessive emojis (more than 3 in a row)
    text = re.sub(r'([\U0001F300-\U0001F9FF]){4,}', lambda m: m.group(0)[:3], text)
    # WhatsApp max message is 4096 chars — trim only if exceeding that
    if len(text) > 4000:
        # Find last complete paragraph before limit
        cut = text[:4000].rfind('\n\n')
        if cut > 2000:
            text = text[:cut]
        else:
            cut = text[:4000].rfind('. ')
            if cut > 0:
                text = text[:cut + 1]
            else:
                text = text[:4000]
    return text.strip()


def _extract_profile_info(phone: str, message: str, user: dict):
    """Extract profile information from user messages using heuristics."""
    msg_lower = message.lower().strip()

    # ── Name extraction ──
    if not user.get("name"):
        name_triggers = [
            "my name is ", "i'm ", "i am ", "mera naam ",
            "this is ", "call me ", "naam ", "name is ",
        ]
        for trigger in name_triggers:
            if trigger in msg_lower:
                name = message[msg_lower.index(trigger) + len(trigger):].strip()
                name = name.split()[0].strip(".,!?")
                if 2 <= len(name) <= 20 and name.isalpha():
                    db.update_user_profile(phone, name=name.title())
                    logger.info(f"📝 Name captured: {phone} → {name.title()}")
                    return

        # Short message early in conversation = likely a name
        msg_count = db.get_message_count(phone)
        if msg_count <= 4 and len(message.split()) <= 2 and len(message) <= 20:
            name = message.strip(".,!?").title()
            if name.isalpha() and len(name) >= 2:
                db.update_user_profile(phone, name=name)
                logger.info(f"📝 Name inferred: {phone} → {name}")

    # ── Diet preference ──
    if not user.get("diet_preference"):
        veg_patterns = {
            "vegetarian": ["vegetarian", "veg ", "pure veg", "shakahari"],
            "non-vegetarian": ["non veg", "non-veg", "nonveg", "i eat meat",
                               "chicken", "mutton", "fish", "non vegetarian"],
            "eggetarian": ["egg only", "eggetarian", "egg but no meat", "anda"],
            "vegan": ["vegan", "no dairy", "plant based"],
            "jain": ["jain", "jain food"],
        }
        for pref, patterns in veg_patterns.items():
            if any(p in msg_lower for p in patterns):
                db.update_user_profile(phone, diet_preference=pref)
                logger.info(f"📝 Diet preference: {phone} → {pref}")
                _check_onboarding_complete(phone)
                return

    # ── Regional cuisine ──
    if not user.get("regional_cuisine"):
        cuisine_patterns = {
            "North Indian": ["north indian", "punjabi", "delhi", "up food", "rajasthani"],
            "South Indian": ["south indian", "tamil", "kerala", "karnataka", "andhra",
                            "telugu", "dosa", "idli lover"],
            "Maharashtrian": ["maharashtrian", "marathi", "maharashtra", "mumbai food"],
            "Gujarati": ["gujarati", "gujrati", "gujarat"],
            "Bengali": ["bengali", "bangla", "kolkata food"],
            "Hyderabadi": ["hyderabadi", "hyderabad"],
            "Mixed / All": ["mixed", "everything", "all types", "sab kuch", "no preference"],
        }
        for cuisine, patterns in cuisine_patterns.items():
            if any(p in msg_lower for p in patterns):
                db.update_user_profile(phone, regional_cuisine=cuisine)
                logger.info(f"📝 Cuisine: {phone} → {cuisine}")
                _check_onboarding_complete(phone)
                return

    # ── Health goal ──
    if not user.get("health_goal"):
        goal_patterns = {
            "eat healthier": ["eat healthy", "eat healthier", "healthy eating",
                             "improve diet", "better diet", "clean eating"],
            "lose weight": ["lose weight", "weight loss", "fat loss", "slim",
                           "weight kam", "vajan kam", "pet kam"],
            "gain muscle": ["gain muscle", "build muscle", "bulk", "mass gain",
                           "muscle bana", "body bana"],
            "more energy": ["more energy", "energy", "stamina", "tired",
                           "fatigue", "thakaan", "active rehna"],
            "manage sugar": ["sugar", "diabetes", "blood sugar", "sugar control"],
            "general wellness": ["general", "overall", "wellness", "fit rehna"],
        }
        for goal, patterns in goal_patterns.items():
            if any(p in msg_lower for p in patterns):
                db.update_user_profile(phone, health_goal=goal)
                logger.info(f"📝 Goal: {phone} → {goal}")
                _check_onboarding_complete(phone)
                return


def _check_onboarding_complete(phone: str):
    """Check if all required profile fields are filled."""
    user = db.get_user(phone)
    if user and user.get("name") and user.get("diet_preference") and user.get("health_goal"):
        db.update_user_profile(phone, onboarding_complete=1)
        logger.info(f"✅ Onboarding complete for {phone}")


# ═══════════════════════════════════════════════════════════════
#  WHATSAPP WEBHOOK
# ═══════════════════════════════════════════════════════════════

async def send_whatsapp_message(to: str, message: str):
    """Send message via WhatsApp Cloud API."""
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
                logger.info(f"✅ Sent to {to}: {message[:60]}...")
            else:
                logger.error(f"❌ WhatsApp API: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"❌ Send failed to {to}: {e}")


@app.get("/webhook")
async def verify_webhook(
    request: Request,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification."""
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
                "Photo mila! 📸 Abhi sirf text se kaam chala lo — "
                "batao kya khaya, main track kar lunga!"
            )

        elif msg_type == "audio":
            await send_whatsapp_message(
                phone,
                "Voice note support aa raha hai jaldi! 🎤 "
                "Filhaal text mein batao kya khaya?"
            )

        else:
            await send_whatsapp_message(
                phone,
                "Hey! Mujhe text mein batao kya khaya ya kya khana hai 😊"
            )

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)

    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════
#  HEALTH & ADMIN
# ═══════════════════════════════════════════════════════════════

@app.get("/")
async def health():
    return {"status": "🟢 DietBuddy Pro is alive!", "version": "Pro 1.0", "model": MODEL}


@app.get("/admin/stats")
async def admin_stats():
    return db.get_stats()


@app.get("/admin/users")
async def admin_users():
    return {"users": db.get_all_users()}


@app.get("/admin/chat/{phone}")
async def admin_chat(phone: str, limit: int = 30):
    user = db.get_user(phone)
    messages = db.get_recent_messages(phone, limit=limit)
    today_food = db.get_today_food_logs(phone)
    water = db.get_today_water(phone)
    return {
        "user": user,
        "messages": messages,
        "today_food": today_food,
        "water_today": water,
    }


@app.get("/admin/weekly/{phone}")
async def admin_weekly(phone: str):
    user = db.get_user(phone)
    summary = db.get_weekly_summary_data(phone)
    return {"user": user, "weekly_summary": summary}
