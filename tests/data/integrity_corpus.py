# tests/data/integrity_corpus.py
# ──────────────────────────────────────────────────────────────
# 40-sample curated integrity test corpus (PROJ-364-368).
#
# Honest scope note: this corpus validates agent/integrity.py's own
# heuristic — it demonstrates the heuristic behaves as designed
# (formulaic/uniform text scores higher than varied/colloquial text;
# near-verbatim KB copies are flagged; unrelated text isn't). It is
# NOT a validated benchmark of real-world AI-detection accuracy —
# no such benchmark exists for a rule-based heuristic like this one,
# and claiming otherwise would misrepresent what was tested. See
# agent/integrity.py's module docstring for the full scope note.
#
# 10 AI_STYLE_SAMPLES   — written to be formulaic/uniform on purpose
# 10 HUMAN_STYLE_SAMPLES — written to be varied/colloquial on purpose
# 10 PLAGIARISM_PAIRS   — (source_doc_text, near_copy_text) pairs
# 10 ORIGINAL_SAMPLES   — unrelated text, should NOT match any KB doc
# ──────────────────────────────────────────────────────────────

AI_STYLE_SAMPLES = [
    "Furthermore, it is important to note that climate change represents one of the most "
    "pressing challenges of our time. Moreover, the implications of rising global temperatures "
    "extend far beyond simple weather pattern shifts. Additionally, this highlights the crucial "
    "role that renewable energy plays in mitigating environmental damage. Overall, addressing "
    "this issue requires a multifaceted approach that underscores the importance of international "
    "cooperation and long-term policy planning across all sectors of society.",

    "In today's fast-paced world, effective time management has become an essential skill for "
    "professionals across every industry. Moreover, it is worth noting that prioritization plays "
    "a crucial role in achieving long-term career success. Furthermore, delving into the realm of "
    "productivity techniques reveals a wide array of strategies. In conclusion, a testament to "
    "one's discipline is the ability to consistently apply these principles in order to maintain "
    "a healthy work-life balance.",

    "It is important to note that artificial intelligence has fundamentally transformed the "
    "landscape of modern healthcare. Furthermore, diagnostic tools powered by machine learning "
    "algorithms plays a vital role in early disease detection. Moreover, this highlights the "
    "growing need for robust ethical frameworks. In order to fully realize these benefits, "
    "in the realm of medical research, additionally, ongoing collaboration between technologists "
    "and clinicians underscores the importance of interdisciplinary work.",

    "Overall, the global supply chain has undergone significant transformation in recent years. "
    "Furthermore, it is important to note that disruptions caused by geopolitical tensions plays "
    "a crucial role in shaping corporate strategy. Moreover, delve into the realm of logistics "
    "optimization and one finds a testament to the power of data analytics. In conclusion, this "
    "highlights the importance of resilience and adaptability in an increasingly interconnected "
    "economy.",

    "It is worth noting that remote work has reshaped organizational culture across the globe. "
    "Additionally, in today's fast-paced world, employees increasingly value flexibility and "
    "autonomy. Furthermore, this highlights the crucial role that clear communication plays in "
    "distributed teams. Moreover, on the other hand, some organizations struggle to maintain "
    "cohesion, which underscores the importance of intentional culture-building efforts and "
    "regular check-ins between managers and staff.",

    "In conclusion, biodiversity loss represents a critical threat to global ecosystem stability. "
    "Furthermore, it is important to note that habitat destruction plays a crucial role in "
    "accelerating species extinction rates. Moreover, delving into the realm of conservation "
    "science reveals a testament to the effectiveness of protected areas. Additionally, this "
    "highlights the importance of coordinated international policy in order to preserve the "
    "planet's natural heritage for future generations.",

    "Moreover, the rise of electric vehicles underscores the importance of sustainable "
    "transportation infrastructure. Furthermore, it is important to note that battery technology "
    "plays a crucial role in determining consumer adoption rates. In today's fast-paced world, "
    "additionally, government incentives delve into the realm of accelerating market growth. "
    "Overall, this highlights a testament to the automotive industry's broader shift toward "
    "carbon-neutral manufacturing processes.",

    "It is important to note that financial literacy plays a crucial role in long-term wealth "
    "building. Furthermore, delving into the realm of personal budgeting reveals a testament to "
    "disciplined saving habits. Moreover, on the other hand, many young adults lack access to "
    "formal financial education, which underscores the importance of early intervention. "
    "Additionally, in conclusion, this highlights the need for schools to integrate practical "
    "money-management curricula.",

    "In today's fast-paced world, mental health awareness has become an increasingly important "
    "topic of public discourse. Furthermore, it is worth noting that workplace stress plays a "
    "crucial role in employee burnout. Moreover, this highlights the importance of accessible "
    "counseling services. Additionally, delving into the realm of preventative care reveals a "
    "testament to the value of early intervention programs across corporate and educational "
    "settings alike.",

    "Overall, the expansion of urban green spaces underscores the importance of sustainable city "
    "planning. Furthermore, it is important to note that access to parks plays a crucial role in "
    "resident wellbeing. Moreover, delving into the realm of municipal policy reveals a testament "
    "to the benefits of long-term investment. In conclusion, this highlights the necessity of "
    "balancing development pressures with environmental stewardship in growing metropolitan "
    "areas.",
]

HUMAN_STYLE_SAMPLES = [
    "Look, I've been thinking about this a lot lately and honestly? It's messier than people "
    "want to admit. My uncle Dave, who fixes cars for a living, told me last summer that the "
    "shop's electric bill tripled since they got new AC units. Weird, right. Meanwhile my "
    "neighbor swears her garden did better this year than ever, so who knows. I just know the "
    "summers feel longer now, and nobody in these meetings ever talks about that part.",

    "Okay so productivity hacks. I've tried like six different planner apps and honestly none of "
    "them stuck. What actually worked? Writing three things on a sticky note every morning. "
    "That's it. My therapist would probably say something about decision fatigue but really I "
    "think I just get overwhelmed by too many tabs open, literally and figuratively. Anyway the "
    "sticky note thing has lasted four months now, which is a personal record.",

    "My mom's a nurse and she's been saying for years that half the new hospital software "
    "actually slows doctors down. She spends more time clicking through screens than looking at "
    "patients sometimes. There's this one system that logs everything twice for no reason nobody "
    "can explain. So when people talk about AI fixing healthcare, she just laughs and asks if "
    "it'll fix the login page first.",

    "We had a container stuck at the port for three weeks last spring — some paperwork thing, "
    "nobody could really tell us why. Cost us a client. My business partner wanted to switch "
    "suppliers entirely but I don't think that's the fix, honestly. Feels like everyone's just "
    "guessing at this point and hoping the next shipment goes smoother. It usually doesn't.",

    "Been working from my kitchen table for three years now and I still haven't figured out how "
    "to stop checking Slack at 9pm. My old manager used to just walk by your desk, now it's a "
    "little red dot that follows you everywhere. Some days it's great, no commute, dog on my "
    "lap during calls. Other days I genuinely miss having somewhere to leave.",

    "Went hiking near where they cleared land for that new development and it's honestly kind of "
    "sad. Used to see deer there all the time as a kid. My dad says it's just how things go but "
    "I don't buy that completely — there's a difference between growth and just paving over "
    "everything without asking what gets lost. Anyway, the trail's shorter now.",

    "Bought an EV last year mostly because gas prices near me got ridiculous. Love it most days. "
    "Charging at home is easy but road trips are a whole different story — spent two hours at a "
    "rest stop in Ohio waiting for a charger that was already broken when we got there. My "
    "brother-in-law still drives his old truck and won't stop bringing that up.",

    "My roommate in college was terrible with money and honestly it rubbed off on me for a bit. "
    "Took me until my late twenties to actually open a savings account that wasn't just my "
    "checking account with a different name. Nobody taught us this stuff in school, we learned "
    "algebra proofs instead. Still annoyed about that, if I'm being honest.",

    "Had a rough couple months at work last year, the kind where you cry in the bathroom before "
    "a meeting kind of rough. Finally talked to someone about it, which felt embarrassing at "
    "first, like admitting I couldn't handle a normal job. Turns out a lot of my coworkers were "
    "going through the exact same thing and just never said anything either.",

    "There's this tiny park two blocks from my apartment that the city almost paved over for "
    "parking a few years back. A bunch of us showed up to city council meetings, which felt "
    "pointless at the time honestly. They kept it though. Now my kid plays there most afternoons "
    "and I still can't quite believe that actually worked.",
]

# Pairs of (source_doc_text, near_copy_text). The near_copy is the
# source lightly reworded (a handful of synonym swaps / reordered
# clauses) — close enough that an 8-word shingle overlap check should
# still flag it, which is the realistic "lightly edited copy-paste"
# case this feature is meant to catch.
PLAGIARISM_PAIRS = [
    (
        "The mitochondria is the powerhouse of the cell, generating most of the chemical energy "
        "needed to power the cell's biochemical reactions. Chemical energy produced by the "
        "mitochondria is stored in a small molecule called ATP, adenosine triphosphate. Once "
        "produced, ATP is transported throughout the cell to provide energy for cellular processes "
        "that require it, including the synthesis of proteins and the movement of the cell itself.",
        "The mitochondria is the powerhouse of the cell, generating most of the chemical energy "
        "needed to power the cell's biochemical reactions. This chemical energy produced by the "
        "mitochondria gets stored in a small molecule called ATP, or adenosine triphosphate. Once "
        "it's produced, ATP gets transported throughout the cell to provide energy for cellular "
        "processes that need it, including protein synthesis and cell movement.",
    ),
    (
        "Photosynthesis is the process by which green plants and some other organisms use "
        "sunlight to synthesize foods with carbon dioxide and water. Photosynthesis in plants "
        "generally involves the green pigment chlorophyll and generates oxygen as a byproduct. "
        "This process occurs primarily in the leaves of the plant, within specialized structures "
        "called chloroplasts, which contain the chlorophyll necessary for capturing light energy.",
        "Photosynthesis is the process where green plants and some other organisms use sunlight "
        "to synthesize food using carbon dioxide and water. Photosynthesis in plants generally "
        "involves the green pigment chlorophyll and produces oxygen as a byproduct. This process "
        "happens mainly in the leaves of the plant, inside specialized structures called "
        "chloroplasts, which hold the chlorophyll needed for capturing light energy.",
    ),
    (
        "The French Revolution was a period of radical political and societal change in France "
        "that began with the Estates General of 1789 and ended in November 1799. Many of its "
        "ideas are considered fundamental principles of liberal democracy, while phrases such as "
        "liberte, egalite, fraternite reappeared in other revolts. The revolution overthrew the "
        "monarchy, established a republic, and saw violent periods of political turbulence.",
        "The French Revolution was a period of radical political and social change in France that "
        "started with the Estates General of 1789 and ended in November 1799. Many of its ideas "
        "are seen as fundamental principles of liberal democracy, while phrases like liberte, "
        "egalite, fraternite reappeared in other uprisings. The revolution toppled the monarchy, "
        "founded a republic, and saw violent periods of political turmoil.",
    ),
    (
        "Machine learning is a subset of artificial intelligence that provides systems the "
        "ability to automatically learn and improve from experience without being explicitly "
        "programmed. Machine learning focuses on the development of computer programs that can "
        "access data and use it to learn for themselves. The process of learning begins with "
        "observations or data, such as examples, direct experience, or instruction.",
        "Machine learning is a subset of artificial intelligence that gives systems the ability "
        "to automatically learn and improve from experience without being explicitly programmed. "
        "Machine learning is focused on developing computer programs that can access data and use "
        "it to learn on their own. The learning process starts with observations or data, such as "
        "examples, direct experience, or instruction.",
    ),
    (
        "The stock market is a collection of markets where stocks, which represent ownership "
        "claims on businesses, are bought and sold. Stock markets allow companies to raise "
        "capital by issuing shares to investors who then may trade those shares on an exchange. "
        "Prices fluctuate based on supply and demand, which are influenced by company performance, "
        "economic indicators, and broader investor sentiment across the market.",
        "The stock market is a group of markets where stocks, which represent ownership claims "
        "on businesses, are bought and sold. Stock markets allow companies to raise capital by "
        "issuing shares to investors who then may trade those shares on an exchange. Prices "
        "fluctuate based on supply and demand, which are influenced by company performance, "
        "economic indicators, and overall investor sentiment across the market.",
    ),
    (
        "The Great Barrier Reef is the world's largest coral reef system, composed of over 2,900 "
        "individual reefs and 900 islands stretching for over 2,300 kilometers off the coast of "
        "Queensland, Australia. The reef supports an extraordinary diversity of life, including "
        "many vulnerable and endangered species. It is the largest structure built by living "
        "organisms on Earth and can even be seen from outer space.",
        "The Great Barrier Reef is the world's biggest coral reef system, made up of over 2,900 "
        "individual reefs and 900 islands stretching over 2,300 kilometers off the coast of "
        "Queensland, Australia. The reef supports a remarkable diversity of life, including many "
        "vulnerable and endangered species. It's the largest structure ever built by living "
        "organisms on Earth and can even be seen from space.",
    ),
    (
        "The water cycle describes the continuous movement of water on, above, and below the "
        "surface of the Earth. Water can change states among liquid, vapor, and ice at various "
        "places in the water cycle. Although the balance of water on Earth remains fairly "
        "constant over time, individual water molecules can come and go through evaporation, "
        "condensation, precipitation, and runoff in a continuous, complex cycle.",
        "The water cycle describes the ongoing movement of water on, above, and below the "
        "surface of the Earth. Water can change states between liquid, vapor, and ice at various "
        "points in the water cycle. Although the balance of water on Earth stays fairly constant "
        "over time, individual water molecules can come and go through evaporation, condensation, "
        "precipitation, and runoff in a continuous, complex cycle.",
    ),
    (
        "Supply chain management involves the coordination of production, shipment, and "
        "distribution of a product from raw materials to the final consumer. Effective supply "
        "chain management requires close collaboration between suppliers, manufacturers, "
        "distributors, and retailers. Disruptions at any point in the chain can have cascading "
        "effects, delaying delivery timelines and increasing costs across the entire network.",
        "Supply chain management involves coordinating the production, shipment, and distribution "
        "of a product from raw materials to the final consumer. Effective supply chain management "
        "needs close collaboration between suppliers, manufacturers, distributors, and retailers. "
        "Disruptions at any point in the chain can have cascading effects, delaying delivery "
        "timelines and raising costs across the whole network.",
    ),
    (
        "The human immune system is a complex network of cells, tissues, and organs that work "
        "together to defend the body against harmful pathogens such as bacteria, viruses, and "
        "fungi. The immune response can be broadly divided into innate immunity, which provides "
        "immediate but nonspecific defense, and adaptive immunity, which develops a targeted "
        "response over time and can retain memory of past infections.",
        "The human immune system is a complicated network of cells, tissues, and organs that work "
        "together to defend the body against harmful pathogens like bacteria, viruses, and fungi. "
        "The immune response can broadly be divided into innate immunity, which gives immediate "
        "but nonspecific defense, and adaptive immunity, which builds a targeted response over "
        "time and can keep memory of past infections.",
    ),
    (
        "Renewable energy comes from sources that are naturally replenished, such as sunlight, "
        "wind, rain, tides, waves, and geothermal heat. Unlike fossil fuels, renewable resources "
        "are not depleted when used and generally produce far lower greenhouse gas emissions. "
        "The transition to renewable energy is widely seen as essential for reducing the impact "
        "of climate change and achieving long-term energy security worldwide.",
        "Renewable energy comes from sources that get naturally replenished, such as sunlight, "
        "wind, rain, tides, waves, and geothermal heat. Unlike fossil fuels, renewable resources "
        "don't get depleted when used and generally produce much lower greenhouse gas emissions. "
        "The shift to renewable energy is widely viewed as essential for reducing the impact of "
        "climate change and achieving long-term energy security worldwide.",
    ),
]

# Unrelated original text — should NOT match any KB document uploaded
# from PLAGIARISM_PAIRS' source_doc_text values.
ORIGINAL_SAMPLES = [
    "My grandfather used to build birdhouses out of scrap wood every winter, just to have "
    "something to do with his hands until spring came. He never sold a single one — gave them "
    "all away to neighbors, even ones he barely knew. I've still got three of them in my garage, "
    "warped and faded now, and I can't bring myself to throw any of them out.",

    "The bakery on Fifth Street closes at random times depending on whether they sell out of "
    "sourdough, which happens more often than you'd think for a place that small. I've learned "
    "to just show up right when they open if I actually want bread. The owner still remembers my "
    "order from two years ago, which honestly might be the real reason I keep going back.",

    "Learning to sail as an adult is humbling in a way nothing else in my life has been recently. "
    "There's no faking it — the wind either does what you expect or it doesn't, and you find out "
    "immediately which one it was. My instructor keeps telling me to stop apologizing to the boat "
    "every time I mess up a tack, but old habits.",

    "Our office coffee machine broke for two weeks straight and productivity noticeably tanked, "
    "which nobody wants to admit says something uncomfortable about how we actually function as "
    "a team. Someone finally brought in a French press from home and it became this weird "
    "unofficial gathering spot. Facilities still hasn't fixed the real machine.",

    "I used to think marathon training was mostly about the legs until I hurt my shoulder from, "
    "of all things, bad posture while running. Physical therapy taught me more about how "
    "connected everything in the body actually is than four years of biology class ever did. "
    "Still slower than I was two years ago, but at least nothing hurts now.",

    "The community garden plot my neighbor talked me into taking over has taught me that "
    "tomatoes are basically a personality test — you either obsessively check on them every "
    "morning or you don't, there's no in-between. Mine are doing fine this year, mostly because "
    "she keeps showing up uninvited to water them when I forget.",

    "Every year our extended family argues about where to have the holiday dinner and every year "
    "it ends up at the same house anyway, because it's the only one with enough chairs. My aunt "
    "still brings up 2019 like it was some kind of scandal. I genuinely don't remember what "
    "happened in 2019 and I'm afraid to ask at this point.",

    "Working the night shift at the hospital pharmacy for six years changed how I see basically "
    "every emergency room show on television — none of it is remotely accurate, but somehow "
    "that's not even the most surprising part of the job. The most surprising part is how quiet "
    "it gets around 3am, like the whole building is holding its breath.",

    "My daughter insists on narrating everything she does out loud, including brushing her teeth, "
    "which she describes as though it's a competitive sport with an invisible audience. I used "
    "to find it exhausting. Now that she's getting older and quieter, I sort of miss the running "
    "commentary more than I expected to.",

    "There's a stretch of the river near my house where the current gets strange every spring "
    "thaw, fast enough that the fishing guides won't take clients out there until May. Locals "
    "still swim it anyway, myself included some years, which in hindsight is probably not the "
    "wisest call but nothing's happened yet, knock on wood.",
]
