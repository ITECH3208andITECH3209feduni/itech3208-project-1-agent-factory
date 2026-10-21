/* Interface language for the whole dashboard.
 *
 * The language dropdown picks one of seven languages. English (AU) is the source
 * text already in the HTML; every other language is looked up here by that text,
 * so the markup needs no per-string attributes. A MutationObserver translates
 * rows and messages the page adds later (activity rows, delivery history, errors).
 *
 * Row format: ["English text", es, hi, zh, fr, de]. "{0}" matches any value that is
 * carried over unchanged (a count, a version, a PROJ tag).
 * Text with no row (names, phone numbers, server-written summaries) is left as is.
 */
(function () {
  "use strict";

  const COLS = ["es", "hi", "zh", "fr", "de"];

  const ROWS = [
    // ── sidebar ──
    ["Online · v{0}", "En línea · v{0}", "ऑनलाइन · v{0}", "在线 · v{0}", "En ligne · v{0}", "Online · v{0}"],
    ["Workspace", "Espacio de trabajo", "कार्यस्थान", "工作区", "Espace de travail", "Arbeitsbereich"],
    ["Amazon Seller AI", "IA para vendedores de Amazon", "Amazon विक्रेता AI", "亚马逊卖家 AI", "IA vendeur Amazon", "Amazon-Verkäufer-KI"],
    ["Literature AI", "IA de literatura", "साहित्य AI", "文献 AI", "IA de littérature", "Literatur-KI"],
    ["AI Receptionist", "Recepcionista con IA", "AI रिसेप्शनिस्ट", "AI 前台接待", "Réceptionniste IA", "KI-Empfang"],
    ["Recent", "Recientes", "हाल के", "最近", "Récents", "Zuletzt"],
    ["Personalise UI & Theme", "Personalizar interfaz y tema", "इंटरफ़ेस और थीम अनुकूलित करें", "个性化界面与主题", "Personnaliser l'interface et le thème", "Oberfläche & Design anpassen"],
    ["Information Website", "Sitio web informativo", "जानकारी वेबसाइट", "信息网站", "Site d'information", "Informationswebsite"],
    ["Sign out", "Cerrar sesión", "साइन आउट", "退出登录", "Se déconnecter", "Abmelden"],

    // ── welcome screen ──
    ["Your AI-powered research platform. Pick an agent to get started.", "Tu plataforma de investigación con IA. Elige un agente para empezar.", "आपका AI-संचालित शोध प्लेटफ़ॉर्म। शुरू करने के लिए एक एजेंट चुनें।", "由 AI 驱动的研究平台。选择一个智能体开始使用。", "Votre plateforme de recherche propulsée par l'IA. Choisissez un agent pour commencer.", "Ihre KI-gestützte Recherche-Plattform. Wählen Sie einen Agenten, um zu starten."],
    ["Online · v{0} · Powered by Claude AI", "En línea · v{0} · Con tecnología de Claude AI", "ऑनलाइन · v{0} · Claude AI द्वारा संचालित", "在线 · v{0} · 由 Claude AI 提供支持", "En ligne · v{0} · Propulsé par Claude AI", "Online · v{0} · Unterstützt von Claude AI"],
    ["Amazon & Seller Tools", "Amazon y herramientas para vendedores", "Amazon और विक्रेता टूल", "亚马逊与卖家工具", "Amazon et outils vendeur", "Amazon & Verkäufer-Tools"],
    ["Research products, source suppliers from Alibaba, build PPC campaigns, and optimise profit margins.", "Investiga productos, encuentra proveedores en Alibaba, crea campañas PPC y optimiza márgenes de beneficio.", "उत्पादों पर शोध करें, Alibaba से आपूर्तिकर्ता खोजें, PPC अभियान बनाएँ और लाभ मार्जिन अनुकूलित करें।", "调研产品、从 Alibaba 寻找供应商、创建 PPC 广告活动并优化利润率。", "Recherchez des produits, trouvez des fournisseurs sur Alibaba, créez des campagnes PPC et optimisez vos marges.", "Produkte recherchieren, Lieferanten auf Alibaba finden, PPC-Kampagnen erstellen und Gewinnmargen optimieren."],
    ["Search academic papers, detect AI-generated content, check plagiarism, and ask any general question.", "Busca artículos académicos, detecta contenido generado por IA, comprueba plagio y haz cualquier pregunta general.", "शैक्षणिक पेपर खोजें, AI-जनित सामग्री पहचानें, साहित्यिक चोरी जाँचें और कोई भी सामान्य प्रश्न पूछें।", "搜索学术论文、检测 AI 生成内容、查重，并提出任何通用问题。", "Recherchez des articles académiques, détectez le contenu généré par l'IA, vérifiez le plagiat et posez toute question générale.", "Wissenschaftliche Arbeiten suchen, KI-generierte Inhalte erkennen, Plagiate prüfen und beliebige Allgemeinfragen stellen."],
    ["24/7 virtual receptionist — answers calls and SMS, books appointments, and handles enquiries via voice or text.", "Recepcionista virtual 24/7: atiende llamadas y SMS, reserva citas y gestiona consultas por voz o texto.", "24/7 वर्चुअल रिसेप्शनिस्ट — कॉल और SMS का जवाब देती है, अपॉइंटमेंट बुक करती है और आवाज़ या टेक्स्ट से पूछताछ संभालती है।", "24/7 虚拟前台——接听电话和短信、预约，并通过语音或文字处理咨询。", "Réceptionniste virtuelle 24 h/24, 7 j/7 : répond aux appels et SMS, prend les rendez-vous et traite les demandes par voix ou texte.", "Virtuelle Rezeption rund um die Uhr – beantwortet Anrufe und SMS, bucht Termine und bearbeitet Anfragen per Sprache oder Text."],
    ["Product Research", "Investigación de productos", "उत्पाद अनुसंधान", "产品调研", "Recherche de produits", "Produktrecherche"],
    ["PPC Builder", "Creador de PPC", "PPC बिल्डर", "PPC 构建器", "Créateur PPC", "PPC-Builder"],
    ["Supplier Finder", "Buscador de proveedores", "आपूर्तिकर्ता खोजक", "供应商查找", "Recherche de fournisseurs", "Lieferantensuche"],
    ["Profit Analyser", "Analizador de beneficios", "लाभ विश्लेषक", "利润分析器", "Analyseur de profits", "Gewinnanalyse"],
    ["AI Detector", "Detector de IA", "AI डिटेक्टर", "AI 检测器", "Détecteur d'IA", "KI-Detektor"],
    ["Plagiarism Check", "Comprobación de plagio", "साहित्यिक चोरी जाँच", "查重检测", "Vérification du plagiat", "Plagiatsprüfung"],
    ["Voice & SMS", "Voz y SMS", "वॉइस और SMS", "语音与短信", "Voix et SMS", "Sprache & SMS"],
    ["Appointments", "Citas", "अपॉइंटमेंट", "预约", "Rendez-vous", "Termine"],
    ["FAQ Lookup", "Consulta de preguntas frecuentes", "FAQ खोज", "常见问题查询", "Recherche FAQ", "FAQ-Suche"],

    // ── Amazon agent ──
    ["Your AI-powered FBA toolkit — research products, source suppliers, launch PPC campaigns and analyse profit margins.", "Tu kit FBA con IA: investiga productos, encuentra proveedores, lanza campañas PPC y analiza márgenes de beneficio.", "आपका AI-संचालित FBA टूलकिट — उत्पादों की खोज करें, आपूर्तिकर्ता खोजें, PPC अभियान शुरू करें और लाभ मार्जिन का विश्लेषण करें।", "由 AI 驱动的 FBA 工具包——调研产品、寻找供应商、发起 PPC 广告活动并分析利润率。", "Votre boîte à outils FBA propulsée par l'IA : recherchez des produits, trouvez des fournisseurs, lancez des campagnes PPC et analysez vos marges.", "Ihr KI-gestütztes FBA-Toolkit – Produkte recherchieren, Lieferanten finden, PPC-Kampagnen starten und Gewinnmargen analysieren."],
    ["Search", "Buscar", "खोजें", "搜索", "Rechercher", "Suchen"],
    ["Amazon · Alibaba · PPC · Profit Optimiser · 📎 attach files", "Amazon · Alibaba · PPC · Optimizador de beneficios · 📎 adjuntar archivos", "Amazon · Alibaba · PPC · लाभ अनुकूलक · 📎 फ़ाइलें जोड़ें", "Amazon · Alibaba · PPC · 利润优化器 · 📎 添加附件", "Amazon · Alibaba · PPC · Optimiseur de profits · 📎 joindre des fichiers", "Amazon · Alibaba · PPC · Gewinnoptimierer · 📎 Dateien anhängen"],
    ["Press", "Pulsa", "दबाएँ", "按", "Appuyez sur", "Drücke"],
    ["Enter", "Intro", "Enter", "Enter", "Entrée", "Eingabe"],
    ["to search", "para buscar", "खोजने के लिए", "搜索", "pour rechercher", "zum Suchen"],
    ["to ask", "para preguntar", "पूछने के लिए", "提问", "pour demander", "zum Fragen"],
    ["to send", "para enviar", "भेजने के लिए", "发送", "pour envoyer", "zum Senden"],
    ["to submit ·", "para enviar ·", "सबमिट करने के लिए ·", "提交 ·", "pour soumettre ·", "zum Absenden ·"],
    ["for new line", "para nueva línea", "नई पंक्ति के लिए", "换行", "pour un saut de ligne", "für neue Zeile"],

    // ── Literature agent ──
    ["Research Search", "Búsqueda de investigación", "शोध खोज", "研究搜索", "Recherche scientifique", "Forschungssuche"],
    ["Ask Anything", "Pregunta lo que quieras", "कुछ भी पूछें", "随意提问", "Demandez n'importe quoi", "Frag alles"],
    ["Integrity Check", "Verificación de integridad", "अखंडता जाँच", "诚信检查", "Contrôle d'intégrité", "Integritätsprüfung"],
    ["Search academic papers, detect AI-generated content, and run plagiarism checks — all in one place.", "Busca artículos académicos, detecta contenido generado por IA y comprueba plagio, todo en un solo lugar.", "शैक्षणिक पेपर खोजें, AI-जनित सामग्री पहचानें और साहित्यिक चोरी की जाँच करें — सब एक ही जगह।", "搜索学术论文、检测 AI 生成内容并进行查重——一站式完成。", "Recherchez des articles académiques, détectez le contenu généré par l'IA et vérifiez le plagiat, le tout au même endroit.", "Wissenschaftliche Arbeiten suchen, KI-generierte Inhalte erkennen und Plagiatsprüfungen durchführen – alles an einem Ort."],
    ["Research Papers", "Artículos de investigación", "शोध पत्र", "研究论文", "Articles de recherche", "Forschungsarbeiten"],
    ["Full Report", "Informe completo", "पूर्ण रिपोर्ट", "完整报告", "Rapport complet", "Vollständiger Bericht"],
    ["arXiv · Semantic Scholar · AI synthesis · 📎 attach files", "arXiv · Semantic Scholar · síntesis con IA · 📎 adjuntar archivos", "arXiv · Semantic Scholar · AI संश्लेषण · 📎 फ़ाइलें जोड़ें", "arXiv · Semantic Scholar · AI 综合分析 · 📎 添加附件", "arXiv · Semantic Scholar · synthèse IA · 📎 joindre des fichiers", "arXiv · Semantic Scholar · KI-Synthese · 📎 Dateien anhängen"],
    ["Ask any question — general knowledge, definitions, explanations, how-to guides, current topics. Powered by Claude AI.", "Haz cualquier pregunta: cultura general, definiciones, explicaciones, guías prácticas, temas de actualidad. Con tecnología de Claude AI.", "कोई भी प्रश्न पूछें — सामान्य ज्ञान, परिभाषाएँ, व्याख्याएँ, निर्देश-पुस्तिकाएँ, वर्तमान विषय। Claude AI द्वारा संचालित।", "提出任何问题——常识、定义、解释、操作指南、时事话题。由 Claude AI 提供支持。", "Posez n'importe quelle question : culture générale, définitions, explications, tutoriels, sujets d'actualité. Propulsé par Claude AI.", "Stellen Sie jede Frage – Allgemeinwissen, Definitionen, Erklärungen, Anleitungen, aktuelle Themen. Unterstützt von Claude AI."],
    ["General Knowledge", "Cultura general", "सामान्य ज्ञान", "常识", "Culture générale", "Allgemeinwissen"],
    ["Explain a Concept", "Explicar un concepto", "कोई अवधारणा समझाएँ", "解释概念", "Expliquer un concept", "Ein Konzept erklären"],
    ["How Does It Work", "¿Cómo funciona?", "यह कैसे काम करता है", "工作原理", "Comment ça marche", "Wie funktioniert das"],
    ["Compare Two Things", "Comparar dos cosas", "दो चीज़ों की तुलना करें", "比较两者", "Comparer deux choses", "Zwei Dinge vergleichen"],
    ["Ask", "Preguntar", "पूछें", "提问", "Demander", "Fragen"],
    ["Claude AI · General Knowledge · Any topic", "Claude AI · Cultura general · Cualquier tema", "Claude AI · सामान्य ज्ञान · कोई भी विषय", "Claude AI · 常识 · 任意主题", "Claude AI · Culture générale · Tout sujet", "Claude AI · Allgemeinwissen · Jedes Thema"],
    ["Academic Integrity Check", "Verificación de integridad académica", "शैक्षणिक अखंडता जाँच", "学术诚信检查", "Contrôle d'intégrité académique", "Prüfung der akademischen Integrität"],
    ["Detect AI-generated text, scan for plagiarism, and generate full integrity reports with risk scoring.", "Detecta texto generado por IA, analiza plagio y genera informes de integridad completos con puntuación de riesgo.", "AI-जनित पाठ का पता लगाएँ, साहित्यिक चोरी की स्कैनिंग करें और जोखिम स्कोर के साथ पूर्ण अखंडता रिपोर्ट बनाएँ।", "检测 AI 生成的文本、扫描抄袭，并生成带风险评分的完整诚信报告。", "Détectez le texte généré par l'IA, recherchez le plagiat et générez des rapports d'intégrité complets avec score de risque.", "KI-generierte Texte erkennen, auf Plagiate prüfen und vollständige Integritätsberichte mit Risikobewertung erstellen."],
    ["AI Detection", "Detección de IA", "AI पहचान", "AI 检测", "Détection d'IA", "KI-Erkennung"],
    ["Plagiarism Scan", "Análisis de plagio", "साहित्यिक चोरी स्कैन", "抄袭扫描", "Analyse de plagiat", "Plagiatsscan"],
    ["Check", "Verificar", "जाँचें", "检查", "Vérifier", "Prüfen"],
    ["AI probability · Plagiarism score · Risk report · 📎 attach document", "Probabilidad de IA · Puntuación de plagio · Informe de riesgo · 📎 adjuntar documento", "AI संभावना · साहित्यिक चोरी स्कोर · जोखिम रिपोर्ट · 📎 दस्तावेज़ जोड़ें", "AI 概率 · 抄袭评分 · 风险报告 · 📎 添加文档", "Probabilité d'IA · Score de plagiat · Rapport de risque · 📎 joindre un document", "KI-Wahrscheinlichkeit · Plagiatswert · Risikobericht · 📎 Dokument anhängen"],

    // ── receptionist: top bar, stats, tabs ──
    ["Voice", "Voz", "वॉइस", "语音", "Voix", "Sprache"],
    ["Web Chat", "Chat web", "वेब चैट", "网页聊天", "Chat web", "Web-Chat"],
    ["Connecting", "Conectando", "कनेक्ट हो रहा है", "连接中", "Connexion", "Verbinde"],
    ["Connecting…", "Conectando…", "कनेक्ट हो रहा है…", "连接中…", "Connexion…", "Verbinde …"],
    ["Live", "En vivo", "लाइव", "实时", "En direct", "Live"],
    ["Calls today", "Llamadas hoy", "आज की कॉल", "今日通话", "Appels aujourd'hui", "Anrufe heute"],
    ["SMS today", "SMS hoy", "आज के SMS", "今日短信", "SMS aujourd'hui", "SMS heute"],
    ["Booked", "Reservadas", "बुक किए गए", "已预约", "Réservés", "Gebucht"],
    ["Escalations", "Escalaciones", "एस्केलेशन", "升级事件", "Escalades", "Eskalationen"],
    ["Chat", "Chat", "चैट", "聊天", "Chat", "Chat"],
    ["Contacts", "Contactos", "संपर्क", "联系人", "Contacts", "Kontakte"],
    ["Reminders", "Recordatorios", "रिमाइंडर", "提醒", "Rappels", "Erinnerungen"],
    ["Ask MyAI", "Preguntar a MyAI", "MyAI से पूछें", "询问 MyAI", "Demander à MyAI", "MyAI fragen"],
    ["Patient preview", "Vista previa del paciente", "मरीज़ का पूर्वावलोकन", "患者预览", "Aperçu patient", "Patientenvorschau"],
    ["Ask me how to use this dashboard: adding contacts, scheduling reminders, reading results.", "Pregúntame cómo usar este panel: añadir contactos, programar recordatorios, leer resultados.", "मुझसे पूछें कि इस डैशबोर्ड का उपयोग कैसे करें: संपर्क जोड़ना, रिमाइंडर शेड्यूल करना, परिणाम पढ़ना।", "问我如何使用此面板：添加联系人、安排提醒、查看结果。", "Demandez-moi comment utiliser ce tableau de bord : ajouter des contacts, programmer des rappels, lire les résultats.", "Fragen Sie mich, wie Sie dieses Dashboard nutzen: Kontakte hinzufügen, Erinnerungen planen, Ergebnisse lesen."],
    ["How do I add a contact?", "¿Cómo añado un contacto?", "संपर्क कैसे जोड़ूँ?", "如何添加联系人？", "Comment ajouter un contact ?", "Wie füge ich einen Kontakt hinzu?"],
    ["How do I schedule a reminder?", "¿Cómo programo un recordatorio?", "रिमाइंडर कैसे शेड्यूल करूँ?", "如何安排提醒？", "Comment programmer un rappel ?", "Wie plane ich eine Erinnerung?"],
    ["What does Delivery History show?", "¿Qué muestra el historial de entregas?", "डिलीवरी इतिहास में क्या दिखता है?", "发送记录显示什么？", "Que montre l'historique des envois ?", "Was zeigt der Zustellverlauf?"],
    ["What are escalations?", "¿Qué son las escalaciones?", "एस्केलेशन क्या हैं?", "什么是升级事件？", "Que sont les escalades ?", "Was sind Eskalationen?"],
    ["Ask MyAI how to use the dashboard…", "Pregunta a MyAI cómo usar el panel…", "MyAI से पूछें कि डैशबोर्ड कैसे इस्तेमाल करें…", "向 MyAI 询问如何使用面板…", "Demandez à MyAI comment utiliser le tableau de bord…", "Fragen Sie MyAI, wie das Dashboard funktioniert …"],
    ["Dashboard help · Contacts · Reminders · Delivery · Calendar", "Ayuda del panel · Contactos · Recordatorios · Entregas · Calendario", "डैशबोर्ड सहायता · संपर्क · रिमाइंडर · डिलीवरी · कैलेंडर", "面板帮助 · 联系人 · 提醒 · 发送 · 日历", "Aide du tableau de bord · Contacts · Rappels · Envois · Calendrier", "Dashboard-Hilfe · Kontakte · Erinnerungen · Zustellung · Kalender"],
    ["This is a preview of what patients get on web chat, SMS and calls.", "Esta es una vista previa de lo que reciben los pacientes por chat web, SMS y llamadas.", "यह उसका पूर्वावलोकन है जो मरीज़ों को वेब चैट, SMS और कॉल पर मिलता है।", "这是患者在网页聊天、短信和电话中所见内容的预览。", "Aperçu de ce que les patients reçoivent par chat web, SMS et appel.", "Vorschau dessen, was Patienten im Web-Chat, per SMS und am Telefon erhalten."],
    ["Activity", "Actividad", "गतिविधि", "活动", "Activité", "Aktivität"],
    ["Analytics", "Analítica", "विश्लेषण", "数据分析", "Analyses", "Analysen"],
    ["Delivery History", "Historial de entregas", "डिलीवरी इतिहास", "发送记录", "Historique des envois", "Zustellverlauf"],
    ["Calendar", "Calendario", "कैलेंडर", "日历", "Calendrier", "Kalender"],

    // ── receptionist: chat ──
    ["Your 24/7 virtual receptionist — answers calls and SMS, books appointments, and handles enquiries via voice or text.", "Tu recepcionista virtual 24/7: atiende llamadas y SMS, reserva citas y gestiona consultas por voz o texto.", "आपकी 24/7 वर्चुअल रिसेप्शनिस्ट — कॉल और SMS का जवाब देती है, अपॉइंटमेंट बुक करती है और आवाज़ या टेक्स्ट से पूछताछ संभालती है।", "您的 24/7 虚拟前台——接听电话和短信、预约，并通过语音或文字处理咨询。", "Votre réceptionniste virtuelle 24 h/24, 7 j/7 : répond aux appels et SMS, prend les rendez-vous et traite les demandes par voix ou texte.", "Ihre virtuelle Rezeption rund um die Uhr – beantwortet Anrufe und SMS, bucht Termine und bearbeitet Anfragen per Sprache oder Text."],
    ["Opening Hours", "Horario de apertura", "खुलने का समय", "营业时间", "Horaires d'ouverture", "Öffnungszeiten"],
    ["Book Appointment", "Reservar cita", "अपॉइंटमेंट बुक करें", "预约", "Prendre rendez-vous", "Termin buchen"],
    ["Our Services", "Nuestros servicios", "हमारी सेवाएँ", "我们的服务", "Nos services", "Unsere Leistungen"],
    ["Contact Info", "Contacto", "संपर्क जानकारी", "联系方式", "Coordonnées", "Kontaktdaten"],
    ["Send", "Enviar", "भेजें", "发送", "Envoyer", "Senden"],
    ["Web chat · SMS · Voice · Calendar booking", "Chat web · SMS · Voz · Reserva en calendario", "वेब चैट · SMS · वॉइस · कैलेंडर बुकिंग", "网页聊天 · 短信 · 语音 · 日历预约", "Chat web · SMS · Voix · Réservation par calendrier", "Web-Chat · SMS · Sprache · Kalenderbuchung"],
    ["Ask the receptionist anything…", "Pregunta lo que quieras a la recepcionista…", "रिसेप्शनिस्ट से कुछ भी पूछें…", "向前台随便问点什么…", "Posez n'importe quelle question à la réceptionniste…", "Fragen Sie den Empfang alles …"],

    // ── receptionist: activity and analytics ──
    ["Loading activity…", "Cargando actividad…", "गतिविधि लोड हो रही है…", "正在加载活动…", "Chargement de l'activité…", "Aktivität wird geladen …"],
    ["No recent activity.", "Sin actividad reciente.", "कोई हालिया गतिविधि नहीं।", "暂无最近活动。", "Aucune activité récente.", "Keine aktuelle Aktivität."],
    ["just now", "ahora mismo", "अभी-अभी", "刚刚", "à l'instant", "gerade eben"],
    ["Delivery Rate", "Tasa de entrega", "डिलीवरी दर", "送达率", "Taux de livraison", "Zustellrate"],
    ["Tracking active", "Seguimiento activo", "ट्रैकिंग सक्रिय", "跟踪已启用", "Suivi actif", "Tracking aktiv"],
    ["Reply Rate (SMS)", "Tasa de respuesta (SMS)", "उत्तर दर (SMS)", "回复率（短信）", "Taux de réponse (SMS)", "Antwortrate (SMS)"],
    ["People who texted back", "Personas que respondieron por texto", "जिन लोगों ने जवाब दिया", "回复短信的人数", "Personnes ayant répondu par SMS", "Personen, die zurückgeschrieben haben"],
    ["Total Outbound Sent", "Total enviados", "कुल भेजे गए आउटबाउंड", "发出总数", "Total envoyés", "Gesendet gesamt"],
    ["In-flight: {0}", "En tránsito: {0}", "प्रक्रिया में: {0}", "发送中：{0}", "En cours : {0}", "Unterwegs: {0}"],
    ["Failed / Bounces", "Fallidos / rebotes", "विफल / बाउंस", "失败 / 退回", "Échecs / rebonds", "Fehlgeschlagen / Bounces"],
    ["Suppressed emails: {0}", "Correos suprimidos: {0}", "दबाए गए ईमेल: {0}", "已屏蔽邮件：{0}", "E-mails supprimés : {0}", "Unterdrückte E-Mails: {0}"],
    ["7-Day Delivery & Activity Trend", "Tendencia de entregas y actividad (7 días)", "7-दिन डिलीवरी और गतिविधि रुझान", "7 天送达与活动趋势", "Tendance des envois et de l'activité sur 7 jours", "7-Tage-Trend für Zustellung & Aktivität"],
    ["Seed Demo Data", "Cargar datos de demostración", "डेमो डेटा जोड़ें", "载入演示数据", "Charger des données de démo", "Demodaten laden"],
    ["Channel Breakdown", "Desglose por canal", "चैनल विवरण", "渠道明细", "Répartition par canal", "Aufschlüsselung nach Kanal"],
    ["No channel volume", "Sin volumen por canal", "कोई चैनल वॉल्यूम नहीं", "暂无渠道数据", "Aucun volume par canal", "Kein Kanalvolumen"],
    ["No delivery data yet. Click \"Seed Demo Data\" above to view trends.", "Aún no hay datos de entrega. Pulsa «Cargar datos de demostración» arriba para ver las tendencias.", "अभी तक कोई डिलीवरी डेटा नहीं। रुझान देखने के लिए ऊपर \"डेमो डेटा जोड़ें\" पर क्लिक करें।", "暂无发送数据。点击上方“载入演示数据”查看趋势。", "Aucune donnée d'envoi pour l'instant. Cliquez sur « Charger des données de démo » ci-dessus pour voir les tendances.", "Noch keine Zustelldaten. Klicken Sie oben auf „Demodaten laden“, um Trends zu sehen."],
    ["No texts sent yet", "Aún no se han enviado textos", "अभी तक कोई टेक्स्ट नहीं भेजा गया", "尚未发送短信", "Aucun SMS envoyé pour l'instant", "Noch keine SMS gesendet"],
    ["nothing to measure yet", "nada que medir todavía", "अभी मापने के लिए कुछ नहीं", "暂无可统计数据", "rien à mesurer pour l'instant", "noch nichts zu messen"],
    ["No response", "Sin respuesta", "कोई उत्तर नहीं", "无回复", "Aucune réponse", "Keine Antwort"],
    ["Failed to load analytics:", "No se pudo cargar la analítica:", "विश्लेषण लोड नहीं हो सका:", "无法加载分析数据：", "Impossible de charger les analyses :", "Analysen konnten nicht geladen werden:"],

    // ── receptionist: delivery history ──
    ["All Channels", "Todos los canales", "सभी चैनल", "所有渠道", "Tous les canaux", "Alle Kanäle"],
    ["Email", "Correo electrónico", "ईमेल", "电子邮件", "E-mail", "E-Mail"],
    ["All Statuses", "Todos los estados", "सभी स्थितियाँ", "所有状态", "Tous les statuts", "Alle Status"],
    ["Delivered", "Entregado", "डिलीवर हुआ", "已送达", "Livré", "Zugestellt"],
    ["Sent", "Enviado", "भेजा गया", "已发送", "Envoyé", "Gesendet"],
    ["Queued", "En cola", "कतार में", "排队中", "En file d'attente", "In Warteschlange"],
    ["Failed", "Fallido", "विफल", "失败", "Échec", "Fehlgeschlagen"],
    ["Bounced", "Rebotado", "बाउंस हुआ", "已退回", "Rebondi", "Zurückgewiesen"],
    ["+ Send Reminder", "+ Enviar recordatorio", "+ रिमाइंडर भेजें", "+ 发送提醒", "+ Envoyer un rappel", "+ Erinnerung senden"],
    ["Time", "Hora", "समय", "时间", "Heure", "Zeit"],
    ["Channel", "Canal", "चैनल", "渠道", "Canal", "Kanal"],
    ["Recipient", "Destinatario", "प्राप्तकर्ता", "收件人", "Destinataire", "Empfänger"],
    ["Type", "Tipo", "प्रकार", "类型", "Type", "Typ"],
    ["Status", "Estado", "स्थिति", "状态", "Statut", "Status"],
    ["Error / Diagnostic", "Error / diagnóstico", "त्रुटि / निदान", "错误 / 诊断", "Erreur / diagnostic", "Fehler / Diagnose"],
    ["Action", "Acción", "कार्रवाई", "操作", "Action", "Aktion"],
    ["Retry", "Reintentar", "पुनः प्रयास", "重试", "Réessayer", "Wiederholen"],
    ["Search recipient, message ID, or error…", "Buscar destinatario, ID de mensaje o error…", "प्राप्तकर्ता, संदेश ID या त्रुटि खोजें…", "搜索收件人、消息 ID 或错误…", "Rechercher un destinataire, un ID de message ou une erreur…", "Empfänger, Nachrichten-ID oder Fehler suchen …"],
    ["Loading delivery logs…", "Cargando registros de entrega…", "डिलीवरी लॉग लोड हो रहे हैं…", "正在加载发送日志…", "Chargement des journaux d'envoi…", "Zustellprotokolle werden geladen …"],
    ["No delivery records match filter criteria.", "Ningún registro de entrega coincide con los filtros.", "फ़िल्टर से कोई डिलीवरी रिकॉर्ड मेल नहीं खाता।", "没有符合筛选条件的发送记录。", "Aucun enregistrement d'envoi ne correspond aux filtres.", "Keine Zustellungen entsprechen den Filtern."],
    ["Error: Failed to fetch delivery logs", "Error: no se pudo obtener el historial de entregas", "त्रुटि: डिलीवरी लॉग प्राप्त नहीं हो सके", "错误：无法获取发送日志", "Erreur : impossible de récupérer les journaux d'envoi", "Fehler: Zustellprotokolle konnten nicht abgerufen werden"],

    // ── receptionist: escalations and calendar ──
    ["Loading escalations…", "Cargando escalaciones…", "एस्केलेशन लोड हो रहे हैं…", "正在加载升级事件…", "Chargement des escalades…", "Eskalationen werden geladen …"],
    ["Escalation data loading…", "Cargando datos de escalaciones…", "एस्केलेशन डेटा लोड हो रहा है…", "正在加载升级数据…", "Chargement des données d'escalade…", "Eskalationsdaten werden geladen …"],
    ["No open escalations.", "No hay escalaciones abiertas.", "कोई खुला एस्केलेशन नहीं।", "没有未处理的升级事件。", "Aucune escalade ouverte.", "Keine offenen Eskalationen."],
    ["Loading appointments…", "Cargando citas…", "अपॉइंटमेंट लोड हो रहे हैं…", "正在加载预约…", "Chargement des rendez-vous…", "Termine werden geladen …"],
    ["Unconfirmed", "Sin confirmar", "अपुष्ट", "未确认", "Non confirmé", "Unbestätigt"],
    ["Booking confirmed", "Reserva confirmada", "बुकिंग की पुष्टि हुई", "预约已确认", "Réservation confirmée", "Buchung bestätigt"],
    ["No upcoming appointments.", "No hay citas próximas.", "कोई आगामी अपॉइंटमेंट नहीं।", "暂无即将到来的预约。", "Aucun rendez-vous à venir.", "Keine anstehenden Termine."],

    // ── personalisation panel ──
    ["Interface Personalisation", "Personalización de la interfaz", "इंटरफ़ेस वैयक्तिकरण", "界面个性化", "Personnalisation de l'interface", "Oberflächenanpassung"],
    ["Color Theme ({0})", "Tema de color ({0})", "रंग थीम ({0})", "颜色主题（{0}）", "Thème de couleur ({0})", "Farbdesign ({0})"],
    ["Accent Color ({0})", "Color de énfasis ({0})", "एक्सेंट रंग ({0})", "强调色（{0}）", "Couleur d'accent ({0})", "Akzentfarbe ({0})"],
    ["Widget Visibility & Ordering ({0})", "Visibilidad y orden de los widgets ({0})", "विजेट दृश्यता और क्रम ({0})", "小组件显示与排序（{0}）", "Visibilité et ordre des widgets ({0})", "Widget-Sichtbarkeit & Reihenfolge ({0})"],
    ["Dark", "Oscuro", "गहरा", "深色", "Sombre", "Dunkel"],
    ["Light", "Claro", "हल्का", "浅色", "Clair", "Hell"],
    ["High Contrast", "Alto contraste", "उच्च कंट्रास्ट", "高对比度", "Contraste élevé", "Hoher Kontrast"],
    ["Indigo", "Índigo", "इंडिगो", "靛蓝", "Indigo", "Indigo"],
    ["Emerald", "Esmeralda", "पन्ना", "翠绿", "Émeraude", "Smaragd"],
    ["Violet", "Violeta", "बैंगनी", "紫罗兰", "Violet", "Violett"],
    ["Amber", "Ámbar", "एम्बर", "琥珀", "Ambre", "Bernstein"],
    ["Rose", "Rosa", "गुलाबी", "玫红", "Rose", "Rosé"],
    ["Analytics KPI Cards", "Tarjetas KPI de analítica", "विश्लेषण KPI कार्ड", "分析 KPI 卡片", "Cartes KPI d'analyse", "Analyse-KPI-Karten"],
    ["7-Day Trend Chart", "Gráfico de tendencia de 7 días", "7-दिन रुझान चार्ट", "7 天趋势图", "Graphique de tendance sur 7 jours", "7-Tage-Trenddiagramm"],
    ["Delivery History Log", "Registro de historial de entregas", "डिलीवरी इतिहास लॉग", "发送历史日志", "Journal de l'historique des envois", "Zustellverlaufsprotokoll"],
    ["Live Activity Feed", "Actividad en vivo", "लाइव गतिविधि फ़ीड", "实时活动动态", "Flux d'activité en direct", "Live-Aktivitätsfeed"],
    ["Escalation Queue", "Cola de escalaciones", "एस्केलेशन कतार", "升级队列", "File d'escalades", "Eskalationswarteschlange"],
    ["Reset to Defaults", "Restablecer valores", "डिफ़ॉल्ट पर रीसेट करें", "恢复默认设置", "Réinitialiser", "Auf Standard zurücksetzen"],
    ["Save & Apply", "Guardar y aplicar", "सहेजें और लागू करें", "保存并应用", "Enregistrer et appliquer", "Speichern & anwenden"],

    // ── send-reminder dialog ──
    ["Send Outbound Reminder", "Enviar recordatorio saliente", "आउटबाउंड रिमाइंडर भेजें", "发送外发提醒", "Envoyer un rappel sortant", "Ausgehende Erinnerung senden"],
    ["Recipient (Phone or Email)", "Destinatario (teléfono o correo)", "प्राप्तकर्ता (फ़ोन या ईमेल)", "收件人（电话或邮箱）", "Destinataire (téléphone ou e-mail)", "Empfänger (Telefon oder E-Mail)"],
    ["Appointment", "Cita", "अपॉइंटमेंट", "预约", "Rendez-vous", "Termin"],
    ["Followup", "Seguimiento", "फ़ॉलो-अप", "跟进", "Suivi", "Nachverfolgung"],
    ["Alert", "Alerta", "अलर्ट", "警报", "Alerte", "Warnung"],
    ["General", "General", "सामान्य", "一般", "Général", "Allgemein"],
    ["Message Text", "Texto del mensaje", "संदेश पाठ", "消息内容", "Texte du message", "Nachrichtentext"],
    ["Cancel", "Cancelar", "रद्द करें", "取消", "Annuler", "Abbrechen"],
    ["Send Outbound", "Enviar saliente", "आउटबाउंड भेजें", "发送外发消息", "Envoyer", "Ausgehend senden"],
    ["Reminder message content…", "Contenido del recordatorio…", "रिमाइंडर संदेश की सामग्री…", "提醒消息内容…", "Contenu du message de rappel…", "Inhalt der Erinnerung …"],

    // ── attachments, search boxes, tooltips ──
    ["Attach file (PDF, DOCX, image, text)", "Adjuntar archivo (PDF, DOCX, imagen, texto)", "फ़ाइल जोड़ें (PDF, DOCX, छवि, टेक्स्ट)", "添加文件（PDF、DOCX、图片、文本）", "Joindre un fichier (PDF, DOCX, image, texte)", "Datei anhängen (PDF, DOCX, Bild, Text)"],
    ["Attach file", "Adjuntar archivo", "फ़ाइल जोड़ें", "添加文件", "Joindre un fichier", "Datei anhängen"],
    ["Attach document to check (PDF, DOCX, TXT)", "Adjuntar documento para verificar (PDF, DOCX, TXT)", "जाँच के लिए दस्तावेज़ जोड़ें (PDF, DOCX, TXT)", "添加待检查文档（PDF、DOCX、TXT）", "Joindre un document à vérifier (PDF, DOCX, TXT)", "Zu prüfendes Dokument anhängen (PDF, DOCX, TXT)"],
    ["Search research papers, topics, authors…", "Buscar artículos, temas, autores…", "शोध पत्र, विषय, लेखक खोजें…", "搜索研究论文、主题、作者…", "Rechercher des articles, sujets, auteurs…", "Forschungsarbeiten, Themen, Autoren suchen …"],
    ["Ask anything — e.g. what is machine learning? how does GPS work?", "Pregunta lo que quieras, p. ej., ¿qué es el aprendizaje automático? ¿cómo funciona el GPS?", "कुछ भी पूछें — जैसे मशीन लर्निंग क्या है? GPS कैसे काम करता है?", "随意提问——例如：什么是机器学习？GPS 如何工作？", "Posez n'importe quelle question, p. ex. qu'est-ce que l'apprentissage automatique ? comment fonctionne le GPS ?", "Fragen Sie alles – z. B. Was ist maschinelles Lernen? Wie funktioniert GPS?"],
    ["Paste text to check for AI generation or plagiarism… (min 50 words)", "Pega texto para comprobar si lo generó una IA o es plagio… (mín. 50 palabras)", "AI-जनित या साहित्यिक चोरी की जाँच के लिए पाठ चिपकाएँ… (न्यूनतम 50 शब्द)", "粘贴文本以检测 AI 生成或抄袭…（至少 50 个词）", "Collez un texte pour vérifier s'il est généré par l'IA ou plagié… (50 mots min.)", "Text einfügen, um auf KI-Erzeugung oder Plagiat zu prüfen … (mind. 50 Wörter)"],
    ["Voice language", "Idioma de voz", "वॉइस भाषा", "语音语言", "Langue vocale", "Sprachausgabe"],
  ];

  // English (US) differs from the English (AU) source only in spelling.
  const EN_US = {
    "Personalise UI & Theme": "Personalize UI & Theme",
    "Interface Personalisation": "Interface Personalization",
    "Profit Analyser": "Profit Analyzer",
    "Amazon · Alibaba · PPC · Profit Optimiser · 📎 attach files": "Amazon · Alibaba · PPC · Profit Optimizer · 📎 attach files",
    "Research products, source suppliers from Alibaba, build PPC campaigns, and optimise profit margins.": "Research products, source suppliers from Alibaba, build PPC campaigns, and optimize profit margins.",
    "Your AI-powered FBA toolkit — research products, source suppliers, launch PPC campaigns and analyse profit margins.": "Your AI-powered FBA toolkit — research products, source suppliers, launch PPC campaigns and analyze profit margins.",
    "Your 24/7 virtual receptionist — answers calls and SMS, books appointments, and handles enquiries via voice or text.": "Your 24/7 virtual receptionist — answers calls and SMS, books appointments, and handles inquiries via voice or text.",
    "24/7 virtual receptionist — answers calls and SMS, books appointments, and handles enquiries via voice or text.": "24/7 virtual receptionist — answers calls and SMS, books appointments, and handles inquiries via voice or text.",
  };

  const SUPPORTED = ["en-AU", "en-US", "es-US", "hi-IN", "cmn-CN", "fr-FR", "de-DE"];
  const COL_OF = { "es-US": 0, "hi-IN": 1, "cmn-CN": 2, "fr-FR": 3, "de-DE": 4 };
  const HTML_LANG = { "en-AU": "en-AU", "en-US": "en-US", "es-US": "es", "hi-IN": "hi", "cmn-CN": "zh", "fr-FR": "fr", "de-DE": "de" };
  const ATTRS = ["placeholder", "title", "aria-label"];
  const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "TEXTAREA", "NOSCRIPT", "OPTION", "CODE", "PRE"]);

  // Exact lookups, and "{0}" rows turned into patterns.
  const exact = new Map();
  const patterns = [];
  // Longest rules first, so "Online · v{0} · Powered by …" wins over "Online · v{0}".
  [...ROWS].sort((a, b) => b[0].length - a[0].length).forEach((row) => {
    const key = row[0];
    if (key.includes("{0}")) {
      const re = new RegExp("^" + key.replace(/[.*+?^$()|[\]\\]/g, "\\$&").replace("{0}", "(.+?)") + "$", "i");
      patterns.push({ re, row });
    } else {
      exact.set(key.toLowerCase(), row);
    }
  });

  const OBSERVE = { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS };
  let current = "en-AU";
  const originals = new WeakMap(); // text node -> source text
  let observer = null;

  const norm = (s) => s.replace(/\s+/g, " ").trim();

  function fromRow(row, lang, carried) {
    let out;
    if (lang === "en-US") {
      out = EN_US[row[0]];
      if (!out) return null;
    } else {
      out = row[1 + COL_OF[lang]];
    }
    return carried === undefined ? out : out.replace("{0}", carried);
  }

  function lookup(core, lang) {
    const hit = exact.get(core.toLowerCase());
    if (hit) {
      const out = fromRow(hit, lang);
      if (out == null) return null;
      // Keep all-lowercase source text lowercase, e.g. the "delivered" status pill.
      return core === core.toLowerCase() && core !== core.toUpperCase() && /^[\x00-\x7f]+$/.test(core) && lang !== "hi-IN" && lang !== "cmn-CN"
        ? out.toLowerCase()
        : out;
    }
    for (const p of patterns) {
      const m = core.match(p.re);
      if (m) {
        const out = fromRow(p.row, lang, m[1]);
        if (out != null) return out;
      }
    }
    return null;
  }

  // Translate one piece of text, keeping its leading icon and trailing arrow.
  function translate(source, lang) {
    if (lang === "en-AU") return source;
    const lead = source.match(/^\s*/)[0];
    const trail = source.match(/\s*$/)[0];
    const text = norm(source);
    if (!text) return source;
    let out = lookup(text, lang);
    if (out != null) return lead + out + trail;
    const m = text.match(/^([^\p{L}\p{N}+]*)(.*?)([\s↑↗]*)$/su);
    if (m && m[2]) {
      out = lookup(m[2], lang);
      if (out != null) return lead + m[1] + out + m[3] + trail;
    }
    return source;
  }

  function skip(node) {
    for (let el = node.parentElement; el; el = el.parentElement) {
      if (SKIP_TAGS.has(el.tagName) || el.hasAttribute("data-no-i18n")) return true;
      // What people and the AI wrote in the chat is not interface text.
      if (el.classList && (el.classList.contains("msg-row") || el.classList.contains("md-content"))) return true;
    }
    return false;
  }

  function applyText(node) {
    if (skip(node)) return;
    const value = node.nodeValue;
    if (!value || !value.trim()) return;
    let source = originals.get(node);
    // If the page changed this node to something we did not write, that is the new source.
    if (source === undefined || (node.__afOut !== undefined && value !== node.__afOut)) {
      source = value;
      originals.set(node, source);
    }
    const out = translate(source, current);
    node.__afOut = out;
    if (out !== value) node.nodeValue = out;
  }

  function applyAttrs(el) {
    if (el.nodeType !== 1 || el.hasAttribute("data-no-i18n")) return;
    ATTRS.forEach((attr) => {
      if (!el.hasAttribute(attr)) return;
      const store = "data-i18n-src-" + attr;
      const value = el.getAttribute(attr);
      let source = el.getAttribute(store);
      if (source === null || (el.__afOutAttr && el.__afOutAttr[attr] !== undefined && value !== el.__afOutAttr[attr])) {
        source = value;
        el.setAttribute(store, source);
      }
      const out = translate(source, current);
      (el.__afOutAttr = el.__afOutAttr || {})[attr] = out;
      if (out !== value) el.setAttribute(attr, out);
    });
  }

  function walk(root) {
    if (root.nodeType === 3) return applyText(root);
    if (root.nodeType !== 1) return;
    applyAttrs(root);
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let n = tw.nextNode(); n; n = tw.nextNode()) {
      if (n.nodeType === 3) applyText(n);
      else applyAttrs(n);
    }
  }

  function startObserver() {
    if (observer || !document.body) return;
    observer = new MutationObserver((records) => {
      if (current === "en-AU") return;
      observer.disconnect();
      records.forEach((r) => {
        if (r.type === "characterData") applyText(r.target);
        else if (r.type === "attributes") applyAttrs(r.target);
        else r.addedNodes.forEach((n) => walk(n));
      });
      observer.observe(document.body, OBSERVE);
    });
    observer.observe(document.body, OBSERVE);
  }

  function apply(lang) {
    if (!SUPPORTED.includes(lang)) lang = "en-AU";
    current = lang;
    document.documentElement.lang = HTML_LANG[lang];
    if (observer) observer.disconnect();
    walk(document.body);
    if (observer) observer.observe(document.body, OBSERVE);
    else startObserver();
  }

  // Messages built in script (alerts) go through here.
  function t(text) {
    return translate(String(text), current);
  }

  window.AFI18n = { apply, t, supported: SUPPORTED, get current() { return current; } };
})();
