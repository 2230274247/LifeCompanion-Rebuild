// The only bridge into the pet page: ask the main process to pop the tray menu
// where the cursor is. Nothing else about Node is exposed.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pet', {
  showMenu: () => ipcRenderer.send('pet:menu'),
});
