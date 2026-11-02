(function (window) {
  // Set this to the deployed Render service URL before publishing GitHub Pages.
  window.ASSOCIATIONHUB_API_BASE_URL = 'https://associationhub2.onrender.com';
  const configuredBase = (window.ASSOCIATIONHUB_API_BASE_URL || '').trim();
  let apiBase = configuredBase.replace(/\/+$/, '');

  if (apiBase) {
    let parsed;
    try {
      parsed = new URL(apiBase);
    } catch (error) {
      throw new Error('ASSOCIATIONHUB_API_BASE_URL must be an absolute HTTP(S) URL.');
    }
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
      throw new Error('ASSOCIATIONHUB_API_BASE_URL must be an HTTP(S) URL without embedded credentials.');
    }
  } else if (
    window.location.protocol === 'file:' ||
    (['localhost', '127.0.0.1'].includes(window.location.hostname) && window.location.port !== '8080')
  ) {
    apiBase = 'http://127.0.0.1:8080';
  } else if (!window.location.hostname.endsWith('.github.io')) {
    apiBase = window.location.origin;
  }

  window.API_BASE = apiBase;
  window.apiFetch = function (path, options = {}) {
    if (!apiBase) {
      const error = new Error(
        'AssociationHub backend is not configured. Set ASSOCIATIONHUB_API_BASE_URL in api-config.js to the Render service URL.'
      );
      if (!window._associationHubApiConfigErrorShown) {
        window._associationHubApiConfigErrorShown = true;
        console.error(error.message);
      }
      return Promise.reject(error);
    }

    const url = /^https?:\/\//i.test(path)
      ? path
      : apiBase + (path.startsWith('/') ? path : `/${path}`);
    return fetch(url, options);
  };

  if (!apiBase && window.location.hostname.endsWith('.github.io')) {
    window.addEventListener('DOMContentLoaded', function () {
      const notice = document.createElement('div');
      notice.setAttribute('role', 'alert');
      notice.style.cssText = 'position:relative;z-index:10000;padding:12px 20px;background:#3b1d1d;color:#fff;text-align:center;font:500 14px/1.5 sans-serif';
      notice.textContent = 'Backend API is not configured. Set ASSOCIATIONHUB_API_BASE_URL in api-config.js to the Render service URL.';
      document.body.prepend(notice);
    });
  }
})(window);
