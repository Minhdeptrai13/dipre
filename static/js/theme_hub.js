/**
 * DIPRE Studio — Theme RPC Hub, Bot Selector & Community Forum JS
 * Tương thích hoàn toàn Supabase và SQLite Realtime Sync
 */

let currentBotAppId = '1118182981329244241';
let currentThemeSubTab = 'forum';
let currentForumTag = '';
let currentForumSearch = '';

document.addEventListener('DOMContentLoaded', () => {
  loadUserBots();
  loadForumTemplates();
});

function switchThemeSubTab(subtab) {
  currentThemeSubTab = subtab;
  
  const btnForum = document.getElementById('btn-subtab-forum');
  const btnMy = document.getElementById('btn-subtab-my');
  const btnEditor = document.getElementById('btn-subtab-editor');
  
  const viewForum = document.getElementById('theme-view-forum');
  const viewEditor = document.getElementById('theme-view-editor');
  
  if (btnForum) btnForum.classList.toggle('active', subtab === 'forum');
  if (btnMy) btnMy.classList.toggle('active', subtab === 'my');
  if (btnEditor) btnEditor.classList.toggle('active', subtab === 'editor');
  
  if (subtab === 'forum') {
    if (viewForum) viewForum.classList.remove('d-none');
    if (viewEditor) viewEditor.classList.add('d-none');
    loadForumTemplates();
  } else if (subtab === 'my') {
    if (viewForum) viewForum.classList.remove('d-none');
    if (viewEditor) viewEditor.classList.add('d-none');
    loadForumTemplates('', '', 'mine');
  } else if (subtab === 'editor') {
    if (viewForum) viewForum.classList.add('d-none');
    if (viewEditor) viewEditor.classList.remove('d-none');
    if (typeof updateLivePreview === 'function') updateLivePreview();
  }
}

async function loadUserBots() {
  try {
    const res = await fetch('/api/portal/apps');
    const data = await res.json();
    if (!data.success || !data.bots) return;
    
    const container = document.getElementById('bot-selector-list');
    if (!container) return;
    
    let html = '';
    data.bots.forEach((b, idx) => {
      const isActive = b.app_id === currentBotAppId || (idx === 0 && !currentBotAppId);
      if (isActive) currentBotAppId = b.app_id;
      
      const avatar = b.bot_avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png';
      html += `
        <div class="bot-selector-card ${isActive ? 'active' : ''}" data-app-id="${b.app_id}" onclick="selectBotApp('${b.app_id}', '${escapeHtml(b.bot_name)}', this)">
          <div class="bot-card-avatar">
            <img src="${avatar}" alt="${escapeHtml(b.bot_name)}" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
          </div>
          <div class="bot-card-info">
            <div class="bot-card-name">${escapeHtml(b.bot_name)}</div>
            <div class="bot-card-id">${b.app_id.slice(0, 7)}...</div>
          </div>
        </div>
      `;
    });
    
    html += `
      <div class="bot-selector-card bot-card-add" onclick="promptAddNewBot()">
        <span>+ Thêm App ID</span>
      </div>
    `;
    container.innerHTML = html;
  } catch (err) {
    console.error('Lỗi nạp Bot Apps:', err);
  }
}

function selectBotApp(appId, botName, el) {
  currentBotAppId = appId;
  document.querySelectorAll('.bot-selector-card').forEach(c => c.classList.remove('active'));
  if (el) el.classList.add('active');
  
  if (typeof showToast === 'function') {
    showToast(`Đã chọn Bot Application: ${botName} (${appId})`, 'info');
  }
  
  const clientInput = document.getElementById('input-client-id');
  if (clientInput) clientInput.value = appId;
  
  if (typeof updateLivePreview === 'function') updateLivePreview();
}

async function promptAddNewBot() {
  const appId = prompt('Nhập Application ID từ Discord Developer Portal (chuỗi số 18-19 chữ số):');
  if (!appId || !appId.trim()) return;
  
  const botName = prompt('Nhập Tên Ứng Dụng / Bot (Ví dụ: Valorant Tracker, Lofi Radio):') || 'Custom Bot App';
  
  try {
    const res = await fetch('/api/portal/apps/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_id: appId.trim(), bot_name: botName.trim() })
    });
    const data = await res.json();
    if (data.success) {
      if (typeof showToast === 'function') showToast(data.message, 'success');
      loadUserBots();
    } else {
      alert(data.message || 'Không thể thêm bot application');
    }
  } catch (err) {
    alert('Lỗi kết nối khi thêm Bot Application');
  }
}

async function loadForumTemplates(tag = '', search = '', sort = 'newest') {
  const grid = document.getElementById('forum-templates-grid');
  if (!grid) return;
  
  grid.innerHTML = '<div style="grid-column: 1 / -1; text-align:center; padding: 40px; color: var(--text-subtle);">Đang nạp dữ liệu mẫu RPC...</div>';
  
  try {
    let url = `/api/templates?sort=${sort}`;
    if (tag) url += `&tag=${encodeURIComponent(tag)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    
    const res = await fetch(url);
    const data = await res.json();
    
    if (!data.success || !data.templates || data.templates.length === 0) {
      renderDefaultMockTemplates(grid);
      return;
    }
    
    renderTemplatesList(grid, data.templates);
  } catch (err) {
    console.warn('Không thể nạp templates, hiển thị kho mẫu phong phú có sẵn:', err);
    renderDefaultMockTemplates(grid);
  }
}

function renderTemplatesList(container, list) {
  let html = '';
  list.forEach(t => {
    const preview = t.preview_image_url || (t.rpc_config && t.rpc_config.large_image) || 'https://media.giphy.com/media/LmN8OYiY4m0X85QbZ8/giphy.gif';
    const tags = Array.isArray(t.tags) ? t.tags : [];
    const tagsHtml = tags.map(tg => `<span class="template-tag">#${escapeHtml(tg)}</span>`).join('');
    
    html += `
      <div class="template-card">
        <div class="template-preview-box">
          <img src="${preview}" alt="${escapeHtml(t.title)}" class="template-preview-img" onerror="this.src='https://media.giphy.com/media/LmN8OYiY4m0X85QbZ8/giphy.gif'">
        </div>
        <div class="template-content">
          <div class="template-header">
            <div class="template-title">${escapeHtml(t.title)}</div>
          </div>
          <div class="template-author">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            <span>${escapeHtml(t.author_name || 'DIPRE Member')}</span>
          </div>
          <div class="template-desc">${escapeHtml(t.description || 'Mẫu RPC thiết kế chuyên nghiệp cho Discord.')}</div>
          <div class="template-tags">${tagsHtml}</div>
          <div class="template-footer">
            <div class="template-stats">
              <span class="template-stat-item" style="cursor:pointer" onclick="toggleLikeTemplate(${t.id}, this)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="${t.is_liked ? '#f43f5e' : 'none'}" stroke="${t.is_liked ? '#f43f5e' : 'currentColor'}" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
                <b class="like-num">${t.likes_count || 0}</b>
              </span>
              <span class="template-stat-item">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                <span>${t.uses_count || 0}</span>
              </span>
            </div>
            <button type="button" class="template-btn-use" onclick="applyTemplate(${t.id}, ${escapeHtml(JSON.stringify(t.rpc_config || {}))})">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              <span>Dùng Template</span>
            </button>
          </div>
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

function renderDefaultMockTemplates(container) {
  const defaultTemplates = [
    {
      id: 101,
      title: 'Cyberpunk 2077 Night City',
      author_name: 'Minhdeptrai',
      description: 'Phong cách hacker cyberpunk ngập tràn ánh đèn neon và âm hưởng synthwave viễn tưởng.',
      preview_image_url: 'https://media.giphy.com/media/LmN8OYiY4m0X85QbZ8/giphy.gif',
      tags: ['cyberpunk', 'gaming', 'matrix'],
      likes_count: 42,
      uses_count: 189,
      rpc_config: {
        activity_type: 'playing',
        activity_name: 'Cyberpunk 2077',
        details: 'Hacking Arasaka Mainframe',
        state: 'Overclocking Cyberware [99%]',
        large_image: 'https://media.giphy.com/media/LmN8OYiY4m0X85QbZ8/giphy.gif',
        large_text: 'Cyberpunk Neural Network',
        button1_label: 'Connect Matrix',
        button1_url: 'https://discord.gg',
        button2_label: 'Profile',
        button2_url: 'https://github.com'
      }
    },
    {
      id: 102,
      title: 'Anime Lofi Chill & Rainy Mood',
      author_name: 'AsagiVibes',
      description: 'Giai điệu lofi êm dịu hòa quyện cùng tiếng mưa rơi bên ô cửa sổ anime yên bình.',
      preview_image_url: 'https://media.giphy.com/media/3oKIPnAiaMCws8nOsE/giphy.gif',
      tags: ['anime', 'lofi', 'chill'],
      likes_count: 67,
      uses_count: 312,
      rpc_config: {
        activity_type: 'listening',
        activity_name: 'Lofi Girl - Beats to relax/study',
        details: 'Drinking hot matcha latte',
        state: 'Watching raindrops fall',
        large_image: 'https://media.giphy.com/media/3oKIPnAiaMCws8nOsE/giphy.gif',
        large_text: 'Cozy Rainy Days',
        button1_label: 'Listen Along',
        button1_url: 'https://youtube.com',
        button2_label: 'Lofi Playlist',
        button2_url: 'https://spotify.com'
      }
    },
    {
      id: 103,
      title: 'Fullstack Dev in Deep Focus',
      author_name: 'TrisArchitect',
      description: 'Trạng thái tập trung viết code với VS Code, tối ưu hóa thuật toán và xây dựng hệ sinh thái.',
      preview_image_url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/vscode/vscode-original.svg',
      tags: ['gaming', 'cyberpunk'],
      likes_count: 38,
      uses_count: 145,
      rpc_config: {
        activity_type: 'playing',
        activity_name: 'Visual Studio Code',
        details: 'Refactoring DiscordRPC Core Engine',
        state: 'Writing clean code without mercy',
        large_image: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/vscode/vscode-original.svg',
        large_text: 'VS Code Insiders',
        button1_label: 'View Repository',
        button1_url: 'https://github.com',
        button2_label: 'Discord Server',
        button2_url: 'https://discord.gg'
      }
    },
    {
      id: 104,
      title: 'Retro Synthwave Highway Run',
      author_name: 'SolsticeUser',
      description: 'Lái siêu xe xuyên qua con đường hoàng hôn tím rực và dãy núi neon thập niên 80.',
      preview_image_url: 'https://media.giphy.com/media/xT9IgzoKnwFNmISR8I/giphy.gif',
      tags: ['music', 'lofi'],
      likes_count: 53,
      uses_count: 220,
      rpc_config: {
        activity_type: 'listening',
        activity_name: 'Synthwave Radio 1984',
        details: 'Driving Testarossa on Neon Sunset Highway',
        state: 'Cruising at 180 km/h',
        large_image: 'https://media.giphy.com/media/xT9IgzoKnwFNmISR8I/giphy.gif',
        large_text: 'Outrun Synthwave',
        button1_label: 'Stream Track',
        button1_url: 'https://soundcloud.com',
        button2_label: 'Join Ride',
        button2_url: 'https://discord.gg'
      }
    }
  ];
  
  renderTemplatesList(container, defaultTemplates);
}

function applyTemplate(templateId, config) {
  if (typeof config === 'string') {
    try { config = JSON.parse(config); } catch (e) { config = {}; }
  }
  
  if (config.activity_name) {
    const actInput = document.getElementById('input-activity-name');
    if (actInput) actInput.value = config.activity_name;
  }
  if (config.details) {
    const detInput = document.getElementById('input-details');
    if (detInput) detInput.value = config.details;
  }
  if (config.state) {
    const stInput = document.getElementById('input-state');
    if (stInput) stInput.value = config.state;
  }
  if (config.activity_type) {
    const typeSelect = document.getElementById('select-activity-type');
    if (typeSelect) typeSelect.value = config.activity_type;
  }
  if (config.large_image) {
    const imgInput = document.getElementById('input-large-img') || document.getElementById('input-custom-large-url');
    if (imgInput) imgInput.value = config.large_image;
    currentLargeImageUrl = config.large_image;
    const boxLarge = document.getElementById('box-large-preview');
    if (boxLarge) {
      boxLarge.src = config.large_image;
      boxLarge.style.display = 'block';
    }
  }
  if (config.button1_label) {
    const b1l = document.getElementById('input-btn1-label') || document.getElementById('input-btn1-text');
    if (b1l) b1l.value = config.button1_label;
  }
  if (config.button1_url) {
    const b1u = document.getElementById('input-btn1-url');
    if (b1u) b1u.value = config.button1_url;
  }
  if (config.button2_label) {
    const b2l = document.getElementById('input-btn2-label') || document.getElementById('input-btn2-text');
    if (b2l) b2l.value = config.button2_label;
  }
  if (config.button2_url) {
    const b2u = document.getElementById('input-btn2-url');
    if (b2u) b2u.value = config.button2_url;
  }

  if (templateId) {
    fetch(`/api/templates/${templateId}/use`, { method: 'POST' }).catch(() => {});
  }

  switchThemeSubTab('editor');
  if (typeof updateLivePreview === 'function') {
    updateLivePreview();
  }
  
  if (typeof showToast === 'function') {
    showToast('Đã áp dụng Template thành công! Bạn có thể xem trước và bấm "Bắt Đầu Presence".', 'success');
  }
}

async function toggleLikeTemplate(templateId, el) {
  try {
    const res = await fetch(`/api/templates/${templateId}/like`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      const numSpan = el.querySelector('.like-num');
      const svg = el.querySelector('svg');
      if (numSpan) {
        let count = parseInt(numSpan.textContent) || 0;
        count = data.liked ? count + 1 : Math.max(0, count - 1);
        numSpan.textContent = count;
      }
      if (svg) {
        svg.setAttribute('fill', data.liked ? '#f43f5e' : 'none');
        svg.setAttribute('stroke', data.liked ? '#f43f5e' : 'currentColor');
      }
    }
  } catch (err) {
    console.error('Lỗi like template:', err);
  }
}

async function handlePublishToForum() {
  const title = (document.getElementById('input-template-title')?.value || '').trim();
  if (!title) {
    alert('Vui lòng nhập Tiêu Đề cho Template tại mục "D — Chia Sẻ Lên Diễn Đàn"!');
    document.getElementById('input-template-title')?.focus();
    return;
  }

  const desc = (document.getElementById('input-template-desc')?.value || '').trim();
  const tagsStr = (document.getElementById('input-template-tags')?.value || '').trim();
  const tags = tagsStr ? tagsStr.split(',').map(s => s.trim()).filter(Boolean) : ['custom'];
  const isPublic = document.getElementById('check-template-public')?.checked ?? true;

  const config = {
    activity_name: document.getElementById('input-activity-name')?.value || '',
    details: document.getElementById('input-details')?.value || '',
    state: document.getElementById('input-state')?.value || '',
    activity_type: document.getElementById('select-activity-type')?.value || 'playing',
    large_image: document.getElementById('input-custom-large-url')?.value || '',
    button1_label: document.getElementById('input-btn1-text')?.value || '',
    button1_url: document.getElementById('input-btn1-url')?.value || '',
    button2_label: document.getElementById('input-btn2-text')?.value || '',
    button2_url: document.getElementById('input-btn2-url')?.value || ''
  };

  try {
    const res = await fetch('/api/templates/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        description: desc,
        tags: tags,
        rpc_config: config,
        preview_image_url: config.large_image,
        is_public: isPublic
      })
    });
    const data = await res.json();
    if (data.success) {
      if (typeof showToast === 'function') {
        showToast('Chúc mừng! Mẫu RPC của bạn đã được xuất bản lên Diễn Đàn thành công!', 'success');
      }
      switchThemeSubTab('forum');
    } else {
      alert(data.message || 'Lỗi khi lưu mẫu RPC');
    }
  } catch (err) {
    alert('Lỗi kết nối khi xuất bản Template');
  }
}

function handleForumSearch() {
  const val = (document.getElementById('forum-search-input')?.value || '').trim();
  currentForumSearch = val;
  loadForumTemplates(currentForumTag, currentForumSearch);
}

function filterForumByTag(tag, el) {
  currentForumTag = tag;
  document.querySelectorAll('.tag-filter-btn').forEach(b => b.classList.remove('active'));
  if (el) el.classList.add('active');
  loadForumTemplates(currentForumTag, currentForumSearch);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}