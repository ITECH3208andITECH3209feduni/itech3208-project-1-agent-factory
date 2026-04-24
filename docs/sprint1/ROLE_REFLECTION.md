# Agent Factory — Sprint 1 Role Reflection

**Course:** ITECH3208 / ITECH3209 — Federation University  
**Sprint:** Sprint 1 — 16 April 2026 to 25 April 2026  
**Compiled by:** Dilraj Singh (Product Owner)

Each team member reflects on their role in Sprint 1: what they contributed, what they learned, and what they would approach differently in future sprints.

---

## Dilraj Singh — Product Owner

**What I did this sprint:**  
As Product Owner, I managed the sprint backlog across 76 tickets in Jira, configured the Claude API key and validated the routing logic across 5 diverse prompts (all 5 routed correctly), fixed the 7 bugs raised by Sahil in the QA pass (PROJ-81), and conducted the final MVP review, approving the agent for sprint review with a GO decision. I also coordinated the showcase presentation, team documentation, and all Jira epic closures.

**What I learned:**  
I learned how critical it is to define acceptance criteria before a ticket moves into development, not during QA. Several of the bugs Sahil found were preventable with clearer definition of done upfront. I also gained hands-on experience with the Claude API routing architecture and developed confidence managing a full Scrum backlog from scratch.

**What I would do differently:**  
In Sprint 2, I would set up the API key and environment configuration in the very first week rather than leaving it until routing test time. A shared .env template committed to the repo would save the team setup time and reduce environment-related bugs.

---

## Dhiman Roy — Lead Developer

**What I did this sprint:**  
I built the core of Agent Factory from the ground up: the main agent loop (main.py), the orchestrator that routes queries to skills, the formatter that renders Markdown output, and the memory module that persists session history to memory.json. I independently verified all functionality on my machine across 5 test queries, and wrote the Spec-Driven Development plan documenting both skill specifications.

**What I learned:**  
I learned how to structure a multi-module Python project cleanly — separating concerns between the orchestrator, skills, formatter, and memory. The retry logic for Semantic Scholar rate limits taught me practical resilience patterns. Working with the Claude API for intent classification was new and interesting — seeing how a language model routes queries in real time.

**What I would do differently:**  
I would write unit tests for the orchestrator routing logic from day one rather than relying solely on manual testing. Automated tests would have caught the routing edge cases earlier and made the QA pass smoother.

---

## Sahil K C — Scrum Master

**What I did this sprint:**  
I ran all Sprint 1 ceremonies: sprint planning, daily standups, sprint review, and retrospective. I maintained the Jira board, created all tickets at sprint start (including 10 new tickets per the SDD plan), tracked burn-down, and chose Python 3.12 as the project stack. I ran the full integration QA pass — 10 routing queries covering both skills — and raised 7 bug subtasks (PROJ-81 group) that Dilraj then fixed.

**What I learned:**  
I learned that Scrum ceremonies have real value when the team uses them to surface blockers early rather than just report status. The QA pass was the most valuable thing I did — finding 7 bugs before the showcase rather than during it. I also learned that Jira setup needs to happen on day one, not midway through the sprint.

**What I would do differently:**  
I would create a sprint template in Jira before the sprint starts so ticket creation is faster and more consistent. I would also run a mini QA pass at the midpoint of the sprint rather than only at the end, so bugs are caught with more time to fix them.

---

## Prabhjot Singh — Developer (Integrations)

**What I did this sprint:**  
I connected the three academic APIs — arXiv, Semantic Scholar, and PubMed — to the literature research skill, and verified that the agent returns live results from all three sources. I set up Docker Desktop on all team machines, configured the NanoClaw container, and got the Telegram bot working end-to-end with the Agent Factory orchestrator. I was the first team member to run the agent successfully and confirm it works.

**What I learned:**  
I learned how to work with multiple REST APIs simultaneously and handle rate limits and error conditions gracefully. Setting up Docker and NanoClaw taught me containerisation basics that I had no prior experience with. I also learned the value of being the first to test — finding issues early gave the team time to fix them.

**What I would do differently:**  
I would document the Docker setup steps in a README as I build rather than after the fact. Other team members had trouble replicating the setup because the steps were not written down until late in the sprint. A setup guide from day one would have saved everyone time.

---

## Saifur Rahman — Developer (Amazon Skill)

**What I did this sprint:**  
I built the Amazon product research skill using Playwright with playwright-stealth to bypass Amazon's bot detection. The stealth layer patches 17 fingerprinting signals and adds randomised request delays to mimic human browsing. I also drafted the formal skill specifications for both the paper-search and amazon-product-search skills, defining inputs, outputs, API sources, and error conditions for each.

**What I learned:**  
I learned a lot about web scraping challenges — Amazon actively blocks bots and requires sophisticated countermeasures. Playwright-stealth was new to me and I now understand how browser fingerprinting works and how to work around it. Writing formal skill specs also taught me how to think about a component's interface before building the implementation.

**What I would do differently:**  
I would explore using an official Amazon product API (like RapidAPI's Amazon Data API) as a fallback for when scraping is blocked. Relying solely on web scraping is fragile — Amazon changes its page layout regularly. A dual approach (scraping + API fallback) would make the skill more reliable for Sprint 2.

---

*Agent Factory | ITECH3208/3209 | Federation University | Sprint 1 Role Reflection | April 2026*
