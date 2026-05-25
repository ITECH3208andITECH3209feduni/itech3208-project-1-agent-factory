# Agent Factory — Sprint 2 Presentation Run Sheet
## ITECH3208 · Federation University · 10-Minute Class Presentation

---

## ⏱ Timing Overview

| Clock | Duration | Slide | Speaker | Section |
|-------|----------|-------|---------|---------|
| 0:00  | 0:30     | 1 — Title        | **Dilraj**   | Opening & intro |
| 0:30  | 1:00     | 2 — Dilraj       | **Dilraj**   | Web UI · Seller Tools · Integrity |
| 1:30  | 1:00     | 3 — Dhiman       | **Dhiman**   | Amazon Intelligence |
| 2:30  | 1:00     | 4 — Prabhjot     | **Prabhjot** | OpenClaw SDK · Docker |
| 3:30  | 1:00     | 5 — Sahil        | **Sahil**    | Test Suite · CI/CD · Scrum |
| 4:30  | 0:30     | 7 — Delivery     | **Sahil**    | Sprint metrics — 178 tickets |
| 5:00  | 1:00     | 6 — Saifur       | **Saifur**   | Literature Skill · SQLite Memory |
| 6:00  | 2:30     | 8 — Live Demo    | **Dilraj**   | Live browser demo |
| 8:30  | 1:25     | 9 — Sprint 3     | **Dilraj**   | What's coming next |
| 9:55  | 0:05     | 10 — Thank You   | **Dilraj**   | Thank you |

---

## 🎙 SLIDE 1 — Title (0:00 → 0:30) · DILRAJ

> **Dilraj walks to the front, clicks to Slide 1.**

**Script:**
> "Good [morning/afternoon] everyone. We're Team C — Agent Factory.
> This is our Sprint 2 showcase for ITECH3208.
> Over the past two weeks we built a fully working AI research platform —
> it searches Amazon, finds academic papers, checks plagiarism, builds PPC campaigns,
> and now accepts file attachments — all powered by Claude AI.
> Each of us will take you through what we personally built. Let's go."

*[Click to Slide 2 — stay at podium]*

---

## 🎙 SLIDE 2 — Dilraj Singh (0:30 → 1:30) · DILRAJ

**Script:**
> "I'm Dilraj, lead developer. I handled three main areas.
>
> First — the **Web UI**. I built the entire chat interface you'll see in the demo —
> dark theme, card results, the dual-panel Literature AI with search and integrity modes,
> and the file attachment system where you can drop in a PDF, Word doc, or image
> and the AI reads it for you.
>
> Second — **Seller Intelligence Tools**. I built four tools inside the Amazon tab:
> PPC Campaign Builder that generates keyword lists with bids,
> Alibaba Supplier Finder, Product Progress Tracker, and a Profit Optimiser.
>
> Third — **Academic Integrity**. I built the AI Content Detector,
> the Plagiarism Scanner that cross-checks against over a billion web pages,
> and PDF and Excel export so you can download any result.
>
> 67 Jira tickets closed — all done."

*[Nod to Dhiman — click to Slide 3]*

---

## 🎙 SLIDE 3 — Dhiman Roy (1:30 → 2:30) · DHIMAN

> **Dhiman steps forward.**

**Script:**
> "I'm Dhiman, I led the Amazon intelligence layer.
>
> The core of my work was the **scraper pipeline** —
> I built an async Playwright scraper that pulls live Amazon data:
> prices, ratings, Prime status, BSR ranks.
> When Amazon blocks the scraper, it automatically falls back to RapidAPI —
> so results always come through.
>
> On top of that I built the **AI scoring engine** — every product gets
> a 0 to 100 opportunity score calculated from price, rating, review count and BSR,
> and results are cached using an MD5 TTL cache so repeat searches are instant.
>
> I also built the three Claude prompt templates — Search, Compare, Recommend —
> and wired up the REST API endpoints: /api/amazon and /api/literature,
> plus the API key authentication middleware.
>
> 31 tickets closed, everything in production."

*[Nod to Prabhjot — click to Slide 4]*

---

## 🎙 SLIDE 4 — Prabhjot Singh (2:30 → 3:30) · PRABHJOT

> **Prabhjot steps forward.**

**Script:**
> "I'm Prabhjot, I handled infrastructure and the OpenClaw SDK integration.
>
> My biggest Sprint 2 deliverable was the **OpenClaw integration** —
> I built a full wrapper client with connect, execute, and retry logic,
> a route_query router with classify, a skills registry that registers
> both Amazon and Literature skills, and a fallback decorator so the agent
> never crashes if OpenClaw is unavailable.
> That's what lets this agent run 24/7 on a Mac Mini.
>
> On the DevOps side, I wrote the Dockerfile and docker-compose file
> with proper environment variable injection,
> set up Docker across all team machines,
> and documented every .env variable in the README
> so the whole team could run the project with one command.
>
> 27 tickets — infrastructure solid the whole sprint."

*[Nod to Sahil — click to Slide 5]*

---

## 🎙 SLIDE 5 — Sahil K C (3:30 → 4:30) · SAHIL

> **Sahil steps forward.**

**Script:**
> "I'm Sahil, I owned quality assurance, testing, and scrum.
>
> On the **test engineering side**, I wrote the entire test suite from scratch —
> a conftest.py with five fixtures, then five test modules:
> routing tests with 12 parametrised cases, Amazon tests, Literature tests,
> and Web UI tests using FastAPI's TestClient.
> I also set up the GitHub Actions CI/CD pipeline —
> pytest runs automatically on every push to main.
>
> I then did **live browser QA** — manually verified the Amazon and Literature
> Web UI on localhost, confirmed results, error messages, and edge cases,
> and wrote up the QA report with screenshots.
>
> And I ran all our **scrum ceremonies** — set up Jira, ran standups,
> created the sprint burndown chart, facilitated the retrospective,
> and prepped the team for this demo.
>
> 29 tickets closed."

*[Sahil stays at podium — click to Slide 7]*

---

## 🎙 SLIDE 7 — Every Commitment Delivered (4:30 → 5:00) · SAHIL

> **Sahil stays at podium — this is his slide too.**

**Script:**
> "And as a full team — 178 Jira tickets closed, 14 pull requests merged,
> 5 members, 100% sprint goal achieved.
>
> Every workstream delivered: Literature AI, Amazon Intelligence, OpenClaw SDK,
> Web UI, SQLite memory, test suite and CI/CD, seller tools, integrity checks.
>
> Nothing left open. Sprint 2 is complete."

*[Nod to Saifur — click to Slide 6]*

---

## 🎙 SLIDE 6 — Saifur Rahman Bhuiyan (5:00 → 6:00) · SAIFUR

> **Saifur steps forward.**

**Script:**
> "I'm Saifur, I built the Literature research skill and the memory layer.
>
> For the **Literature skill**, I built the full pipeline from scratch —
> an arXiv fetcher, a Semantic Scholar API client with 429 rate-limit retry,
> a deduplication layer, and a Claude Haiku synthesizer that turns
> ten papers into a single synthesis paragraph with research gaps and citations.
> I also built the PaperCard dataclass that formats results into clean cards.
>
> For **memory**, I replaced the old flat JSON file with a proper SQLite database —
> I wrote the schema with sessions and messages tables, foreign key constraints,
> and indexes. Then I built the SessionMemory class with create_session,
> add_message, and get_history, and wired it into the agent
> so every conversation persists across restarts with zero data loss.
>
> I also wrote the healthcare AI demo script that shows the full
> Literature pipeline end to end.
>
> 24 tickets, all shipped."

*[Saifur sits — Dilraj returns to podium — click to Slide 8]*

---

## 🎙 SLIDE 8 — Live Demo (6:00 → 8:30) · DILRAJ

> **⚠️ Pre-demo checklist — do this BEFORE the presentation:**
> - [ ] Server running: `python3 -m app.web_ui.main` at localhost:8000
> - [ ] Browser tab open and ready at http://localhost:8000
> - [ ] Test query pre-typed: "transformers in NLP"
> - [ ] Second query ready: "build ppc campaign for: yoga mat"
> - [ ] A sample PDF ready to attach (any paper PDF)

**Demo flow — 2 min 30 sec:**

### Demo 1 — Literature Search (45 sec)
> "Let me show you the Literature AI tab."

*[Click Literature AI in sidebar]*

> "I'll search for 'transformers in NLP'."

*[Type and hit Enter — wait for results]*

> "You can see it's pulling from arXiv and Semantic Scholar simultaneously,
> returning paper cards with titles, authors, year, citations —
> and Claude synthesises all of them into that summary at the top."

---

### Demo 2 — File Attachment (30 sec)
> "Now watch the attachment system."

*[Click the 📎 button, attach a PDF]*

> "I'll attach a PDF. It extracts the full text client-side using PDF.js —
> no upload, no server round-trip — and sends the content with the query."

---

### Demo 3 — Amazon PPC Builder (45 sec)
> "Now switching to Amazon Seller AI."

*[Click Amazon Seller AI in sidebar]*

> "I'll build a PPC campaign."

*[Type "build ppc campaign for: yoga mat" — hit Enter]*

> "It generates a full Sponsored Products campaign —
> keywords, match types, suggested bids, estimated clicks per day.
> This would take a human seller hours. Done in seconds."

---

### Demo 4 — Integrity Check (30 sec)
> "Finally, the Academic Integrity checker."

*[Click Literature AI → Integrity Check tab]*

> "Paste any text and it runs AI detection —
> perplexity score, burstiness score, probability it was AI-generated,
> and a plagiarism cross-check against the web."

*[Click to Slide 9]*

---

## 🎙 SLIDE 9 — Sprint 3 Roadmap (8:30 → 9:55) · DILRAJ

**Script:**
> "For Sprint 3, we're taking this further.
>
> Both agents are now fully live — the agent will run 24/7 on a Mac Mini
> using OpenClaw. And we're building something new on top:
> an **AI Receptionist** — an automated call centre agent.
>
> It will have a Telegram bot so you can talk to your agents from your phone,
> no browser needed.
> A smart intent router that reads your message and routes it to the right agent —
> no commands, no menus, just natural language.
> A knowledge base you can upload your FAQs, pricing, and services to —
> so the agent answers from your real business data.
> Appointment booking straight into Google Calendar — instant confirmation,
> no human needed.
> An escalation engine that hands complex cases to a human
> with the full conversation summary — it never drops context.
> And a multi-client setup — one platform, configured independently
> for multiple business clients.
>
> Sprint 2 built the engine. Sprint 3 turns it into a product."

*[Click to Slide 10]*

---

## 🎙 SLIDE 10 — Thank You (9:55 → 10:00) · DILRAJ

**Script:**
> "Thank you."

*[Hold slide — wait for applause / questions from lecturer]*

---

## 📋 Quick Reference Cue Card
*(Print this and hold during the presentation)*

```
0:00  DILRAJ    → Intro (30s)
0:30  DILRAJ    → Own slide (1min)
1:30  DHIMAN    → Own slide (1min)
2:30  PRABHJOT  → Own slide (1min)
3:30  SAHIL     → Own slide (1min)  ← stays at podium
4:30  SAHIL     → Delivery stats (30s)
5:00  SAIFUR    → Own slide (1min)
6:00  DILRAJ    → Live demo (2min 30s)
          Demo 1: Literature search "transformers in NLP"
          Demo 2: Attach a PDF
          Demo 3: PPC "build ppc campaign for: yoga mat"
          Demo 4: Integrity check
8:30  DILRAJ    → Sprint 3 roadmap (1min 25s)
9:55  DILRAJ    → "Thank you." (5s)
```

---

## ⚠️ Contingency Plan (if demo fails)

If the server is down or internet is slow:
> "We have the demo recorded — let me show you the screenshots."

Keep these browser tabs open as backup:
- Screenshot of Literature results
- Screenshot of PPC campaign output
- Screenshot of Integrity check result

---

*Run sheet prepared by Agent Factory · Sprint 2 · Federation University · 2026*
