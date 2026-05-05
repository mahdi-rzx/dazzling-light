(()=>{var b=document.createElement("style");b.textContent=`@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400;1,700&display=swap');\r
\r
.support-widget-button {\r
    border: 1px solid #fff;\r
    border-radius: 99px;\r
    width: 3.5rem;\r
    height: 3.5rem;\r
    margin-bottom: 1rem;\r
    margin-left: 1rem;\r
    box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);\r
    cursor: pointer;\r
    font-size: 2.5em;\r
    font-weight: bold;\r
    background-color: #127BC4;\r
    color: #fff;\r
}\r
\r
.support-widget-button-img {\r
    width: 100%;\r
    height: 100%;\r
}\r
\r
.support-modal {\r
    font-family: 'Atkinson Hyperlegible', sans-serif;\r
    display: none;\r
    position: fixed;\r
    z-index: 1000;\r
    left: 50%;\r
    top: 50%;\r
    width: 25rem;\r
    height: 25rem;\r
    overflow: auto;\r
    border: 1px solid gray;\r
    border-radius: 0.375rem; /* Davis rounded-md */\r
    visibility: hidden;\r
    transform: translate(-50%, -50%);\r
    padding: 1rem;\r
\r
    background: #fff;\r
    box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);\r
}\r
\r
.support-modal-content {\r
    display: flex;\r
    flex-direction: column;\r
    align-items: center;\r
    justify-content: flex-start;\r
    height: 100%;\r
}\r
\r
.support-modal-header-logo {\r
    width: 95%;\r
    height: 100px;\r
    margin-top: 0.25rem;\r
    margin-bottom: 0.25rem;\r
}\r
\r
.support-modal-body {\r
    display: flex;\r
    flex-direction: column;\r
    align-items: center;\r
    justify-content: center;\r
}\r
\r
.support-modal-header {\r
    font-size: 1.75em;\r
    font-weight: bold;\r
    margin-top: 0px;\r
    margin-bottom: 0px;\r
}\r
\r
.support-modal-button {\r
    background: #127BC4;\r
    color: white;\r
    border: none;\r
    border-radius: 0.375rem; /* Davis rounded-md */\r
    padding: 0.5rem 1rem;\r
    margin-bottom: 0.75rem;\r
    cursor: pointer;\r
    width: 90%;\r
    height: 4rem;\r
    font-size: 1.15em;\r
    font-weight: bold;\r
}\r
\r
.support-modal-button:hover {\r
    background-color: #106098; /* Davis primary-600 */\r
    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);\r
}\r
\r
.support-modal-close-button {\r
    position: absolute;\r
    top: 0.5rem;\r
    right: 0.5rem;\r
    background: none;\r
    border: none;\r
    cursor: pointer;\r
    font-size: 1.5em;\r
}\r
\r
.support-widget-button:focus-visible {\r
    outline: 3px solid #fff;\r
    outline-offset: 3px;\r
}\r
\r
.support-modal-button:focus-visible {\r
    outline: 3px solid #106098; /* Davis primary-600 */\r
    outline-offset: 2px;\r
    background-color: #0e6aaa;\r
}\r
\r
.support-modal-close-button:focus-visible {\r
    outline: 3px solid #106098; /* Davis primary-600 */\r
    outline-offset: 2px;\r
}\r
\r
.support-widget-sr-only {\r
    position: absolute;\r
    width: 1px;\r
    height: 1px;\r
    padding: 0;\r
    margin: -1px;\r
    overflow: hidden;\r
    clip: rect(0, 0, 0, 0);\r
    white-space: nowrap;\r
    border: 0;\r
}`;document.head.appendChild(b);var l=!1;f();function f(){let t=document.getElementById("support-widget-container");if(!t){console.error('LibreTexts Support Widget: Parent element not found. Please add a div with id="support-widget-container" to your page.');return}let e=document.createElement("button"),n=document.createElement("img");n.src="https://cdn.libretexts.net/Icons/libretexts.png",n.alt="LibreTexts Support",n.className="support-widget-button-img",e.id="supportButton",e.className="support-widget-button",e.innerHTML="?",e.setAttribute("aria-label","Open support menu"),e.setAttribute("aria-expanded","false"),e.setAttribute("aria-controls","supportModal"),e.addEventListener("click",()=>x()),t.appendChild(e),h()}function h(){let t=document.createElement("div");t.id="supportModal",t.className="support-modal",t.setAttribute("role","dialog"),t.setAttribute("aria-modal","true"),t.setAttribute("aria-labelledby","supportModalTitle"),t.setAttribute("tabindex","-1");let e=document.createElement("div");e.className="support-modal-content";let n=document.createElement("img");n.src="https://cdn.libretexts.net/Icons/full_logo.png",n.alt="LibreTexts Logo",n.className="support-modal-header-logo",e.appendChild(n);let s=document.createElement("h2");s.id="supportModalTitle",s.className="support-modal-header",s.innerHTML="Support Center",e.appendChild(s);let u=document.createElement("h3");u.innerHTML="How can we help you today?",e.appendChild(u);let i=document.createElement("button");i.className="support-modal-button",i.innerHTML='Contact Support<span class="support-widget-sr-only"> (opens in new tab)</span>',i.addEventListener("click",()=>y());let a=document.createElement("button");a.className="support-modal-button",a.innerHTML='Search the Insight Knowledge Base<span class="support-widget-sr-only"> (opens in new tab)</span>',a.addEventListener("click",()=>w());let d=document.createElement("button");d.className="support-modal-button",d.innerHTML='Check System Status<span class="support-widget-sr-only"> (opens in new tab)</span>',d.addEventListener("click",()=>v());let r=document.createElement("button");r.className="support-modal-close-button",r.innerHTML="&times;",r.setAttribute("aria-label","Close dialog"),r.addEventListener("click",()=>g()),e.insertBefore(r,n),e.appendChild(i),e.appendChild(a),e.appendChild(d),t.appendChild(e),document.body.appendChild(t),document.body.addEventListener("keydown",o=>{if(o.key==="Escape"&&l){g();return}if(o.key==="Tab"&&l){let p=Array.from(t.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'));if(p.length===0)return;let c=p[0],m=p[p.length-1];o.shiftKey?document.activeElement===c&&(o.preventDefault(),m.focus()):document.activeElement===m&&(o.preventDefault(),c.focus())}})}function x(){let t=document.getElementById("supportModal");if(!t){console.error('LibreTexts Support Widget: Modal not found. Please add a div with id="supportModal" to your page.');return}document.querySelectorAll("body > *:not(#supportModal)").forEach(n=>{n.setAttribute("aria-hidden","true")}),t.style.display="block",t.style.visibility="visible";let e=t.querySelector("button");e?e.focus():t.focus(),l=!0,document.getElementById("supportButton").setAttribute("aria-expanded","true")}function g(){let t=document.getElementById("supportModal");if(!t){console.error('LibreTexts Support Widget: Modal not found. Please add a div with id="supportModal" to your page.');return}document.querySelectorAll("body > *:not(#supportModal)").forEach(e=>{e.removeAttribute("aria-hidden")}),t.style.display="none",t.style.visibility="hidden",l=!1,document.getElementById("supportButton").setAttribute("aria-expanded","false"),document.getElementById("supportButton").focus()}function y(){let t=window.location.href;window.open("https://commons.libretexts.org/support/contact?from=widget&fromURL="+t,"_blank")}function w(){window.open("https://commons.libretexts.org/insight","_blank")}function v(){window.open("https://status.libretexts.org","_blank")}})();
