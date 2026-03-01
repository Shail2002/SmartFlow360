// smartflow360-extension/background.js

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg?.type === "SF360_OPEN_WINDOW") {
    const url = chrome.runtime.getURL("popup.html");
    chrome.windows.create({
      url,
      type: "popup",
      width: 420,
      height: 720
    });
  }
});