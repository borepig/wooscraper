window.wooscraperDirect = function (url) {
  return new Promise((resolve) => {
    const id = String(Math.random());
    function onMessage(event) {
      if (event.source !== window || !event.data || event.data.source !== 'wooscraper-extension' || event.data.id !== id) {
        return;
      }
      window.removeEventListener('message', onMessage);
      if (!event.data.base64) {
        resolve(null);
        return;
      }
      const binary = atob(event.data.base64);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      resolve(bytes);
    }
    window.addEventListener('message', onMessage);
    window.postMessage({ source: 'wooscraper-page', id: id, url: url }, '*');
  });
};
