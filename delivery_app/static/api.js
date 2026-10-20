// HTTP client for the Python backend. tools/build_demo.py swaps this file for
// mock-api.js to produce the standalone demo, so both must expose the same API.
(function () {
  async function request(method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Erreur ${res.status}`);
    return data;
  }
  const get = (u) => request('GET', u);
  const post = (u, b) => request('POST', u, b ?? {});
  const put = (u, b) => request('PUT', u, b);
  const del = (u) => request('DELETE', u);

  window.API = {
    demo: false,
    getSettings: () => get('/api/settings'),
    saveSettings: (data) => put('/api/settings', data),

    listTasks: () => get('/api/tasks'),
    createTask: (data) => post('/api/tasks', data),
    updateTask: (id, data) => put(`/api/tasks/${id}`, data),
    deleteTask: (id) => del(`/api/tasks/${id}`),
    reorderTasks: (ids) => post('/api/tasks/reorder', { ids }),

    listDeliveries: () => get('/api/deliveries'),
    createDelivery: (data) => post('/api/deliveries', data),
    getDelivery: (id) => get(`/api/deliveries/${id}`),
    updateDelivery: (id, data) => put(`/api/deliveries/${id}`, data),
    deleteDelivery: (id) => del(`/api/deliveries/${id}`),
    addDeliveryTask: (id, data) => post(`/api/deliveries/${id}/tasks`, data),
    reorderDeliveryTasks: (id, ids) => post(`/api/deliveries/${id}/reorder`, { ids }),

    updateDeliveryTask: (id, data) => put(`/api/delivery-tasks/${id}`, data),
    deleteDeliveryTask: (id) => del(`/api/delivery-tasks/${id}`),
    taskAction: (id, action) => post(`/api/delivery-tasks/${id}/action`, { action }),
    addComment: (id, body) => post(`/api/delivery-tasks/${id}/comments`, { body }),
    deleteComment: (id) => del(`/api/comments/${id}`),
    deleteImage: (id) => del(`/api/images/${id}`),

    async uploadImage(taskId, file) {
      const res = await fetch(`/api/delivery-tasks/${taskId}/images`, {
        method: 'POST',
        headers: { 'Content-Type': file.type, 'X-Filename': encodeURIComponent(file.name || 'capture.png') },
        body: file,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `Erreur ${res.status}`);
      return data;
    },

    exportReport: (id, fmt) => download(`/api/deliveries/${id}/report.${fmt}`, `livraison.${fmt}`),
    exportTaskTable: (id, index) => download(
      index === null || index === undefined ? `/api/delivery-tasks/${id}/tables.docx` : `/api/delivery-tasks/${id}/tables/${index}.docx`,
      'tableaux.docx'),
  };

  async function download(url, fallbackName) {
    const res = await fetch(url);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `Erreur ${res.status}`);
    }
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob());
    a.download = match ? decodeURIComponent(match[1]) : fallbackName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }
})();
