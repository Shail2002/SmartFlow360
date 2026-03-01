// smartflow360-extension/content.js

(function () {
  // Prevent double-inject
  if (document.getElementById("sf360-float-btn")) return;

  const btn = document.createElement("button");
  btn.id = "sf360-float-btn";
  btn.textContent = "SmartFlow360";
  btn.style.position = "fixed";
  btn.style.right = "16px";
  btn.style.bottom = "16px";
  btn.style.zIndex = "999999";
  btn.style.padding = "10px 12px";
  btn.style.borderRadius = "10px";
  btn.style.border = "1px solid rgba(0,0,0,0.2)";
  btn.style.background = "#111";
  btn.style.color = "#fff";
  btn.style.fontSize = "14px";
  btn.style.cursor = "pointer";
  btn.style.boxShadow = "0 8px 18px rgba(0,0,0,0.25)";

  btn.addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "SF360_OPEN_WINDOW" });
  });

  document.documentElement.appendChild(btn);

  // OPTIONAL: auto-open (disabled by default)
  // If you want it to automatically open once per page load:
  // chrome.runtime.sendMessage({ type: "SF360_OPEN_WINDOW" });
})();