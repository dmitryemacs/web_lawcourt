document.addEventListener('DOMContentLoaded', () => {
  const openBtn = document.getElementById('ai-chat-open');
  const chatModal = document.getElementById('ai-chat-modal');
  const closeBtn = document.getElementById('ai-chat-close');
  const form = document.getElementById('ai-chat-form');
  const messagesBox = document.getElementById('ai-messages');

  function appendMessage(role, text) {
    const div = document.createElement('div');
    div.className = 'ai-message ' + (role === 'user' ? 'user' : 'assistant');
    div.textContent = text;
    messagesBox.appendChild(div);
    messagesBox.scrollTop = messagesBox.scrollHeight;
  }

  openBtn && openBtn.addEventListener('click', () => {
    chatModal.classList.add('is-active');
    document.getElementById('ai-chat-input').focus();
  });

  closeBtn && closeBtn.addEventListener('click', () => {
    chatModal.classList.remove('is-active');
  });

  form && form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('ai-chat-input');
    const text = input.value.trim();
    if (!text) return;
    appendMessage('user', text);
    input.value = '';

    appendMessage('assistant', '...');
    const placeholder = messagesBox.querySelector('.assistant:last-child');

    try {
      const resp = await fetch('/ai-chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: text})
      });

      if (!resp.ok) {
        if (resp.status === 403) {
          placeholder.innerHTML = 'Требуется вход. <a href="/login">Войти</a>';
          return;
        }
        const err = await resp.json().catch(() => ({}));
        if (resp.status === 503) {
          placeholder.innerHTML = `<strong>AI Chat недоступен:</strong><br>${err.detail || 'Сервис временно недоступен.<br>Docker DNS issue - нужна конфигурация.'}`;
        } else {
          placeholder.textContent = 'Ошибка: ' + (err.detail || resp.statusText);
        }
        return;
      }

      const data = await resp.json();
      // Prefer normalized `reply` field, fall back to common structures
      let reply = '';
      if (data.reply) {
        reply = data.reply;
      } else if (data.choices && data.choices.length) {
        reply = data.choices[0].message?.content || data.choices[0].text || '';
      } else if (data.result) {
        reply = data.result;
      } else {
        reply = JSON.stringify(data);
      }

      placeholder.textContent = reply;
    } catch (err) {
      placeholder.textContent = 'Ошибка сети: ' + err.message;
    }
  });
});
