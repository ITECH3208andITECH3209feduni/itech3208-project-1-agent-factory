# Agent Factory — Full Presentation Script
## ITECH3208 · Sprint 2 · Plain English — Word for Word

> **How to use this:** Read it out loud a few times before the day.
> You don't have to say it word for word — but know it well enough
> that you can say it naturally without reading off the screen.
> The *[stage directions]* are in italics — those are actions, not words.

---

---

# SLIDE 1 — TITLE
## Speaker: DILRAJ · 0:00 → 0:30

*[Walk to the front. Click to Slide 1. Face the class.]*

---

"Hi everyone. We're Agent Factory — Team C for ITECH3208.

Sprint 2 is done, and today we're going to show you what we built.

In a nutshell — we made an AI-powered research platform. You can search Amazon for products, find academic papers, check if writing is AI-generated or plagiarised, build advertising campaigns, find suppliers — all from one chat interface, all powered by Claude AI.

We've got five people, and each of us is going to talk about what we personally built. I'll start."

*[Click to Slide 2.]*

---
---

# SLIDE 2 — DILRAJ SINGH
## Speaker: DILRAJ · 0:30 → 1:30

*[Stay at the podium.]*

---

"So I'm Dilraj, I was the lead developer this sprint.

I worked on three things.

**First — the web interface.** Everything you see when you open the app at localhost 8000 — I built that. The dark theme, the chat layout, the cards that show results, all of it. I also built the Literature AI tab so it has two modes — one for searching research papers and one for checking academic integrity — you can switch between them with one click. And I added a file attachment button so you can attach a PDF, a Word document, or an image, and the AI reads the file and uses it in the query.

**Second — seller tools.** Inside the Amazon tab, I built four extra tools: a PPC Campaign Builder that generates a full keyword campaign with bids, an Alibaba Supplier Finder that matches you to verified suppliers, a Product Progress Tracker for Amazon sellers, and a Profit Optimiser that analyses your margins and fees.

**Third — academic integrity.** I built an AI Content Detector that scores how likely a piece of writing is AI-generated, a Plagiarism Scanner that cross-checks text against over a billion web pages, arXiv, and PubMed, and a report export system so you can download results as a PDF or Excel file.

67 Jira tickets — all closed."

*[Look at Dhiman. Click to Slide 3.]*

---
---

# SLIDE 3 — DHIMAN ROY
## Speaker: DHIMAN · 1:30 → 2:30

*[Dhiman walks to the front.]*

---

"Hi, I'm Dhiman and I built the Amazon intelligence layer.

My main job was getting real live data from Amazon. I built a scraper using Playwright — that's a browser automation tool — which goes onto Amazon, loads the product pages, and pulls back prices, ratings, how many reviews a product has, whether it's Prime, and its Best Seller Rank. The problem with scraping Amazon is they block bots, so I also built a fallback — if the scraper gets blocked, the system automatically switches to a paid API called RapidAPI, so results always come through one way or another.

Once we have the products, I built a scoring engine. Every product gets a score from 0 to 100 based on price, rating, number of reviews, and BSR. So instead of just dumping a list of products, the agent tells you which ones are actually good opportunities. I also added caching — if someone searches the same thing twice, it returns instantly from cache instead of scraping again.

On top of that, I wrote the three Claude AI prompt templates — one for searching products, one for comparing them side by side, and one for making recommendations. And I built the REST API endpoints — /api/amazon and /api/literature — and added API key authentication so the endpoints are protected.

31 tickets, everything is live."

*[Look at Prabhjot. Click to Slide 4.]*

---
---

# SLIDE 4 — PRABHJOT SINGH
## Speaker: PRABHJOT · 2:30 → 3:30

*[Prabhjot walks to the front.]*

---

"Hey, I'm Prabhjot and I handled the infrastructure side of things.

My biggest piece of work this sprint was integrating the OpenClaw SDK. OpenClaw is what lets our agent run as a proper service — it handles routing, retries, and keeps the agent alive. I built a wrapper client that connects to OpenClaw and handles retries if it goes down. I built a router called route_query that classifies what the user is asking and sends it to the right skill — Amazon or Literature. I built a skills registry that registers both skills so the router knows what's available. And I built a fallback decorator — basically if OpenClaw is completely unavailable, the agent doesn't crash, it just handles the request directly. That's important for 24/7 uptime. I also wrote a smoke test script and a full README for the OpenClaw setup.

On the DevOps side, I wrote the Dockerfile and the docker-compose file. The docker-compose has proper environment variable injection so you don't hardcode any API keys. I got Docker set up on all of the team's machines. And I wrote documentation for every single environment variable in the README — so anyone can clone the repo and get it running with one command.

27 tickets — infrastructure was solid the whole sprint, no outages."

*[Look at Sahil. Click to Slide 5.]*

---
---

# SLIDE 5 — SAHIL K C
## Speaker: SAHIL · 3:30 → 4:30

*[Sahil walks to the front.]*

---

"Hi, I'm Sahil and I covered testing, CI/CD, and scrum.

On the **testing side** — I built the entire test suite from nothing. I started with a conftest.py file that sets up five shared fixtures — a mock agent, mock Amazon response, mock literature response, a test client, and a database session. Then I wrote five test modules. The routing tests have 12 parametrised test cases that check the classify function routes queries to the right skill. Then separate test files for Amazon, Literature, and the Web UI — five tests each, all using proper mocking with @patch so they don't make real API calls.

I also set up **GitHub Actions** — there's a pytest.yml workflow file that runs the full test suite automatically every time someone pushes to main. So if someone breaks something, we know immediately.

Then I did **manual browser QA** — I went through the live web interface on localhost, ran test queries on both the Amazon and Literature tabs, checked all the error messages and empty states, and wrote up a QA report with pass/fail results.

And I ran our **scrum** the whole sprint — set up and maintained Jira, ran standups, created the sprint burndown chart, facilitated the retrospective, and organised the team for today's demo.

29 tickets closed."

*[Stay at the podium. Click to Slide 7.]*

---
---

# SLIDE 7 — EVERY COMMITMENT DELIVERED
## Speaker: SAHIL · 4:30 → 5:00

*[Sahil stays at the podium.]*

---

"And as a team — this is the full picture.

178 Jira tickets closed. 14 pull requests merged into main. Five team members. Sprint goal — 100% achieved.

Every single workstream on this table was delivered. Literature AI, Amazon intelligence, OpenClaw SDK, the web UI and REST API, SQLite session memory, the test suite and CI/CD pipeline, and the seller tools and integrity checks.

As of this morning, there are zero open tickets. Sprint 2 is complete."

*[Look at Saifur. Click to Slide 6.]*

---
---

# SLIDE 6 — SAIFUR RAHMAN BHUIYAN
## Speaker: SAIFUR · 5:00 → 6:00

*[Saifur walks to the front.]*

---

"Hi, I'm Saifur and I built the Literature research skill and the memory system.

For the **Literature skill** — when you search for a research topic, the app needs to actually find academic papers. I built the arXiv fetcher that queries the arXiv API and pulls papers. I also built the Semantic Scholar client — it searches a separate academic database and it has rate limiting, so I built in automatic retry when it gets a 429 error. The results from both sources get deduplicated so you don't see the same paper twice. Then I built the synthesizer — it takes all the papers and sends them to Claude Haiku, and Claude writes a single paragraph that summarises the key findings, identifies research gaps, and lists citations. I also built the PaperCard dataclass that formats each paper into a clean result card with title, authors, year, abstract, source, and citation count.

For the **memory system** — before I got to it, the agent was saving everything to a flat JSON file, which is fine for testing but not production. I replaced it with SQLite. I wrote the database schema — two tables, sessions and messages, with foreign key constraints and indexes. Then I built the SessionMemory class with methods for creating a session, adding a message, and retrieving history. And I wired it into the agent so every conversation is saved and survives restarts. No data loss.

I also wrote the demo script — it runs a healthcare AI query end to end and shows the full synthesis output.

24 tickets, all shipped."

*[Saifur sits. Dilraj walks back to the front.]*

---
---

# SLIDE 8 — LIVE DEMO
## Speaker: DILRAJ · 6:00 → 8:30

*[Dilraj is at the podium. Browser is open at localhost:8000.]*

---

### Demo 1 — Literature Search (6:00 → 6:45)

"Let me show you the app live.

I'm on the Literature AI tab. I'll search for 'transformers in NLP' — that's a real academic topic."

*[Type "transformers in NLP" and press Enter. Wait for results.]*

"So you can see it's querying arXiv and Semantic Scholar at the same time. Each card shows the paper title, the authors, what year it was published, how many citations it has, and a short abstract. And up at the top — that's Claude's synthesis. It read all ten papers and wrote that summary paragraph itself. It also flags research gaps — areas that haven't been studied yet."

---

### Demo 2 — File Attachment (6:45 → 7:15)

"Now let me show the file attachment."

*[Click the 📎 button on the left of the input box. Select a PDF file.]*

"I'm attaching a PDF. Watch — it reads the file right here in the browser using PDF.js. There's no file upload, no server round trip, it extracts the text client side and includes it in the query. So you could attach a paper you already have and ask the AI questions about it."

---

### Demo 3 — Amazon PPC Builder (7:15 → 8:00)

"Now I'll switch to the Amazon tab."

*[Click Amazon Seller AI in the sidebar.]*

"I'll use the PPC Builder."

*[Type "build ppc campaign for: yoga mat" and press Enter.]*

"So this is building a full Amazon Sponsored Products campaign for yoga mats. Each card is a keyword — it tells you the keyword, the match type — broad, phrase, or exact — the suggested bid in dollars, and the estimated clicks per day. If you were an actual Amazon seller you'd be paying a consultant to do this. It takes seconds here."

---

### Demo 4 — Integrity Check (8:00 → 8:30)

"Last one — the integrity checker."

*[Click Literature AI in the sidebar. Click Integrity Check tab.]*

"Paste any text in here — you could paste an essay, an assignment, anything — and it runs two checks. First, AI detection — it measures perplexity and burstiness, which are signals that AI-generated text tends to have, and gives you a probability score. Second, plagiarism — it cross-checks the phrases against web pages, arXiv, and PubMed."

*[Click to Slide 9.]*

---
---

# SLIDE 9 — SPRINT 3 ROADMAP
## Speaker: DILRAJ · 8:30 → 9:55

---

"So where are we going next.

Sprint 2 built the engine — the AI agents are working, the web UI is live, everything is tested and deployed. Sprint 3 is about putting it in front of real users.

The agent is going to run 24/7 on a Mac Mini using OpenClaw — always on, always available.

And we're building what we're calling an **AI Receptionist**. Think of it as an automated call centre agent. Here's what it does:

**Telegram bot.** You text it from your phone like you'd text a friend. No browser, no login, no app to install. It's just a chat.

**Smart intent router.** You don't need to use commands or menus. You just say what you want — 'I need to book an appointment' or 'what are your prices' — and the AI figures out what you mean and routes it to the right place.

**Knowledge base.** Each business client uploads their own FAQs, services, and pricing. The agent answers from that data — it's not making things up, it's reading from the actual business information.

**Appointment booking.** It connects to Google Calendar and books appointments in real time. The customer gets a confirmation, the business gets the booking — no human needed.

**Escalation engine.** If someone asks something too complex or wants to speak to a person, the agent hands it over to a human with the full conversation history attached. It never loses context.

**Multi-client setup.** One platform, but each business client gets their own isolated configuration. So you could run this for ten different businesses from the same system.

The Amazon and Literature agents from Sprint 2 are the foundation. Sprint 3 turns the whole thing into a product that a real business could use."

*[Click to Slide 10.]*

---
---

# SLIDE 10 — THANK YOU
## Speaker: DILRAJ · 9:55 → 10:00

---

"Thank you."

*[Hold. Smile. Wait for the lecturer.]*

---
---

## 📋 ONE-PAGE CUE CARD
*(Print this. One copy each. Hold it during the presentation.)*

```
╔══════════════════════════════════════════════════════╗
║         AGENT FACTORY — SPRINT 2 CUE CARD           ║
╠══════════════════════════════════════════════════════╣
║ 0:00  DILRAJ    Intro — "Hi everyone, we're Agent    ║
║                Factory, Team C for ITECH3208…"       ║
║                                                      ║
║ 0:30  DILRAJ    Web UI · Seller Tools · Integrity    ║
║                "I'm Dilraj, lead developer…"         ║
║                                                      ║
║ 1:30  DHIMAN    Amazon scraper · scorer · REST API   ║
║                "I'm Dhiman, Amazon intelligence…"    ║
║                                                      ║
║ 2:30  PRABHJOT  OpenClaw SDK · Docker · DevOps       ║
║                "I'm Prabhjot, infrastructure…"       ║
║                                                      ║
║ 3:30  SAHIL     Tests · CI/CD · Scrum                ║
║                "I'm Sahil, testing and scrum…"       ║
║                                                      ║
║ 4:30  SAHIL     Delivery stats — STAYS AT PODIUM     ║
║                "178 tickets, 100% complete…"         ║
║                                                      ║
║ 5:00  SAIFUR    Literature skill · SQLite memory     ║
║                "I'm Saifur, Literature and memory…"  ║
║                                                      ║
║ 6:00  DILRAJ    LIVE DEMO — open browser             ║
║                1. Search "transformers in NLP"       ║
║                2. Attach a PDF                       ║
║                3. PPC "build ppc campaign for:       ║
║                         yoga mat"                    ║
║                4. Integrity check (paste text)       ║
║                                                      ║
║ 8:30  DILRAJ    Sprint 3 — AI Receptionist           ║
║                Telegram · Router · KB · Calendar     ║
║                Escalation · Multi-client             ║
║                                                      ║
║ 9:55  DILRAJ    "Thank you."                         ║
╚══════════════════════════════════════════════════════╝
```

---

## ⚠️ IF THE DEMO BREAKS

Say this:
> "The server seems to be taking a moment — let me show you a screenshot while it loads."

Have these ready as browser tabs before you walk in:
- A screenshot of the Literature results page
- A screenshot of a PPC campaign result
- A screenshot of the Integrity check result

---

## 💡 TIPS FOR THE DAY

- **Don't read off the screen.** Know your section well enough to talk to the room.
- **Speak slower than you think you need to.** Everyone always rushes.
- **Each person: walk up, say your name first, then go.** Don't wait to be introduced.
- **Sahil: don't sit down after your slide** — go straight into the delivery stats, it flows naturally.
- **Dilraj: during the demo, narrate what's happening on screen** — don't let silence sit.
- **If someone finishes early** — pause, breathe, don't rush to the next person.

---

*Agent Factory · Sprint 2 · Federation University · 2026*
