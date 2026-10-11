const hook = document.createElement('script');
hook.src = chrome.runtime.getURL('page-hook.js');
hook.onload = () => hook.remove();
(document.head || document.documentElement).appendChild(hook);

window.addEventListener('message', (event) => {
  if (event.source !== window || !event.data || event.data.source !== 'wooscraper-page') {
    return;
  }
  chrome.runtime.sendMessage({ type: 'fetch', url: event.data.url }, (response) => {
    const failed = chrome.runtime.lastError;
    window.postMessage({
      source: 'wooscraper-extension',
      id: event.data.id,
      base64: response && response.base64,
      error: failed ? failed.message : (response && response.error)
    }, '*');
  });
});
