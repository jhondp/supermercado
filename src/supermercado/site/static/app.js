document.addEventListener("DOMContentLoaded", () => {
  const pills = document.querySelectorAll("[data-filter]");
  pills.forEach((pill) => {
    pill.addEventListener("click", () => {
      const value = pill.dataset.filter;
      pills.forEach((other) => other.classList.toggle("is-active", other === pill));
      document.querySelectorAll("tr[data-category]").forEach((row) => {
        row.hidden = value !== "all" && row.dataset.category !== value;
      });
    });
  });

  const dataEl = document.getElementById("chart-data");
  const canvas = document.getElementById("price-chart");
  if (!dataEl || !canvas || typeof Chart === "undefined") return;
  const data = JSON.parse(dataEl.textContent);
  const palette = ["#003F91", "#5DA9E9", "#6D326D", "#2E8B57", "#E07A5F", "#3D405B"];
  const clp = (value) => "$" + Number(value).toLocaleString("es-CL");
  const datasets = data.series.map((series, index) => {
    const byWeek = Object.fromEntries(series.points.map((point) => [point.week, point]));
    const changed = (week) => Boolean(byWeek[week] && byWeek[week].sku_changed);
    const color = palette[index % palette.length];
    return {
      label: series.label,
      data: data.weeks.map((week) => (byWeek[week] ? byWeek[week].unit_price : null)),
      pointStyle: data.weeks.map((week) => (changed(week) ? "triangle" : "circle")),
      pointRadius: data.weeks.map((week) => (changed(week) ? 7 : 3)),
      borderColor: color,
      backgroundColor: color,
      spanGaps: false,
      tension: 0.2,
    };
  });
  new Chart(canvas, {
    type: "line",
    data: { labels: data.weeks, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${clp(ctx.parsed.y)}` } },
      },
      scales: { y: { ticks: { callback: (value) => clp(value) } } },
    },
  });
});
