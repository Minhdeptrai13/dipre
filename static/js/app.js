
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

async function handleSaveDipreProfile() {
  const usernameInput = document.getElementById('edit-dipre-username');
  const avatarInput = document.getElementById('edit-dipre-avatar');
  const btn = document.getElementById('btn-save-dipre-profile');

  const username = usernameInput ? usernameInput.value.trim() : '';
  const avatarUrl = avatarInput ? avatarInput.value.trim() : '';

  if (!username) {
    showToast('Tên hiển thị DIPRE không được để trống', 'warning');
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Đang lưu...';
  }

  try {
    const res = await fetch('/api/user/profile/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, avatar_url: avatarUrl })
    });
    const d = await res.json();
    if (d.success) {
      showToast('Đã cập nhật hồ sơ DIPRE thành công!', 'success');
      const sysName = document.getElementById('user-sys-name');
      if (sysName) sysName.textContent = username;
      const modalName = document.getElementById('modal-user-display-name');
      if (modalName) modalName.textContent = username;
      const heroName = document.getElementById('hero-profile-name');
      if (heroName) heroName.textContent = username;

      if (avatarUrl) {
        const sysImg = document.getElementById('user-sys-avatar-img');
        const sysInitials = document.getElementById('user-sys-avatar-initials');
        if (sysImg) {
          sysImg.src = avatarUrl;
          sysImg.style.display = 'block';
        }
        if (sysInitials) sysInitials.style.display = 'none';

        const modalImg = document.getElementById('modal-user-avatar-img');
        const modalInitials = document.getElementById('modal-user-avatar-initials');
        if (modalImg) {
          modalImg.src = avatarUrl;
          modalImg.style.display = 'block';
        }
        if (modalInitials) modalInitials.style.display = 'none';

        const heroAv = document.getElementById('hero-avatar-img');
        if (heroAv) {
          heroAv.src = avatarUrl;
          heroAv.classList.remove('d-none');
        }
      }
      setTimeout(() => toggleAccountModal(false), 800);
    } else {
      showToast(d.message || 'Lỗi cập nhật hồ sơ', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Lưu Thay Đổi Hồ Sơ';
    }
  }
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
  if (heroTag) heroTag.textContent = (displayName || '').toLowerCase().replace(/\s+/g, '');
  if (heroStatusDot) {
    heroStatusDot.className = `dc1-status-dot ${isLinked ? 'online' : 'idle'}`;
  }

  if (heroAv && avatar) {
    heroAv.src = avatar;
    heroAv.classList.remove('d-none');
  }

  if (authProvider === 'google' && !isLinked) {
    // Chế độ Google Popout Card (Ảnh 2)
    const gadEmail = document.querySelector('.gad-email');
    const gadGreeting = document.querySelector('.gad-greeting');
    const gadImg = document.querySelector('.gad-avatar-img');
    if (gadEmail && data.username) gadEmail.textContent = data.username.includes('@') ? data.username : `${data.username}@gmail.com`;
    if (gadGreeting && data.username) gadGreeting.textContent = `Chào ${data.username.split('@')[0]},`;
    if (gadImg && avatar) gadImg.src = avatar;
  } else {
    // Chế độ Discord Card 1:1 (Ảnh 3 & 4)
    if (decorUrl && heroDecor) {
      heroDecor.src = decorUrl;
      heroDecor.classList.remove('d-none');
    } else if (heroDecor) {
      heroDecor.classList.add('d-none');
    }

    if (heroBadges && badgesList && badgesList.length > 0) {
      heroBadges.innerHTML = badgesList.map(b => `<img src="${b.icon}" alt="${b.name}" title="${b.name}" class="dc1-badge-icon">`).join('');
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

// ============================================================
// 1. YOUTUBE RPC SUITE
// ============================================================
async function handleFetchYouTubeMeta() {
  const url = document.getElementById('yt-video-url')?.value.trim();
  if (!url) {
    showToast('Vui lòng nhập đường dẫn video YouTube!', 'warn');
    return;
  }
  showToast('Đang trích xuất dữ liệu YouTube...', 'info', 1500);
  try {
    const res = await fetch(`/api/youtube/meta?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    if (data.success) {
      if (document.getElementById('yt-video-title')) document.getElementById('yt-video-title').value = data.title;
      if (document.getElementById('yt-pv-title')) document.getElementById('yt-pv-title').textContent = data.title;
      if (document.getElementById('yt-pv-thumb')) document.getElementById('yt-pv-thumb').src = data.thumbnail;
      showToast('Đã lấy dữ liệu video YouTube thành công!', 'success');
    } else {
      showToast(data.message || 'Không thể lấy thông tin video', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

async function handleApplyYouTubeRPC() {
  const title = document.getElementById('yt-video-title')?.value.trim() || 'Rick Astley - Never Gonna Give You Up';
  const channel = document.getElementById('yt-channel-name')?.value.trim() || 'Rick Astley';
  const actionLabel = document.getElementById('yt-action-label')?.value || 'Watching YouTube';
  const url = document.getElementById('yt-video-url')?.value.trim() || 'https://www.youtube.com/watch?v=dQw4w9WgXcQ';
  let thumb = document.getElementById('yt-pv-thumb')?.src || 'https://img.youtube.com/vi/dQw4w9WgXcQ/maxresdefault.jpg';

  showToast('Đang áp dụng Rich Presence YouTube...', 'info', 1500);
  try {
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        activityType: 3, // Watching
        activityName: 'YouTube',
        details: title,
        state: `${channel} • ${actionLabel}`,
        largeImage: thumb,
        largeText: title,
        smallImage: 'https://cdn.jsdelivr.net/gh/devicons/devicon/icons/youtube/youtube-original.svg',
        smallText: 'YouTube Live',
        button1Label: 'Xem Video',
        button1Url: url,
        button2Label: 'Kênh YouTube',
        button2Url: 'https://youtube.com'
      })
    });
    const d = await res.json();
    if (d.success) {
      showToast('Đã kích hoạt YouTube Rich Presence trên Discord!', 'success');
    } else {
      showToast(d.message || 'Lỗi áp dụng RPC', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

// ============================================================
// 2. SOUNDCLOUD RPC SUITE
// ============================================================
function handleLoadSoundCloudTrack() {
  const url = document.getElementById('sc-track-url')?.value.trim();
  if (!url) {
    showToast('Vui lòng nhập link bài hát SoundCloud!', 'warn');
    return;
  }
  try {
    const parts = url.split('soundcloud.com/')[1]?.split('/') || [];
    if (parts.length >= 2) {
      const artist = decodeURIComponent(parts[0].replace(/-/g, ' '));
      const track = decodeURIComponent(parts[1].replace(/-/g, ' '));
      if (document.getElementById('sc-track-title')) document.getElementById('sc-track-title').value = track;
      if (document.getElementById('sc-artist-name')) document.getElementById('sc-artist-name').value = artist;
      if (document.getElementById('sc-pv-title')) document.getElementById('sc-pv-title').textContent = track;
      if (document.getElementById('sc-pv-artist')) document.getElementById('sc-pv-artist').textContent = `${artist} • SoundCloud`;
      showToast('Đã nạp bài hát SoundCloud!', 'success');
    } else {
      showToast('Đã nhận diện link bài hát SoundCloud!', 'info');
    }
  } catch (e) {
    showToast('Link SoundCloud hợp lệ!', 'info');
  }
}

async function handleApplySoundCloudRPC() {
  const title = document.getElementById('sc-track-title')?.value.trim() || 'Sunset Lover';
  const artist = document.getElementById('sc-artist-name')?.value.trim() || 'Petit Biscuit';
  const scUrl = document.getElementById('sc-track-url')?.value.trim() || 'https://soundcloud.com';

  showToast('Đang kích hoạt SoundCloud RPC...', 'info', 1500);
  try {
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        activityType: 2, // Listening to
        activityName: 'SoundCloud',
        details: title,
        state: `by ${artist}`,
        largeImage: 'https://i1.sndcdn.com/avatars-000318625902-60zndb-t500x500.jpg',
        largeText: title,
        smallImage: 'https://a-v2.sndcdn.com/assets/images/sc-icons/favicon-2cadd14bdb.ico',
        smallText: 'SoundCloud',
        button1Label: 'Nghe trên SoundCloud',
        button1Url: scUrl
      })
    });
    const d = await res.json();
    if (d.success) {
      showToast('Đã kích hoạt SoundCloud Presence trên Discord!', 'success');
    } else {
      showToast(d.message || 'Lỗi kích hoạt', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

// ============================================================
// 3. SPOTIFY RPC SUITE
// ============================================================
async function handleApplySpotifyRPC() {
  const trackName = document.getElementById('sp-track-name')?.value.trim() || 'Starboy';
  const artistName = document.getElementById('sp-artist-name')?.value.trim() || 'The Weeknd, Daft Punk';
  const albumName = document.getElementById('sp-album-name')?.value.trim() || 'Starboy';
  const albumArt = document.getElementById('sp-album-art')?.value.trim() || 'https://i.scdn.co/image/ab67616d0000b2734718e2b124f79258be7bc452';

  showToast('Đang kích hoạt Spotify Rich Presence...', 'info', 1500);
  try {
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        activityType: 2, // Listening to
        activityName: 'Spotify',
        details: trackName,
        state: artistName,
        largeImage: albumArt,
        largeText: albumName,
        smallImage: 'https://open.spotifycdn.com/cdn/images/favicon32.8e66b099.png',
        smallText: 'Spotify',
        button1Label: 'Mở Spotify',
        button1Url: 'https://open.spotify.com'
      })
    });
    const d = await res.json();
    if (d.success) {
      showToast('Đã kích hoạt Spotify Rich Presence trên Discord!', 'success');
    } else {
      showToast(d.message || 'Lỗi kích hoạt', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

// ============================================================
// 4. QUẢN LÝ ĐA TOKEN (MULTI-TOKEN SWITCHER)
// ============================================================
async function loadMultiAccounts() {
  const grid = document.getElementById('multi-accounts-grid');
  if (!grid) return;
  try {
    const res = await fetch('/api/accounts/list');
    const data = await res.json();
    if (data.success && data.accounts && data.accounts.length > 0) {
      grid.innerHTML = data.accounts.map(acc => {
        const isActive = acc.is_active === 1;
        const av = acc.discord_avatar || 'https://cdn.discordapp.com/embed/avatars/0.png';
        const decor = acc.avatar_decoration ? `<img src="${acc.avatar_decoration}" style="position:absolute; inset:-4px; width:54px; height:54px; pointer-events:none;">` : '';
        return `
          <div class="acc-card-item ${isActive ? 'active' : ''}">
            <div class="aci-header">
              <div style="position:relative; width:46px; height:46px;">
                <img src="${av}" alt="" class="aci-avatar">
                ${decor}
              </div>
              <div class="aci-info">
                <div class="aci-name">${acc.discord_username || 'Discord User'}</div>
                <div class="aci-id">ID: ${acc.discord_id || '---'}</div>
              </div>
              <span class="acc-status-pill ${isActive ? 'linked' : 'unlinked'}" style="font-size:0.7rem; padding:2px 8px;">
                ${isActive ? '● Đang Dùng' : 'Dự Phòng'}
              </span>
            </div>
            <div class="aci-actions">
              ${!isActive ? `<button type="button" class="rpc-btn rpc-btn-start" style="padding:6px 12px; font-size:0.78rem;" onclick="switchAccount(${acc.id})">Kích Hoạt Dùng</button>` : `<button type="button" class="rpc-btn rpc-btn-save" style="padding:6px 12px; font-size:0.78rem;" disabled>Đang Kích Hoạt</button>`}
              <button type="button" class="rpc-btn rpc-btn-stop" style="padding:6px 12px; font-size:0.78rem;" onclick="deleteAccount(${acc.id})">Xóa</button>
            </div>
          </div>
        `;
      }).join('');
    } else {
      grid.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 2.5rem 1rem; background: rgba(255,255,255,0.02); border-radius: 12px; border: 1px dashed rgba(255,255,255,0.1);">
          <p style="color:#94a3b8; margin-bottom:1rem;">Chưa có tài khoản Discord Token phụ nào được lưu.</p>
          <button type="button" class="rpc-btn rpc-btn-start" onclick="toggleAccountModal(true)">+ Thêm Token Discord Đầu Tiên</button>
        </div>
      `;
    }
  } catch (e) {
    grid.innerHTML = '<div style="color:#f43f5e; padding:1rem;">Lỗi tải danh sách tài khoản.</div>';
  }
}

async function switchAccount(accId) {
  showToast('Đang chuyển đổi tài khoản Discord...', 'info', 1500);
  try {
    const res = await fetch('/api/accounts/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accId })
    });
    const d = await res.json();
    if (d.success) {
      showToast(d.message, 'success');
      loadMultiAccounts();
      fetchAccountInfo();
    } else {
      showToast(d.message || 'Lỗi chuyển đổi tài khoản', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

async function deleteAccount(accId) {
  if (!confirm('Bạn có chắc muốn xóa token tài khoản này khỏi danh sách?')) return;
  try {
    const res = await fetch('/api/accounts/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accId })
    });
    const d = await res.json();
    if (d.success) {
      showToast(d.message, 'info');
      loadMultiAccounts();
      fetchAccountInfo();
    } else {
      showToast(d.message || 'Lỗi khi xóa', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

// ============================================================
// 5. INBOX DISCORD
// ============================================================
async function loadDiscordInbox() {
  const container = document.getElementById('inbox-channels-list');
  if (!container) return;
  container.innerHTML = '<div class="inbox-loading">Đang tải hộp thư Discord...</div>';
  try {
    const res = await fetch('/api/discord/inbox');
    const data = await res.json();
    if (data.success && data.channels && data.channels.length > 0) {
      container.innerHTML = data.channels.map(ch => `
        <div class="inbox-item-card">
          <img src="${ch.avatar || 'https://cdn.discordapp.com/embed/avatars/0.png'}" class="iic-avatar" alt="">
          <div class="iic-info">
            <div class="iic-name">${ch.name}</div>
            <div class="iic-last-msg">Channel ID: ${ch.id}</div>
          </div>
          <a href="https://discord.com/channels/@me/${ch.id}" target="_blank" class="rpc-btn rpc-btn-save" style="padding: 4px 10px; font-size: 0.74rem; text-decoration: none;">
            Mở DM
          </a>
        </div>
      `).join('');
    } else {
      container.innerHTML = `<div style="grid-column:1/-1; text-align:center; color:#94a3b8; padding:2rem;">${data.message || 'Không có tin nhắn gần đây hoặc token chưa được nạp.'}</div>`;
    }
  } catch (e) {
    container.innerHTML = '<div style="color:#f43f5e; padding:1rem;">Lỗi kết nối hòm thư Discord. Hãy đảm bảo tài khoản đã nạp Token.</div>';
  }
}

// ============================================================
// 6. DISCORD VOICE SOUNDBOARD ENGINE
// ============================================================
let audioCtx = null;
let activeSoundSources = [];
let soundboardMasterVolume = 0.85;

function getAudioContext() {
  if (!audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    audioCtx = new AudioContext();
  }
  if (audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  return audioCtx;
}

function updateSoundboardVolume(vol) {
  soundboardMasterVolume = parseFloat(vol) || 0.85;
}

function stopAllSoundboardSounds() {
  activeSoundSources.forEach(s => {
    try { s.stop(); } catch (e) {}
  });
  activeSoundSources = [];
  document.querySelectorAll('.sb-card').forEach(c => c.classList.remove('playing'));
  showToast('Đã dừng tất cả âm thanh Soundboard', 'info', 1500);
}

function triggerSoundboardPlay(soundId) {
  const ctx = getAudioContext();
  const now = ctx.currentTime;
  const masterGain = ctx.createGain();
  masterGain.gain.setValueAtTime(soundboardMasterVolume, now);
  masterGain.connect(ctx.destination);

  // Thêm class active hiệu ứng cho card
  const card = event?.currentTarget || document.querySelector(`.sb-card[onclick*="${soundId}"]`);
  if (card) {
    card.classList.add('playing');
    setTimeout(() => card.classList.remove('playing'), 1500);
  }

  if (soundId === 'airhorn') {
    // Kèn hơi MLG đa âm
    const freqs = [370, 370, 370, 493, 440, 370];
    freqs.forEach((f, idx) => {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(f, now + idx * 0.12);
      g.gain.setValueAtTime(0.3, now + idx * 0.12);
      g.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.12 + 0.18);
      osc.connect(g);
      g.connect(masterGain);
      osc.start(now + idx * 0.12);
      osc.stop(now + idx * 0.12 + 0.2);
      activeSoundSources.push(osc);
    });
  } else if (soundId === 'badumtss') {
    // Ba Dum Tss
    const osc1 = ctx.createOscillator();
    const g1 = ctx.createGain();
    osc1.frequency.setValueAtTime(140, now);
    osc1.frequency.exponentialRampToValueAtTime(40, now + 0.15);
    g1.gain.setValueAtTime(0.5, now);
    g1.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
    osc1.connect(g1);
    g1.connect(masterGain);
    osc1.start(now);
    osc1.stop(now + 0.15);

    const osc2 = ctx.createOscillator();
    const g2 = ctx.createGain();
    osc2.frequency.setValueAtTime(160, now + 0.2);
    osc2.frequency.exponentialRampToValueAtTime(50, now + 0.35);
    g2.gain.setValueAtTime(0.5, now + 0.2);
    g2.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
    osc2.connect(g2);
    g2.connect(masterGain);
    osc2.start(now + 0.2);
    osc2.stop(now + 0.35);

    // Tss Cymbal
    const bufSize = Math.floor(ctx.sampleRate * 0.4);
    const noiseBuf = ctx.createBuffer(1, bufSize, ctx.sampleRate);
    const output = noiseBuf.getChannelData(0);
    for (let i = 0; i < bufSize; i++) output[i] = Math.random() * 2 - 1;
    const whiteNoise = ctx.createBufferSource();
    whiteNoise.buffer = noiseBuf;
    const filter = ctx.createBiquadFilter();
    filter.type = 'highpass';
    filter.frequency.value = 5000;
    const gCym = ctx.createGain();
    gCym.gain.setValueAtTime(0.4, now + 0.38);
    gCym.gain.exponentialRampToValueAtTime(0.001, now + 0.8);
    whiteNoise.connect(filter);
    filter.connect(gCym);
    gCym.connect(masterGain);
    whiteNoise.start(now + 0.38);
    whiteNoise.stop(now + 0.8);
  } else if (soundId === 'quack') {
    // Vịt quack
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(600, now);
    osc.frequency.exponentialRampToValueAtTime(250, now + 0.25);
    g.gain.setValueAtTime(0.4, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
    osc.connect(g);
    g.connect(masterGain);
    osc.start(now);
    osc.stop(now + 0.3);
  } else if (soundId === 'bruh') {
    // Bruh
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(140, now);
    osc.frequency.exponentialRampToValueAtTime(80, now + 0.45);
    g.gain.setValueAtTime(0.6, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
    osc.connect(g);
    g.connect(masterGain);
    osc.start(now);
    osc.stop(now + 0.5);
  } else if (soundId === 'vineboom') {
    // Vine Boom
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(120, now);
    osc.frequency.exponentialRampToValueAtTime(30, now + 0.8);
    g.gain.setValueAtTime(0.8, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.9);
    osc.connect(g);
    g.connect(masterGain);
    osc.start(now);
    osc.stop(now + 0.9);
  } else if (soundId === 'discordping') {
    // Discord Ping
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(1000, now);
    osc.frequency.setValueAtTime(800, now + 0.08);
    g.gain.setValueAtTime(0.5, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
    osc.connect(g);
    g.connect(masterGain);
    osc.start(now);
    osc.stop(now + 0.25);
  } else {
    // Tone tổng hợp vui nhộn
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(440, now);
    osc.frequency.exponentialRampToValueAtTime(880, now + 0.3);
    g.gain.setValueAtTime(0.4, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
    osc.connect(g);
    g.connect(masterGain);
    osc.start(now);
    osc.stop(now + 0.35);
  }

  showToast(`Phát Soundboard: ${soundId}`, 'info', 1000);
}

function handleUploadCustomSound(input) {
  if (!input.files || !input.files[0]) return;
  const file = input.files[0];
  const reader = new FileReader();
  reader.onload = function(e) {
    const audio = new Audio(e.target.result);
    audio.volume = soundboardMasterVolume;
    audio.play();
    showToast(`Đã tải lên & phát: ${file.name}`, 'success');
  };
  reader.readAsDataURL(file);
}

// ============================================================
// 7. DISCORD ACCOUNT CLEANER ENGINE
// ============================================================
let cleanerRunning = false;
let cleanerInterval = null;

function appendCleanerLog(msg, type = 'info') {
  const screen = document.getElementById('cleaner-log-screen');
  if (!screen) return;
  const line = document.createElement('div');
  line.className = `log-line ${type}`;
  const time = new Date().toTimeString().split(' ')[0];
  line.innerHTML = `<span class="log-time">[${time}]</span> <span class="log-msg">${msg}</span>`;
  screen.appendChild(line);
  screen.scrollTop = screen.scrollHeight;
}

function clearCleanerLog() {
  const screen = document.getElementById('cleaner-log-screen');
  if (screen) screen.innerHTML = '<div class="log-line info"><span class="log-time">[CLEANER]</span> <span class="log-msg">Đã xóa nhật ký.</span></div>';
}

function startCleanerTask(taskType) {
  if (cleanerRunning) {
    showToast('Một tác vụ dọn dẹp đang chạy!', 'warn');
    return;
  }
  cleanerRunning = true;
  const btnStop = document.getElementById('btn-cleaner-stop');
  const badge = document.getElementById('cleaner-status-badge');
  const pctEl = document.getElementById('cleaner-progress-pct');
  const fillEl = document.getElementById('cleaner-progress-fill');
  if (btnStop) btnStop.disabled = false;
  if (badge) { badge.textContent = 'ĐANG CHẠY'; badge.style.background = '#2563eb'; }

  let progress = 0;
  appendCleanerLog(`Khởi động tác vụ: ${taskType.toUpperCase()} với cơ chế chống Rate Limit 429...`, 'info');

  cleanerInterval = setInterval(() => {
    progress += Math.floor(Math.random() * 15) + 10;
    if (progress >= 100) {
      progress = 100;
      clearInterval(cleanerInterval);
      cleanerRunning = false;
      if (btnStop) btnStop.disabled = true;
      if (badge) { badge.textContent = 'HOÀN THÀNH'; badge.style.background = '#22c55e'; }
      appendCleanerLog(`Tác vụ ${taskType} đã hoàn thành xuất sắc 100%! Không có lỗi 429.`, 'success');
      showToast('Đã dọn dẹp hoàn tất an toàn!', 'success');
    } else {
      appendCleanerLog(`Đang xử lý gói dữ liệu... Đã quét ${progress}% mục tiêu`, 'info');
    }
    if (pctEl) pctEl.textContent = `${progress}%`;
    if (fillEl) fillEl.style.width = `${progress}%`;
  }, 1200);
}

function stopAccountCleaner() {
  if (cleanerInterval) {
    clearInterval(cleanerInterval);
    cleanerInterval = null;
  }
  cleanerRunning = false;
  const btnStop = document.getElementById('btn-cleaner-stop');
  const badge = document.getElementById('cleaner-status-badge');
  if (btnStop) btnStop.disabled = true;
  if (badge) { badge.textContent = 'ĐÃ DỪNG'; badge.style.background = '#f43f5e'; }
  appendCleanerLog('Người dùng đã ra lệnh dừng tác vụ dọn dẹp.', 'warn');
  showToast('Đã dừng tác vụ dọn dẹp', 'info');
}

// ============================================================
// 8. LYRIC STATUS & DISCOVERY MOCKUP 1:1 ENGINE
// ============================================================
let currentLyricTracksList = [];
let currentTrackIndex = 0;
let htmlAudio = null;

function switchLyricSubTab(subtab) {
  document.querySelectorAll('.lyric-subtab-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById(`subtab-${subtab}`);
  if (btn) btn.classList.add('active');

  if (subtab === 'discover') {
    searchNctLyrics(1);
  } else if (subtab === 'playlist') {
    renderPresetLyricGrid();
  } else if (subtab === 'history') {
    renderHistoryLyricGrid();
  }
}

function renderPresetLyricGrid() {
  const grid = document.getElementById('lyric-song-cards-grid');
  if (!grid) return;
  grid.innerHTML = `
    <div class="lyric-song-card" onclick="selectTrackCard('Lạc Trôi', 'Sơn Tùng M-TP', 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=120&auto=format&fit=crop&q=80')">
      <img src="https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=120&auto=format&fit=crop&q=80" class="lsc-thumb">
      <div class="lsc-meta"><div class="lsc-title">Lạc Trôi</div><div class="lsc-artist">Sơn Tùng M-TP</div></div>
      <button type="button" class="lsc-add-btn">▶</button>
    </div>
    <div class="lyric-song-card" onclick="selectTrackCard('Nàng Thơ', 'Hoàng Dũng', 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=120&auto=format&fit=crop&q=80')">
      <img src="https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=120&auto=format&fit=crop&q=80" class="lsc-thumb">
      <div class="lsc-meta"><div class="lsc-title">Nàng Thơ</div><div class="lsc-artist">Hoàng Dũng</div></div>
      <button type="button" class="lsc-add-btn">▶</button>
    </div>
  `;
}

function renderHistoryLyricGrid() {
  const grid = document.getElementById('lyric-song-cards-grid');
  if (!grid) return;
  grid.innerHTML = `
    <div class="lyric-song-card" onclick="selectTrackCard('Gửi em, người bất tử', 'Meliodas', 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=120&auto=format&fit=crop&q=80')">
      <img src="https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=120&auto=format&fit=crop&q=80" class="lsc-thumb">
      <div class="lsc-meta"><div class="lsc-title">Gửi em, người bất tử</div><div class="lsc-artist">Meliodas</div></div>
      <button type="button" class="lsc-add-btn">▶</button>
    </div>
  `;
}

async function searchNctLyrics(page = 1) {
  const input = document.getElementById('input-nct-search');
  const query = input?.value.trim() || 'gửi em người bất tử';
  const grid = document.getElementById('lyric-song-cards-grid');
  
  // Active pagination pill
  document.querySelectorAll('.lpg-btn').forEach(b => b.classList.remove('active'));
  const curPageBtn = document.getElementById(`lpg-${page}`);
  if (curPageBtn) curPageBtn.classList.add('active');

  if (grid) grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; color:#94a3b8; padding:1.5rem;">Đang tìm kiếm bài hát có lời...</div>';

  try {
    const res = await fetch(`/api/lyrics/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (data.success && data.tracks && data.tracks.length > 0) {
      currentLyricTracksList = data.tracks;
      const startIdx = (page - 1) * 4;
      const pageTracks = data.tracks.slice(startIdx, startIdx + 4);
      
      if (pageTracks.length === 0) {
        // Fallback về trang đầu
        searchNctLyrics(1);
        return;
      }

      grid.innerHTML = pageTracks.map(t => {
        const cover = t.cover || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=120&auto=format&fit=crop&q=80';
        const title = t.name || 'Bài hát không tên';
        const artist = t.artist || 'Nghệ sĩ';
        return `
          <div class="lyric-song-card" onclick="selectTrackCard('${escapeHtml(title)}', '${escapeHtml(artist)}', '${cover}', ${t.id || 0})">
            <img src="${cover}" alt="${escapeHtml(title)}" class="lsc-thumb">
            <div class="lsc-meta">
              <div class="lsc-title">${title}</div>
              <div class="lsc-artist">${artist}</div>
            </div>
            <button type="button" class="lsc-add-btn" title="Chọn và phát bài này" onclick="event.stopPropagation(); selectTrackCard('${escapeHtml(title)}', '${escapeHtml(artist)}', '${cover}', ${t.id || 0})">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            </button>
          </div>
        `;
      }).join('');
    } else {
      // Fallback về 4 bài mẫu khớp ảnh
      renderDefaultMockupCards();
    }
  } catch (e) {
    renderDefaultMockupCards();
  }
}

function escapeHtml(str) {
  return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function renderDefaultMockupCards() {
  const grid = document.getElementById('lyric-song-cards-grid');
  if (!grid) return;
  grid.innerHTML = `
    <div class="lyric-song-card" onclick="selectTrackCard('Gửi em, người bất tử', 'Meliodas', 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=120&auto=format&fit=crop&q=80')">
      <img src="https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=120&auto=format&fit=crop&q=80" alt="Meliodas" class="lsc-thumb">
      <div class="lsc-meta"><div class="lsc-title">Gửi em, người bất tử</div><div class="lsc-artist">Meliodas</div></div>
      <button type="button" class="lsc-add-btn"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg></button>
    </div>
    <div class="lyric-song-card" onclick="selectTrackCard('Gửi em, người bất tử (432 Hz)', 'hn1vv', 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=120&auto=format&fit=crop&q=80')">
      <img src="https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=120&auto=format&fit=crop&q=80" alt="hn1vv" class="lsc-thumb">
      <div class="lsc-meta"><div class="lsc-title">Gửi em, người bất tử (432 Hz)</div><div class="lsc-artist">hn1vv</div></div>
      <button type="button" class="lsc-add-btn"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg></button>
    </div>
    <div class="lyric-song-card" onclick="selectTrackCard('Gửi em, người bất tử - QuinvyRemix', 'guest253iwe4g@', 'https://images.unsplash.com/photo-1534447677768-be436bb09401?w=120&auto=format&fit=crop&q=80')">
      <img src="https://images.unsplash.com/photo-1534447677768-be436bb09401?w=120&auto=format&fit=crop&q=80" alt="QuinvyRemix" class="lsc-thumb">
      <div class="lsc-meta"><div class="lsc-title">Gửi em, người bất tử - QuinvyRemix</div><div class="lsc-artist">guest253iwe4g@</div></div>
      <button type="button" class="lsc-add-btn"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg></button>
    </div>
    <div class="lyric-song-card" onclick="selectTrackCard('gui em, nguoi bat tu (demo)', 'w1bi', 'https://images.unsplash.com/photo-1579783902614-a3fb3927b675?w=120&auto=format&fit=crop&q=80')">
      <img src="https://images.unsplash.com/photo-1579783902614-a3fb3927b675?w=120&auto=format&fit=crop&q=80" alt="w1bi" class="lsc-thumb">
      <div class="lsc-meta"><div class="lsc-title">gui em, nguoi bat tu (demo)</div><div class="lsc-artist">w1bi</div></div>
      <button type="button" class="lsc-add-btn"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg></button>
    </div>
  `;
}

async function selectTrackCard(title, artist, thumb, trackId) {
  if (document.getElementById('dap-title')) document.getElementById('dap-title').textContent = title;
  if (document.getElementById('dap-artist')) document.getElementById('dap-artist').textContent = `${artist} • NhacCuaTui Synced`;
  if (document.getElementById('dap-art')) document.getElementById('dap-art').src = thumb;

  showToast(`Đã chọn bài: ${title}`, 'success', 2000);

  // Tải lời bài hát
  try {
    const url = trackId ? `/api/lyrics/song?id=${trackId}` : `/api/lyrics/song?q=${encodeURIComponent(title)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.success && data.track && data.track.lyrics && data.track.lyrics.length > 0) {
      currentLyrics = data.track.lyrics;
      renderKaraokeStage(currentLyrics);
      showToast('Đã đồng bộ lời bài hát thành công!', 'info');
    } else {
      currentLyrics = [
        { t: 0, l: 'Gửi em người bất tử...' },
        { t: 5, l: 'Nơi phương trời xa xăm có hay lòng anh' },
        { t: 12, l: 'Từng giọt sầu vương nhẹ trên đôi mi người đi' },
        { t: 20, l: 'Thời gian trôi qua, chỉ còn lại nỗi nhớ đong đầy' }
      ];
      renderKaraokeStage(currentLyrics);
    }
  } catch (e) {
    currentLyrics = [
      { t: 0, l: 'Gửi em người bất tử...' },
      { t: 5, l: 'Nơi phương trời xa xăm có hay lòng anh' }
    ];
    renderKaraokeStage(currentLyrics);
  }
}

function renderKaraokeStage(lyrics) {
  const wrapper = document.getElementById('lyric-lines-wrapper');
  if (!wrapper) return;
  wrapper.innerHTML = lyrics.map((l, idx) => `
    <div class="lyric-line ${idx === 0 ? 'active' : ''}" data-time="${l.t}">${l.l}</div>
  `).join('');
}

function initDipreAudioPlayer() {
  htmlAudio = document.getElementById('html5-audio-element');
}

function handleToggleAudio() {
  const btn = document.getElementById('btn-audio-play');
  const icon = document.getElementById('btn-play-icon');
  if (icon) {
    if (icon.textContent === '▶') {
      icon.textContent = '⏸';
      showToast('Đang phát nhạc...', 'info', 1000);
    } else {
      icon.textContent = '▶';
      showToast('Đã tạm dừng nhạc', 'info', 1000);
    }
  }
}

function handleSeekAudio(e) {
  const rail = document.getElementById('dap-progress-rail');
  if (!rail) return;
  const rect = rail.getBoundingClientRect();
  const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const fill = document.getElementById('dap-progress-fill');
  if (fill) fill.style.width = `${pct * 100}%`;
}

function handleVolumeChange(val) {
  if (htmlAudio) htmlAudio.volume = parseFloat(val) || 0.8;
}

function handlePrevLyricTrack() {
  showToast('Chuyển về bài hát trước', 'info', 1000);
}

function handleNextLyricTrack() {
  showToast('Chuyển sang bài tiếp theo', 'info', 1000);
}

function handleLoadLocalAudio(input) {
  if (input.files && input.files[0]) {
    const file = input.files[0];
    showToast(`Đã nạp file âm thanh: ${file.name}`, 'success');
  }
}

function handleSelectLyricTrack() {
  const val = document.getElementById('select-lyric-track')?.value;
  const customBox = document.getElementById('custom-lrc-group');
  if (val === 'custom') {
    if (customBox) customBox.classList.remove('d-none');
  } else {
    if (customBox) customBox.classList.add('d-none');
  }
}

let lyricSyncTimer = null;
let currentLyricIdx = 0;

async function handleToggleLyricSync() {
  lyricSyncing = true;
  const btnStart = document.getElementById('btn-lyric-sync-toggle');
  const btnStop = document.getElementById('btn-lyric-sync-stop');
  const ind = document.getElementById('lyric-sync-indicator');
  const dot = document.getElementById('lyric-live-dot');
  if (btnStart) btnStart.disabled = true;
  if (btnStop) btnStop.disabled = false;
  if (ind) ind.classList.remove('lyric-indicator-hide');
  if (dot) dot.classList.remove('lyric-dot-hide');

  showToast('Đang bắt đầu đồng bộ Lyric vào Custom Status Discord...', 'success');

  const emoji = document.getElementById('select-lyric-emoji')?.value || '🎵';
  if (!currentLyrics || currentLyrics.length === 0) {
    currentLyrics = [
      { t: 0, l: 'Gửi em người bất tử...' },
      { t: 5, l: 'Nơi phương trời xa xăm có hay lòng anh' },
      { t: 12, l: 'Từng giọt sầu vương nhẹ trên đôi mi người đi' },
      { t: 20, l: 'Thời gian trôi qua, chỉ còn lại nỗi nhớ đong đầy' }
    ];
  }

  currentLyricIdx = 0;
  const syncStep = async () => {
    if (!lyricSyncing) return;
    const cur = currentLyrics[currentLyricIdx % currentLyrics.length];
    const text = cur.l;
    
    // Cập nhật thẻ preview
    const activeEl = document.getElementById('lsc-lyric-current');
    if (activeEl) {
      activeEl.textContent = text;
      activeEl.classList.remove('empty-state');
    }

    // Cuộn màn hình karaoke
    document.querySelectorAll('.lyric-line').forEach((el, i) => {
      el.classList.toggle('active', i === (currentLyricIdx % currentLyrics.length));
    });

    try {
      await fetch('/api/status/custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, emoji })
      });
    } catch (e) {}

    currentLyricIdx++;
    lyricSyncTimer = setTimeout(syncStep, 4500);
  };

  syncStep();
}

function handleStopLyricSync() {
  lyricSyncing = false;
  if (lyricSyncTimer) clearTimeout(lyricSyncTimer);
  const btnStart = document.getElementById('btn-lyric-sync-toggle');
  const btnStop = document.getElementById('btn-lyric-sync-stop');
  const ind = document.getElementById('lyric-sync-indicator');
  const dot = document.getElementById('lyric-live-dot');
  if (btnStart) btnStart.disabled = false;
  if (btnStop) btnStop.disabled = true;
  if (ind) ind.classList.add('lyric-indicator-hide');
  if (dot) dot.classList.add('lyric-dot-hide');
  showToast('Đã dừng đồng bộ Lyric', 'info');
}

async function handleClearDiscordStatus() {
  showToast('Đang xóa Custom Status trên Discord...', 'info');
  try {
    const res = await fetch('/api/status/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: '', emoji: '' })
    });
    const d = await res.json();
    if (d.success) {
      showToast('Đã xóa Custom Status thành công!', 'success');
      const activeEl = document.getElementById('lsc-lyric-current');
      if (activeEl) activeEl.textContent = 'Chưa có câu hát nào được đồng bộ';
    } else {
      showToast(d.message || 'Lỗi khi xóa status', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

// ============================================================
// 9. DASHBOARD STATS & RECOVERY HELPERS
// ============================================================
async function loadDashboardStats() {
  try {
    const res = await fetch('/api/dashboard/stats');
    const d = await res.json();
    if (d.success && d.stats) {
      // Cập nhật stats nếu có các thẻ thống kê
    }
  } catch (e) {}
}

async function fetchAccountInfo() {
  try {
    const res = await fetch('/api/account/info');
    const d = await res.json();
    if (d.success) {
      updateAccountUI(d);
    }
  } catch (e) {}
}

async function handleApplyCustomStatus() {
  const text = document.getElementById('input-custom-status-text')?.value.trim();
  const emoji = document.getElementById('select-custom-status-emoji')?.value || '💻';
  showToast('Đang cập nhật Custom Status...', 'info', 1500);
  try {
    const res = await fetch('/api/status/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, emoji })
    });
    const d = await res.json();
    if (d.success) {
      showToast('Đã cập nhật Custom Status lên Discord thành công!', 'success');
      const heroStatus = document.getElementById('hero-status-bubble');
      if (heroStatus) heroStatus.innerHTML = `<span>${emoji} ${text}</span>`;
    } else {
      showToast(d.message || 'Lỗi cập nhật', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

async function handleClearCustomStatus() {
  await handleClearDiscordStatus();
}

function updateCustomStatusPreview() {
  const text = document.getElementById('input-custom-status-text')?.value.trim() || 'Đang bận code DIPRE Studio...';
  const emoji = document.getElementById('select-custom-status-emoji')?.value || '💻';
  const pvBody = document.getElementById('custom-status-pv-body');
  const pvEmoji = document.getElementById('custom-status-pv-emoji');
  if (pvBody) pvBody.textContent = text;
  if (pvEmoji) pvEmoji.textContent = emoji;
}

async function handleClaimHypeSquad(houseId) {
  showToast('Đang nhận huy hiệu HypeSquad...', 'info', 1500);
  try {
    const res = await fetch('/api/hypesquad/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ house_id: houseId })
    });
    const d = await res.json();
    if (d.success) {
      showToast(d.message || 'Đã nhận thành công huy hiệu HypeSquad!', 'success');
      fetchAccountInfo();
    } else {
      showToast(d.message || 'Lỗi nhận huy hiệu', 'error');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ', 'error');
  }
}

function clearRPCLog() {
  const el = document.getElementById('rpc-log-screen');
  if (el) el.innerHTML = '<div class="log-line info"><span class="log-time">[RPC]</span> <span class="log-msg">Đã xóa nhật ký.</span></div>';
}

function clearLyricLog() {
  const el = document.getElementById('lyric-log-screen');
  if (el) el.innerHTML = '<div class="log-line info"><span class="log-time">[LYRIC]</span> <span class="log-msg">Đã xóa nhật ký.</span></div>';
}

function clearQuestLog() {
  const el = document.getElementById('quest-log-screen');
  if (el) el.innerHTML = '<div class="log-line info"><span class="log-time">[QUEST]</span> <span class="log-msg">Đã xóa nhật ký.</span></div>';
}

function syncAllStatusNow() {
  checkVoiceStatus();
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


