
const KNOWN_ASSET_ICONS = {
  vscode: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/vscode/vscode-original.svg', name: 'VSCode' },
  python: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/python/python-original.svg', name: 'Python' },
  git: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/git/git-original.svg', name: 'Git' },
  docker: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/docker/docker-original.svg', name: 'Docker' },
  js: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/javascript/javascript-original.svg', name: 'JavaScript' },
  ts: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/typescript/typescript-original.svg', name: 'TypeScript' },
  jsx: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/react/react-original.svg', name: 'React JSX' },
  tsx: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/react/react-original.svg', name: 'React TSX' },
  html: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/html5/html5-original.svg', name: 'HTML' },
  css: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/css3/css3-original.svg', name: 'CSS' },
  c: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/c/c-original.svg', name: 'C' },
  cpp: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/cplusplus/cplusplus-original.svg', name: 'C++' },
  csharp: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/csharp/csharp-original.svg', name: 'C#' },
  java: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/java/java-original.svg', name: 'Java' },
  rust: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/rust/rust-original.svg', name: 'Rust' },
  go: { url: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/go/go-original.svg', name: 'Go' }
};

const LYRIC_TRACKS = {
  sunset: {
    url: 'https://w.soundcloud.com/player/?url=https%3A//api.soundcloud.com/tracks/236166415&color=%236366f1&auto_play=false&hide_related=true&show_comments=false',
    lyrics: [
      { t: 0, l: '' },
      { t: 5, l: 'Chieu tan, anh den neon le loi' },
      { t: 12, l: 'Bong toi phu mo con duong nhung nguoi di' },
      { t: 20, l: 'Ta nhin troi, mua roi thay tung giot le roi' },
      { t: 28, l: 'Nho ai do, noi xa xoi, mot minh toi' },
      { t: 36, l: 'Sunset lover, em trong giac mo anh' },
      { t: 44, l: 'Mau vang hong phu len nhung duong chan troi' },
      { t: 52, l: 'Song con song... am am tren mat bien' },
      { t: 60, l: 'Gio thoi, mem mai, nghe nhu tieng goi' },
      { t: 68, l: 'Ta bay di cung em, noi minh tu do' },
      { t: 76, l: 'Khong con lo, khong con so, chi yeu thoi...' },
    ]
  },
  cyber: {
    url: 'https://w.soundcloud.com/player/?url=https%3A//api.soundcloud.com/tracks/1087027808&color=%2306b6d4&auto_play=false&hide_related=true&show_comments=false',
    lyrics: [
      { t: 0, l: '' },
      { t: 4, l: 'Neon lights flicker in the rain' },
      { t: 10, l: 'Circuits pulse beneath the city veins' },
      { t: 17, l: 'We run through data streams and code' },
      { t: 24, l: 'A ghost in the machine, alone on this road' },
      { t: 32, l: 'System override — engage' },
      { t: 40, l: 'The future burns, turn the page' },
      { t: 48, l: 'Chrome and steel, synthetic heart' },
      { t: 56, l: 'We were built for breaking apart' },
    ]
  },
  midnight: {
    url: 'https://w.soundcloud.com/player/?url=https%3A//api.soundcloud.com/tracks/1391843740&color=%23a855f7&auto_play=false&hide_related=true&show_comments=false',
    lyrics: [
      { t: 0, l: '' },
      { t: 6, l: 'Mua roi tren Tokyo, uot mem ban tay' },
      { t: 14, l: 'Den sap tat, con gac tro vang bong den' },
      { t: 22, l: 'Tieng piano khe khang, nho ai tu xa' },
      { t: 30, l: 'Dem Nhat Ban, ben minh chi co mot minh' },
      { t: 38, l: 'Sakura roi tren toc, lanh nhung dep' },
      { t: 46, l: 'Tieng hat vong, tieng hat vong trong gio' },
    ]
  }
};

let rpcRunning = false;
let rpcStartTime = null;
let timerInterval = null;
let logPollingInterval = null;
let rotatorInterval = null;
let currentPresets = [];
let currentLargeImageUrl = '';
let currentSmallImageUrl = '';
let detectedAppAvatarUrl = '';
let SCWidget = null;
let lyricSyncing = false;
let lyricInterval = null;
let currentLyrics = [];
let scDuration = 0;
let questRunnerInterval = null;
let questLogInterval = null;
let questLogLastCount = 0;
let currentQuestId = null;

// ============================================================
// TAB NAVIGATION (SPA ZERO-LAG)
// ============================================================

const TAB_TITLES = {
  'tab-home': 'DASHBOARD COMMAND CENTER',
  'tab-rpc': 'CUSTOM RPC PRESENCE',
  'tab-rpc-youtube': 'YOUTUBE RPC',
  'tab-rpc-soundcloud': 'SOUNDCLOUD RPC',
  'tab-rpc-spotify': 'SPOTIFY RPC',
  'tab-status-custom': 'CUSTOM STATUS DISCORD',
  'tab-lyric': 'LYRIC STATUS (KARAOKE)',
  'tab-voice-afk': 'TREO VOICE 24/7 (AFK)',
  'tab-voice-coming': 'VOICE SOUNDBOARD (COMING SOON)',
  'tab-quest': 'DISCORD AUTO QUEST',
  'tab-script-coming': 'ACCOUNT CLEANER (COMING SOON)',
  'tab-accounts': 'QUẢN LÝ ĐA TOKEN',
  'tab-inbox': 'INBOX DISCORD'
};

function switchTab(tabId) {
  if (!tabId) tabId = 'tab-home';
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.sidebar-nav-item').forEach(b => b.classList.remove('active'));
  
  const panel = document.getElementById(tabId);
  if (panel) panel.classList.add('active');
  
  const btn = document.querySelector(`[data-tab="${tabId}"]`);
  if (btn) btn.classList.add('active');

  // Cập nhật Breadcrumb trên Topbar
  const topTitle = document.getElementById('topbar-tab-title');
  if (topTitle && TAB_TITLES[tabId]) {
    topTitle.textContent = TAB_TITLES[tabId];
  }

  // Lưu hash URL để khi F5 không bị mất tab
  if (window.location.hash !== `#${tabId}`) {
    history.replaceState(null, null, `#${tabId}`);
  }

  // Khởi động các module tương ứng
  if (tabId === 'tab-home') { loadDashboardStats(); }
  else if (tabId === 'tab-rpc') { startLogPolling(); }
  else if (tabId === 'tab-quest') { loadAvailableQuests(); startLogPolling('quest'); }
  else if (tabId === 'tab-inbox') { loadDiscordInbox(); }
  else if (tabId === 'tab-accounts') { loadMultiAccounts(); }
  else if (tabId === 'tab-voice-afk') { checkVoiceStatus(); }
}

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================

function showToast(msg, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 350);
  }, duration);
}

// ============================================================
// ACCOUNT MODAL
// ============================================================

function toggleAccountModal(show) {
  const bd = document.getElementById('account-modal-backdrop');
  if (!bd) return;
  if (show === true || show === undefined) {
    bd.classList.remove('d-none');
    bd.classList.add('modal-visible');
    document.body.style.overflow = 'hidden';
  } else {
    bd.classList.add('d-none');
    bd.classList.remove('modal-visible');
    document.body.style.overflow = '';
  }
}

function handleBackdropClick(e) {
  if (e.target === document.getElementById('account-modal-backdrop')) toggleAccountModal(false);
}

function toggleTokenVisibility() {
  const inp = document.getElementById('input-token');
  if (!inp) return;
  inp.type = inp.type === 'password' ? 'text' : 'password';
}

function copyTokenScript() {
  const script = `window.webpackChunkdiscord_app.push([[Math.random()],{},(e)=>{for(const n of Object.values(e.c)){try{const e=n?.exports?.default;if(e?.getToken){const t=e.getToken();copy(t);console.log("%c[SUCCESS] Token copied!","color:#22c55e;font-size:16px;font-weight:bold");return}}catch{}}}]);`;
  navigator.clipboard.writeText(script).then(() => showToast('Đã sao chép Script lấy Token — Vào Discord Web > F12 > Console > Dán & Enter', 'success'))
    .catch(() => {
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = script;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showToast('Đã sao chép Script lấy Token vào Clipboard!', 'success');
    });
}

async function handleBindToken() {
  const tokenEl = document.getElementById('input-token');
  const appIdEl = document.getElementById('input-app-id');
  if (!tokenEl || !tokenEl.value.trim()) {
    showToast('Vui lòng dán Discord Token vào ô nhập', 'error');
    return;
  }
  showToast('Đang xác minh token...', 'info', 2000);
  try {
    const r = await fetch('/api/account/bind_token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: tokenEl.value.trim(), app_id: (appIdEl && appIdEl.value) ? appIdEl.value.trim() : '' })
    });
    const d = await r.json();
    if (d.success) {
      showToast(`Đã liên kết thành công với: ${d.discord_username || d.username}!`, 'success');
      updateAccountUI(d);
      updateLivePreview();
      toggleAccountModal(false);
      loadAvailableQuests();
    } else {
      showToast(d.message || d.error || 'Token không hợp lệ', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

async function handleSaveConfig() {
  const cfg = buildRPCConfig();
  showToast('Dang luu cau hinh...', 'info', 1500);
  try {
    const r = await fetch('/api/save_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg)
    });
    const d = await r.json();
    if (d.success) {
      showToast('Da luu cau hinh thanh cong!', 'success');
    } else {
      showToast(d.message || 'Loi khi luu cau hinh', 'error');
    }
  } catch (e) {
    showToast('Loi ket noi toi may chu', 'error');
  }
}

async function handleUnbindToken() {
  if (!confirm('Huy lien ket Discord Token?')) return;
  try {
    await fetch('/api/account/unbind_token', { method: 'POST' });
    showToast('Da huy lien ket token', 'info');
    location.reload();
  } catch (e) { showToast('Loi huy lien ket', 'error'); }
}

function updateAccountUI(data) {
  if (!data) return;
  const isLinked = !!(data.has_token === true || (data.accounts && data.accounts.length > 0));
  const sysUsername = data.username || window.CURRENT_USERNAME || 'User';
  const discordUsername = data.discord_username || '';
  const displayName = isLinked ? (discordUsername || sysUsername) : sysUsername;
  const authProvider = data.auth_provider || (data.google_avatar ? 'google' : 'local');
  const avatar = isLinked 
    ? (data.discord_avatar || data.avatar_url || '') 
    : (data.avatar_url || data.google_avatar || data.discord_avatar || '');

  // 1. Sidebar Account Bottom Selector
  const sadName = document.getElementById('sad-name');
  const sadTag = document.getElementById('sad-tag');
  const sadImg = document.getElementById('sad-avatar-img');
  const sadLocked = document.getElementById('sad-avatar-locked');
  if (sadName) sadName.textContent = isLinked ? (discordUsername || sysUsername) : 'Chưa chọn Token';
  if (sadTag) {
    sadTag.textContent = isLinked ? 'Active' : 'Trống';
    sadTag.className = `sad-tag ${isLinked ? 'linked' : 'unlinked'}`;
  }
  if (isLinked && avatar) {
    if (sadImg) { sadImg.src = avatar; sadImg.style.display = 'block'; }
    if (sadLocked) sadLocked.style.display = 'none';
  } else {
    if (sadImg) sadImg.style.display = 'none';
    if (sadLocked) sadLocked.style.display = 'flex';
  }

  // 2. Modal Quản Lý Tài Khoản
  const accName = document.getElementById('account-view-name');
  const accStatus = document.getElementById('account-view-status');
  const accAvatar = document.getElementById('account-view-avatar');
  const accAvatarLocked = document.getElementById('account-view-avatar-locked');
  if (accName) accName.textContent = displayName;
  if (accStatus) {
    accStatus.className = `acc-status-pill ${isLinked ? 'linked' : 'unlinked'}`;
    accStatus.innerHTML = `<span class="acc-status-dot ${isLinked ? 'green' : 'amber'}"></span><span>${isLinked ? 'Đã liên kết Discord' : 'Chưa nạp Discord Token'}</span>`;
  }
  if (avatar) {
    if (accAvatar) { accAvatar.src = avatar; accAvatar.classList.remove('d-none'); }
    if (accAvatarLocked) accAvatarLocked.classList.add('d-none');
  } else {
    if (accAvatar) accAvatar.classList.add('d-none');
    if (accAvatarLocked) accAvatarLocked.classList.remove('d-none');
  }

  // 3. Tab Lyric Sync
  const lscUser = document.getElementById('lsc-username');
  const lscAv = document.getElementById('lsc-avatar');
  const lscAvLocked = document.getElementById('lsc-avatar-locked');
  if (lscUser) lscUser.textContent = displayName;
  if (avatar) {
    if (lscAv) { lscAv.src = avatar; lscAv.classList.remove('d-none'); }
    if (lscAvLocked) lscAvLocked.classList.add('d-none');
  }

  // 4. Tab RPC Live Preview Card
  const pvDisp = document.getElementById('pv-display-name');
  const pvHandle = document.getElementById('pv-handle');
  const pvAv = document.getElementById('pv-avatar');
  const pvAvLocked = document.getElementById('pv-avatar-locked');
  if (pvDisp) pvDisp.textContent = displayName;
  if (pvHandle) pvHandle.textContent = `@${displayName.toLowerCase().replace(/\s+/g, '')}`;
  if (avatar) {
    if (pvAv) { pvAv.src = avatar; pvAv.classList.remove('d-none'); }
    if (pvAvLocked) pvAvLocked.classList.add('d-none');
  }

  // 5. CẬP NHẬT THẺ PROFILE ĐỘNG Ở HERO (DASHBOARD COMMAND CENTER)
  const cardWrap = document.getElementById('discord-main-card');
  const heroName = document.getElementById('hero-profile-name');
  const heroTag = document.getElementById('hero-profile-tag');
  const heroAv = document.getElementById('hero-avatar-img');
  const heroDecor = document.getElementById('hero-avatar-decoration');
  const heroBanner = document.getElementById('hero-profile-banner');
  const heroBadges = document.getElementById('hero-badges-row');
  const heroStatusDot = document.getElementById('hero-status-dot');
  const heroStatusText = document.getElementById('hero-custom-status-text');
  const heroBio = document.getElementById('hero-profile-bio');
  const heroAvatarWrap = document.querySelector('.dc1-avatar-wrap');

  const decorUrl = isLinked ? (data.avatar_decoration || data.decoration || '') : '';
  const badgesList = isLinked ? (data.badges || []) : [];

  if (heroName) heroName.textContent = displayName;
  if (heroTag) heroTag.textContent = `@${displayName.toLowerCase().replace(/\s+/g, '')}`;
  if (heroStatusDot) {
    heroStatusDot.className = `dc1-status-dot ${isLinked ? 'online' : 'idle'}`;
  }

  if (heroAv && avatar) {
    heroAv.src = avatar;
    heroAv.classList.remove('d-none');
  }

  if (authProvider === 'google' && !isLinked) {
    // Chế độ Google VIP với vòng hào quang Google One / Ultra đa sắc
    if (cardWrap) cardWrap.classList.add('google-profile-card');
    if (heroAvatarWrap) heroAvatarWrap.classList.add('google-one-ring');
    if (heroDecor) heroDecor.classList.add('d-none');
    if (heroStatusText) heroStatusText.textContent = 'Tài khoản Google liên kết • Sẵn sàng nạp Token';
    if (heroBio) heroBio.textContent = 'Tài khoản Google đã kết nối an toàn với DIPRE Studio. Nạp token Discord trong Quản Lý Token để điều khiển RPC & Voice 24/7.';
    if (heroBadges) {
      heroBadges.innerHTML = `
        <span class="google-badge-pill">
          <svg width="12" height="12" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/></svg>
          Google Verified
        </span>
        <span class="google-badge-pill ultra">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
          Google One Ultra
        </span>
      `;
    }
  } else {
    // Chế độ Discord hoặc DIPRE
    if (cardWrap) cardWrap.classList.remove('google-profile-card');
    if (heroAvatarWrap) heroAvatarWrap.classList.remove('google-one-ring');
    if (decorUrl && heroDecor) {
      heroDecor.src = decorUrl;
      heroDecor.classList.remove('d-none');
    } else if (heroDecor) {
      heroDecor.classList.add('d-none');
    }

    if (heroBadges) {
      if (badgesList && badgesList.length > 0) {
        heroBadges.innerHTML = badgesList.map(b => `<img src="${b.icon}" alt="${b.name}" title="${b.name}" class="dc1-badge-icon">`).join('');
      } else if (isLinked) {
        heroBadges.innerHTML = `
          <span class="google-badge-pill" style="background:rgba(88,101,242,0.18); border-color:rgba(88,101,242,0.4); color:#818cf8;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg>
            Active Discord
          </span>
          <span class="google-badge-pill" style="background:rgba(6,182,212,0.18); border-color:rgba(6,182,212,0.4); color:#38bdf8;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            Verified Developer
          </span>
        `;
      } else {
        heroBadges.innerHTML = `
          <span class="google-badge-pill" style="background:rgba(99,102,241,0.18); border-color:rgba(99,102,241,0.4); color:#a5b4fc;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            DIPRE VIP
          </span>
        `;
      }
    }

    if (heroStatusText) {
      heroStatusText.textContent = isLinked ? 'Đang chạy DIPRE Studio Active' : 'Sẵn sàng nạp Discord Token phụ';
    }
    if (heroBio) {
      heroBio.textContent = data.bio || (isLinked ? 'DIPRE Studio User • Ultra Rich Presence & Voice AFK Active.' : 'Chào mừng đến với DIPRE Studio Luxury Edition. Nạp token trong mục Account để bắt đầu.');
    }
  }

  // Banner
  if (heroBanner && data.banner) {
    heroBanner.style.backgroundImage = `url('${data.banner}')`;
  }

  // 6. THAY VÌ BẬT OVERLAY ĐEN, ĐIỀU KHIỂN TOKEN NOTICE BANNER
  const rpcNotice = document.getElementById('rpc-token-notice');
  const lyricNotice = document.getElementById('lyric-token-notice');
  const statusNotice = document.getElementById('status-token-notice');
  const voiceNotice = document.getElementById('voice-token-notice');

  if (isLinked) {
    if (rpcNotice) rpcNotice.classList.add('d-none');
    if (lyricNotice) lyricNotice.classList.add('d-none');
    if (statusNotice) statusNotice.classList.add('d-none');
    if (voiceNotice) voiceNotice.classList.add('d-none');
  } else {
    if (rpcNotice) rpcNotice.classList.remove('d-none');
    if (lyricNotice) lyricNotice.classList.remove('d-none');
    if (statusNotice) statusNotice.classList.remove('d-none');
    if (voiceNotice) voiceNotice.classList.remove('d-none');
  }
}

// ============================================================
// RPC CONTROLS
// ============================================================

function buildRPCConfig() {
  const actType = document.getElementById('select-activity-type')?.value || 'playing';
  const name = document.getElementById('input-activity-name')?.value.trim() || 'Discord RPC';
  const details = document.getElementById('input-details')?.value.trim() || '';
  const state = document.getElementById('input-state')?.value.trim() || '';
  const largeImage = document.getElementById('input-large-image')?.value.trim() || currentLargeImageUrl || 'bot_avatar';
  const smallImage = document.getElementById('input-small-image')?.value.trim() || currentSmallImageUrl || '';
  const largeText = document.getElementById('input-large-text')?.value.trim() || '';
  const smallText = document.getElementById('input-small-text')?.value.trim() || '';
  const btn1Label = document.getElementById('input-btn1-label')?.value.trim() || '';
  const btn1Url = document.getElementById('input-btn1-url')?.value.trim() || '';
  const btn2Label = document.getElementById('input-btn2-label')?.value.trim() || '';
  const btn2Url = document.getElementById('input-btn2-url')?.value.trim() || '';
  const useTimestamp = document.getElementById('check-timestamp')?.checked || false;
  const status = document.getElementById('select-user-status')?.value || 'online';
  const appId = document.getElementById('input-app-id')?.value.trim() || '1546849576986607657';
  const streamUrl = document.getElementById('input-stream-url')?.value.trim() || '';
  const buttons = [];
  if (btn1Label && btn1Url) buttons.push({ label: btn1Label, url: btn1Url });
  if (btn2Label && btn2Url) buttons.push({ label: btn2Label, url: btn2Url });
  return {
    activity_type: actType, name, details, state, large_image: largeImage, small_image: smallImage,
    large_text: largeText, small_text: smallText, buttons, use_timestamp: useTimestamp,
    status, app_id: appId, stream_url: streamUrl
  };
}

async function handleStartRPC() {
  const cfg = buildRPCConfig();
  try {
    const r = await fetch('/api/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) });
    const d = await r.json();
    if (d.success) {
      rpcRunning = true; rpcStartTime = Date.now();
      document.getElementById('btn-start').disabled = true;
      document.getElementById('btn-update').disabled = false;
      document.getElementById('btn-stop').disabled = false;
      setLed('running'); startTimer(); startLogPolling();
      showToast('RPC da khoi dong!', 'success');
    } else showToast(d.error || 'Khoi dong that bai', 'error');
  } catch (e) { showToast('Loi ket noi may chu', 'error'); }
}

async function handleUpdateRPC() {
  const cfg = buildRPCConfig();
  try {
    const r = await fetch('/api/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) });
    const d = await r.json();
    if (d.success) showToast('Da cap nhat RPC!', 'success');
    else showToast(d.error || 'Cap nhat that bai', 'error');
  } catch (e) { showToast('Loi ket noi', 'error'); }
}

async function handleStopRPC() {
  try {
    const r = await fetch('/api/stop', { method: 'POST' });
    const d = await r.json();
    if (d.success) {
      rpcRunning = false; rpcStartTime = null;
      document.getElementById('btn-start').disabled = false;
      document.getElementById('btn-update').disabled = true;
      document.getElementById('btn-stop').disabled = true;
      setLed('idle'); stopTimer();
      showToast('Da dung RPC', 'info');
    }
  } catch (e) { showToast('Loi dung RPC', 'error'); }
}




// ============================================================
// LIVE PREVIEW
// ============================================================

function updateLivePreview() {
  const actType = document.getElementById('select-activity-type')?.value || 'playing';
  const name = document.getElementById('input-activity-name')?.value.trim() || '';
  const details = document.getElementById('input-details')?.value.trim() || '';
  const state = document.getElementById('input-state')?.value.trim() || '';
  const btn1L = document.getElementById('input-btn1-label')?.value.trim() || '';
  const btn1U = document.getElementById('input-btn1-url')?.value.trim() || '#';
  const btn2L = document.getElementById('input-btn2-label')?.value.trim() || '';
  const btn2U = document.getElementById('input-btn2-url')?.value.trim() || '#';
  const useTimer = document.getElementById('check-timestamp')?.checked;
  const userStatus = document.getElementById('select-user-status')?.value || 'online';

  const typeMap = { playing: 'PLAYING A GAME', streaming: 'LIVE ON TWITCH', listening: 'LISTENING TO', watching: 'WATCHING', competing: 'COMPETING IN' };
  const el = (id) => document.getElementById(id);
  if (el('pv-activity-type-header')) el('pv-activity-type-header').textContent = typeMap[actType] || 'PLAYING A GAME';

  const emptyCard = el('pv-empty-activity');
  const actCard = el('pv-activity-card');

  if (!name) {
    if (emptyCard) emptyCard.classList.remove('d-none');
    if (actCard) actCard.classList.add('d-none');
  } else {
    if (emptyCard) emptyCard.classList.add('d-none');
    if (actCard) actCard.classList.remove('d-none');
  }

  if (el('pv-activity-name')) el('pv-activity-name').textContent = name || '';
  if (el('pv-details')) {
    el('pv-details').textContent = details || '';
    el('pv-details').style.display = details ? '' : 'none';
  }
  if (el('pv-state')) {
    el('pv-state').textContent = state || '';
    el('pv-state').style.display = state ? '' : 'none';
  }
  if (el('pv-time')) el('pv-time').style.display = useTimer ? '' : 'none';

  const btnsEl = document.getElementById('pv-btn-group') || document.querySelector('.dpm-act-buttons');
  if (btnsEl) {
    const b1 = document.getElementById('pv-btn1');
    const b2 = document.getElementById('pv-btn2');
    if (b1) { b1.textContent = btn1L || ''; b1.href = btn1U; b1.style.display = btn1L ? '' : 'none'; }
    if (b2) { b2.textContent = btn2L || ''; b2.href = btn2U; b2.style.display = btn2L ? '' : 'none'; }
    btnsEl.style.display = (btn1L || btn2L) ? '' : 'none';
  }

  const dotEl = document.getElementById('pv-status-dot');
  if (dotEl) {
    const cols = { online: '#3ba55c', idle: '#faa61a', dnd: '#ed4245', invisible: '#747f8d' };
    dotEl.style.background = cols[userStatus] || '#3ba55c';
  }

  // Đồng bộ hiển thị ảnh lớn: Nếu chưa chọn ảnh thì ẩn hoàn toàn, không hiện icon mặc định
  const largeImgVal = document.getElementById('input-large-image')?.value.trim() || currentLargeImageUrl;
  const pvLarge = document.getElementById('pv-large-img');
  if (pvLarge) {
    if (largeImgVal) {
      if (!largeImgVal.startsWith('http')) {
        const known = KNOWN_ASSET_ICONS[largeImgVal];
        pvLarge.src = known ? known.url : largeImgVal;
      } else {
        pvLarge.src = largeImgVal;
      }
      pvLarge.style.display = 'block';
    } else {
      pvLarge.src = '';
      pvLarge.style.display = 'none';
    }
  }

  // Đồng bộ hiển thị ảnh nhỏ
  const smallImgVal = document.getElementById('input-small-image')?.value.trim() || currentSmallImageUrl;
  const pvSmall = document.getElementById('pv-small-img');
  if (pvSmall) {
    if (smallImgVal) {
      if (!smallImgVal.startsWith('http')) {
        const known = KNOWN_ASSET_ICONS[smallImgVal];
        pvSmall.src = known ? known.url : smallImgVal;
      } else {
        pvSmall.src = smallImgVal;
      }
      pvSmall.style.display = 'block';
    } else {
      pvSmall.src = '';
      pvSmall.style.display = 'none';
    }
  }
}

// ============================================================
// TIMER
// ============================================================

function startTimer() {
  stopTimer();
  timerInterval = setInterval(() => {
    if (!rpcStartTime) return;
    const elapsed = Math.floor((Date.now() - rpcStartTime) / 1000);
    const h = Math.floor(elapsed / 3600);
    const m = Math.floor((elapsed % 3600) / 60);
    const s = elapsed % 60;
    const txt = h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')} elapsed`
      : `${m}:${String(s).padStart(2, '0')} elapsed`;
    const el = document.getElementById('pv-timer-text');
    if (el) el.textContent = txt;
  }, 1000);
}

function stopTimer() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
}

// ============================================================
// LED / STATUS
// ============================================================

function setLed(state) {
  const led = document.getElementById('led-indicator');
  const txt = document.getElementById('status-text');
  if (!led) return;
  led.className = 'status-led';
  if (state === 'running') {
    led.classList.add('led-green');
    if (txt) txt.textContent = 'RPC Dang Chay';
  } else if (state === 'quest') {
    led.classList.add('led-amber');
    if (txt) txt.textContent = 'Quest Dang Chay';
  } else if (state === 'lyric') {
    led.classList.add('led-cyan');
    if (txt) txt.textContent = 'Lyric Dang Dong Bo';
  } else {
    if (txt) txt.textContent = 'Chua Chay';
  }
}

// ============================================================
// LOG ENGINES (RPC, LYRIC, QUEST ISOLATED)
// ============================================================

function startLogPolling() {
  if (logPollingInterval) { clearInterval(logPollingInterval); logPollingInterval = null; }
  logPollingInterval = setInterval(fetchRPCLogs, 2000);
}

async function fetchRPCLogs() {
  try {
    const r = await fetch('/api/logs');
    const d = await r.json();
    const screen = document.getElementById('rpc-log-screen') || document.getElementById('terminal-screen');
    if (!screen || !d.logs) return;
    const wasBottom = screen.scrollTop + screen.clientHeight >= screen.scrollHeight - 5;
    const existing = screen.querySelectorAll('.log-line').length;
    if (d.logs.length > existing) {
      const newLogs = d.logs.slice(existing);
      newLogs.forEach(log => {
        // Filter out quest or lyric specific lines if any
        if (log.message && (log.message.includes('[QUEST]') || log.message.includes('[LYRIC]'))) return;
        const div = document.createElement('div');
        const lvl = log.level || 'info';
        div.className = `log-line ${lvl}`;
        div.innerHTML = `<span class="log-time">[${log.time || 'RPC'}]</span><span class="log-tag">[${lvl.toUpperCase()}]</span><span class="log-msg">${escapeHtml(log.message)}</span>`;
        screen.appendChild(div);
      });
      if (wasBottom) screen.scrollTop = screen.scrollHeight;
    }
  } catch (e) { }
}

function clearRPCLog() {
  const screen = document.getElementById('rpc-log-screen') || document.getElementById('terminal-screen');
  if (screen) screen.innerHTML = '';
}

function clearLogs() {
  clearRPCLog();
}

function logLyric(message, level = 'info') {
  const screen = document.getElementById('lyric-log-screen');
  if (!screen) return;
  const div = document.createElement('div');
  div.className = `log-line ${level}`;
  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
  div.innerHTML = `<span class="log-time">[${timeStr}]</span><span class="log-tag">[LYRIC]</span><span class="log-msg">${escapeHtml(message)}</span>`;
  screen.appendChild(div);
  screen.scrollTop = screen.scrollHeight;
  while (screen.children.length > 80) {
    screen.removeChild(screen.firstChild);
  }
}

function clearLyricLog() {
  const screen = document.getElementById('lyric-log-screen');
  if (screen) screen.innerHTML = '';
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ============================================================
// PRESETS
// ============================================================

async function loadPresets() {
  try {
    const r = await fetch('/api/presets');
    const d = await r.json();
    currentPresets = d.presets || [];
    renderPresets();
  } catch (e) { }
}

function renderPresets() {
  const bar = document.getElementById('preset-list');
  if (!bar) return;
  bar.innerHTML = '';
  if (!currentPresets.length) {
    bar.innerHTML = '<span style="font-size:0.78rem;color:var(--text-muted)">Chua co preset nao. Luu preset de bat dau.</span>';
    return;
  }
  currentPresets.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'preset-chip';
    btn.textContent = p.name;
    btn.title = `Load preset: ${p.name}`;
    btn.onclick = () => loadPreset(p.id);
    const del = document.createElement('button');
    del.className = 'preset-chip-del';
    del.textContent = 'x';
    del.onclick = (e) => { e.stopPropagation(); deletePreset(p.id); };
    const wrap = document.createElement('div');
    wrap.className = 'preset-chip-wrap';
    wrap.appendChild(btn);
    wrap.appendChild(del);
    bar.appendChild(wrap);
  });
}

async function loadPreset(id) {
  try {
    const r = await fetch(`/api/presets/${id}`);
    const d = await r.json();
    if (!d.config) return;
    const c = d.config;
    const set = (elId, val) => { const e = document.getElementById(elId); if (e && val !== undefined) e.value = val; };
    set('input-activity-name', c.name);
    set('input-details', c.details);
    set('input-state', c.state);
    set('input-large-image', c.large_image);
    set('input-small-image', c.small_image);
    set('input-large-text', c.large_text);
    set('input-small-text', c.small_text);
    set('input-btn1-label', c.buttons?.[0]?.label || '');
    set('input-btn1-url', c.buttons?.[0]?.url || '');
    set('input-btn2-label', c.buttons?.[1]?.label || '');
    set('input-btn2-url', c.buttons?.[1]?.url || '');
    set('select-activity-type', c.activity_type || 'playing');
    set('input-app-id', c.app_id || '');
    const ts = document.getElementById('check-timestamp');
    if (ts) ts.checked = !!c.use_timestamp;
    onManualImageChange('large');
    onManualImageChange('small');
    updateLivePreview();
    showToast(`Da load preset "${d.name}"`, 'success');
  } catch (e) { showToast('Loi load preset', 'error'); }
}

async function saveCurrentAsPreset() {
  const name = prompt('Ten Preset:');
  if (!name?.trim()) return;
  const cfg = buildRPCConfig();
  try {
    const r = await fetch('/api/presets', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.trim(), config: cfg }) });
    const d = await r.json();
    if (d.success) { showToast(`Da luu preset "${name}"`, 'success'); loadPresets(); }
    else showToast(d.error || 'Luu that bai', 'error');
  } catch (e) { showToast('Loi luu preset', 'error'); }
}

async function deletePreset(id) {
  if (!confirm('Xoa preset nay?')) return;
  try {
    await fetch(`/api/presets/${id}`, { method: 'DELETE' });
    showToast('Da xoa preset', 'info');
    loadPresets();
  } catch (e) { }
}

// ============================================================
// ACTIVITY TYPE CHANGE
// ============================================================

function onActivityTypeChange() {
  const val = document.getElementById('select-activity-type')?.value;
  const streamGroup = document.getElementById('stream-url-group');
  if (streamGroup) streamGroup.classList.toggle('d-none', val !== 'streaming');
  updateLivePreview();
}

// ============================================================
// IMAGE HANDLING
// ============================================================

function triggerUpload(type) {
  document.getElementById(`file-upload-${type}`)?.click();
}

async function uploadImageFile(input, type) {
  if (!input.files?.length) return;
  const file = input.files[0];
  const formData = new FormData();
  formData.append('image', file);
  formData.append('type', type);
  showToast('Dang tai len anh...', 'info', 2000);
  try {
    const r = await fetch('/api/upload', { method: 'POST', body: formData });
    const d = await r.json();
    if (d.success) {
      const url = d.url;
      if (type === 'large') {
        currentLargeImageUrl = url;
        const img = document.getElementById('box-large-preview');
        if (img) img.src = url;
        const pvImg = document.getElementById('pv-large-img');
        if (pvImg) pvImg.src = url;
        const src = document.getElementById('lbl-large-source');
        if (src) src.textContent = 'Hinh tai len';
      } else {
        currentSmallImageUrl = url;
        const wrap = document.getElementById('wrap-small-preview');
        if (wrap) wrap.style.display = '';
        const img = document.getElementById('box-small-preview');
        if (img) { img.src = url; img.style.display = ''; }
        const pvImg = document.getElementById('pv-small-img');
        if (pvImg) { pvImg.src = url; pvImg.style.display = 'block'; }
        const src = document.getElementById('lbl-small-source');
        if (src) src.textContent = 'Hinh tai len';
        const btnAdd = document.getElementById('btn-add-small');
        if (btnAdd) btnAdd.textContent = 'Doi Anh';
        const btnRemove = document.getElementById('btn-remove-small');
        if (btnRemove) btnRemove.style.display = '';
      }
      showToast('Da tai len anh!', 'success');
    } else showToast(d.error || 'Tai len that bai', 'error');
  } catch (e) { showToast('Loi tai len anh', 'error'); }
}

function onManualImageChange(type) {
  const val = document.getElementById(`input-${type}-image`)?.value.trim() || '';
  if (!val) {
    if (type === 'small') clearSmallImage();
    return;
  }
  let url = val;
  let iconName = val;
  if (['bot_avatar', 'app', 'bot', 'developer_portal', 'portal'].includes(val.toLowerCase())) {
    url = detectedAppAvatarUrl || 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/vscode/vscode-original.svg';
    iconName = 'Bot Avatar';
  } else if (!val.startsWith('http')) {
    const known = KNOWN_ASSET_ICONS[val];
    if (known) {
      url = known.url;
      iconName = known.name;
    } else {
      url = 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/vscode/vscode-original.svg';
      iconName = val;
    }
  }
  if (type === 'large') {
    const img = document.getElementById('box-large-preview');
    const pvImg = document.getElementById('pv-large-img');
    if (img) img.src = url;
    if (pvImg) pvImg.src = url;
    currentLargeImageUrl = url;
    const src = document.getElementById('lbl-large-source');
    if (src) src.textContent = iconName;
  } else {
    currentSmallImageUrl = url;
    const wrap = document.getElementById('wrap-small-preview');
    if (wrap) wrap.style.display = '';
    const img = document.getElementById('box-small-preview');
    if (img) { img.src = url; img.style.display = ''; }
    const pvImg = document.getElementById('pv-small-img');
    if (pvImg) { pvImg.src = url; pvImg.style.display = 'block'; }
    const src = document.getElementById('lbl-small-source');
    if (src) src.textContent = iconName;
    const btnAdd = document.getElementById('btn-add-small');
    if (btnAdd) btnAdd.textContent = 'Doi Anh';
    const btnRemove = document.getElementById('btn-remove-small');
    if (btnRemove) btnRemove.style.display = '';
  }
}

function toggleManualInput(type) {
  const wrap = document.getElementById(`manual-${type}-wrap`);
  if (wrap) wrap.classList.toggle('d-none');
}

function clearSmallImage() {
  currentSmallImageUrl = '';
  const wrap = document.getElementById('wrap-small-preview');
  if (wrap) wrap.style.display = 'none';
  const img = document.getElementById('box-small-preview');
  if (img) { img.src = ''; img.style.display = 'none'; }
  const pvImg = document.getElementById('pv-small-img');
  if (pvImg) { pvImg.src = ''; pvImg.style.display = 'none'; }
  const inp = document.getElementById('input-small-image');
  if (inp) inp.value = '';
  const src = document.getElementById('lbl-small-source');
  if (src) src.textContent = 'Chua them anh nho';
  const btnAdd = document.getElementById('btn-add-small');
  if (btnAdd) btnAdd.textContent = '+ Them / Tai Len';
  const btnRemove = document.getElementById('btn-remove-small');
  if (btnRemove) btnRemove.style.display = 'none';
  showToast('Da go anh nho — xem truoc chi con 1 anh lon', 'info');
}

// ============================================================
// GALLERY GRID
// ============================================================

function buildVisualGallery() {
  const grid = document.getElementById('visual-gallery-grid');
  if (!grid) return;
  grid.innerHTML = '';
  Object.entries(KNOWN_ASSET_ICONS).forEach(([key, val]) => {
    const btn = document.createElement('button');
    btn.className = 'gallery-icon-btn';
    btn.title = val.name;
    btn.innerHTML = `<img src="${val.url}" alt="${val.name}" loading="lazy"><span>${val.name}</span>`;
    btn.onclick = () => {
      const inp = document.getElementById('input-small-image');
      if (inp) { inp.value = key; inp.closest('#manual-small-wrap')?.classList.remove('d-none'); }
      onManualImageChange('small');
      showToast(`Da chon icon: ${val.name}`, 'info', 2000);
    };
    grid.appendChild(btn);
  });
}

// ============================================================
// PORTAL / BOT SCANNING
// ============================================================

async function scanPortalApps(silent = false) {
  if (!silent) showToast('Dang quet Developer Portal...', 'info', 2500);
  try {
    const r = await fetch('/api/portal_app_info');
    const d = await r.json();
    if (d.success && d.apps?.length) {
      const app = d.apps[0];
      detectedAppAvatarUrl = app.avatar_url || '';
      const banner = document.getElementById('detected-app-banner');
      const icon = document.getElementById('detected-app-icon');
      const title = document.getElementById('detected-app-title');
      const desc = document.getElementById('detected-app-desc');
      if (banner) banner.classList.remove('d-none');
      const fallback = document.getElementById('detected-app-fallback');
      if (icon) {
        if (app.avatar_url) {
          icon.src = app.avatar_url;
          icon.style.display = 'block';
          if (fallback) fallback.style.display = 'none';
        } else {
          icon.style.display = 'none';
          if (fallback) fallback.style.display = 'flex';
        }
      }
      if (title) title.textContent = app.name || 'App';
      if (desc) desc.textContent = `ID: ${app.id} — Tìm thấy trên Developer Portal!`;
      const container = document.getElementById('portal-bots-container');
      if (container) {
        container.innerHTML = '';
        d.apps.slice(0, 6).forEach(a => {
          const chip = document.createElement('div');
          chip.className = 'bot-chip';
          const avatarHtml = a.avatar_url
            ? `<img src="${a.avatar_url}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" alt=""><span class="bot-chip-fallback" style="display:none;">🤖</span>`
            : `<span class="bot-chip-fallback">🤖</span>`;
          chip.innerHTML = `${avatarHtml}<span>${escapeHtml(a.name)}</span>`;
          chip.onclick = () => {
            const appId = document.getElementById('input-app-id');
            if (appId) appId.value = a.id;
            detectedAppAvatarUrl = a.avatar_url || '';
            showToast(`Đã chọn app: ${a.name}`, 'success');
          };
          container.appendChild(chip);
        });
      }
      if (!silent) showToast(`Tim thay ${d.apps.length} app(s) tren Portal`, 'success');
    } else {
      if (!silent) showToast('Khong tim thay app nao tren Portal', 'warning');
    }
  } catch (e) { if (!silent) showToast('Loi quet Portal', 'error'); }
}

function applyDetectedAvatar() {
  if (!detectedAppAvatarUrl) { showToast('Chua co avatar de ap dung', 'warning'); return; }
  const img = document.getElementById('box-large-preview');
  const pvImg = document.getElementById('pv-large-img');
  if (img) img.src = detectedAppAvatarUrl;
  if (pvImg) pvImg.src = detectedAppAvatarUrl;
  currentLargeImageUrl = detectedAppAvatarUrl;
  const src = document.getElementById('lbl-large-source');
  if (src) src.textContent = 'Bot Portal Avatar';
  showToast('Da ap dung Bot Avatar!', 'success');
}

async function useDevPortalAvatar() {
  await scanPortalApps(true);
  applyDetectedAvatar();
}

// ============================================================
// ROTATOR
// ============================================================

function toggleRotator() {
  const on = document.getElementById('check-rotator')?.checked;
  if (on) {
    const interval = parseInt(document.getElementById('input-rotator-interval')?.value || '30') * 1000;
    rotatorInterval = setInterval(async () => {
      if (!currentPresets.length) return;
      const idx = Math.floor(Math.random() * currentPresets.length);
      await loadPreset(currentPresets[idx].id);
      if (rpcRunning) await handleUpdateRPC();
    }, interval);
    showToast('Bat che do xoay vong preset', 'info');
  } else {
    clearInterval(rotatorInterval); rotatorInterval = null;
    showToast('Da tat xoay vong preset', 'info');
  }
}

// ============================================================
// SOUNDCLOUD WIDGET
// ============================================================

// ============================================================
// DIPRE NCT & LRCLIB HTML5 AUDIO PLAYER
// ============================================================

let dipreAudio = new Audio();
let lastSyncedLine = '';

function initDipreAudioPlayer() {
  dipreAudio.addEventListener('timeupdate', () => {
    const cur = dipreAudio.currentTime;
    const dur = dipreAudio.duration || 0;
    updateLyricProgress(cur, dur);
    syncLyric();
  });

  dipreAudio.addEventListener('ended', () => {
    if (lyricSyncing) handleStopLyricAudio();
  });

  dipreAudio.addEventListener('loadedmetadata', () => {
    const dur = dipreAudio.duration || 0;
    const tot = document.getElementById('audio-time-total');
    if (tot) tot.textContent = formatTime(dur);
  });
}

function handleAudioSeek(val) {
  if (dipreAudio && dipreAudio.duration) {
    const target = (val / 100) * dipreAudio.duration;
    dipreAudio.currentTime = target;
  }
}

async function searchNctLyrics() {
  const query = (document.getElementById('input-nct-search')?.value || document.getElementById('input-nct-query')?.value || '').trim();
  if (!query) {
    showToast('Vui lòng nhập tên bài hát hoặc ca sĩ', 'warning');
    return;
  }
  const btn = document.querySelector('.sf-addon-btn.primary') || document.getElementById('btn-search-nct');
  const originalText = btn ? btn.innerHTML : 'Tìm Kiếm 🔍';
  if (btn) { btn.disabled = true; btn.innerHTML = '<span>Đang tìm...</span>'; }

  const container = document.getElementById('nct-search-results');
  if (container) {
    container.classList.remove('d-none');
    container.innerHTML = '<div class="nct-search-loading">Đang tìm 10 bản thu có lời đồng bộ & bìa album...</div>';
  }

  try {
    const res = await fetch(`/api/lyrics/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    const tracks = data.tracks || data.songs || [];
    if (data.success && tracks.length > 0) {
      renderSongResults(tracks);
      showToast(`Đã tìm thấy ${tracks.length} bài hát có sẵn bìa & lyric!`, 'success');
    } else {
      if (container) container.innerHTML = '<div class="nct-search-empty">Không tìm thấy bài hát nào có lời đồng bộ. Thử từ khóa khác nhé!</div>';
      showToast('Không tìm thấy bài hát phù hợp', 'warning');
    }
  } catch (err) {
    if (container) container.innerHTML = '<div class="nct-search-error">Lỗi khi tìm kiếm bài hát.</div>';
    showToast('Lỗi tìm kiếm: ' + err.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = originalText; }
  }
}

function renderSongResults(songs) {
  const container = document.getElementById('nct-search-results');
  if (!container) return;
  container.classList.remove('d-none');
  container.innerHTML = '';
  container.className = 'nct-search-grid-10';

  songs.forEach((song, idx) => {
    const card = document.createElement('div');
    card.className = 'nct-song-card-item';
    const coverUrl = song.cover || 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400&auto=format&fit=crop&q=80';
    const durationText = song.duration ? formatTime(song.duration) : 'Full Synced';

    card.innerHTML = `
      <div class="nsci-cover-wrap">
        <img src="${coverUrl}" alt="${escapeHtml(song.name || song.title)}" class="nsci-cover-img" loading="lazy">
        <div class="nsci-overlay">
          <button type="button" class="nsci-play-btn" title="Chọn bài hát này">▶</button>
        </div>
        ${song.has_synced ? '<span class="nsci-badge-sync">SYNCED</span>' : ''}
      </div>
      <div class="nsci-info">
        <div class="nsci-title" title="${escapeHtml(song.name || song.title)}">${escapeHtml(song.name || song.title)}</div>
        <div class="nsci-artist" title="${escapeHtml(song.artist || '')}">${escapeHtml(song.artist || 'Nghệ sĩ')}</div>
        <div class="nsci-time">${durationText}</div>
      </div>
    `;

    card.onclick = () => selectSongForSync(song);
    container.appendChild(card);
  });
}

async function selectSongForSync(song) {
  try {
    const title = song.name || song.title;
    const artist = song.artist || 'Nghệ sĩ';
    const cover = song.cover || 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400&auto=format&fit=crop&q=80';

    // 1. Cập nhật thẻ trình phát HTML5
    const dapTitle = document.getElementById('dap-title');
    const dapArtist = document.getElementById('dap-artist');
    const dapArt = document.getElementById('dap-art');
    if (dapTitle) dapTitle.textContent = title;
    if (dapArtist) dapArtist.textContent = `${artist} • NhacCuaTui Synced`;
    if (dapArt) dapArt.src = cover;

    // 2. Tải lời bài hát đồng bộ từ API
    showToast(`Đang nạp lời bài hát: ${title}...`, 'info');
    let lyricsLoaded = false;

    if (song.id) {
      const res = await fetch(`/api/lyrics/song?id=${encodeURIComponent(song.id)}`);
      const data = await res.json();
      if (data.success && data.track && data.track.lyrics && data.track.lyrics.length > 0) {
        currentLyrics = data.track.lyrics;
        renderKaraokeLyrics(currentLyrics);
        lyricsLoaded = true;
      }
    }

    if (!lyricsLoaded) {
      // Fallback tìm kiếm qua NCT service
      const res = await fetch(`/api/lyrics/song?q=${encodeURIComponent(title)}`);
      const data = await res.json();
      if (data.success && data.track && data.track.lyrics) {
        currentLyrics = data.track.lyrics;
        renderKaraokeLyrics(currentLyrics);
        lyricsLoaded = true;
      }
    }

    // Đổi hiển thị sang đã chọn thành công
    document.querySelectorAll('.nct-song-card-item').forEach(el => el.classList.remove('active'));
    showToast(`Đã chọn: ${title}! Sẵn sàng đồng bộ Status.`, 'success');

    // Tự động cuộn xuống trình phát nhạc
    const playerSec = document.querySelector('.dipre-player-section');
    if (playerSec) playerSec.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  } catch (e) {
    showToast('Lỗi khi nạp lời bài hát: ' + e.message, 'error');
  }
}

function renderKaraokeLyrics(lyrics) {
  const stage = document.getElementById('dipre-karaoke-stage') || document.getElementById('lyric-lines-wrapper');
  if (!stage) return;
  stage.innerHTML = '';
  lyrics.forEach((item, idx) => {
    const div = document.createElement('div');
    div.className = 'lyric-line-item';
    div.id = `lyric-line-${idx}`;
    div.textContent = item.l || '♪ ♫ ♪';
    div.onclick = () => {
      if (dipreAudio) dipreAudio.currentTime = item.t;
    };
    stage.appendChild(div);
  });
}

function handleToggleLyricAudio() {
  if (lyricSyncing) {
    handleStopLyricAudio();
    return;
  }

  const customLrc = document.getElementById('input-custom-lrc')?.value.trim();
  if (customLrc && (!currentLyrics || !currentLyrics.length)) {
    currentLyrics = parseLRC(customLrc);
    renderKaraokeLyrics(currentLyrics);
  }

  if (!currentLyrics || !currentLyrics.length) {
    showToast('Vui lòng chọn bài hát hoặc dán lời LRC trước', 'warning');
    logLyric('Không thể đồng bộ: Chưa chọn bài hát hoặc chưa có lời LRC', 'warn');
    return;
  }

  if (dipreAudio.src) {
    dipreAudio.play().catch(() => {});
  }

  lyricSyncing = true;
  setLed('lyric');
  const playBtn = document.getElementById('btn-lyric-play') || document.getElementById('btn-lyric-sync-toggle');
  const stopBtn = document.getElementById('btn-lyric-stop') || document.getElementById('btn-lyric-sync-stop');
  if (playBtn) playBtn.textContent = 'Dừng Đồng Bộ';
  if (stopBtn) stopBtn.disabled = false;
  const syncInd = document.getElementById('lyric-sync-indicator');
  if (syncInd) syncInd.style.display = '';
  const liveDot = document.getElementById('lyric-live-dot');
  if (liveDot) liveDot.style.display = '';

  logLyric(`Bắt đầu đồng bộ lời bài hát realtime lên Discord Custom Status...`, 'info');
  lyricInterval = setInterval(syncLyric, 400);
}

function handleToggleLyricSync() {
  handleToggleLyricAudio();
}

function handleStopLyricSync() {
  handleStopLyricAudio();
}

function handleStopLyricAudio() {
  if (dipreAudio) dipreAudio.pause();
  lyricSyncing = false;
  clearInterval(lyricInterval);
  lyricInterval = null;
  setLed('idle');
  const playBtn = document.getElementById('btn-lyric-play') || document.getElementById('btn-lyric-sync-toggle');
  const stopBtn = document.getElementById('btn-lyric-stop') || document.getElementById('btn-lyric-sync-stop');
  if (playBtn) playBtn.textContent = 'Bắt Đầu Đồng Bộ Discord';
  if (stopBtn) stopBtn.disabled = true;
  const syncInd = document.getElementById('lyric-sync-indicator');
  if (syncInd) syncInd.style.display = 'none';
  const liveDot = document.getElementById('lyric-live-dot');
  if (liveDot) liveDot.style.display = 'none';
  logLyric('Đã dừng đồng bộ trạng thái Discord.', 'warn');
  showToast('Đã dừng Lyric Sync', 'info');
}

async function handleClearDiscordStatus() {
  try {
    const r = await fetch('/api/lyrics/clear', { method: 'POST' });
    const d = await r.json();
    if (d.success) {
      showToast('Đã xóa Custom Status!', 'success');
      const lyr = document.getElementById('lsc-lyric-current');
      if (lyr) {
        lyr.textContent = 'Chưa có câu hát nào được đồng bộ';
        lyr.classList.add('empty-state');
      }
      logLyric('Đã xóa Custom Status trên tài khoản Discord thành công.', 'info');
    } else {
      showToast(d.error || 'Lỗi xóa status', 'error');
      logLyric(`Lỗi khi xóa status: ${d.error || 'Thất bại'}`, 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối', 'error');
    logLyric('Lỗi kết nối khi gửi yêu cầu xóa status.', 'error');
  }
}

function syncLyric() {
  if (!lyricSyncing || !currentLyrics.length) return;
  const sec = dipreAudio ? dipreAudio.currentTime : 0;
  const line = getCurrentLyric(sec);
  if (line !== undefined) {
    updateLyricDisplay(line, sec);
  }
}

function getCurrentLyric(sec) {
  if (!currentLyrics.length) return undefined;
  let current = '';
  for (let i = 0; i < currentLyrics.length; i++) {
    if (sec >= currentLyrics[i].t) current = currentLyrics[i].l;
    else break;
  }
  return current;
}

function updateLyricDisplay(line, sec) {
  const emoji = document.getElementById('select-lyric-emoji')?.value || '🎵';
  const lscEl = document.getElementById('lsc-lyric-current');
  const emojiEl = document.getElementById('lsc-emoji');
  if (lscEl) {
    if (line) {
      lscEl.textContent = line;
      lscEl.classList.remove('empty-state');
    } else {
      lscEl.textContent = 'Chưa có câu hát nào được đồng bộ';
      lscEl.classList.add('empty-state');
    }
  }
  if (emojiEl) emojiEl.textContent = emoji;

  // Active line highlight & auto-scroll
  let activeIdx = -1;
  for (let i = 0; i < currentLyrics.length; i++) {
    if (sec >= currentLyrics[i].t) activeIdx = i;
    else break;
  }

  if (activeIdx !== -1) {
    document.querySelectorAll('.lyric-line-item').forEach((el, idx) => {
      if (idx === activeIdx) {
        if (!el.classList.contains('active')) {
          el.classList.add('active');
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      } else {
        el.classList.remove('active');
      }
    });
  }

  if (lyricSyncing && line && line !== lastSyncedLine) {
    lastSyncedLine = line;
    logLyric(`[SYNC] ${emoji} ${line}`, 'info');
    fetch('/api/lyrics/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: line, emoji: emoji })
    }).catch(() => {
      logLyric(`[ERROR] Không thể gửi câu hát: "${line}" lên Discord API`, 'error');
    });
  }
}


function updateLyricProgress(sec, total) {
  const fill = document.getElementById('lsc-progress-fill');
  const cur = document.getElementById('audio-time-current');
  const tot = document.getElementById('audio-time-total');
  if (fill && total > 0) fill.style.width = `${(sec / total) * 100}%`;
  if (cur) cur.textContent = formatTime(sec);
  if (tot) tot.textContent = formatTime(total);
}

function formatTime(sec) {
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  const ss = s % 60;
  return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
}

async function handleTranscribeAudio() {
  const fileInput = document.getElementById('input-audio-stt');
  const statusText = document.getElementById('stt-status-text');
  const btn = document.getElementById('btn-stt-transcribe');
  const file = fileInput?.files?.[0];
  if (!file) {
    if (statusText) statusText.textContent = 'Chua chon file nhac nao.';
    return;
  }
  const fd = new FormData();
  fd.append('audio', file);
  if (btn) { btn.disabled = true; btn.textContent = 'Dang nhan dien...'; }
  if (statusText) statusText.textContent = 'Dang xu ly am thanh (co the mat 30s - vai phut tuy do dai bai hat)...';
  try {
    const res = await fetch('/api/lyrics/transcribe', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.success) {
      const ta = document.getElementById('input-custom-lrc');
      if (ta) ta.value = data.lrc;
      currentLyrics = parseLRC(data.lrc);
      const sel = document.getElementById('select-lyric-track');
      if (sel) sel.value = 'custom';
      const customGroup = document.getElementById('custom-lrc-group');
      if (customGroup) customGroup.classList.remove('d-none');
      if (statusText) statusText.textContent = `Da nhan dien xong ${data.segments || 0} dong loi.`;
      showToast('Da tu dong tao loi bai hat tu am thanh', 'success');
    } else {
      if (statusText) statusText.textContent = data.message || 'Nhan dien that bai.';
      showToast(data.message || 'Nhan dien that bai', 'error');
    }
  } catch (e) {
    if (statusText) statusText.textContent = 'Loi ket noi khi nhan dien.';
    showToast('Loi ket noi khi nhan dien', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Nhan Dien Loi'; }
  }
}

function parseLRC(raw) {
  if (!raw) return [];
  const lines = [];
  raw.split('\n').forEach(line => {
    const m = line.match(/\[(\d+):(\d+)\]\s*(.*)/);
    if (m) {
      lines.push({ t: parseInt(m[1]) * 60 + parseInt(m[2]), l: m[3].trim() });
    }
  });
  return lines.sort((a, b) => a.t - b.t);
}

// ============================================================
// ============================================================
// QUEST
// ============================================================

async function loadAvailableQuests() {
  const container = document.getElementById('quests-list-container');
  if (!container) return;
  container.innerHTML = '<div class="quest-loading">Dang tai danh sach nhiem vu Discord...</div>';
  try {
    const r = await fetch('/api/quests');
    const d = await r.json();
    container.innerHTML = '';
    if (!d.quests?.length) {
      container.innerHTML = '<div class="quest-loading">Khong tim thay nhiem vu nao hoac chua lien ket Discord Token.</div>';
      return;
    }
    d.quests.forEach(q => {
      const card = buildQuestCard(q);
      container.appendChild(card);
    });
  } catch (e) {
    container.innerHTML = '<div class="quest-loading">Loi khi tai danh sach nhiem vu tu may chu.</div>';
  }
}

// ============================================================
// QUEST LOG TERMINAL
// ============================================================

const QUEST_LOG_LEVEL_COLOR = {
  'success': '#4ade80',
  'error': '#f87171',
  'warning': '#fbbf24',
  'warn': '#fbbf24',
  'info': '#a5b4fc'
};

function appendQuestLog(entry) {
  const screen = document.getElementById('quest-log-screen');
  if (!screen) return;
  const line = document.createElement('div');
  line.className = `log-line ${entry.level || 'info'}`;
  const color = QUEST_LOG_LEVEL_COLOR[entry.level] || '#a5b4fc';
  line.innerHTML = `<span class="log-time" style="color:#64748b;">[${entry.time}]</span> <span class="log-msg" style="color:${color};">${escapeHtml(entry.message)}</span>`;
  screen.appendChild(line);
  // Auto-scroll to bottom
  screen.scrollTop = screen.scrollHeight;
  // Trim old entries (keep max 100 lines visible)
  while (screen.children.length > 120) {
    screen.removeChild(screen.firstChild);
  }
}

function clearQuestLog() {
  const screen = document.getElementById('quest-log-screen');
  if (screen) screen.innerHTML = '';
  questLogLastCount = 0;
}

async function fetchQuestLogs() {
  try {
    const r = await fetch('/api/quests/logs');
    const d = await r.json();
    if (!d.success || !d.logs) return;
    const logs = d.logs;
    if (logs.length > questLogLastCount) {
      // Append only new entries
      for (let i = questLogLastCount; i < logs.length; i++) {
        appendQuestLog(logs[i]);
      }
      questLogLastCount = logs.length;
    }
  } catch (e) { }
}

function startQuestLogPolling() {
  if (questLogInterval) clearInterval(questLogInterval);
  questLogInterval = setInterval(fetchQuestLogs, 800);
}

function stopQuestLogPolling() {
  if (questLogInterval) { clearInterval(questLogInterval); questLogInterval = null; }
}


async function handleAutoEnrollAll() {
  showToast('Dang tu dong nhan tat ca Quest tren Discord...', 'info', 2500);
  try {
    const r = await fetch('/api/quests/enroll_all', { method: 'POST' });
    const d = await r.json();
    if (d.success) {
      showToast(d.message || `Da nhan tat ca nhiem vu thanh cong!`, 'success');
      loadAvailableQuests();
    } else {
      showToast(d.message || 'Khong the nhan nhiem vu', 'error');
    }
  } catch (e) {
    showToast('Loi ket noi khi nhan nhiem vu', 'error');
  }
}

function buildQuestCard(q) {
  const card = document.createElement('div');
  card.className = 'quest-card-v2';
  const pct = q.progress_pct || 0;
  const imgUrl = q.banner_url || q.banner || '';
  const taskBadge = q.task_type || q.type || 'Quest';
  const isEnrolled = q.enrolled;
  const isCompleted = q.completed;

  let actionBtn = `<button type="button" class="quest-card-start-btn" onclick="handleStartQuest('${escapeHtml(q.id || '')}', '${escapeHtml(q.title || q.name || 'Quest')}', '${escapeHtml(q.game_name || '')}', '${escapeHtml(imgUrl)}', '${escapeHtml(taskBadge)}', ${q.target_seconds || 60})">Bat Dau Auto Cay</button>`;
  if (isCompleted) {
    actionBtn = `<button type="button" class="quest-card-start-btn completed" disabled>Da Hoan Thanh</button>`;
  }

  card.innerHTML = `
    ${imgUrl ? `<img src="${escapeHtml(imgUrl)}" class="quest-card-banner" alt="${escapeHtml(q.title || '')}" onerror="this.style.display='none'">` : ''}
    <div class="quest-card-body">
      <div class="quest-card-badge-row">
        <span class="quest-card-badge">${escapeHtml(taskBadge)}</span>
        ${isEnrolled ? '<span class="quest-tag enrolled">Da Nhan</span>' : '<span class="quest-tag not-enrolled">Chua Nhan</span>'}
      </div>
      <div class="quest-card-title">${escapeHtml(q.title || q.name || 'Nhiem vu')}</div>
      <div class="quest-card-game">${escapeHtml(q.game_name || q.app_name || '')}</div>
      ${q.rewards_text ? `<div class="quest-card-reward">Phan thuong: ${escapeHtml(q.rewards_text)}</div>` : ''}
      <div class="quest-card-progress">
        <div class="quest-card-progress-bar"><div class="quest-card-progress-fill" style="width:${pct}%"></div></div>
        <div class="quest-card-progress-pct">${pct}% hoan thanh (${Math.round(q.seconds_done || 0)}s / ${q.target_seconds || 60}s)</div>
      </div>
      ${actionBtn}
    </div>`;
  return card;
}

async function handleStartAutoQuest() {
  const titleEl = document.getElementById('quest-active-title');
  const subEl = document.getElementById('quest-active-sub');
  const chip = document.getElementById('quest-status-chip');
  if (titleEl) titleEl.textContent = 'Auto Completer Đang Chạy...';
  if (subEl) subEl.textContent = 'Đang tự động quét & hoàn thành tất cả Quest...';
  if (chip) { chip.textContent = 'Đang Chạy Auto'; chip.className = 'quest-status-badge running'; }
  setLed('quest');
  const stopBtn = document.getElementById('btn-quest-stop');
  if (stopBtn) stopBtn.disabled = false;

  // Clear console and start log polling
  clearQuestLog();
  await fetch('/api/quests/logs', { method: 'DELETE' });
  questLogLastCount = 0;
  startQuestLogPolling();

  try {
    const r = await fetch('/api/quests/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto: true })
    });
    const d = await r.json();
    if (d.success) {
      showToast('Đã khởi động Quest Auto-Completer!', 'success');
      startQuestProgressPolling('auto', 100);
    } else {
      showToast(d.message || 'Không thể chạy Auto Quest', 'error');
      if (chip) { chip.textContent = 'Lỗi'; chip.className = 'quest-status-badge'; }
      setLed('idle');
      if (stopBtn) stopBtn.disabled = true;
      stopQuestLogPolling();
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
    stopQuestLogPolling();
  }
}

async function handleStartQuest(id, name, game, imgUrl, taskType, targetSec) {
  currentQuestId = id;
  const titleEl = document.getElementById('quest-active-title');
  const subEl = document.getElementById('quest-active-sub');
  const bannerEl = document.getElementById('quest-game-banner');
  const chip = document.getElementById('quest-status-chip');
  if (titleEl) titleEl.textContent = name;
  if (subEl) subEl.textContent = `Game: ${game || 'Discord'} [${taskType}] — Đang khởi động...`;
  if (chip) { chip.textContent = 'Đang Chạy'; chip.className = 'quest-status-badge running'; }
  if (bannerEl) {
    if (imgUrl) bannerEl.innerHTML = `<img src="${escapeHtml(imgUrl)}" alt="" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none'">`;
    else bannerEl.innerHTML = `<div class="qrc-game-placeholder">${escapeHtml(game || 'Quest')}</div>`;
  }
  setLed('quest');
  const stopBtn = document.getElementById('btn-quest-stop');
  if (stopBtn) stopBtn.disabled = false;

  // Clear console and start log polling
  clearQuestLog();
  await fetch('/api/quests/logs', { method: 'DELETE' });
  questLogLastCount = 0;
  startQuestLogPolling();

  try {
    const r = await fetch('/api/quests/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quest_id: id, quest_name: name, task_type: taskType, target_seconds: targetSec })
    });
    const d = await r.json();
    if (d.success) {
      showToast(`Bắt đầu cày: ${name}`, 'success');
      startQuestProgressPolling(id, targetSec);
    } else {
      showToast(d.message || 'Không thể bắt đầu quest', 'error');
      if (chip) { chip.textContent = 'Lỗi'; chip.className = 'quest-status-badge'; }
      setLed('idle');
      if (stopBtn) stopBtn.disabled = true;
      stopQuestLogPolling();
    }
  } catch (e) { showToast('Lỗi kết nối máy chủ', 'error'); stopQuestLogPolling(); }
}

function startQuestProgressPolling(id, targetSec) {
  if (questRunnerInterval) clearInterval(questRunnerInterval);
  questRunnerInterval = setInterval(async () => {
    try {
      const r = await fetch('/api/quests/status');
      const d = await r.json();
      const st = d.status || {};
      const pct = st.progress_pct || 0;
      const elapsed = st.elapsed_seconds || 0;
      const target = st.target_seconds || targetSec;

      const titleEl = document.getElementById('quest-active-title');
      const subEl = document.getElementById('quest-active-sub');
      if (st.is_auto_mode && st.quest_name && titleEl) {
        titleEl.textContent = `Auto: ${st.quest_name}`;
        if (subEl) subEl.textContent = `Loại: ${st.task_type || 'N/A'} — Đang tự động xử lý`;
      }

      const pctEl = document.getElementById('quest-progress-pct');
      const fillEl = document.getElementById('quest-progress-fill');
      const timeEl = document.getElementById('quest-progress-time');
      if (pctEl) pctEl.textContent = `${pct}%`;
      if (fillEl) fillEl.style.width = `${pct}%`;
      if (timeEl) timeEl.textContent = `${elapsed}s / ${target}s`;

      if (st.status === 'completed') {
        clearInterval(questRunnerInterval);
        questRunnerInterval = null;
        stopQuestLogPolling();
        await fetchQuestLogs();
        const chip = document.getElementById('quest-status-chip');
        if (chip) { chip.textContent = 'Hoàn Thành'; chip.className = 'quest-status-badge completed'; }
        setLed('idle');
        const stopBtn = document.getElementById('btn-quest-stop');
        if (stopBtn) stopBtn.disabled = true;
        showToast('Nhiệm vụ đã hoàn thành!', 'success', 6000);
        loadAvailableQuests();
      } else if (st.status === 'stopped') {
        clearInterval(questRunnerInterval);
        questRunnerInterval = null;
        stopQuestLogPolling();
        const chip = document.getElementById('quest-status-chip');
        if (chip) { chip.textContent = 'Đã Dừng'; chip.className = 'quest-status-badge'; }
        setLed('idle');
        const stopBtn = document.getElementById('btn-quest-stop');
        if (stopBtn) stopBtn.disabled = true;
      }
    } catch (e) { }
  }, 1200);
}

async function handleStopQuest() {
  try {
    await fetch('/api/quests/stop', { method: 'POST' });
    if (questRunnerInterval) {
      clearInterval(questRunnerInterval);
      questRunnerInterval = null;
    }
    stopQuestLogPolling();
    setLed('idle');
    const chip = document.getElementById('quest-status-chip');
    if (chip) { chip.textContent = 'Da Dung'; chip.className = 'quest-status-badge'; }
    document.getElementById('btn-quest-stop').disabled = true;
    showToast('Da dung auto quest', 'info');
  } catch (e) { showToast('Loi dung quest', 'error'); }
}

// ============================================================
// HYPESQUAD
// ============================================================

async function handleClaimHypeSquad(house) {
  const names = { 1: 'Bravery', 2: 'Brilliance', 3: 'Balance' };
  showToast(`Dang nhan HypeSquad ${names[house]}...`, 'info', 2000);
  try {
    const r = await fetch('/api/hypesquad/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ house_id: house })
    });
    const d = await r.json();
    if (d.success) showToast(`Da nhan Huy Hieu ${names[house]}!`, 'success');
    else showToast(d.error || 'Nhan huy hieu that bai', 'error');
  } catch (e) { showToast('Loi ket noi', 'error'); }
}

// Fix typo in HTML for balance button
function handleClaimHypeQuad(house) { handleClaimHypeSquad(house); }

// ============================================================
// INIT
async function loadSavedConfig() {
  try {
    const r = await fetch('/api/get_config');
    const d = await r.json();
    if (d.success && d.config) {
      const c = d.config;
      const set = (elId, val) => { const e = document.getElementById(elId); if (e && val !== undefined && val !== null) e.value = val; };
      if (c.name) set('input-activity-name', c.name);
      if (c.details !== undefined) set('input-details', c.details);
      if (c.state !== undefined) set('input-state', c.state);
      if (c.large_image) set('input-large-image', c.large_image);
      if (c.small_image) set('input-small-image', c.small_image);
      if (c.large_text !== undefined) set('input-large-text', c.large_text);
      if (c.small_text !== undefined) set('input-small-text', c.small_text);
      if (c.buttons?.[0]) {
        set('input-btn1-label', c.buttons[0].label || '');
        set('input-btn1-url', c.buttons[0].url || '');
      }
      if (c.buttons?.[1]) {
        set('input-btn2-label', c.buttons[1].label || '');
        set('input-btn2-url', c.buttons[1].url || '');
      }
      if (c.activity_type) set('select-activity-type', c.activity_type);
      if (c.app_id) set('input-app-id', c.app_id);
      if (c.user_status) set('select-user-status', c.user_status);
      const ts = document.getElementById('check-timestamp');
      if (ts && c.use_timestamp !== undefined) ts.checked = !!c.use_timestamp;

      if (c.large_image) onManualImageChange('large');
      if (c.small_image) {
        onManualImageChange('small');
      } else {
        clearSmallImage();
      }
      updateLivePreview();
    }
  } catch (e) { }
}

// ============================================================
// SOUNDCLOUD, YOUTUBE & SPOTIFY RPC HANDLERS
// ============================================================

function handleLoadSoundCloudTrack() {
  const url = document.getElementById('sc-track-url')?.value.trim();
  if (!url) return;
  const parts = url.split('/').filter(Boolean);
  if (parts.length >= 2) {
    const artist = parts[parts.length - 2];
    const track = parts[parts.length - 1].replace(/-/g, ' ');
    if (document.getElementById('sc-artist-name')) document.getElementById('sc-artist-name').value = artist;
    if (document.getElementById('sc-track-title')) document.getElementById('sc-track-title').value = track;
    if (document.getElementById('sc-pv-title')) document.getElementById('sc-pv-title').textContent = track;
    if (document.getElementById('sc-pv-artist')) document.getElementById('sc-pv-artist').textContent = `${artist} • SoundCloud`;
    showToast('Đã nạp thông tin track SoundCloud!', 'success');
  }
}

async function handleApplySoundCloudRPC() {
  const title = document.getElementById('sc-track-title')?.value.trim() || 'SoundCloud Music';
  const artist = document.getElementById('sc-artist-name')?.value.trim() || 'SoundCloud Artist';

  document.getElementById('select-activity-type').value = 'listening';
  document.getElementById('input-activity-name').value = 'SoundCloud';
  document.getElementById('input-details').value = title;
  document.getElementById('input-state').value = `by ${artist}`;
  document.getElementById('input-large-text').value = 'SoundCloud Web Player';

  updateLivePreview();
  handleStartRPC();
  showToast('Đã áp dụng SoundCloud RPC!', 'success');
}

async function handleFetchYouTubeMeta() {
  const url = document.getElementById('yt-video-url')?.value.trim();
  if (!url) {
    showToast('Vui lòng dán link YouTube', 'error');
    return;
  }
  showToast('Đang lấy dữ liệu video YouTube...', 'info', 2000);
  try {
    const res = await fetch(`/api/youtube/meta?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    if (data.success) {
      if (document.getElementById('yt-video-title')) document.getElementById('yt-video-title').value = data.title;
      if (document.getElementById('yt-pv-title')) document.getElementById('yt-pv-title').textContent = data.title;
      if (document.getElementById('yt-pv-thumb')) document.getElementById('yt-pv-thumb').src = data.thumbnail;
      showToast('Đã nhận diện video YouTube!', 'success');
    } else {
      showToast(data.message || 'Không thể lấy video', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

async function handleApplyYouTubeRPC() {
  const title = document.getElementById('yt-video-title')?.value.trim() || 'YouTube Video';
  const channel = document.getElementById('yt-channel-name')?.value.trim() || 'YouTube Channel';
  const action = document.getElementById('yt-action-label')?.value || 'Watching YouTube';
  const thumb = document.getElementById('yt-pv-thumb')?.src || '';

  document.getElementById('select-activity-type').value = action.includes('Live') ? 'streaming' : 'watching';
  document.getElementById('input-activity-name').value = 'YouTube';
  document.getElementById('input-details').value = title;
  document.getElementById('input-state').value = channel;
  if (thumb) {
    currentLargeImageUrl = thumb;
    document.getElementById('input-large-img').value = thumb;
  }
  updateLivePreview();
  handleStartRPC();
  showToast('Đã áp dụng YouTube RPC!', 'success');
}

async function handleApplySpotifyRPC() {
  const title = document.getElementById('sp-track-name')?.value.trim() || 'Track';
  const artist = document.getElementById('sp-artist-name')?.value.trim() || 'Artist';
  const album = document.getElementById('sp-album-name')?.value.trim() || 'Album';
  const art = document.getElementById('sp-album-art')?.value.trim() || '';

  document.getElementById('select-activity-type').value = 'listening';
  document.getElementById('input-activity-name').value = 'Spotify';
  document.getElementById('input-details').value = title;
  document.getElementById('input-state').value = `by ${artist}`;
  if (art) {
    currentLargeImageUrl = art;
    document.getElementById('input-large-img').value = art;
  }
  updateLivePreview();
  handleStartRPC();
  showToast('Đã áp dụng Spotify RPC!', 'success');
}

// ============================================================
// INBOX DISCORD HANDLER
// ============================================================

async function loadDiscordInbox() {
  const container = document.getElementById('inbox-channels-list');
  if (!container) return;
  container.innerHTML = '<div class="inbox-loading">Đang tải hộp thư & tin nhắn...</div>';
  try {
    const res = await fetch('/api/discord/inbox');
    const data = await res.json();
    if (data.success && data.channels && data.channels.length > 0) {
      container.innerHTML = data.channels.map(ch => `
        <div class="inbox-channel-card">
          <img src="${ch.avatar || 'https://cdn.discordapp.com/embed/avatars/0.png'}" class="inbox-avatar" alt="">
          <div class="inbox-meta">
            <div class="inbox-meta-name">${ch.name}</div>
            <div class="inbox-meta-sub">ID: ${ch.id}</div>
          </div>
        </div>
      `).join('');
    } else {
      container.innerHTML = '<div class="inbox-loading">Không có tin nhắn nào hoặc chưa liên kết Token.</div>';
    }
  } catch (e) {
    container.innerHTML = '<div class="inbox-loading">Lỗi kết nối tải Inbox.</div>';
  }
}

// ============================================================
// MULTI-ACCOUNT SWITCHER HANDLER
// ============================================================

async function loadMultiAccounts() {
  const container = document.getElementById('multi-accounts-grid');
  if (!container) return;
  container.innerHTML = '<div class="acc-grid-loading">Đang nạp danh sách tài khoản...</div>';
  try {
    const res = await fetch('/api/accounts/list');
    const data = await res.json();
    if (data.success && data.accounts && data.accounts.length > 0) {
      container.innerHTML = data.accounts.map(acc => `
        <div class="acc-token-card ${acc.is_active ? 'active' : ''}">
          <div class="atc-left">
            <img src="${acc.discord_avatar || 'https://cdn.discordapp.com/embed/avatars/0.png'}" class="atc-avatar" alt="">
            <div>
              <div class="atc-name">${acc.discord_username || 'Discord User'}</div>
              <div class="atc-tag">ID: ${acc.discord_id || 'N/A'} ${acc.is_active ? '• <span style="color:#22c55e;font-weight:bold;">Đang dùng</span>' : ''}</div>
            </div>
          </div>
          <div class="atc-actions">
            ${!acc.is_active ? `<button type="button" class="ssh-action" onclick="handleSwitchAccount(${acc.id})">Chọn Dùng</button>` : ''}
            <button type="button" class="ssh-action danger" onclick="handleDeleteAccount(${acc.id})">Xóa</button>
          </div>
        </div>
      `).join('');
    } else {
      container.innerHTML = '<div class="acc-grid-loading">Chưa có tài khoản nào được lưu. Bấm "Thêm Token Mới" để liên kết.</div>';
    }
  } catch (e) {
    container.innerHTML = '<div class="acc-grid-loading">Lỗi kết nối máy chủ.</div>';
  }
}

async function handleSwitchAccount(accountId) {
  showToast('Đang chuyển tài khoản...', 'info', 1500);
  try {
    const res = await fetch('/api/accounts/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accountId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      updateAccountUI(data);
      loadMultiAccounts();
    } else {
      showToast(data.message || 'Lỗi chuyển tài khoản', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

async function handleDeleteAccount(accountId) {
  if (!confirm('Bạn có chắc chắn muốn xóa token tài khoản này?')) return;
  try {
    const res = await fetch('/api/accounts/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accountId })
    });
    const data = await res.json();
    if (data.success) {
      showToast('Đã xóa tài khoản!', 'info');
      loadMultiAccounts();
      fetchAccountInfo();
    } else {
      showToast(data.message || 'Lỗi xóa tài khoản', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

function init3DCardTilt() {
  const stage = document.getElementById('hero-cards-stage');
  const card1 = document.getElementById('floating-card-1');
  const card2 = document.getElementById('floating-card-2');
  if (!stage || !card1) return;

  stage.addEventListener('mousemove', (e) => {
    const rect = stage.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;

    const rotX1 = (-y / 20) + 8;
    const rotY1 = (x / 20) - 12;
    card1.style.transform = `rotateX(${rotX1}deg) rotateY(${rotY1}deg) rotateZ(-3deg) translateZ(30px)`;

    if (card2) {
      const rotX2 = (-y / 25) + 10;
      const rotY2 = (x / 25) + 16;
      card2.style.transform = `rotateX(${rotX2}deg) rotateY(${rotY2}deg) rotateZ(5deg) translateZ(-20px)`;
    }
  });

  stage.addEventListener('mouseleave', () => {
    card1.style.transform = '';
    if (card2) card2.style.transform = '';
  });
}

async function fetchAccountInfo() {
  try {
    const res = await fetch('/api/account/info');
    const data = await res.json();
    if (data.success) {
      updateAccountUI(data);
    }
  } catch (e) {}
}

// ============================================================
// THEME SWITCHER (GUI SÁNG & GUI TỐI)
// ============================================================

const SVG_SUN = `<svg id="theme-icon-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`;
const SVG_MOON = `<svg id="theme-icon-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`;

function initTheme() {
  const savedTheme = localStorage.getItem('dipre_theme') || 'dark';
  const container = document.getElementById('theme-icon-container') || document.getElementById('theme-icon');
  if (savedTheme === 'light') {
    document.body.classList.add('light-theme');
    if (container) container.innerHTML = SVG_SUN;
  } else {
    document.body.classList.remove('light-theme');
    if (container) container.innerHTML = SVG_MOON;
  }
}

function toggleTheme() {
  const isLight = document.body.classList.toggle('light-theme');
  const container = document.getElementById('theme-icon-container') || document.getElementById('theme-icon');
  if (isLight) {
    localStorage.setItem('dipre_theme', 'light');
    if (container) container.innerHTML = SVG_SUN;
    showToast('Đã chuyển sang giao diện Sáng (Frost Elegance)', 'info', 2000);
  } else {
    localStorage.setItem('dipre_theme', 'dark');
    if (container) container.innerHTML = SVG_MOON;
    showToast('Đã chuyển sang giao diện Tối (Cyber Luxury)', 'info', 2000);
  }
}

// ============================================================
// LIVE SYSTEM CLOCK
// ============================================================

function initSystemClock() {
  const clockEl = document.getElementById('system-clock');
  if (!clockEl) return;
  const updateClock = () => {
    const now = new Date();
    const hrs = String(now.getHours()).padStart(2, '0');
    const mins = String(now.getMinutes()).padStart(2, '0');
    const secs = String(now.getSeconds()).padStart(2, '0');
    clockEl.textContent = `${hrs}:${mins}:${secs}`;
  };
  updateClock();
  setInterval(updateClock, 1000);
}

// ============================================================
// ANTI-DEVTOOLS & CHỐNG INSPECT ELEMENT
// ============================================================

function showAntiDevToolsShield() {
  const overlay = document.getElementById('anti-devtools-overlay');
  if (overlay) {
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function initAntiInspect() {
  // 1. Chặn phím tắt kỹ thuật: F12, Ctrl+Shift+I, J, C, Ctrl+U, Ctrl+S
  window.addEventListener('keydown', (e) => {
    const isF12 = e.keyCode === 123;
    const isCtrlShiftI = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'I' || e.key === 'i');
    const isCtrlShiftJ = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'J' || e.key === 'j');
    const isCtrlShiftC = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'C' || e.key === 'c');
    const isCtrlU = (e.ctrlKey || e.metaKey) && (e.key === 'u' || e.key === 'U');
    const isCtrlS = (e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S');

    if (isF12 || isCtrlShiftI || isCtrlShiftJ || isCtrlShiftC || isCtrlU || isCtrlS) {
      e.preventDefault();
      e.stopPropagation();
      showToast('⚠️ Thao tác phím tắt này bị vô hiệu hóa vì lý do bảo mật.', 'error', 2500);
      showAntiDevToolsShield();
      return false;
    }
  }, true);

  // 2. Chặn chuột phải mặc định & mở Custom Context Menu
  const customMenu = document.getElementById('dipre-custom-menu');
  window.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    if (!customMenu) return;
    
    let x = e.clientX;
    let y = e.clientY;
    const menuWidth = 220;
    const menuHeight = 220;

    if (x + menuWidth > window.innerWidth) x = window.innerWidth - menuWidth - 10;
    if (y + menuHeight > window.innerHeight) y = window.innerHeight - menuHeight - 10;

    customMenu.style.left = `${x}px`;
    customMenu.style.top = `${y}px`;
    customMenu.style.display = 'block';
  });

  window.addEventListener('click', () => {
    if (customMenu) customMenu.style.display = 'none';
  });

  // 3. Cơ chế phát hiện DevTools bằng chênh lệch kích thước cửa sổ
  setInterval(() => {
    const threshold = 160;
    const widthDiff = window.outerWidth - window.innerWidth > threshold;
    const heightDiff = window.outerHeight - window.innerHeight > threshold;
    if (widthDiff || heightDiff) {
      showAntiDevToolsShield();
    }
  }, 1200);
}

// ============================================================
// REALTIME STATUS ENGINE (ZERO-LAG SYNC)
// ============================================================

async function syncAllStatusNow() {
  try {
    const pingStatus = document.getElementById('ping-status');
    const startTime = performance.now();

    const res = await fetch('/api/live/status');
    const data = await res.json();
    
    const latency = Math.round(performance.now() - startTime);
    if (pingStatus) pingStatus.textContent = `${latency}ms`;

    if (data && data.status === 'ok') {
      const u = data.user;
      
      // Cập nhật thẻ User System trên sidebar
      const sysName = document.getElementById('user-sys-name');
      if (sysName && u.username) sysName.textContent = u.username;

      // Cập nhật avatar nếu là ảnh hoặc initials
      const avatarImg = document.getElementById('user-sys-avatar-img');
      const avatarInitials = document.getElementById('user-sys-avatar-initials');
      if (u.avatar) {
        if (u.avatar.type === 'image' && u.avatar.url) {
          if (avatarImg) {
            avatarImg.src = u.avatar.url;
            avatarImg.style.display = 'block';
          }
          if (avatarInitials) avatarInitials.style.display = 'none';
        } else if (u.avatar.type === 'initials') {
          if (avatarImg) avatarImg.style.display = 'none';
          if (avatarInitials) {
            avatarInitials.textContent = u.avatar.initials;
            if (u.avatar.gradient) avatarInitials.style.background = u.avatar.gradient;
            avatarInitials.style.display = 'flex';
          }
        }
      }

      // Cập nhật trạng thái Discord active pill
      const sadName = document.getElementById('sad-name');
      const sadTag = document.getElementById('sad-tag');
      const sadAvatar = document.getElementById('sad-avatar-img');
      const sadLocked = document.getElementById('sad-avatar-locked');

      if (u.has_token && u.discord_username) {
        if (sadName) sadName.textContent = u.discord_username;
        if (sadTag) {
          sadTag.textContent = 'Active';
          sadTag.className = 'sad-tag linked';
        }
        if (sadAvatar && u.discord_avatar) {
          sadAvatar.src = u.discord_avatar;
          sadAvatar.style.display = 'block';
        }
        if (sadLocked) sadLocked.style.display = 'none';
      } else {
        if (sadName) sadName.textContent = 'Chưa nạp Token';
        if (sadTag) {
          sadTag.textContent = 'Trống';
          sadTag.className = 'sad-tag unlinked';
        }
        if (sadAvatar) sadAvatar.style.display = 'none';
        if (sadLocked) sadLocked.style.display = 'flex';
      }
    }
  } catch (e) {
    const pingStatus = document.getElementById('ping-status');
    if (pingStatus) pingStatus.textContent = 'Offline';
  }
}

// ============================================================
// DASHBOARD STATS & COMMAND CENTER ENGINE
// ============================================================

async function loadDashboardStats() {
  try {
    const res = await fetch('/api/dashboard/stats');
    const data = await res.json();
    if (data.success && data.stats) {
      const s = data.stats;
      const totalTokEl = document.getElementById('stat-total-tokens');
      const activeUserEl = document.getElementById('stat-active-username');
      const mostUsedEl = document.getElementById('stat-most-used');
      const totalRunsEl = document.getElementById('stat-total-runs');

      if (totalTokEl) totalTokEl.innerHTML = `${s.total_tokens || 0} <span class="msc-val-sub">Tokens</span>`;
      if (activeUserEl && s.active_account) {
        activeUserEl.textContent = s.active_account.discord_username || 'Active User';
      }
      if (mostUsedEl) mostUsedEl.textContent = s.most_used_feature || 'Custom RPC';
      if (totalRunsEl) totalRunsEl.textContent = `${s.total_runs || 0} lượt chạy`;

      // Update Breakdown Progress Bars
      if (s.top_features && s.top_features.length > 0) {
        const total = s.total_runs || 1;
        s.top_features.forEach(f => {
          const pct = Math.min(100, Math.round((f.count / total) * 100));
          if (f.name.includes('RPC') || f.name.includes('rich_presence')) {
            const bar = document.getElementById('bar-rpc-fill');
            const cnt = document.getElementById('bar-rpc-count');
            if (bar) bar.style.width = `${pct}%`;
            if (cnt) cnt.textContent = `${f.count} lượt`;
          } else if (f.name.includes('Status') || f.name.includes('Lyric')) {
            const bar = document.getElementById('bar-status-fill');
            const cnt = document.getElementById('bar-status-count');
            if (bar) bar.style.width = `${pct}%`;
            if (cnt) cnt.textContent = `${f.count} lượt`;
          } else if (f.name.includes('Voice')) {
            const bar = document.getElementById('bar-voice-fill');
            const cnt = document.getElementById('bar-voice-count');
            if (bar) bar.style.width = `${pct}%`;
            if (cnt) cnt.textContent = `${f.count} lượt`;
          } else if (f.name.includes('Quest')) {
            const bar = document.getElementById('bar-script-fill');
            const cnt = document.getElementById('bar-script-count');
            if (bar) bar.style.width = `${pct}%`;
            if (cnt) cnt.textContent = `${f.count} lượt`;
          }
        });
      }
    }
  } catch (e) {}
}

// ============================================================
// CUSTOM STATUS & ROTATOR ENGINE
// ============================================================

function updateCustomStatusPreview() {
  const text = document.getElementById('input-custom-status-text')?.value.trim() || 'Đang trải nghiệm DIPRE Studio';
  const emoji = document.getElementById('select-custom-status-emoji')?.value || '💻';
  const pvBody = document.getElementById('custom-status-pv-body');
  const pvEmoji = document.getElementById('custom-status-pv-emoji');

  if (pvBody) pvBody.textContent = text;
  if (pvEmoji) pvEmoji.textContent = emoji;
}

async function handleApplyCustomStatus() {
  const text = document.getElementById('input-custom-status-text')?.value.trim();
  const emoji = document.getElementById('select-custom-status-emoji')?.value || '💻';
  if (!text) {
    showToast('Vui lòng nhập nội dung trạng thái!', 'warn');
    return;
  }
  showToast('Đang cập nhật Custom Status...', 'info', 1500);
  try {
    const res = await fetch('/api/status/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, emoji })
    });
    const data = await res.json();
    if (data.success) {
      showToast('Đã cập nhật trạng thái Discord thành công!', 'success');
      const heroStatus = document.getElementById('hero-custom-status-text');
      if (heroStatus) heroStatus.textContent = `${emoji} ${text}`;
      loadDashboardStats();
    } else {
      showToast(data.message || 'Lỗi cập nhật trạng thái', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

async function handleClearCustomStatus() {
  showToast('Đang xóa trạng thái...', 'info', 1500);
  try {
    const res = await fetch('/api/lyrics/clear', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('Đã xóa Custom Status Discord!', 'info');
      const heroStatus = document.getElementById('hero-custom-status-text');
      if (heroStatus) heroStatus.textContent = 'DIPRE Studio Active';
      const input = document.getElementById('input-custom-status-text');
      if (input) input.value = '';
      updateCustomStatusPreview();
    } else {
      showToast(data.message || 'Lỗi xóa status', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối', 'error');
  }
}

let statusRotatorTimer = null;
let statusRotatorIndex = 0;

function toggleStatusRotator() {
  const check = document.getElementById('check-status-rotator-toggle');
  if (statusRotatorTimer) {
    clearInterval(statusRotatorTimer);
    statusRotatorTimer = null;
  }
  if (check && check.checked) {
    const linesStr = document.getElementById('status-rotator-lines')?.value.trim() || '';
    const lines = linesStr.split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length < 2) {
      showToast('Vui lòng nhập ít nhất 2 câu status để xoay vòng!', 'warn');
      check.checked = false;
      return;
    }
    const sec = Math.max(5, parseInt(document.getElementById('status-rotator-interval')?.value || '15'));
    showToast(`Đã bật Bộ Xoay Vòng Status (đổi mỗi ${sec}s)`, 'success');

    const rotateNext = async () => {
      const curLine = lines[statusRotatorIndex % lines.length];
      statusRotatorIndex++;
      const emoji = document.getElementById('select-custom-status-emoji')?.value || '✨';
      try {
        await fetch('/api/status/custom', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: curLine, emoji })
        });
        const heroStatus = document.getElementById('hero-custom-status-text');
        if (heroStatus) heroStatus.textContent = `${emoji} ${curLine}`;
      } catch (e) {}
    };

    rotateNext();
    statusRotatorTimer = setInterval(rotateNext, sec * 1000);
  } else {
    showToast('Đã tắt Bộ Xoay Vòng Status', 'info');
  }
}

// ============================================================
// VOICE 24/7 (AFK VOICE) ENGINE
// ============================================================

let voiceTimerInterval = null;
let voiceElapsedSeconds = 0;

async function checkVoiceStatus() {
  try {
    const res = await fetch('/api/voice/status');
    const data = await res.json();
    if (data.success) {
      const isRunning = data.is_running;
      const btnStart = document.getElementById('btn-voice-start');
      const btnStop = document.getElementById('btn-voice-stop');
      const dot = document.getElementById('voice-vcs-dot');
      const title = document.getElementById('voice-vcs-title');
      const sub = document.getElementById('voice-vcs-sub');
      const badge = document.getElementById('voice-live-badge');
      const pvCh = document.getElementById('voice-pv-channel-name');

      if (isRunning) {
        if (btnStart) btnStart.disabled = true;
        if (btnStop) btnStop.disabled = false;
        if (dot) dot.className = 'vcs-dot connected';
        if (title) title.textContent = 'Đang treo Voice 24/7: Đã kết nối';
        if (sub) sub.textContent = `Server: ${data.guild_id} | Channel: ${data.channel_id}`;
        if (badge) { badge.textContent = 'CONNECTED'; badge.className = 'preview-live-badge active'; }
        if (pvCh) pvCh.textContent = `Phòng Voice: ${data.channel_id}`;

        voiceElapsedSeconds = data.elapsed_seconds || 0;
        if (!voiceTimerInterval) {
          voiceTimerInterval = setInterval(() => {
            voiceElapsedSeconds++;
            const h = String(Math.floor(voiceElapsedSeconds / 3600)).padStart(2, '0');
            const m = String(Math.floor((voiceElapsedSeconds % 3600) / 60)).padStart(2, '0');
            const s = String(voiceElapsedSeconds % 60).padStart(2, '0');
            const timerEl = document.getElementById('voice-pv-timer');
            if (timerEl) timerEl.textContent = `Thời gian treo: ${h}:${m}:${s}`;
          }, 1000);
        }
      } else {
        if (btnStart) btnStart.disabled = false;
        if (btnStop) btnStop.disabled = true;
        if (dot) dot.className = 'vcs-dot';
        if (title) title.textContent = 'Chưa kết nối Voice';
        if (sub) sub.textContent = 'Nhập Guild ID và Channel ID để bắt đầu treo voice';
        if (badge) { badge.textContent = 'STANDBY'; badge.className = 'preview-live-badge'; }
        if (pvCh) pvCh.textContent = 'Phòng Voice Chưa Kết Nối';
        if (voiceTimerInterval) {
          clearInterval(voiceTimerInterval);
          voiceTimerInterval = null;
        }
        const timerEl = document.getElementById('voice-pv-timer');
        if (timerEl) timerEl.textContent = 'Thời gian treo: 00:00:00';
      }
    }
  } catch (e) {}
}

async function handleStartVoiceAFK() {
  const guild_id = document.getElementById('input-voice-guild-id')?.value.trim();
  const channel_id = document.getElementById('input-voice-channel-id')?.value.trim();
  const self_mute = document.getElementById('check-voice-mute')?.checked ?? true;
  const self_deaf = document.getElementById('check-voice-deaf')?.checked ?? true;

  if (!guild_id || !channel_id) {
    showToast('Vui lòng nhập đầy đủ Guild ID và Channel ID!', 'warn');
    return;
  }

  showToast('Đang kết nối vào phòng voice Discord...', 'info', 2000);
  try {
    const res = await fetch('/api/voice/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ guild_id, channel_id, self_mute, self_deaf })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      checkVoiceStatus();
      loadDashboardStats();
    } else {
      showToast(data.message || 'Lỗi kết nối Voice', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

async function handleStopVoiceAFK() {
  showToast('Đang ngắt kết nối Treo Voice...', 'info', 1500);
  try {
    const res = await fetch('/api/voice/stop', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'info');
      checkVoiceStatus();
    } else {
      showToast(data.message || 'Lỗi ngắt kết nối', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

function init() {
  initTheme();
  initSystemClock();
  initAntiInspect();

  // Khôi phục tab từ URL hash nếu có (ví dụ: #tab-spotify)
  if (window.location.hash) {
    const hashTab = window.location.hash.replace('#', '');
    if (TAB_TITLES[hashTab]) {
      switchTab(hashTab);
    } else {
      switchTab('tab-home');
    }
  } else {
    switchTab('tab-home');
  }

  buildVisualGallery();
  loadPresets();
  onActivityTypeChange();
  updateLivePreview();
  initDipreAudioPlayer();
  init3DCardTilt();
  loadAvailableQuests();
  startLogPolling();
  loadSavedConfig();
  fetchAccountInfo();
  loadMultiAccounts();
  loadDashboardStats();
  checkVoiceStatus();

  // Chạy background polling định kỳ 3.5s
  setInterval(syncAllStatusNow, 3500);
}

document.addEventListener('DOMContentLoaded', init);


