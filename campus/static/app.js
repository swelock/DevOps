"use strict";
const configs = {
  buildings: {title: "Корпуса", singular: "корпус", fields: [
    ["name", "Название", "text", 100], ["address", "Адрес", "text", 250]
  ]},
  departments: {title: "Подразделения", singular: "подразделение", fields: [
    ["name", "Название", "text", 100]
  ]},
  rooms: {title: "Помещения", singular: "помещение", fields: [
    ["building_id", "Корпус", "buildings"], ["department_id", "Подразделение", "departments"],
    ["number", "Номер", "text", 30], ["area", "Площадь, м²", "number", 100000],
    ["height", "Высота, м", "number", 100]
  ]}
};
let resource = "rooms";
let editing = null;
let data = {};
let busy = false;
const el = id => document.getElementById(id);
const numeric = new Intl.NumberFormat("ru-RU", {maximumFractionDigits: 2});
function message(text, error = false) {
  el("message").textContent = text;
  el("message").className = error ? "error" : "success";
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 204) return null;
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Не удалось выполнить запрос.");
  return body;
}
function button(text, action, className = "secondary") {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = text;
  node.className = className;
  node.onclick = action;
  return node;
}
function form(record = null) {
  editing = record ? record.id : null;
  el("form-title").textContent = `${record ? "Изменить" : "Добавить"} ${configs[resource].singular}`;
  el("fields").replaceChildren();
  const needsParents = resource === "rooms" && (!data.buildings.length || !data.departments.length);
  el("hint").textContent = needsParents ? "Сначала добавьте корпус и подразделение во вкладках выше." : "Все поля обязательны.";
  el("save").disabled = needsParents || busy;
  el("cancel").hidden = !record;
  for (const [name, title, type, limit] of configs[resource].fields) {
    const label = document.createElement("label");
    label.textContent = title;
    const input = document.createElement(configs[type] ? "select" : "input");
    input.name = name;
    input.required = true;
    if (configs[type]) {
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Выберите…";
      input.append(placeholder);
      for (const parent of data[type]) {
        const option = document.createElement("option");
        option.value = parent.id;
        option.textContent = parent.name;
        input.append(option);
      }
    } else {
      input.type = type;
      if (type === "number") {
        input.min = "0.000001";
        input.step = "any";
        input.max = limit;
      } else input.maxLength = limit;
    }
    if (record) input.value = record[name];
    label.append(input);
    el("fields").append(label);
  }
}
function render() {
  const config = configs[resource];
  document.querySelectorAll("nav button").forEach(node => {
    node.setAttribute("aria-pressed", String(node.dataset.resource === resource));
  });
  el("list-title").textContent = config.title;
  el("count").textContent = `Записей: ${data[resource].length}`;
  el("head").replaceChildren();
  const header = document.createElement("tr");
  const titles = ["ID", ...config.fields.map(f => f[1])];
  if (resource === "rooms") titles.push("Объём, м³");
  titles.push("Действия");
  for (const title of titles) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = title;
    header.append(th);
  }
  el("head").append(header);
  el("rows").replaceChildren();
  el("empty").hidden = data[resource].length > 0;
  for (const record of data[resource]) {
    const tr = document.createElement("tr");
    const values = [record.id, ...config.fields.map(([name, _title, type]) => {
      if (configs[type]) return data[type].find(item => item.id === record[name])?.name || "—";
      return type === "number" ? numeric.format(record[name]) : record[name];
    })];
    if (resource === "rooms") values.push(numeric.format(record.volume));
    for (const value of values) {
      const td = document.createElement("td");
      td.textContent = value; // Не вставляем пользовательские строки как HTML.
      tr.append(td);
    }
    const actions = document.createElement("td");
    actions.className = "actions";
    actions.append(button("Изменить", () => {
      if (busy) return;
      form(record);
      el("fields").querySelector("input, select").focus();
    }), button("Удалить", async () => {
      if (busy || !window.confirm(`Удалить запись №${record.id}?`)) return;
      await mutate(`/api/${resource}/${record.id}`, {method: "DELETE"}, "Запись удалена.");
    }, "danger"));
    tr.append(actions);
    el("rows").append(tr);
  }
  form();
}
async function load() {
  const entries = await Promise.all(Object.keys(configs).map(async key => [key, await api(`/api/${key}`)]));
  data = Object.fromEntries(entries);
  render();
}
async function mutate(path, options, success) {
  busy = true;
  el("save").disabled = true;
  try {
    await api(path, options);
    // Запись уже сохранена, даже если последующее обновление списка не удалось.
    form();
    await load();
    message(success);
  } catch (error) {
    message(error.message, true);
  } finally {
    busy = false;
    el("save").disabled = resource === "rooms" && (!data.buildings.length || !data.departments.length);
  }
}
el("editor").onsubmit = async event => {
  event.preventDefault();
  if (busy) return;
  const fields = new FormData(event.target);
  const payload = {};
  for (const [name, _title, type] of configs[resource].fields) {
    payload[name] = type === "text" ? fields.get(name).trim() : Number(fields.get(name));
  }
  await mutate(`/api/${resource}${editing === null ? "" : `/${editing}`}`, {
    method: editing === null ? "POST" : "PUT",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
  }, "Запись сохранена.");
};
el("cancel").onclick = () => {if (!busy) form();};
document.querySelectorAll("nav button").forEach(node => {
  node.onclick = () => {
    if (busy || !data.rooms) return;
    resource = node.dataset.resource;
    message("");
    render();
  };
});
load().catch(error => message(`Не удалось загрузить данные: ${error.message}. Обновите страницу.`, true));
