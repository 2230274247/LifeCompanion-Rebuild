const statusNodes = document.querySelectorAll("[data-service]");
const statusLabel = document.querySelector("[data-service-label='librechat']");

if (new URLSearchParams(window.location.search).has("capture")) {
  document.documentElement.classList.add("capture-mode");
}

function applyStatus(service) {
  const label = service.ok ? "运行中" : "未连接";
  statusNodes.forEach((node) => {
    if (node.dataset.service !== service.id) {
      return;
    }
    node.classList.toggle("is-down", !service.ok);
    if (node.textContent.trim() === "检查中" || node.classList.contains("service-pill")) {
      node.textContent = label;
    }
  });
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/services/status", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`status ${response.status}`);
    }
    const payload = await response.json();
    payload.services.forEach(applyStatus);
    const online = payload.services.filter((service) => service.ok).length;
    if (statusLabel) {
      statusLabel.textContent = `${online} / ${payload.services.length} 个本地服务在线`;
    }
  } catch {
    if (statusLabel) {
      statusLabel.textContent = "服务状态暂不可用";
    }
    document.querySelectorAll(".status-light").forEach((node) => node.classList.add("is-down"));
  }
}

refreshStatus();
