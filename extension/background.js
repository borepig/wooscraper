function hostAllowed(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch (error) {
    return false;
  }
  const host = parsed.hostname.toLowerCase();
  if (parsed.protocol !== 'https:') {
    return false;
  }
  return (
    host.endsWith('.dmm.co.jp')
    || host.endsWith('.javtrailers.com')
    || host === 'javtrailers.com'
    || host.endsWith('.jdbstatic.com')
    || host.endsWith('.javmiku.com')
    || host.endsWith('.javsts.com')
    || host === 'jav.guru'
    || host.endsWith('.javdatabase.com')
    || host === 'javdatabase.com'
    || host.endsWith('.javmost.com')
  );
}

function encodeBytes(bytes) {
  let binary = '';
  const step = 0x8000;
  for (let index = 0; index < bytes.length; index += step) {
    binary += String.fromCharCode.apply(null, bytes.subarray(index, index + step));
  }
  return btoa(binary);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== 'fetch' || !hostAllowed(message.url)) {
    return;
  }
  fetch(message.url).then(async (response) => {
    if (!response.ok) {
      sendResponse({ error: 'status ' + response.status });
      return;
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (!bytes.length || bytes.length > 80_000_000) {
      sendResponse({ error: 'size' });
      return;
    }
    sendResponse({ base64: encodeBytes(bytes) });
  }).catch((error) => {
    sendResponse({ error: String(error) });
  });
  return true;
});
