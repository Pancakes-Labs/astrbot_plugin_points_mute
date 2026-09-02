// AstrBot Dashboard 前端业务逻辑

const bridge = window.AstrBotPluginPage;

// 全局状态
let currentPage = 1;
let totalPages = 1;
let currentCurrency = "喵币";
let activeUserModalData = null;

// 初始化
document.addEventListener("DOMContentLoaded", async () => {
  try {
    if (bridge && typeof bridge.ready === "function") {
      await bridge.ready();
    }
  } catch (e) {
    console.warn("Bridge ready fallback:", e);
  }

  initTabs();
  initEventListeners();
  await loadStats();
  await loadGroups();
  await loadUsers();
  await loadConfig();
});

// Toast 提示
function showToast(message, duration = 3000) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => {
    toast.classList.add("hidden");
  }, duration);
}

// 选项卡切换
function initTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");
    });
  });
}

// 事件监听
function initEventListeners() {
  // 刷新按钮
  document.getElementById("btn-refresh").addEventListener("click", async () => {
    await loadStats();
    await loadUsers();
    showToast("数据已刷新喵~");
  });

  // 搜索与筛选
  document.getElementById("btn-search").addEventListener("click", () => {
    currentPage = 1;
    loadUsers();
  });
  document.getElementById("input-search").addEventListener("keyup", (e) => {
    if (e.key === "Enter") {
      currentPage = 1;
      loadUsers();
    }
  });
  document.getElementById("select-group").addEventListener("change", () => {
    currentPage = 1;
    loadUsers();
  });
  document.getElementById("select-sort").addEventListener("change", () => {
    currentPage = 1;
    loadUsers();
  });

  // 分页
  document.getElementById("btn-prev-page").addEventListener("click", () => {
    if (currentPage > 1) {
      currentPage--;
      loadUsers();
    }
  });
  document.getElementById("btn-next-page").addEventListener("click", () => {
    if (currentPage < totalPages) {
      currentPage++;
      loadUsers();
    }
  });

  // 配置保存表单
  document.getElementById("btn-save-config").addEventListener("click", async (e) => {
    e.preventDefault();
    await saveConfig();
  });

  // 弹窗关闭与提交
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  document.getElementById("modal-action").addEventListener("change", (e) => {
    const action = e.target.value;
    const valGroup = document.getElementById("modal-value-group");
    const valLabel = document.getElementById("modal-value-label");
    if (action === "reset_checkin") {
      valGroup.style.display = "none";
    } else {
      valGroup.style.display = "flex";
      if (action.includes("points")) valLabel.textContent = `积分数量 (${currentCurrency})`;
      else if (action.includes("shields")) valLabel.textContent = "护盾数量 (张)";
      else if (action.includes("streak")) valLabel.textContent = "连续签到天数 (天)";
    }
  });

  document.getElementById("modal-submit").addEventListener("click", async () => {
    await submitUserModify();
  });
}

// 1. 加载大盘统计
async function loadStats() {
  try {
    const data = await bridge.apiGet("stats");
    if (!data) return;

    currentCurrency = data.currency_name || "喵币";
    document.getElementById("stat-total-users").textContent = (data.total_unique_users || 0).toLocaleString();
    document.getElementById("stat-points-pool").textContent = `${(data.total_points_pool || 0).toLocaleString()} ${currentCurrency}`;
    document.getElementById("stat-today-checkins").textContent = (data.today_checkins || 0).toLocaleString();
    document.getElementById("stat-today-mutes").textContent = (data.today_mutes || 0).toLocaleString();
    document.getElementById("stat-shields-pool").textContent = `${(data.total_shields_pool || 0).toLocaleString()} 张`;

    const badgeMode = document.getElementById("badge-mode");
    if (data.isolation_mode === "group_isolated") {
      badgeMode.textContent = "🛡️ 群隔离模式";
      badgeMode.className = "badge badge-primary";
    } else {
      badgeMode.textContent = "🌐 全局共享模式";
      badgeMode.className = "badge";
      badgeMode.style.background = "#fef3c7";
      badgeMode.style.color = "#d97706";
    }
  } catch (err) {
    console.error("加载统计失败:", err);
  }
}

// 2. 加载群组列表
async function loadGroups() {
  try {
    const res = await bridge.apiGet("groups");
    const select = document.getElementById("select-group");
    select.innerHTML = '<option value="">全部群组 / 全局</option>';

    if (res && res.groups) {
      res.groups.forEach((gid) => {
        const opt = document.createElement("option");
        opt.value = gid;
        opt.textContent = `群聊: ${gid}`;
        select.appendChild(opt);
      });
    }
  } catch (err) {
    console.error("加载群组失败:", err);
  }
}

// 3. 加载用户列表
async function loadUsers() {
  const tbody = document.getElementById("user-tbody");
  tbody.innerHTML = '<tr><td colspan="9" class="loading-cell">正在查询用户数据...</td></tr>';

  const search = document.getElementById("input-search").value.trim();
  const groupId = document.getElementById("select-group").value;
  const [sortBy, sortOrder] = document.getElementById("select-sort").value.split(":");

  try {
    const res = await bridge.apiGet("users", {
      search,
      group_id: groupId,
      sort_by: sortBy,
      sort_order: sortOrder,
      page: currentPage,
      page_size: 15,
    });

    if (!res || !res.items || res.items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="loading-cell">暂无匹配的用户记录喵~</td></tr>';
      updatePagination(0, 1, 1);
      return;
    }

    totalPages = res.total_pages || 1;
    updatePagination(res.total, res.page, totalPages);

    tbody.innerHTML = "";
    res.items.forEach((u) => {
      const tr = document.createElement("tr");

      const groupLabel = u.group_id === "_global_" ? "🌐 全局" : `群 ${u.group_id}`;
      const name = u.nickname || `用户_${u.user_id.slice(-4)}`;
      const luckBadge = u.today_luck ? `【${u.today_luck}】` : '<span style="color:var(--text-muted)">未签到</span>';
      const updatedTime = u.updated_at ? new Date(u.updated_at * 1000).toLocaleString() : "-";

      tr.innerHTML = `
        <td><span class="badge" style="background:var(--bg-subtle)">${groupLabel}</span></td>
        <td>
          <div class="user-cell">
            <div class="user-avatar">${name.slice(0, 1)}</div>
            <div>
              <div style="font-weight:600">${name}</div>
              <div style="font-size:12px;color:var(--text-muted)">QQ: ${u.user_id}</div>
            </div>
          </div>
        </td>
        <td><strong style="color:var(--primary)">${u.points.toLocaleString()}</strong> ${currentCurrency}</td>
        <td>🛡️ ${u.shields} 张</td>
        <td>🔥 ${u.continuous_checkin_days} 天 / 📊 ${u.total_checkin_count} 天</td>
        <td>${luckBadge}</td>
        <td><span style="color:var(--success)">+${u.total_points_earned}</span> / <span style="color:var(--danger)">-${u.total_points_spent}</span></td>
        <td style="font-size:12px;color:var(--text-muted)">${updatedTime}</td>
        <td>
          <button class="btn btn-sm btn-secondary btn-action" data-user='${JSON.stringify(u)}'>⚙️ 管理</button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    // 绑定管理按钮点击
    document.querySelectorAll(".btn-action").forEach((btn) => {
      btn.addEventListener("click", () => {
        const udata = JSON.parse(btn.getAttribute("data-user"));
        openModal(udata);
      });
    });
  } catch (err) {
    console.error("加载用户失败:", err);
    tbody.innerHTML = `<tr><td colspan="9" class="loading-cell text-danger">加载失败: ${err.message || err}</td></tr>`;
  }
}

// 分页更新
function updatePagination(total, page, pages) {
  document.getElementById("page-info").textContent = `第 ${page} / ${pages} 页 (共 ${total} 条数据)`;
  document.getElementById("btn-prev-page").disabled = page <= 1;
  document.getElementById("btn-next-page").disabled = page >= pages;
}

// 4. 打开管理弹窗
function openModal(userData) {
  activeUserModalData = userData;
  const modal = document.getElementById("modal-modify");
  const name = userData.nickname || `用户_${userData.user_id.slice(-4)}`;
  document.getElementById("modal-user-desc").textContent = `目标：${name} (QQ: ${userData.user_id}) | 所属：${userData.group_id === "_global_" ? "全局" : `群 ${userData.group_id}`} | 当前积分：${userData.points} ${currentCurrency}`;
  document.getElementById("modal-value").value = "100";
  document.getElementById("modal-action").value = "add_points";
  document.getElementById("modal-value-group").style.display = "flex";
  document.getElementById("modal-value-label").textContent = `积分数量 (${currentCurrency})`;
  modal.classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal-modify").classList.add("hidden");
  activeUserModalData = null;
}

// 提交用户状态修改
async function submitUserModify() {
  if (!activeUserModalData) return;

  const action = document.getElementById("modal-action").value;
  const val = parseInt(document.getElementById("modal-value").value, 10) || 0;

  try {
    const res = await bridge.apiPost("user/modify", {
      group_id: activeUserModalData.group_id,
      user_id: activeUserModalData.user_id,
      action,
      value: val,
    });

    showToast("操作执行成功喵~");
    closeModal();
    await loadStats();
    await loadUsers();
  } catch (err) {
    alert(`操作失败: ${err.message || err}`);
  }
}

// 5. 加载配置
async function loadConfig() {
  try {
    const cfg = await bridge.apiGet("config");
    if (!cfg) return;

    document.getElementById("cfg-isolation").value = cfg.points_isolation_mode || "group_isolated";
    document.getElementById("cfg-curr-name").value = cfg.currency_name || "喵币";
    document.getElementById("cfg-init-pts").value = cfg.initial_points || 0;
    document.getElementById("cfg-min-pts").value = cfg.checkin_min_points || 10;
    document.getElementById("cfg-max-pts").value = cfg.checkin_max_points || 50;
    document.getElementById("cfg-streak-bonus").value = cfg.checkin_streak_bonus_per_day || 3;
    document.getElementById("cfg-mute-cost").value = cfg.mute_cost_per_minute || 5;
    document.getElementById("cfg-mute-default").value = cfg.mute_default_duration || 60;
    document.getElementById("cfg-shield-price").value = cfg.shield_price || 80;
    document.getElementById("cfg-shield-max").value = cfg.shield_max_hold || 3;
    document.getElementById("cfg-daily-mute").value = cfg.daily_user_mute_limit || 5;
    document.getElementById("cfg-daily-muted").value = cfg.daily_user_muted_limit || 5;
  } catch (err) {
    console.error("加载配置失败:", err);
  }
}

// 保存配置
async function saveConfig() {
  const payload = {
    points_isolation_mode: document.getElementById("cfg-isolation").value,
    currency_name: document.getElementById("cfg-curr-name").value.trim(),
    initial_points: parseInt(document.getElementById("cfg-init-pts").value, 10) || 0,
    checkin_min_points: parseInt(document.getElementById("cfg-min-pts").value, 10) || 10,
    checkin_max_points: parseInt(document.getElementById("cfg-max-pts").value, 10) || 50,
    checkin_streak_bonus_per_day: parseInt(document.getElementById("cfg-streak-bonus").value, 10) || 3,
    mute_cost_per_minute: parseInt(document.getElementById("cfg-mute-cost").value, 10) || 5,
    mute_default_duration: parseInt(document.getElementById("cfg-mute-default").value, 10) || 60,
    shield_price: parseInt(document.getElementById("cfg-shield-price").value, 10) || 80,
    shield_max_hold: parseInt(document.getElementById("cfg-shield-max").value, 10) || 3,
    daily_user_mute_limit: parseInt(document.getElementById("cfg-daily-mute").value, 10) || 5,
    daily_user_muted_limit: parseInt(document.getElementById("cfg-daily-muted").value, 10) || 5,
  };

  try {
    await bridge.apiPost("config/save", payload);
    showToast("🎉 配置已成功保存并实时生效喵~");
    await loadStats();
    await loadUsers();
  } catch (err) {
    alert(`保存配置失败: ${err.message || err}`);
  }
}
