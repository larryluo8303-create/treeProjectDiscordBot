# BigTree Discord RAG Bot

Production Discord bot for a 5,000+ member stock-discussion community. It answers member questions with **RAG** over the channel owner's historical posts, routes low-confidence or high-risk answers to **human review**, and includes ops automation (Jin10 news, daily/weekly summaries, YouTube lessons, promotions) plus optional web/mobile clients.

**Stack:** Python, discord.py, OpenAI (GPT / embeddings / Whisper), ChromaDB, FastAPI, React, Expo  
**Docs:** [docs/README.md](./docs/README.md) (Chinese & English) · [Feature list](./docs/en/features/FEATURE_LIST.md) · [Project guide](./docs/en/architecture/PROJECT_GUIDE.md) · [Setup](./docs/en/getting-started/SETUP_AND_TEST.md)

### Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # set DISCORD_BOT_TOKEN, OPENAI_API_KEY, OWNER_USER_ID, TARGET_CHANNEL_IDS
python -m ingestion.ingest
python -m bot.main
```

### Highlights

- RAG retrieve → generate → multi-gate confidence routing (auto-reply vs owner DM Approve / Edit / Reject)
- Live learning from owner posts, review outcomes, and YouTube transcripts
- News feed with offline backfill, scheduled summaries, AutoMod, feature flags / canary rollout
- FastAPI management + public client APIs for admin and end-user apps

> Do not commit real tokens. Use `.env` locally; only `.env.example` is in the repo.
