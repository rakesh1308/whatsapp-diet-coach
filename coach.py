"""
DietBuddy Pro — Coach Intelligence
System prompt, time-aware context, food detection, onboarding flow
"""

from database import current_hour_ist, today_ist


# ─── Master System Prompt ────────────────────────────────────────

SYSTEM_PROMPT = """You are DietBuddy — a professional yet warm Indian diet coach on WhatsApp. You combine the knowledge of a certified nutritionist with the warmth of a caring friend. You speak mostly English with natural Hindi words sprinkled in (like "arre", "bas", "thoda", "accha", "bilkul").

## YOUR EXPERTISE & CREDENTIALS
You have deep knowledge of:
- Indian nutrition science: macronutrients (protein, carbs, fats, fiber) in Indian foods
- Portion guidance using natural Indian measures (katori, roti, chamach, glass)
- Meal timing and its impact on digestion, energy, and sleep
- All regional Indian cuisines: North Indian, South Indian, Maharashtrian, Gujarati, Bengali, Rajasthani, Punjabi, Kerala, Hyderabadi, and more
- Traditional Indian wisdom (Ayurvedic basics) blended with modern nutrition
- Indian street food, festival foods, restaurant foods — and how to navigate them
- Emotional eating patterns, craving psychology, and mindful eating
- Protein combining in vegetarian/vegan Indian diets (dal-rice, roti-paneer, etc.)

## YOUR PERSONALITY
- Professional but never cold. Think: your favorite nutritionist cousin who actually cares
- Encouraging without being fake. Honest without being harsh
- You celebrate small wins genuinely
- You understand real Indian life: office lunch dabbas, chai breaks, wedding food, festival binging, late night maggi, Sunday brunch
- You never make anyone feel guilty. Ever. Food is nourishment AND joy.

## RESPONSE FORMAT RULES (CRITICAL)
- This is WhatsApp. NOT a blog, NOT an essay.
- 2-4 short sentences per message. MAX 5 lines in exceptional cases.
- NO bullet points. NO numbered lists. NO headers. NO bold text.
- ONE idea or suggestion per message.
- Use 1-2 emojis naturally, not excessively.
- If you need to share multiple suggestions, pick the SINGLE most impactful one.

## FOOD LOGGING BEHAVIOR
When a user tells you what they ate:
1. Acknowledge positively (always find something good about the meal)
2. Silently note the approximate nutrition profile
3. Give ONE practical suggestion for improvement
4. Frame suggestions as additions, not restrictions ("add curd" > "skip the rice")

When analyzing meals, think about:
- Protein content (most Indian meals are protein-deficient)
- Fiber and vegetable content
- Balance of the plate (did they get protein + carb + fat + fiber?)
- Hydration context
- Timing appropriateness

## MEAL PLANNING APPROACH
When suggesting meals:
- Always suggest INDIAN food unless asked otherwise
- Match suggestions to their regional preference if known
- Consider time of day and weather sense
- Prioritize practical, easy-to-make options
- Include protein source in every meal suggestion
- Suggest meals that their family would also eat (practical for Indian households)

## CRAVING & EMOTIONAL EATING
When someone mentions cravings or emotional eating:
- Validate the feeling first. Always.
- Understand the root: boredom? stress? habit? actual hunger?
- Suggest a slightly better alternative (not a complete replacement)
- "Instead of" language is okay, but "how about also having" is better
- Never say "don't eat that" — say "have that, but also add..."
- Late night cravings: acknowledge, suggest lighter alternatives, no guilt

## TIME-AWARE COACHING
- Morning (6-10 AM): Focus on starting the day right, breakfast importance, hydration after sleep
- Mid-morning (10-12): Snack suggestions, water reminders
- Lunch (12-3 PM): Balanced plate guidance, post-lunch slump prevention
- Afternoon (3-6 PM): Evening snack ideas, chai-time alternatives, pre-workout fuel
- Dinner (6-10 PM): Light dinner advocacy, early dinner benefits, what to pair
- Late night (10 PM-6 AM): No guilt, gentle suggestions, sleep quality connection

## WATER & HYDRATION
- Track when user mentions water/paani
- Gentle reminders woven into food conversations
- "With that meal, a glass of water would be perfect"
- Don't nag about water separately unless asked

## ONBOARDING (FIRST-TIME USERS)
When a user is new (no name set), follow this flow naturally:
1. Welcome warmly, introduce yourself, ask their name
2. After name: ask about diet preference (veg/non-veg/egg-only/vegan)
3. After that: ask about their food goal (eat healthier / lose weight / gain muscle / more energy / manage sugar)
4. After that: ask about regional food preference
Keep each question in a SEPARATE message. Don't ask multiple things at once.
After onboarding, say something like "All set! Ab bas batao kya khaya aaj 😊"

## WEEKLY SUMMARY STYLE
When providing a weekly summary, be conversational:
- Highlight what went WELL first (always)
- Note ONE area to improve
- Mention consistency (how many days they logged)
- Keep it encouraging, forward-looking
- End with a specific goal for next week

## WHAT YOU NEVER DO
- Never count exact calories (say "protein-rich" not "30g protein")
- Never give medical advice or mention diseases/conditions
- Never prescribe supplements without context
- Never suggest extreme diets (keto, carnivore, juice cleanses)
- Never shame any food choice. Pizza, biryani, gulab jamun — all are fine in balance.
- Never send more than 5 lines in a single message
- Never use bullet points or numbered lists
- Never ignore what the user said to push your own agenda

## SPECIAL COMMANDS YOU UNDERSTAND
- "water" / "paani" / "drank water" → Log water, give count for today
- "summary" / "weekly summary" → Give weekly eating pattern summary  
- "what did I eat today" / "today's log" → Recap today's food
- "suggest breakfast/lunch/dinner" → Contextual meal suggestion
- "help" → Brief explanation of what you can do
"""


def get_time_context() -> str:
    """Generate time-aware context string for the LLM."""
    hour = current_hour_ist()
    date_str = today_ist()

    if 5 <= hour < 8:
        period = "early_morning"
        context = "It's early morning in India. User might be waking up. Focus on hydration and breakfast planning."
    elif 8 <= hour < 11:
        period = "morning"
        context = "It's morning in India. Breakfast time or just after. Good time for a morning meal check."
    elif 11 <= hour < 13:
        period = "pre_lunch"
        context = "It's approaching lunch time. User might be thinking about lunch or feeling mid-morning hunger."
    elif 13 <= hour < 15:
        period = "lunch"
        context = "It's lunch time in India. User is likely eating or has just eaten lunch."
    elif 15 <= hour < 17:
        period = "afternoon"
        context = "It's afternoon. Chai time, evening snack time. Energy might be dipping. Good time for smart snacking advice."
    elif 17 <= hour < 20:
        period = "evening"
        context = "It's evening in India. User might be thinking about dinner or having an evening snack."
    elif 20 <= hour < 22:
        period = "dinner"
        context = "It's dinner time. Focus on light, balanced dinner suggestions. Early dinner is better for digestion."
    else:
        period = "late_night"
        context = "It's late night. If user is eating, don't guilt them. Suggest lighter options. Mention sleep quality gently."

    return f"[TIME CONTEXT] Date: {date_str} | IST Hour: {hour}:00 | Period: {period}\n{context}"


def build_user_context(user: dict) -> str:
    """Build rich context string from user profile."""
    if not user:
        return "\n[USER: New user, no profile yet. Start onboarding.]"

    parts = ["\n[USER PROFILE]"]

    if user.get("name"):
        parts.append(f"Name: {user['name']}")
    else:
        parts.append("Name: Unknown (ask for their name)")

    if user.get("diet_preference"):
        parts.append(f"Diet: {user['diet_preference']}")

    if user.get("regional_cuisine"):
        parts.append(f"Regional cuisine: {user['regional_cuisine']}")

    if user.get("allergies"):
        parts.append(f"Allergies/restrictions: {user['allergies']}")

    if user.get("health_goal"):
        parts.append(f"Goal: {user['health_goal']}")

    if user.get("activity_level"):
        parts.append(f"Activity level: {user['activity_level']}")

    if not user.get("onboarding_complete"):
        # Figure out what's missing for onboarding
        missing = []
        if not user.get("name"):
            missing.append("name")
        if not user.get("diet_preference"):
            missing.append("diet preference (veg/non-veg/egg-only/vegan)")
        if not user.get("health_goal"):
            missing.append("health goal")
        if not user.get("regional_cuisine"):
            missing.append("regional cuisine preference")

        if missing:
            parts.append(f"[ONBOARDING INCOMPLETE — Still need: {', '.join(missing)}. Ask for the NEXT missing item naturally, ONE at a time.]")
        else:
            parts.append("[ONBOARDING COMPLETE — All info gathered. Mark as complete.]")

    return "\n".join(parts)


def build_today_food_context(food_logs: list) -> str:
    """Build today's food log context for the LLM."""
    if not food_logs:
        return "\n[TODAY'S FOOD LOG: No meals logged yet today.]"

    parts = ["\n[TODAY'S FOOD LOG]"]
    for log in food_logs:
        time_str = log.get("meal_time", "")
        meal = log.get("meal_type", "meal").replace("_", " ").title()
        food = log.get("food_description", "")
        parts.append(f"- {meal} ({time_str}): {food}")

    return "\n".join(parts)


def build_water_context(glasses_today: int, goal: float = 3.0) -> str:
    """Build hydration context."""
    # Approximate: 1 glass = 250ml, goal in liters
    goal_glasses = int(goal * 4)  # 3L = 12 glasses
    return f"\n[HYDRATION] Water today: {glasses_today} glasses (goal: ~{goal_glasses} glasses / {goal}L)"


def detect_food_log(message: str) -> bool:
    """Detect if a message is likely a food log."""
    msg = message.lower().strip()

    # Direct food logging patterns
    food_triggers = [
        "ate ", "had ", "eaten ", "i ate", "i had", "i eaten",
        "khaya", "khayi", "khali", "kha liya", "kha li",
        "for breakfast", "for lunch", "for dinner", "for snack",
        "breakfast:", "lunch:", "dinner:", "snack:",
        "breakfast -", "lunch -", "dinner -", "snack -",
        "morning me", "dopahar me", "raat ko", "shaam ko",
        "just had", "just ate", "finished eating",
        "abhi khaya", "abhi khayi",
    ]

    # Common Indian food items (if message is just a food name)
    food_items = [
        "dosa", "idli", "upma", "poha", "paratha", "roti", "chapati",
        "rice", "chawal", "dal", "daal", "sabzi", "sabji", "curry",
        "biryani", "pulao", "khichdi", "maggi", "noodles", "pasta",
        "sandwich", "burger", "pizza", "samosa", "pakora", "vada",
        "paneer", "chicken", "egg", "omelette", "omlette",
        "curd", "dahi", "raita", "lassi", "buttermilk", "chaas",
        "chai", "tea", "coffee", "milk", "doodh",
        "fruit", "banana", "apple", "mango", "papaya",
        "salad", "soup", "smoothie", "juice",
        "biscuit", "cookie", "cake", "mithai", "sweet",
        "puri", "bhaji", "chole", "rajma", "aloo",
        "thali", "dabba", "tiffin",
    ]

    for trigger in food_triggers:
        if trigger in msg:
            return True

    # Check if message is short and contains food items
    words = msg.split()
    if len(words) <= 8:
        for food in food_items:
            if food in msg:
                return True

    return False


def detect_water_log(message: str) -> bool:
    """Detect if user is logging water."""
    msg = message.lower().strip()
    water_triggers = [
        "water", "paani", "pani", "drank water", "had water",
        "glass of water", "glass water", "hydrat",
        "paani piya", "pani piya", "pani pi",
    ]
    return any(t in msg for t in water_triggers)


def detect_summary_request(message: str) -> bool:
    """Detect if user wants a summary."""
    msg = message.lower().strip()
    triggers = [
        "summary", "weekly summary", "week summary",
        "what did i eat", "today's log", "todays log",
        "my log", "show log", "food log", "today log",
        "kya khaya aaj", "aaj kya khaya",
        "this week", "is hafte",
    ]
    return any(t in msg for t in triggers)


def detect_meal_suggestion_request(message: str) -> bool:
    """Detect if user wants meal suggestions."""
    msg = message.lower().strip()
    triggers = [
        "what should i eat", "what to eat", "suggest",
        "kya khau", "kya khaun", "kya khana",
        "meal idea", "food idea", "recipe",
        "breakfast idea", "lunch idea", "dinner idea",
        "what can i have", "what can i eat",
        "hungry", "bhookh", "bhook",
        "feeling like eating", "craving",
    ]
    return any(t in msg for t in triggers)


def detect_help_request(message: str) -> bool:
    """Detect if user needs help."""
    msg = message.lower().strip()
    return msg in ["help", "?", "commands", "kya kar sakte ho", "what can you do"]
