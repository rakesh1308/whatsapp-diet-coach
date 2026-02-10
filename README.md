# 🥗 DietBuddy — WhatsApp AI Diet Coach

A WhatsApp-based AI diet coach that helps people eat better through simple awareness and gentle guidance — no calorie counting, no guilt, no complex plans. Built for Indian food context.

## Architecture

```
User (WhatsApp) → Meta Cloud API → Zeabur (FastAPI) → HuggingFace Llama 3
                                         ↕
                                    SQLite (Memory)
```

**How memory works:** Each user is identified by phone number. All messages are stored in SQLite. Before every AI response, the last 15 messages are loaded as context. The LLM is stateless — the backend creates the illusion of memory.

---

## 🚀 Deploy to Zeabur (Step by Step)

### Step 1: Push Code to GitHub

```bash
cd whatsapp-diet-coach
git init
git add .
git commit -m "DietBuddy MVP"
git remote add origin https://github.com/YOUR_USERNAME/whatsapp-diet-coach.git
git push -u origin main
```

### Step 2: Deploy on Zeabur

1. Go to [dash.zeabur.com](https://dash.zeabur.com)
2. Create a new project
3. Click **Add Service** → **Deploy from GitHub** → Select your repo
4. Zeabur auto-detects the Dockerfile and deploys

### Step 3: Set Environment Variables on Zeabur

In your Zeabur service → **Variables** tab, add:

| Variable | Value |
|----------|-------|
| `HF_API_KEY` | Your HuggingFace API key |
| `HF_MODEL` | `meta-llama/Meta-Llama-3-8B-Instruct` |
| `WHATSAPP_TOKEN` | From Meta Dashboard (Step 5) |
| `PHONE_NUMBER_ID` | From Meta Dashboard (Step 5) |
| `VERIFY_TOKEN` | `dietbuddy_verify_2024` (or any string you choose) |
| `DB_PATH` | `/tmp/dietbuddy.db` |

### Step 4: Generate a Public Domain

1. In your Zeabur service → **Networking** tab
2. Click **Generate Domain** (you'll get something like `dietbuddy-xyz.zeabur.app`)
3. Note this URL — you need it for Meta webhook setup

### Step 5: Meta Developer Dashboard Setup

#### 5a. Create a Meta App
1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps/)
2. **Create App** → Select **Other** → Select **Business** → Next
3. Name it "DietBuddy" → Create App

#### 5b. Add WhatsApp Product
1. In your app dashboard, find **Add Products**
2. Find **WhatsApp** → Click **Set Up**

#### 5c. Get Your Credentials
From the **API Setup** / **Getting Started** page:
- Copy **Phone Number ID** → add to Zeabur as `PHONE_NUMBER_ID`
- Copy **Temporary Access Token** → add to Zeabur as `WHATSAPP_TOKEN`

⚠️ Temporary token expires in ~24 hours. For long-term use, create a **System User** token (see below).

#### 5d. Configure Webhook
1. Go to **WhatsApp** → **Configuration** in sidebar
2. Under **Webhook**, click **Edit**
3. Enter:
   - **Callback URL:** `https://YOUR-ZEABUR-DOMAIN.zeabur.app/webhook`
   - **Verify Token:** `dietbuddy_verify_2024` (must match your env var)
4. Click **Verify and Save**
5. Under **Webhook Fields**, subscribe to: **`messages`**

#### 5e. Add Test Phone Numbers
1. On the **API Setup** page, under **Send and receive messages**
2. Click **Manage phone number list**
3. Add your family members' phone numbers (up to 5 on free tier)
4. Each person will receive a verification code on WhatsApp

### Step 6: Test It!

1. Open WhatsApp on a test phone number
2. Find the Meta test business number (shown in your dashboard)
3. Send: "Hi"
4. You should get a reply from DietBuddy! 🎉

---

## 📱 The WhatsApp Number Question

**Q: Which number do my family members message?**

A: Meta gives you a **test phone number** (visible in your developer dashboard). Your family messages THIS number. It will show up as a business account. On the free tier, you can add up to 5 recipient phone numbers.

**For production:** You can either keep Meta's test number, or migrate to your own business number (requires Business Verification).

---

## 🔧 Admin Endpoints

Once deployed, you can check on your bot:

| Endpoint | What it shows |
|----------|---------------|
| `GET /` | Health check |
| `GET /admin/stats` | Total users, messages, active today |
| `GET /admin/users` | All users with message counts |
| `GET /admin/chat/{phone}` | View a specific user's conversation |

Example: `https://your-domain.zeabur.app/admin/stats`

---

## 🔑 Getting a Permanent WhatsApp Token

The temporary token expires in ~24 hours. For your family MVP:

1. Go to **Business Settings** → [business.facebook.com/settings](https://business.facebook.com/settings)
2. **System Users** → **Add**
3. Name: "DietBuddy Bot", Role: Admin
4. **Generate Token** → Select your app → Add permission: `whatsapp_business_messaging`
5. Copy the token → Update `WHATSAPP_TOKEN` in Zeabur variables

This token doesn't expire.

---

## 🗂 Project Structure

```
whatsapp-diet-coach/
├── main.py              # FastAPI app, webhook handlers, AI logic
├── database.py          # SQLite memory layer
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container config for Zeabur
├── zbpack.json          # Zeabur build config
├── .env.example         # Environment variables template
├── .gitignore
└── README.md
```

---

## ⚠️ Important Notes for MVP

1. **SQLite on /tmp**: Data persists as long as the container runs. If Zeabur restarts your service, the DB resets. For proper persistence, add a Zeabur volume mount or switch to Zeabur's PostgreSQL add-on later.

2. **24-hour messaging window**: WhatsApp only lets you reply within 24 hours of the user's last message. Perfect for a diet coach since users message first.

3. **Rate limits**: Free HuggingFace API has rate limits. If you hit them, consider HF Pro ($9/month) or switch to another provider.

4. **No authentication on admin endpoints**: Fine for MVP. Add API key auth before going public.

---

## 🚀 Phase 2 Ideas

- [ ] Persistent database (PostgreSQL on Zeabur)
- [ ] Food photo analysis (image → description → advice)
- [ ] Daily check-in reminders (WhatsApp template messages)
- [ ] Weekly summary reports
- [ ] User preferences (veg/non-veg, allergies, regional cuisine)
- [ ] Swap to GPT-4o-mini or Claude for better quality
- [ ] Landing page + waitlist
