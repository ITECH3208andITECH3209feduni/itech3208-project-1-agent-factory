/**
 * static/js/app.js — Agent Factory Chat UI
 * PROJ-142 (Dilraj Singh)
 * sendMessage(), loadHistory(), renderCards()
 */
const API_BASE = "";
const chatArea = document.getElementById("chat-area");
const input = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const cardsSection = document.getElementById("cards-section");
const cardsGrid = document.getElementById("cards-grid");
const cardsTitle = document.getElementById("cards-title");
const statusDot = document.getElementById("status-dot");
let isLoading = false;
document.addEventListener("DOMContentLoaded", () => {
  checkStatus(); loadHistory();
  input.addEventListener("keydown", e => { if (e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMessage();} });
  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("input", () => { input.style.height="auto"; input.style.height=Math.min(input.scrollHeight,100)+"px"; });
});
async function checkStatus() {
  try { const r=await fetch(API_BASE+"/status"); const d=await r.json(); statusDot.className=d.status==="ok"?"online":"offline"; }
  catch { statusDot.className="offline"; }
}
async function sendMessage() {
  const query=input.value.trim(); if(!query||isLoading)return;
  appendBubble(query,"user"); input.value=""; input.style.height="auto"; setLoading(true);
  const tid=showTyping();
  try {
    const res=await fetch(API_BASE+"/query",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query})});
    if(!res.ok)throw new Error("Server error: "+res.status);
    const data=await res.json(); removeTyping(tid);
    appendBubble(data.response,"agent");
    if(data.cards&&data.cards.length>0)renderCards(data.cards,data.type); else hideCards();
  } catch(err) { removeTyping(tid); appendBubble("Sorry, something went wrong: "+err.message,"error"); hideCards(); }
  finally { setLoading(false); scrollToBottom(); }
}
async function loadHistory() {
  try {
    const res=await fetch(API_BASE+"/history"); if(!res.ok)return;
    const history=await res.json(); if(!history||history.length===0)return;
    const div=document.createElement("div"); div.style.cssText="text-align:center;color:var(--text-dim);font-size:12px;padding:4px 0;";
    div.textContent=`-- ${history.length} previous queries --`; chatArea.insertBefore(div,chatArea.firstChild);
    history.slice(-5).forEach(item=>{ appendBubble(item.query,"user",true); if(item.summary)appendBubble(item.summary,"agent",true); });
  } catch{}
}
function renderCards(cards,type) {
  cardsGrid.innerHTML="";
  cardsTitle.textContent=type==="amazon"?`🛒 Amazon Results (${cards.length})`:`📚 Research Papers (${cards.length})`;
  cards.forEach(card=>{ const el=document.createElement("div"); el.innerHTML=type==="amazon"?buildProductCard(card):buildPaperCard(card); cardsGrid.appendChild(el.firstElementChild); });
  cardsSection.classList.remove("hidden"); cardsSection.scrollIntoView({behavior:"smooth",block:"nearest"});
}
function buildProductCard(c) {
  const cm={green:"#27ae60",amber:"#f39c12",red:"#e74c3c"}; const bc=cm[c.score_color]||"#888";
  const stars="★".repeat(Math.round(c.rating))+"☆".repeat(5-Math.round(c.rating));
  const href=c.url?`href="${escHtml(c.url)}" target="_blank"`:""; const bsr=c.bsr?`<div class="card-bsr">BSR #${c.bsr}${c.category?" in "+c.category:""}</div>`:""; 
  return `<div class="card product-card" data-score="${c.score}"><div class="card-score-badge" style="background:${bc}">${c.score}</div><div class="card-body"><a ${href} class="card-title">${escHtml(c.title)}</a><div class="card-meta"><span class="card-price">${escHtml(c.price||"N/A")}</span><span class="card-stars">${stars}</span><span>(${(c.review_count||0).toLocaleString()} reviews)</span></div>${bsr}</div></div>`;
}
function buildPaperCard(c) {
  const src=(c.source||"arxiv").replace("_"," ").toUpperCase(); const href=c.url?`href="${escHtml(c.url)}" target="_blank"`:""; 
  const cit=c.citations?`<span class="card-citations" data-citations="${c.citations}">📚 ${c.citations.toLocaleString()} citations</span>`:""; 
  return `<div class="card paper-card" data-citations="${c.citations||0}"><div class="card-source-tag">${escHtml(src)}</div><div class="card-body"><a ${href} class="card-title">${escHtml(c.title)}</a><div class="card-meta"><span class="card-authors">${escHtml(c.authors||"")} </span>${c.year?`<span class="card-year">(${escHtml(c.year)})</span>`:""} ${cit}</div><p class="card-abstract">${escHtml(c.abstract||"")} </p></div></div>`;
}
function hideCards(){cardsSection.classList.add("hidden");cardsGrid.innerHTML="";}
function appendBubble(text,type,prepend=false){
  const el=document.createElement("div"); const cls=type==="user"?"user-bubble":type==="error"?"error-bubble":"agent-bubble"; el.className=`chat-bubble ${cls}`; el.textContent=text;
  if(prepend){const d=chatArea.querySelector("div[style]");chatArea.insertBefore(el,d?d.nextSibling:chatArea.firstChild);}else chatArea.appendChild(el); return el;
}
function showTyping(){const id="t"+Date.now();const el=document.createElement("div");el.id=id;el.className="chat-bubble typing-bubble";el.innerHTML='<div class="typing-dots"><span></span><span></span><span></span></div>';chatArea.appendChild(el);scrollToBottom();return id;}
function removeTyping(id){const el=document.getElementById(id);if(el)el.remove();}
function setLoading(s){isLoading=s;sendBtn.disabled=s;input.disabled=s;}
function scrollToBottom(){chatArea.scrollTop=chatArea.scrollHeight;}
function escHtml(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
