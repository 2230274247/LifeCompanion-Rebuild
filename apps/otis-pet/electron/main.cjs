// Otis — a frameless, transparent, always-on-top Electron window that hosts
// the portfolio's stretchable face as a desktop pet. The original page is
// still available from the tray as a normal window.

const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  nativeImage,
  screen,
  ipcMain,
} = require('electron');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const PET_WIDTH = 380;
const PET_HEIGHT = 420;
const MARGIN = 28;
const DIST = path.join(__dirname, '..', 'dist');

let petWin = null;
let fullWin = null;
let tray = null;
let menu = null;
let quitting = false;
let server = null;
let baseUrl = '';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webp': 'image/webp',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};

app.setAppUserModelId('com.lifecompanion.otis');

// The Otis page loads faces from absolute `/faces/...` paths, so a file://
// window would miss them. A loopback static server keeps the original source
// untouched (no base-path rewrite) and stays inside dist/.
function startServer() {
  return new Promise((resolve, reject) => {
    server = http.createServer((req, res) => {
      const raw = decodeURIComponent((req.url || '/').split('?')[0]);
      const relative = raw === '/' ? 'index.html' : raw.replace(/^\/+/, '');
      const file = path.resolve(DIST, relative);
      const root = path.resolve(DIST);
      if (file !== root && !file.startsWith(root + path.sep)) {
        res.writeHead(403).end();
        return;
      }
      fs.readFile(file, (err, data) => {
        if (err) {
          res.writeHead(404).end();
          return;
        }
        res.writeHead(200, {
          'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
          'Cache-Control': 'no-store',
        });
        res.end(data);
      });
    });
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      baseUrl = `http://127.0.0.1:${server.address().port}`;
      resolve();
    });
  });
}

function stateFile() {
  return path.join(app.getPath('userData'), 'otis-pet.json');
}

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(stateFile(), 'utf8'));
  } catch {
    return {};
  }
}

function saveState(patch) {
  try {
    fs.mkdirSync(path.dirname(stateFile()), { recursive: true });
    fs.writeFileSync(stateFile(), JSON.stringify({ ...loadState(), ...patch }, null, 2));
  } catch {
    /* position is a nicety; never let it keep the pet from running */
  }
}

function bottomRight() {
  const { workArea } = screen.getPrimaryDisplay();
  return {
    x: workArea.x + workArea.width - PET_WIDTH - MARGIN,
    y: workArea.y + workArea.height - PET_HEIGHT - MARGIN,
  };
}

function onScreen(x, y) {
  return screen.getAllDisplays().some(({ workArea }) => {
    return (
      x + PET_WIDTH > workArea.x &&
      x < workArea.x + workArea.width &&
      y + PET_HEIGHT > workArea.y &&
      y < workArea.y + workArea.height
    );
  });
}

function initialPosition() {
  const saved = loadState();
  if (Number.isFinite(saved.x) && Number.isFinite(saved.y) && onScreen(saved.x, saved.y)) {
    return { x: saved.x, y: saved.y };
  }
  return bottomRight();
}

function createPetWindow() {
  const position = initialPosition();

  petWin = new BrowserWindow({
    width: PET_WIDTH,
    height: PET_HEIGHT,
    x: position.x,
    y: position.y,
    show: false,
    title: 'Otis',
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    resizable: false,
    maximizable: false,
    minimizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    roundedCorners: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
      spellcheck: false,
    },
  });

  petWin.setAlwaysOnTop(true, 'floating');
  petWin.loadURL(`${baseUrl}/pet.html`);
  petWin.once('ready-to-show', () => petWin.showInactive());

  let moveTimer = 0;
  petWin.on('moved', () => {
    clearTimeout(moveTimer);
    moveTimer = setTimeout(() => saveState(petWin.getBounds()), 400);
  });

  petWin.on('close', (event) => {
    if (!quitting) {
      event.preventDefault();
      petWin.hide();
    }
  });
}

function showFullPage() {
  if (fullWin && !fullWin.isDestroyed()) {
    fullWin.show();
    fullWin.focus();
    return;
  }
  fullWin = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 900,
    minHeight: 640,
    title: 'Otis Pell — character designer',
    backgroundColor: '#e8ebf1',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });
  fullWin.loadURL(`${baseUrl}/index.html`);
  fullWin.on('closed', () => {
    fullWin = null;
  });
}

function toggleVisible() {
  if (!petWin) return;
  if (petWin.isVisible()) petWin.hide();
  else petWin.showInactive();
}

function resetPosition() {
  if (!petWin) return;
  const { x, y } = bottomRight();
  petWin.setPosition(x, y);
  saveState({ x, y });
}

function buildTray() {
  const iconPath = path.join(__dirname, 'tray.png');
  const icon = nativeImage.createFromPath(iconPath);
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setToolTip('Otis · 桌面小宠物');

  menu = Menu.buildFromTemplate([
    { label: '显示 / 隐藏宠物', click: toggleVisible },
    { label: '打开完整页面', click: showFullPage },
    { type: 'separator' },
    {
      label: '总在最前',
      type: 'checkbox',
      checked: true,
      click: (item) => petWin && petWin.setAlwaysOnTop(item.checked, 'floating'),
    },
    {
      label: '鼠标穿透（只能在托盘关闭）',
      type: 'checkbox',
      checked: false,
      click: (item) => {
        if (!petWin) return;
        petWin.setIgnoreMouseEvents(item.checked, { forward: true });
      },
    },
    { label: '回到右下角', click: resetPosition },
    { type: 'separator' },
    { label: '重新载入宠物', click: () => petWin && petWin.reload() },
    { label: '退出', click: () => app.quit() },
  ]);

  tray.setContextMenu(menu);
  tray.on('click', toggleVisible);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (petWin) {
      petWin.showInactive();
      petWin.setAlwaysOnTop(true, 'floating');
    }
  });

  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null);
    await startServer();
    createPetWindow();
    buildTray();

    // Right-click on the pet opens the same menu as the tray.
    ipcMain.on('pet:menu', () => {
      if (petWin && menu) menu.popup({ window: petWin });
    });

    screen.on('display-metrics-changed', () => {
      if (!petWin || !petWin.isVisible()) return;
      const bounds = petWin.getBounds();
      if (!onScreen(bounds.x, bounds.y)) resetPosition();
    });
  });
}

app.on('before-quit', () => {
  quitting = true;
});

app.on('window-all-closed', () => {});

app.on('will-quit', () => {
  if (server) server.close();
});
