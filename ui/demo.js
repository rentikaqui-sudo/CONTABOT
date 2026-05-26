/* ContaBot — Estudio Contable Aristizábal — Lógica multi-empresa */

const COP  = v => '$' + Math.round(v).toLocaleString('es-CO');
const MCOP = v => (v / 1_000_000).toFixed(2) + 'M';
const sleep = ms => new Promise(r => setTimeout(r, ms));

// Redirige al login si la sesión expira (401)
const _origFetch = window.fetch;
window.fetch = async (...args) => {
  const res = await _origFetch(...args);
  if (res.status === 401) { window.location.href = '/login'; }
  return res;
};

let empresasData   = [];
let empresaActual  = null;

const CATS = {
  insumos:'Insumos', transporte:'Transporte', servicios:'Servicios',
  telecomunicaciones:'Telecom', seguros:'Seguros', arrendamiento:'Arrend.',
  publicidad:'Publicidad', honorarios:'Honorarios', alimentacion:'Alimentación',
  tecnologia:'Tecnología', seguridad:'Seguridad', servicios_publicos:'Serv. Públicos',
};

// ── Navegación principal ──────────────────────────────────────────────────────

function navTo(id, btn) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('section-' + id).classList.add('active');
  if (btn) btn.classList.add('active');
  else {
    document.querySelectorAll('.nav-btn').forEach(b => {
      if (b.dataset.section === id) b.classList.add('active');
    });
  }
  if (id === 'alertas')       loadAlertasGlobal();
  if (id === 'declaraciones') loadDeclaraciones();
}

// ── Subtabs de empresa ────────────────────────────────────────────────────────

function subtabTo(id, btn) {
  document.querySelectorAll('.subtab-content').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.subtab').forEach(b => b.classList.remove('active'));
  document.getElementById('subtab-' + id).classList.add('active');
  if (btn) btn.classList.add('active');

  if (id === 'gastos'        && empresaActual) loadGastosEmpresa(empresaActual.id);
  if (id === 'alertas-e'     && empresaActual) loadAlertasEmpresa(empresaActual.id);
  if (id === 'retenciones-e' && empresaActual) loadRetencionesEmpresa(empresaActual.id);
  if (id === 'flujo-caja'    && empresaActual) loadFlujoCaja(empresaActual.id);
  if (id === 'conciliacion'  && empresaActual) initConciliacion();
}

// ── INICIO: Mis clientes ──────────────────────────────────────────────────────

async function loadInicio() {
  const [resumen, empresas] = await Promise.all([
    fetch('/api/resumen').then(r => r.json()),
    fetch('/api/empresas').then(r => r.json()),
  ]);
  empresasData = empresas;

  // KPIs consolidados
  document.getElementById('kpi-consolidado').innerHTML = `
    <div class="kpi-card">
      <div class="kpi-label">Empresas Gestionadas</div>
      <div class="kpi-value">${resumen.n_empresas}</div>
      <div class="kpi-sub">${resumen.total_facturas} facturas en total</div>
    </div>
    <div class="kpi-card green">
      <div class="kpi-label">Total Facturado (clientes)</div>
      <div class="kpi-value">${MCOP(resumen.total_ventas)} COP</div>
      <div class="kpi-sub">Por cobrar: ${MCOP(resumen.por_cobrar)} COP</div>
    </div>
    <div class="kpi-card red">
      <div class="kpi-label">Cartera Vencida</div>
      <div class="kpi-value">${MCOP(resumen.cartera_vencida)} COP</div>
      <div class="kpi-sub">${resumen.n_vencidas} fact. vencidas · ${resumen.n_por_vencer} por vencer</div>
    </div>
    <div class="kpi-card yellow">
      <div class="kpi-label">Total Gastos (clientes)</div>
      <div class="kpi-value">${MCOP(resumen.total_gastos)} COP</div>
      <div class="kpi-sub">Por pagar: ${MCOP(resumen.por_pagar)} COP</div>
    </div>
  `;

  // Tarjetas de empresas
  const grid = document.getElementById('empresas-grid');
  grid.innerHTML = '';
  empresas.forEach((e, i) => {
    const alertaClass = e.semaforo === 'verde' ? 'ok' : e.semaforo === 'amarillo' ? 'warn' : 'danger';
    const alertaTexto = e.alertas === 0
      ? '✓ Sin alertas pendientes'
      : `${e.ventas.n_vencidas} vencidas · ${e.ventas.n_por_vencer} por vencer`;

    const card = document.createElement('div');
    card.className = 'empresa-card';
    card.style.setProperty('--empresa-color', e.color);
    card.style.cssText += `--empresa-color:${e.color};`;
    card.style.animationDelay = `${i * 0.07}s`;
    card.innerHTML = `
      <style>.empresa-card:nth-child(${i+1})::before{background:${e.color}}</style>
      <div class="empresa-card-top">
        <div class="empresa-info-header">
          <span class="empresa-icono">${e.icono}</span>
          <div>
            <div class="empresa-nombre">${e.razon_social}</div>
            <div class="empresa-sector">${e.sector}</div>
            <div class="empresa-ciudad">${e.ciudad}</div>
          </div>
        </div>
        <div class="semaforo ${e.semaforo}" title="Estado: ${e.semaforo}"></div>
      </div>

      <div class="empresa-metrics">
        <div class="metric-item">
          <div class="metric-label">Facturado</div>
          <div class="metric-valor" style="color:${e.color}">${MCOP(e.ventas.neto)} COP</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">Por cobrar</div>
          <div class="metric-valor" style="color:var(--blue)">${MCOP(e.ventas.por_cobrar)} COP</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">Gastos</div>
          <div class="metric-valor" style="color:var(--purple)">${MCOP(e.gastos.neto)} COP</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">Cartera vencida</div>
          <div class="metric-valor" style="color:var(--red)">${MCOP(e.ventas.vencido)} COP</div>
        </div>
      </div>

      <div class="empresa-alertas-bar ${alertaClass}">
        <span>${alertaTexto}</span>
      </div>

      <div class="empresa-contacto">
        NIT ${e.nit} · Contacto: ${e.contacto}
      </div>
    `;
    card.onclick = () => abrirEmpresa(e);
    grid.appendChild(card);
  });
}

// ── Detalle empresa ───────────────────────────────────────────────────────────

async function abrirEmpresa(empresa) {
  empresaActual = empresa;

  // Mostrar tab empresa en nav
  const navEmpresa = document.getElementById('nav-empresa');
  document.getElementById('nav-empresa-nombre').textContent = empresa.razon_social.split(' ').slice(0,2).join(' ');
  navEmpresa.style.display = 'flex';
  navTo('empresa', navEmpresa);

  // Resetear subtabs
  document.querySelectorAll('.subtab-content').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.subtab').forEach(b => b.classList.remove('active'));
  document.getElementById('subtab-ventas').classList.add('active');
  document.querySelectorAll('.subtab')[0].classList.add('active');

  // Header detalle
  const dash = await fetch(`/api/empresa/${empresa.id}/dashboard`).then(r => r.json());
  document.getElementById('empresa-detail-header').innerHTML = `
    <button class="btn-volver" onclick="volverAClientes()">← Mis Clientes</button>
    <span style="font-size:32px">${empresa.icono}</span>
    <div>
      <div style="font-size:17px;font-weight:700">${empresa.razon_social}</div>
      <div style="font-size:12px;color:var(--muted)">${empresa.sector} · NIT ${empresa.nit} · ${empresa.ciudad}</div>
      <div style="font-size:12px;color:var(--muted)">Contacto: ${empresa.contacto}</div>
    </div>
    <div class="empresa-detail-kpis">
      <div class="detail-kpi">
        <div class="detail-kpi-label">Facturado</div>
        <div class="detail-kpi-valor" style="color:${empresa.color}">${MCOP(dash.ventas.neto)} COP</div>
      </div>
      <div class="detail-kpi">
        <div class="detail-kpi-label">Por cobrar</div>
        <div class="detail-kpi-valor" style="color:var(--blue)">${MCOP(dash.ventas.por_cobrar)} COP</div>
      </div>
      <div class="detail-kpi">
        <div class="detail-kpi-label">Gastos</div>
        <div class="detail-kpi-valor" style="color:var(--purple)">${MCOP(dash.gastos.neto)} COP</div>
      </div>
      <div class="detail-kpi">
        <div class="detail-kpi-label">Vencido</div>
        <div class="detail-kpi-valor" style="color:var(--red)">${MCOP(dash.ventas.vencido)} COP</div>
      </div>
    </div>
  `;

  // Cargar ventas
  loadVentasEmpresa(empresa.id);
}

function volverAClientes() {
  document.getElementById('nav-empresa').style.display = 'none';
  navTo('inicio', document.querySelectorAll('.nav-btn')[0]);
}

// ── Ventas de empresa ─────────────────────────────────────────────────────────

let ventasEmpresaData = {};

async function loadVentasEmpresa(eid) {
  if (ventasEmpresaData[eid]) { renderVentas(ventasEmpresaData[eid]); return; }
  const data = await fetch(`/api/empresa/${eid}/facturas/venta`).then(r => r.json());
  ventasEmpresaData[eid] = data;
  renderVentas(data);
}

function renderVentas(data) {
  document.getElementById('badge-ventas-e').textContent = data.length + ' facturas';
  const tbody = document.getElementById('tbody-ventas-e');
  tbody.innerHTML = '';
  data.forEach((f, i) => {
    const tr = document.createElement('tr');
    tr.id = `row-v-${f.numero.replace(/[^a-zA-Z0-9]/g,'_')}`;
    tr.style.animationDelay = `${i * 0.03}s`;
    const pagada = f.estado === 'PAGADA';
    tr.innerHTML = `
      <td><b>${f.numero}</b></td>
      <td class="muted">${f.fecha}</td>
      <td>${f.cliente_nombre}</td>
      <td class="muted">${f.cliente_ciudad}</td>
      <td>${COP(f.subtotal)}</td>
      <td style="color:var(--yellow)">${COP(f.iva)}</td>
      <td style="color:var(--red)">(${COP(f.retefuente)})</td>
      <td style="color:var(--red)">(${COP(f.reteiva)})</td>
      <td style="color:var(--red)">(${COP(f.reteica)})</td>
      <td><b>${COP(f.total_factura)}</b></td>
      <td style="color:var(--green)"><b>${COP(f.valor_neto)}</b></td>
      <td>${estadoBadge(f.estado)}</td>
      <td>${pagada ? '' : `<button class="btn-pagar" onclick="marcarPagada('venta','${f.numero}',this)">✓ Pagada</button>`}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ── Flujo A: Procesamiento animado ────────────────────────────────────────────

async function runFlujoA() {
  if (!empresaActual) return;
  const btn = document.querySelector('#subtab-ventas .btn-demo');
  btn.disabled = true;

  const progress = document.getElementById('flujo-a-progress');
  const label    = document.getElementById('flujo-a-label');
  const fill     = document.getElementById('flujo-a-fill');
  const tbody    = document.getElementById('tbody-ventas-e');

  progress.style.display = 'block';
  tbody.innerHTML = '';
  fill.style.width = '0%';

  const pasos = [
    `Escaneando carpeta empresa_${empresaActual.id}_... `,
    'Leyendo CUFE y Resolucion DIAN ...',
    'Extrayendo NIT, fecha y valores de cada factura ...',
    'Calculando IVA 19%, Retefuente, ReteIVA, ReteICA ...',
    'Verificando grandes contribuyentes ...',
    'Clasificando estados de cartera ...',
    'Actualizando base de datos ...',
    'Proceso completado.',
  ];

  for (let i = 0; i < pasos.length; i++) {
    label.textContent = pasos[i];
    fill.style.width = ((i + 1) / pasos.length * 100) + '%';
    await sleep(350);
  }

  delete ventasEmpresaData[empresaActual.id];
  const data = await fetch(`/api/empresa/${empresaActual.id}/facturas/venta`).then(r => r.json());
  ventasEmpresaData[empresaActual.id] = data;
  document.getElementById('badge-ventas-e').textContent = data.length + ' facturas';

  for (let i = 0; i < data.length; i++) {
    label.textContent = `Registrando ${i + 1}/${data.length}: ${data[i].numero} — ${data[i].cliente_nombre}`;
    fill.style.width = ((i + 1) / data.length * 100) + '%';
    const f = data[i];
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><b>${f.numero}</b></td>
      <td class="muted">${f.fecha}</td>
      <td>${f.cliente_nombre}</td>
      <td class="muted">${f.cliente_ciudad}</td>
      <td>${COP(f.subtotal)}</td>
      <td style="color:var(--yellow)">${COP(f.iva)}</td>
      <td style="color:var(--red)">(${COP(f.retefuente)})</td>
      <td style="color:var(--red)">(${COP(f.reteiva)})</td>
      <td style="color:var(--red)">(${COP(f.reteica)})</td>
      <td><b>${COP(f.total_factura)}</b></td>
      <td style="color:var(--green)"><b>${COP(f.valor_neto)}</b></td>
      <td>${estadoBadge(f.estado)}</td>
    `;
    tbody.appendChild(tr);
    await sleep(120);
  }

  label.textContent = `Listo. ${data.length} facturas procesadas automaticamente.`;
  btn.disabled = false;
}

// ── Gastos de empresa ─────────────────────────────────────────────────────────

async function loadGastosEmpresa(eid) {
  const data = await fetch(`/api/empresa/${eid}/facturas/gastos`).then(r => r.json());
  document.getElementById('badge-gastos-e').textContent = data.length + ' facturas';
  const tbody = document.getElementById('tbody-gastos-e');
  tbody.innerHTML = '';
  data.forEach((f, i) => {
    const tr = document.createElement('tr');
    tr.id = `row-g-${f.numero.replace(/[^a-zA-Z0-9]/g,'_')}`;
    tr.style.animationDelay = `${i * 0.04}s`;
    const pagada = f.estado === 'PAGADA';
    tr.innerHTML = `
      <td><b>${f.numero}</b></td>
      <td class="muted">${f.fecha}</td>
      <td>${f.proveedor_nombre}</td>
      <td class="muted">${CATS[f.categoria] || f.categoria}</td>
      <td>${COP(f.subtotal)}</td>
      <td style="color:var(--yellow)">${COP(f.iva)}</td>
      <td style="color:var(--red)">(${COP(f.retefuente)})</td>
      <td style="color:var(--red)">(${COP(f.reteiva)})</td>
      <td style="color:var(--red)">(${COP(f.reteica)})</td>
      <td><b>${COP(f.total_factura)}</b></td>
      <td style="color:var(--purple)"><b>${COP(f.valor_neto)}</b></td>
      <td>${estadoBadge(f.estado)}</td>
      <td>${pagada ? '' : `<button class="btn-pagar" onclick="marcarPagada('gasto','${f.numero}',this)">✓ Pagada</button>`}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ── Alertas de empresa ────────────────────────────────────────────────────────

async function loadAlertasEmpresa(eid) {
  const data = await fetch(`/api/empresa/${eid}/alertas`).then(r => r.json());
  document.getElementById('badge-alertas-e').textContent = data.length;
  renderAlertasCards(data, 'alertas-empresa-lista', true);
}

async function runEmailsEmpresa() {
  if (!empresaActual) return;
  const btn = document.querySelector('#subtab-alertas-e .btn-demo');
  btn.disabled = true;
  const container = document.getElementById('alertas-empresa-lista');
  for (const msg of ['Analizando cartera...','Identificando facturas vencidas...','Redactando emails...']) {
    container.innerHTML = `<p style="color:var(--muted);padding:.75rem">${msg}</p>`;
    await sleep(600);
  }
  await loadAlertasEmpresa(empresaActual.id);
  btn.disabled = false;
}

// ── Alertas globales ──────────────────────────────────────────────────────────

async function loadAlertasGlobal() {
  const data = await fetch('/api/alertas/global').then(r => r.json());
  document.getElementById('badge-alertas-global').textContent = data.length + ' alertas';

  // Agrupar por empresa
  const porEmpresa = {};
  data.forEach(a => {
    if (!porEmpresa[a.empresa_id]) porEmpresa[a.empresa_id] = { nombre: a.empresa_nombre, color: a.empresa_color, alertas: [] };
    porEmpresa[a.empresa_id].alertas.push(a);
  });

  const container = document.getElementById('alertas-global-lista');
  container.innerHTML = '';

  Object.values(porEmpresa).forEach(grupo => {
    const div = document.createElement('div');
    div.className = 'alerta-global-grupo';
    div.innerHTML = `
      <div class="alerta-global-empresa-title" style="background:${grupo.color}22;color:${grupo.color}">
        ${grupo.nombre} — ${grupo.alertas.length} alertas
      </div>
      <div class="alertas-grid" id="grid-${Math.random().toString(36).slice(2)}"></div>
    `;
    const grid = div.querySelector('.alertas-grid');
    grupo.alertas.forEach(a => {
      const esVencida = a.estado.toUpperCase().includes('VENCIDA');
      const card = document.createElement('div');
      card.className = 'alerta-card' + (esVencida ? '' : ' por-vencer');
      card.innerHTML = `
        <div class="alerta-cliente">${a.cliente_nombre}</div>
        <div class="alerta-numero">Factura ${a.numero}</div>
        <div class="alerta-monto">${COP(a.valor_neto)} COP</div>
        <div class="alerta-fecha">Vto: ${a.fecha_vencimiento} · <b>${a.estado}</b></div>
      `;
      grid.appendChild(card);
    });
    container.appendChild(div);
  });

  if (data.length === 0) {
    container.innerHTML = '<p style="color:var(--muted);padding:2rem">No hay alertas pendientes.</p>';
  }
}

async function runEmailsGlobal() {
  const container = document.getElementById('alertas-global-lista');
  for (const msg of ['Revisando todas las empresas...','Cruzando fechas de vencimiento...','Generando emails personalizados...']) {
    container.innerHTML = `<p style="color:var(--muted);padding:.75rem">${msg}</p>`;
    await sleep(700);
  }
  await loadAlertasGlobal();
}

// ── Retenciones empresa ───────────────────────────────────────────────────────

async function loadRetencionesEmpresa(eid) {
  const [dash, porCliente] = await Promise.all([
    fetch(`/api/empresa/${eid}/dashboard`).then(r => r.json()),
    fetch(`/api/empresa/${eid}/retenciones-por-cliente`).then(r => r.json()),
  ]);

  const rv = dash.retenciones_ventas;
  const rg = dash.retenciones_gastos;

  document.getElementById('retenciones-empresa-contenido').innerHTML = `
    <div class="ret-grid">
      <div class="ret-card">
        <div class="ret-card-title">Retenciones que los clientes nos practican</div>
        <div class="ret-card-sub">Valores descontados en el pago — se declaran como saldo a favor</div>
        <div class="ret-items">
          <div class="ret-item"><span class="ret-item-label">Retefuente</span><span class="ret-item-valor">${COP(rv.retefuente)}</span></div>
          <div class="ret-item"><span class="ret-item-label">ReteIVA</span><span class="ret-item-valor">${COP(rv.reteiva)}</span></div>
          <div class="ret-item"><span class="ret-item-label">ReteICA</span><span class="ret-item-valor">${COP(rv.reteica)}</span></div>
          <div class="ret-item" style="border-top:1px solid var(--border)">
            <span class="ret-item-label"><b>Total retenido</b></span>
            <span class="ret-item-valor" style="color:var(--red)"><b>${COP(rv.retefuente+rv.reteiva+rv.reteica)}</b></span>
          </div>
        </div>
      </div>
      <div class="ret-card">
        <div class="ret-card-title">Retenciones que nosotros practicamos a proveedores</div>
        <div class="ret-card-sub">Valores descontados al pagar — se declaran y consignan</div>
        <div class="ret-items">
          <div class="ret-item"><span class="ret-item-label">Retefuente</span><span class="ret-item-valor">${COP(rg.retefuente)}</span></div>
          <div class="ret-item"><span class="ret-item-label">ReteIVA</span><span class="ret-item-valor">${COP(rg.reteiva)}</span></div>
          <div class="ret-item"><span class="ret-item-label">ReteICA</span><span class="ret-item-valor">${COP(rg.reteica)}</span></div>
          <div class="ret-item" style="border-top:1px solid var(--border)">
            <span class="ret-item-label"><b>Total retenido</b></span>
            <span class="ret-item-valor" style="color:var(--yellow)"><b>${COP(rg.retefuente+rg.reteiva+rg.reteica)}</b></span>
          </div>
        </div>
      </div>
    </div>

    <div class="ret-por-cliente">
      <h4>Detalle retenciones por cliente</h4>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>
            <th>Cliente</th><th>Ciudad</th><th>Facturas</th>
            <th>Retefuente</th><th>ReteIVA</th><th>ReteICA</th>
            <th>Total Retenido</th><th>Neto Cobrado</th>
          </tr></thead>
          <tbody>
            ${porCliente.map(c => `<tr>
              <td><b>${c.cliente_nombre}</b></td>
              <td class="muted">${c.cliente_ciudad}</td>
              <td class="muted">${c.n_facturas}</td>
              <td style="color:var(--red)">(${COP(c.retefuente)})</td>
              <td style="color:var(--red)">(${COP(c.reteiva)})</td>
              <td style="color:var(--red)">(${COP(c.reteica)})</td>
              <td style="color:var(--yellow)"><b>(${COP(c.total_ret)})</b></td>
              <td style="color:var(--green)"><b>${COP(c.valor_neto)}</b></td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ── Alertas cards helper ──────────────────────────────────────────────────────

function renderAlertasCards(alertas, containerId, conEmail) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  if (!alertas.length) {
    container.innerHTML = '<p style="color:var(--muted);padding:1rem">No hay alertas para esta empresa.</p>';
    return;
  }
  const grid = document.createElement('div');
  grid.className = 'alertas-grid';
  alertas.forEach((a, i) => {
    const esVencida = a.estado.toUpperCase().includes('VENCIDA');
    const card = document.createElement('div');
    card.className = 'alerta-card' + (esVencida ? '' : ' por-vencer');
    card.style.animationDelay = `${i * 0.05}s`;
    card.innerHTML = `
      <div class="alerta-cliente">${a.cliente_nombre}</div>
      <div class="alerta-numero">Factura ${a.numero} · ${a.cliente_ciudad}</div>
      <div class="alerta-monto">${COP(a.valor_neto)} COP</div>
      <div class="alerta-fecha">Vto: ${a.fecha_vencimiento} · <b>${a.estado}</b></div>
      ${conEmail ? '<div class="alerta-hint">Clic para ver email generado automáticamente</div>' : ''}
    `;
    if (conEmail && a.email_preview) {
      card.onclick = () => {
        document.querySelectorAll('.alerta-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        const sec = document.getElementById('email-preview-section');
        document.getElementById('email-preview-box').textContent = a.email_preview;
        sec.style.display = 'block';
        sec.scrollIntoView({ behavior:'smooth' });
      };
    }
    grid.appendChild(card);
  });
  container.appendChild(grid);
}

// ── Estado badge ──────────────────────────────────────────────────────────────

function estadoBadge(estado) {
  const e = estado.toUpperCase();
  if (e.includes('PAGADA'))     return `<span class="estado-badge estado-pagada">Pagada</span>`;
  if (e.includes('PENDIENTE'))  return `<span class="estado-badge estado-pendiente">Pendiente</span>`;
  if (e.includes('VENCIDA'))    return `<span class="estado-badge estado-vencida">${estado}</span>`;
  if (e.includes('POR_VENCER')) return `<span class="estado-badge estado-por_vencer">Por vencer</span>`;
  return `<span class="estado-badge">${estado}</span>`;
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadInicio();
  initFormManual();
});

// ── LOGIN redirect ────────────────────────────────────────────────────────────
// (el login es solo visual, no hay sesión real en la demo)

// ── FORMULARIO MANUAL ─────────────────────────────────────────────────────────

const RETENCIONES = {
  insumos:          { retefuente:0.025, reteiva:0,    reteica:0.00414, label:'Compras generales (2.5% retefuente)' },
  servicios:        { retefuente:0.04,  reteiva:0.15, reteica:0.00414, label:'Servicios (4% retefuente + ReteIVA si gran contribuyente)' },
  honorarios:       { retefuente:0.11,  reteiva:0.15, reteica:0.00414, label:'Honorarios (11% retefuente — la mas alta)' },
  arrendamiento:    { retefuente:0.035, reteiva:0,    reteica:0.00414, label:'Arrendamiento (3.5% retefuente)' },
  transporte:       { retefuente:0.04,  reteiva:0,    reteica:0.00414, label:'Transporte (4% retefuente)' },
  telecomunicaciones:{retefuente:0.025, reteiva:0,    reteica:0.00414, label:'Telecomunicaciones (2.5% retefuente)' },
  publicidad:       { retefuente:0.04,  reteiva:0.15, reteica:0.00414, label:'Publicidad (4% retefuente + ReteIVA)' },
  seguros:          { retefuente:0.025, reteiva:0,    reteica:0,       label:'Seguros (2.5% retefuente, sin ReteICA)' },
  tecnologia:       { retefuente:0.04,  reteiva:0.15, reteica:0.00414, label:'Tecnologia / Software (4% retefuente + ReteIVA)' },
  servicios_publicos:{retefuente:0.025, reteiva:0,    reteica:0,       label:'Servicios publicos (2.5%, sin ReteICA)' },
};

async function initFormManual() {
  // Cargar empresas en el select
  try {
    const empresas = await fetch('/api/empresas').then(r => r.json());
    const sel = document.getElementById('fm-empresa');
    if (!sel) return;
    empresas.forEach(e => {
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = e.razon_social;
      sel.appendChild(opt);
    });
  } catch(e) {}

  // Fecha por defecto: hoy
  const hoy = new Date().toISOString().split('T')[0];
  const fechaInput = document.getElementById('fm-fecha');
  if (fechaInput) fechaInput.value = hoy;
}

function onTipoChange() {
  const tipo = document.getElementById('fm-tipo').value;
  const label = document.getElementById('fm-tercero-label');
  const catGroup = document.getElementById('fm-categoria').closest('.fm-group');
  if (tipo === 'venta') {
    label.textContent = 'Cliente (quien recibe la factura) *';
    catGroup.style.display = 'none';
  } else {
    label.textContent = 'Proveedor (quien emite la factura) *';
    catGroup.style.display = '';
  }
  recalcular();
}

function recalcular() {
  const subtotal    = parseFloat(document.getElementById('fm-subtotal')?.value) || 0;
  const ivaRate     = parseFloat(document.getElementById('fm-iva-rate')?.value) || 0.19;
  const categoria   = document.getElementById('fm-categoria')?.value || 'insumos';
  const granContrib = document.getElementById('fm-gran-contrib')?.value === 'si';
  const tipo        = document.getElementById('fm-tipo')?.value || 'gasto';

  const ret = RETENCIONES[categoria] || RETENCIONES.insumos;

  const iva        = Math.round(subtotal * ivaRate);
  const total      = subtotal + iva;
  const base_ret   = subtotal >= 892000 ? subtotal : 0;
  const retefuente = tipo === 'gasto' ? Math.round(base_ret * ret.retefuente) : Math.round(base_ret * 0.025);
  const reteiva    = (granContrib && iva > 0) ? Math.round(iva * 0.15) : 0;
  const reteica    = tipo === 'gasto' ? Math.round(subtotal * ret.reteica) : Math.round(subtotal * 0.00414);
  const neto       = total - retefuente - reteiva - reteica;

  // Actualizar panel
  document.getElementById('fc-subtotal').textContent    = COP(subtotal);
  document.getElementById('fc-iva').textContent         = COP(iva);
  document.getElementById('fc-total').textContent       = COP(total);
  document.getElementById('fc-retefuente').textContent  = retefuente > 0 ? `(${COP(retefuente)})` : '$0';
  document.getElementById('fc-reteiva').textContent     = reteiva > 0 ? `(${COP(reteiva)})` : '$0';
  document.getElementById('fc-reteica').textContent     = reteica > 0 ? `(${COP(reteica)})` : '$0';
  document.getElementById('fc-neto').innerHTML          = `<b>${COP(neto)}</b>`;

  // Explicacion
  let explicacion = '';
  if (subtotal === 0) {
    explicacion = 'Ingrese un subtotal para ver el calculo.';
  } else {
    explicacion = ret.label + '.';
    if (base_ret === 0) explicacion += ' La retefuente no aplica porque el valor es menor a $892.000.';
    if (reteiva > 0)    explicacion += ' ReteIVA aplica porque el cliente es gran contribuyente.';
    if (reteica === 0 && tipo === 'gasto') explicacion += ' Sin ReteICA para esta categoria.';
  }
  document.getElementById('fm-ret-explicacion').textContent = explicacion;
}

async function submitFacturaManual(e) {
  e.preventDefault();
  const btn = document.getElementById('fm-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Registrando...';

  const subtotal    = parseFloat(document.getElementById('fm-subtotal').value) || 0;
  const ivaRate     = parseFloat(document.getElementById('fm-iva-rate').value) || 0.19;
  const categoria   = document.getElementById('fm-categoria').value;
  const granContrib = document.getElementById('fm-gran-contrib').value === 'si';
  const tipo        = document.getElementById('fm-tipo').value;
  const ret         = RETENCIONES[categoria] || RETENCIONES.insumos;
  const iva         = Math.round(subtotal * ivaRate);
  const total       = subtotal + iva;
  const base_ret    = subtotal >= 892000 ? subtotal : 0;
  const retefuente  = Math.round(base_ret * ret.retefuente);
  const reteiva     = (granContrib && iva > 0) ? Math.round(iva * 0.15) : 0;
  const reteica     = Math.round(subtotal * ret.reteica);
  const neto        = total - retefuente - reteiva - reteica;
  const diasPago    = parseInt(document.getElementById('fm-forma-pago').value);

  const payload = {
    empresa_id:     document.getElementById('fm-empresa').value,
    tipo,
    numero:         document.getElementById('fm-numero').value,
    fecha:          document.getElementById('fm-fecha').value,
    dias_pago:      diasPago,
    tercero_nombre: document.getElementById('fm-tercero-nombre').value,
    tercero_nit:    document.getElementById('fm-tercero-nit').value,
    descripcion:    document.getElementById('fm-descripcion').value,
    categoria,
    subtotal, iva, retefuente, reteiva, reteica,
    total_factura: total,
    valor_neto: neto,
  };

  try {
    const res = await fetch('/api/factura-manual', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.ok) {
      // Invalidar cache de ventas/gastos
      ventasEmpresaData = {};
      // Mostrar confirmación
      document.getElementById('fm-layout') && (document.querySelector('.fm-layout').style.display = 'none');
      document.querySelector('.fm-header').style.display = 'none';
      const conf = document.getElementById('fm-confirmacion');
      conf.style.display = 'block';
      document.getElementById('fm-conf-sub').innerHTML =
        `Factura <b>${payload.numero}</b> registrada para <b>${document.getElementById('fm-empresa').options[document.getElementById('fm-empresa').selectedIndex].text}</b>.<br>
         Neto: <b>${COP(neto)}</b> COP · Retenciones calculadas automaticamente.`;
    }
  } catch(err) {
    alert('Error al registrar. Verifique que el servidor esta corriendo.');
  }

  btn.disabled = false;
  btn.textContent = 'Registrar factura';
}

function nuevaFactura() {
  document.getElementById('fm-confirmacion').style.display = 'none';
  document.querySelector('.fm-header').style.display = '';
  document.querySelector('.fm-layout').style.display = '';
  document.getElementById('form-manual').reset();
  initFormManual();
  recalcular();
}

// ── LEER IMAGEN ──────────────────────────────────────────────────────────────

function liDragOver(e) {
  e.preventDefault();
  document.getElementById('li-upload-area').classList.add('drag-over');
}
function liDragLeave() {
  document.getElementById('li-upload-area').classList.remove('drag-over');
}
function liDrop(e) {
  e.preventDefault();
  liDragLeave();
  const file = e.dataTransfer.files[0];
  if (file) liProcesar(file);
}
function liFileSelected(input) {
  if (input.files[0]) liProcesar(input.files[0]);
}

async function liProcesar(file) {
  const uploadArea = document.getElementById('li-upload-area');
  const resultado  = document.getElementById('li-resultado');
  const preview    = document.getElementById('li-preview-img');
  const estadoCard = document.getElementById('li-estado-card');
  const estadoIcon = document.getElementById('li-estado-icon');
  const estadoTit  = document.getElementById('li-estado-titulo');
  const estadoSub  = document.getElementById('li-estado-sub');

  // Mostrar preview
  preview.src = URL.createObjectURL(file);
  uploadArea.style.display = 'none';
  resultado.style.display  = 'block';
  document.getElementById('li-datos-extraidos').style.display = 'none';
  document.getElementById('li-acciones').style.display = 'none';

  estadoCard.className  = 'li-estado-card';
  estadoIcon.textContent = '⏳';
  estadoTit.textContent  = 'Procesando...';
  estadoSub.textContent  = 'Buscando código QR de la DIAN...';

  const form = new FormData();
  form.append('imagen', file);

  try {
    const res  = await fetch('/api/procesar-imagen', { method: 'POST', body: form });
    const data = await res.json();

    if (!data.ok) {
      estadoCard.className   = 'li-estado-card error';
      estadoIcon.textContent  = '❌';
      estadoTit.textContent   = 'Error al procesar';
      estadoSub.textContent   = data.error || 'No se pudo leer la imagen.';
      document.getElementById('li-acciones').style.display = 'flex';
      return;
    }

    if (data.metodo === 'qr') {
      estadoCard.className   = 'li-estado-card success';
      estadoIcon.textContent  = '✅';
      estadoTit.textContent   = 'QR de la DIAN detectado';
      estadoSub.textContent   = 'Código QR leído exitosamente. Los datos provienen directamente del portal DIAN — máxima confiabilidad.';
    } else if (data.metodo === 'ocr') {
      estadoCard.className   = 'li-estado-card ocr';
      estadoIcon.textContent  = '🔍';
      estadoTit.textContent   = 'Texto reconocido (OCR)';
      estadoSub.textContent   = 'No se encontró QR. Se usó reconocimiento óptico de texto. Verifique los valores antes de guardar.';
    } else {
      estadoCard.className   = 'li-estado-card error';
      estadoIcon.textContent  = '⚠️';
      estadoTit.textContent   = 'No se pudo leer automáticamente';
      estadoSub.textContent   = data.mensaje || 'Use el formulario manual para ingresar esta factura.';
      document.getElementById('li-acciones').style.display = 'flex';
      return;
    }

    // Mostrar datos extraídos
    liMostrarDatos(data);
    document.getElementById('li-datos-extraidos').style.display = 'block';
    document.getElementById('li-acciones').style.display = 'flex';

    // OCR raw text
    if (data.metodo === 'ocr' && data.raw) {
      document.getElementById('li-raw-text').style.display = 'block';
      document.getElementById('li-raw-pre').textContent = data.raw;
    }

  } catch (err) {
    estadoCard.className   = 'li-estado-card error';
    estadoIcon.textContent  = '❌';
    estadoTit.textContent   = 'Error de conexión';
    estadoSub.textContent   = 'No se pudo contactar el servidor.';
    document.getElementById('li-acciones').style.display = 'flex';
  }
}

function liMostrarDatos(data) {
  const d = data.datos || {};
  const items = [];

  const LABELS = {
    cufe:         ['CUFE', 'blue'],
    cufe_corto:   ['CUFE', 'blue'],
    nit:          ['NIT', 'text'],
    numero:       ['N° Factura', 'text'],
    fecha:        ['Fecha', 'text'],
    total_texto:  ['Total', 'green'],
    url:          ['URL DIAN', 'blue'],
    fuente:       ['Fuente', 'text'],
    confiabilidad:['Confiabilidad', d.confiabilidad && d.confiabilidad.startsWith('Alta') ? 'green' : 'yellow'],
  };

  const skip = new Set(['tipo', 'total']);
  if (d.cufe_corto) skip.add('cufe');  // show cufe_corto instead

  for (const [key, val] of Object.entries(d)) {
    if (skip.has(key) || !val) continue;
    const [label, cls] = LABELS[key] || [key, 'text'];
    const display = key === 'url' && val.length > 60 ? val.slice(0, 60) + '…' : val;
    items.push(`<div class="li-dato-item">
      <div class="li-dato-label">${label}</div>
      <div class="li-dato-val ${cls}">${display}</div>
    </div>`);
  }

  document.getElementById('li-datos-grid').innerHTML = items.length
    ? items.join('')
    : '<p style="color:var(--muted);font-size:13px">No se extrajeron campos estructurados.</p>';
}

function liNueva() {
  document.getElementById('li-upload-area').style.display = '';
  document.getElementById('li-resultado').style.display   = 'none';
  document.getElementById('li-file-input').value = '';
  document.getElementById('li-raw-text').style.display = 'none';
}

// ── MARCAR FACTURA COMO PAGADA ────────────────────────────────────────────────

async function marcarPagada(tipo, numero, btn) {
  if (!empresaActual) return;
  btn.disabled = true;
  btn.textContent = '⏳';
  const res = await fetch(`/api/factura/${tipo}/${encodeURIComponent(numero)}/empresa/${empresaActual.id}/pagar`, { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    btn.textContent = '✓';
    btn.style.background = '#059669';
    const td = btn.closest('tr').querySelector('td:nth-child(12)');
    if (td) td.innerHTML = estadoBadge('PAGADA');
    // Limpiar caché para que recargue datos actualizados
    delete ventasEmpresaData[empresaActual.id];
  } else {
    btn.disabled = false;
    btn.textContent = '✓ Pagada';
  }
}

// ── DESCARGAR INFORME PDF ─────────────────────────────────────────────────────

function descargarInforme() {
  if (!empresaActual) return;
  const btn = document.querySelector('.pdf-btn');
  const orig = btn.textContent;
  btn.textContent = '⏳ Generando PDF...';
  btn.disabled = true;

  fetch(`/api/empresa/${empresaActual.id}/informe-pdf`)
    .then(res => res.blob())
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const a   = document.createElement('a');
      a.href    = url;
      a.download = `Informe_${empresaActual.razon_social.replace(/\s+/g,'_')}_2026.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      btn.textContent = '✓ PDF descargado';
      setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 2500);
    })
    .catch(() => { btn.textContent = orig; btn.disabled = false; });
}

// ── DESCARGAR EXCEL ───────────────────────────────────────────────────────────

function descargarExcel() {
  if (!empresaActual) return;
  const btn = document.querySelector('.subtab.pdf-btn:last-child');
  if (btn) { btn.textContent = '⏳ Generando...'; btn.disabled = true; }

  fetch(`/api/empresa/${empresaActual.id}/informe-excel`)
    .then(res => res.blob())
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const a   = document.createElement('a');
      a.href    = url;
      a.download = `ContaBot_${empresaActual.razon_social.replace(/\s+/g,'_')}_2026.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      if (btn) { btn.textContent = '✓ Excel descargado'; setTimeout(() => { btn.textContent = '⬇ Excel'; btn.disabled = false; }, 2500); }
    })
    .catch(() => { if (btn) { btn.textContent = '⬇ Excel'; btn.disabled = false; } });
}

// ── CONCILIACIÓN BANCARIA ─────────────────────────────────────────────────────

function initConciliacion() {
  document.getElementById('conc-upload-area').style.display = '';
  document.getElementById('conc-resultado').style.display   = 'none';
  document.getElementById('conc-file-input').value = '';
}

async function procesarExtracto(file) {
  if (!file || !empresaActual) return;
  const area = document.getElementById('conc-upload-area');
  area.innerHTML = `<div class="li-upload-icon">⏳</div><div class="li-upload-text">Procesando extracto...</div>`;

  const form = new FormData();
  form.append('archivo', file);

  const res  = await fetch(`/api/empresa/${empresaActual.id}/conciliacion`, { method: 'POST', body: form });
  const data = await res.json();

  if (!data.ok) {
    area.innerHTML = `
      <div class="li-upload-icon">⚠</div>
      <div class="li-upload-text" style="color:var(--red)">${data.error}</div>
      <button class="li-upload-btn" onclick="initConciliacion()">Intentar de nuevo</button>`;
    return;
  }

  area.style.display = 'none';
  const result = document.getElementById('conc-resultado');
  result.style.display = '';

  const r = data.resumen;
  document.getElementById('conc-resumen').innerHTML = `
    <div class="kpi-card green">
      <div class="kpi-label">Transacciones en extracto</div>
      <div class="kpi-value">${r.total_filas}</div>
    </div>
    <div class="kpi-card green">
      <div class="kpi-label">Identificadas con facturas</div>
      <div class="kpi-value">${r.matches}</div>
      <div class="kpi-sub">${r.pct_match}% del extracto</div>
    </div>
    <div class="kpi-card ${r.sin_match > 0 ? 'yellow' : 'green'}">
      <div class="kpi-label">Sin identificar</div>
      <div class="kpi-value">${r.sin_match}</div>
      <div class="kpi-sub">Revisar manualmente</div>
    </div>`;

  const matchTbody = document.getElementById('conc-matches-tbody');
  matchTbody.innerHTML = data.coincidencias.map(c => `
    <tr>
      <td><b>${COP(c.extracto_monto)}</b></td>
      <td class="muted">${c.extracto_fecha}</td>
      <td>${c.extracto_desc || '—'}</td>
      <td><b>${c.factura_numero}</b></td>
      <td>${c.factura_tercero}</td>
      <td style="color:var(--green)">${COP(c.factura_neto)}</td>
      <td class="muted">${c.diferencia > 0 ? COP(c.diferencia) : '—'}</td>
      <td><span class="badge ${c.tipo === 'exacto' ? 'green' : 'yellow'}">${c.tipo}</span></td>
    </tr>`).join('');

  const sinTbody = document.getElementById('conc-sinmatch-tbody');
  sinTbody.innerHTML = data.sin_match.length
    ? data.sin_match.map(s => `<tr><td>${COP(s.monto)}</td><td class="muted">${s.fecha}</td><td>${s.descripcion || '—'}</td></tr>`).join('')
    : '<tr><td colspan="3" style="color:var(--green);text-align:center">Todas las transacciones fueron identificadas</td></tr>';
}

function concNueva() { initConciliacion(); }

// ── DECLARACIONES DIAN ────────────────────────────────────────────────────────

let _flujoCajaChart = null;

async function loadDeclaraciones() {
  const data = await fetch('/api/declaraciones').then(r => r.json());

  document.getElementById('badge-decl').textContent = data.empresas.length + ' empresas';

  // Alerta global de fecha límite
  const diasCls = data.dias <= 3 ? 'red' : data.dias <= 7 ? 'yellow' : 'green';
  document.getElementById('decl-fecha-limite').innerHTML = `
    <div class="decl-alerta ${diasCls}">
      <div class="decl-alerta-label">Fecha límite declaración</div>
      <div class="decl-alerta-fecha">${data.fecha_limite}</div>
      <div class="decl-alerta-dias">${data.dias > 0 ? data.dias + ' días' : data.dias === 0 ? '¡HOY!' : 'VENCIDA'}</div>
    </div>`;

  // Consolidado total
  document.getElementById('decl-consolidado').innerHTML = `
    <div class="decl-total-label">Total a declarar — todas las empresas</div>
    <div class="decl-total-val">${COP(data.total_consolidado)} COP</div>
    <div class="decl-total-sub">Retefuente + ReteIVA + ReteICA · Período: ${data.mes}</div>`;

  // Grid por empresa
  const grid = document.getElementById('decl-empresas-grid');
  grid.innerHTML = data.empresas.map(e => `
    <div class="decl-card">
      <div class="decl-card-header" style="border-left:4px solid ${e.color}">
        <div>
          <div class="decl-card-empresa">${e.razon_social}</div>
          <div class="decl-card-nit">NIT ${e.nit}</div>
        </div>
        <div class="decl-card-total">${COP(e.total)}</div>
      </div>
      <div class="decl-card-rows">
        <div class="decl-row"><span>Retefuente practicada</span><span class="red">${COP(e.retefuente)}</span></div>
        <div class="decl-row"><span>ReteIVA practicada</span><span class="red">${COP(e.reteiva)}</span></div>
        <div class="decl-row"><span>ReteICA practicada</span><span class="red">${COP(e.reteica)}</span></div>
        <div class="decl-row muted"><span>Retefuente sufrida (a compensar)</span><span class="blue">(${COP(e.sufrido_retefuente)})</span></div>
      </div>
      <div class="decl-card-footer ${e.estado === 'VENCIDA' ? 'red' : e.dias <= 7 ? 'yellow' : 'green'}">
        ${e.estado === 'VENCIDA' ? '⚠ DECLARACIÓN VENCIDA' : e.dias <= 7 ? `⚡ Vence en ${e.dias} días` : `✓ Vence el ${e.fecha_limite}`}
      </div>
    </div>`).join('');
}

// ── FLUJO DE CAJA ─────────────────────────────────────────────────────────────

async function loadFlujoCaja(eid) {
  const data = await fetch(`/api/empresa/${eid}/flujo-caja`).then(r => r.json());

  // KPIs
  const totalIng = data.semanas.reduce((s, w) => s + w.ingresos, 0);
  const totalEgr = data.semanas.reduce((s, w) => s + w.egresos, 0);
  const neto60   = totalIng - totalEgr;
  document.getElementById('flujo-caja-kpis').innerHTML = `
    <div class="fc-kpi green"><div class="fc-kpi-label">Ingresos esperados (60d)</div><div class="fc-kpi-val">${COP(totalIng)}</div></div>
    <div class="fc-kpi red">  <div class="fc-kpi-label">Egresos esperados (60d)</div> <div class="fc-kpi-val">${COP(totalEgr)}</div></div>
    <div class="fc-kpi ${neto60 >= 0 ? 'blue' : 'red'}"><div class="fc-kpi-label">Flujo neto proyectado</div><div class="fc-kpi-val">${COP(neto60)}</div></div>
    ${data.cartera_vencida > 0 ? `<div class="fc-kpi red"><div class="fc-kpi-label">Cartera vencida (no incluida)</div><div class="fc-kpi-val">${COP(data.cartera_vencida)}</div></div>` : ''}`;

  // Chart
  const labels  = data.semanas.map(w => w.label);
  const ingrArr = data.semanas.map(w => w.ingresos / 1_000_000);
  const egrArr  = data.semanas.map(w => -w.egresos / 1_000_000);
  const netoArr = data.semanas.map(w => w.neto / 1_000_000);

  if (_flujoCajaChart) _flujoCajaChart.destroy();
  const ctx = document.getElementById('flujo-caja-chart').getContext('2d');
  _flujoCajaChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Ingresos (M COP)', data: ingrArr, backgroundColor: 'rgba(16,185,129,.7)', borderColor: '#10b981', borderWidth: 1.5, borderRadius: 4 },
        { label: 'Egresos (M COP)',  data: egrArr,  backgroundColor: 'rgba(239,68,68,.7)',  borderColor: '#ef4444', borderWidth: 1.5, borderRadius: 4 },
        { label: 'Neto (M COP)',     data: netoArr, type: 'line', borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,.1)', borderWidth: 2.5, pointRadius: 4, tension: 0.3, fill: false },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      plugins: { legend: { labels: { color: '#94a3b8', font: { size: 12 } } } },
      scales: {
        x: { stacked: false, ticks: { color: '#64748b' }, grid: { color: 'rgba(100,116,139,.15)' } },
        y: { ticks: { color: '#64748b', callback: v => v.toFixed(1) + 'M' }, grid: { color: 'rgba(100,116,139,.15)' } }
      }
    }
  });

  // Tabla resumen
  document.getElementById('flujo-caja-tabla').innerHTML = `
    <table class="data-table" style="margin-top:1.25rem">
      <thead><tr><th>Semana</th><th>Ingresos</th><th>Egresos</th><th>Flujo Neto</th></tr></thead>
      <tbody>${data.semanas.map(w => `
        <tr>
          <td>${w.label}</td>
          <td class="green">${w.ingresos > 0 ? COP(w.ingresos) : '—'}</td>
          <td class="red">${w.egresos > 0 ? COP(w.egresos) : '—'}</td>
          <td class="${w.neto >= 0 ? 'green' : 'red'}">${COP(w.neto)}</td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}
