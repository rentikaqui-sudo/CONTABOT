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
      <div style="font-size:12px;color:var(--muted)">${empresa.sector} · NIT ${empresa.nit} · ${empresa.ciudad} · ${empresa.regimen || 'Jurídica'}</div>
      <div style="font-size:12px;color:var(--muted)">Contacto: ${empresa.contacto || '—'}</div>
    </div>
    <button class="btn-demo" style="margin-left:auto;font-size:13px;padding:.45rem .9rem" onclick="abrirModalEmpresa(empresaActual)">✏️ Editar</button>
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
  // Verificar pendientes al cargar para mostrar badge
  fetch('/api/pendientes').then(r => r.json()).then(res => {
    if (res.ok && res.pendientes && res.pendientes.length > 0) {
      const badge = document.getElementById('badge-pendientes');
      if (badge) { badge.textContent = res.pendientes.length; badge.style.display = 'inline'; }
    }
  }).catch(() => {});
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

// ── SUBIR FACTURA DIAN ────────────────────────────────────────────────────────

let _sfDatosActuales = null;

function sfDragOver(e) {
  e.preventDefault();
  document.getElementById('sf-upload-area').classList.add('drag-over');
}
function sfDragLeave() {
  document.getElementById('sf-upload-area').classList.remove('drag-over');
}
function sfDrop(e) {
  e.preventDefault();
  sfDragLeave();
  const file = e.dataTransfer.files[0];
  if (file) sfProcesar(file);
}

async function sfProcesar(file) {
  if (!file) return;
  const uploadArea = document.getElementById('sf-upload-area');
  const resultado  = document.getElementById('sf-resultado');
  const icon       = document.getElementById('sf-estado-icon');
  const tit        = document.getElementById('sf-estado-titulo');
  const sub        = document.getElementById('sf-estado-sub');
  const datosBox   = document.getElementById('sf-datos-box');
  const selector   = document.getElementById('sf-empresa-selector');

  uploadArea.style.display = 'none';
  resultado.style.display  = 'block';
  datosBox.style.display   = 'none';
  selector.style.display   = 'none';
  icon.textContent = '⏳';
  tit.textContent  = 'Procesando...';
  sub.textContent  = 'Extrayendo datos de la factura electrónica...';

  const form = new FormData();
  form.append('archivo', file);

  try {
    const res  = await fetch('/api/subir-factura', { method: 'POST', body: form });
    const data = await res.json();

    if (!data.ok) {
      icon.textContent = '❌';
      tit.textContent  = 'Error';
      sub.textContent  = data.error || 'No se pudo procesar la factura.';
      return;
    }

    _sfDatosActuales = data.datos;
    sfMostrarDatos(data.datos);
    datosBox.style.display = 'block';

    if (data.duplicada) {
      icon.textContent = '=';
      tit.textContent  = 'Factura duplicada';
      sub.textContent  = data.mensaje;
      return;
    }

    if (data.empresa_detectada === false) {
      icon.textContent = '⚠';
      tit.textContent  = 'Empresa no detectada';
      sub.textContent  = data.mensaje;
      const sel = document.getElementById('sf-empresa-select');
      sel.innerHTML = '<option value="">— Selecciona empresa —</option>';
      (data.empresas_disponibles || []).forEach(e => {
        sel.innerHTML += `<option value="${e.id}">${e.razon_social}</option>`;
      });
      selector.style.display = 'block';
      return;
    }

    icon.textContent = 'OK';
    tit.textContent  = 'Factura registrada';
    sub.textContent  = data.mensaje;

  } catch (err) {
    icon.textContent = '❌';
    tit.textContent  = 'Error de conexión';
    sub.textContent  = 'No se pudo contactar el servidor.';
  }
}

function sfMostrarDatos(d) {
  if (!d) return;
  const LABELS = {
    numero:           'N° Factura',
    fecha:            'Fecha',
    proveedor_nombre: 'Proveedor',
    proveedor_nit:    'NIT Proveedor',
    receptor_nombre:  'Empresa receptora',
    receptor_nit:     'NIT Receptor',
    total_factura:    'Total',
    iva:              'IVA',
    subtotal:         'Subtotal',
    cufe:             'CUFE',
  };
  const fmt = v => typeof v === 'number' ? `$${v.toLocaleString('es-CO')}` : v;
  const items = Object.entries(LABELS)
    .filter(([k]) => d[k])
    .map(([k, label]) => {
      const val = k === 'cufe' ? d[k].slice(0, 20) + '…' : fmt(d[k]);
      return `<div class="li-dato-item">
        <div class="li-dato-label">${label}</div>
        <div class="li-dato-val">${val}</div>
      </div>`;
    });
  document.getElementById('sf-datos-grid').innerHTML = items.join('') || '<p style="color:var(--muted)">Sin datos estructurados.</p>';
}

async function sfConfirmar() {
  const empresa_id = document.getElementById('sf-empresa-select').value;
  if (!empresa_id) { alert('Selecciona una empresa'); return; }

  const res  = await fetch('/api/subir-factura/confirmar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ datos: _sfDatosActuales, empresa_id: parseInt(empresa_id) }),
  });
  const data = await res.json();

  document.getElementById('sf-estado-icon').textContent = data.ok ? 'OK' : '❌';
  document.getElementById('sf-estado-titulo').textContent = data.ok ? 'Factura registrada' : 'Error';
  document.getElementById('sf-estado-sub').textContent   = data.mensaje || '';
  document.getElementById('sf-empresa-selector').style.display = 'none';
}

function sfReset() {
  _sfDatosActuales = null;
  document.getElementById('sf-upload-area').style.display = '';
  document.getElementById('sf-resultado').style.display   = 'none';
  document.getElementById('sf-file-input').value = '';
}

// ── BANDEJA PENDIENTE ────────────────────────────────────────────────────────

async function cargarPendientes() {
  const lista = document.getElementById('pendientes-lista');
  const vacio = document.getElementById('pendientes-vacio');
  lista.innerHTML = '<p style="color:#64748b;padding:1rem">Cargando...</p>';
  vacio.style.display = 'none';

  const res = await fetch('/api/pendientes').then(r => r.json());
  if (!res.ok) { lista.innerHTML = `<p style="color:red">${res.error}</p>`; return; }

  const { pendientes, empresas } = res;

  // Actualizar badge
  const badge = document.getElementById('badge-pendientes');
  if (pendientes.length > 0) {
    badge.textContent = pendientes.length;
    badge.style.display = 'inline';
  } else {
    badge.style.display = 'none';
  }

  if (!pendientes.length) {
    lista.innerHTML = '';
    vacio.style.display = '';
    return;
  }

  const fmt = v => v ? `$${Math.round(v).toLocaleString('es-CO')}` : '$0';

  lista.innerHTML = pendientes.map(p => {
    const d = p.factura_data || {};
    const opts = empresas.map(e => `<option value="${e.id}">${e.razon_social}</option>`).join('');
    return `
    <div class="pend-card" id="pend-${p.id}" style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.25rem;margin-bottom:1rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:.75rem">
        <div>
          <div style="font-weight:700;font-size:15px">📄 ${d.numero || '(sin número)'}</div>
          <div style="font-size:13px;color:#64748b;margin-top:3px">
            Proveedor: <b>${d.proveedor_nombre || d.proveedor_nit || '—'}</b>
            &nbsp;·&nbsp; Fecha: ${d.fecha || '—'}
          </div>
          <div style="font-size:13px;color:#64748b">
            NIT receptor leído: <code style="background:#1e293b;padding:1px 6px;border-radius:4px">${d.receptor_nit || 'no detectado'}</code>
            &nbsp;·&nbsp; Nombre: ${d.receptor_nombre || '—'}
          </div>
        </div>
        <div style="text-align:right">
          <div style="font-size:20px;font-weight:700;color:var(--green)">${fmt(d.total_factura)}</div>
          <div style="font-size:12px;color:#64748b">IVA ${fmt(d.iva)}</div>
        </div>
      </div>
      <div style="margin-top:1rem;display:flex;gap:.75rem;align-items:center;flex-wrap:wrap">
        <select id="sel-${p.id}" style="flex:1;min-width:200px;padding:.4rem .75rem;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px">
          <option value="">— Selecciona empresa —</option>
          ${opts}
        </select>
        <button class="btn-demo" style="padding:.4rem 1rem;font-size:13px" onclick="asignarPendiente('${p.id}')">Asignar</button>
        <button onclick="ignorarPendiente('${p.id}')" style="background:none;border:none;color:#64748b;cursor:pointer;font-size:13px;padding:.4rem">✕ Ignorar</button>
      </div>
    </div>`;
  }).join('');
}

async function asignarPendiente(pendienteId) {
  const sel = document.getElementById(`sel-${pendienteId}`);
  if (!sel.value) { alert('Selecciona una empresa'); return; }
  const res = await fetch(`/api/pendientes/${pendienteId}/asignar`, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ empresa_id: parseInt(sel.value) })
  }).then(r => r.json());
  if (res.ok) {
    document.getElementById(`pend-${pendienteId}`).remove();
    await cargarPendientes();
    mostrarToast('Factura asignada correctamente');
  } else {
    alert('Error: ' + res.error);
  }
}

async function ignorarPendiente(pendienteId) {
  if (!confirm('¿Eliminar esta factura pendiente?')) return;
  await fetch(`/api/pendientes/${pendienteId}`, { method: 'DELETE' });
  document.getElementById(`pend-${pendienteId}`).remove();
  await cargarPendientes();
}

// ── CREAR / EDITAR EMPRESA ────────────────────────────────────────────────────

let _empresaEditandoId = null;

function abrirModalEmpresa(empresa) {
  _empresaEditandoId = empresa ? empresa.id : null;
  const titulo = document.getElementById('ne-titulo');
  const btn    = document.getElementById('ne-btn-guardar');
  titulo.textContent = empresa ? 'Editar Empresa' : 'Nueva Empresa Cliente';
  btn.textContent    = empresa ? 'Guardar cambios' : 'Guardar empresa';

  document.getElementById('ne-nit').value     = empresa ? (empresa.nit || '') : '';
  document.getElementById('ne-razon').value   = empresa ? (empresa.razon_social || '') : '';
  document.getElementById('ne-ciudad').value  = empresa ? (empresa.ciudad || '') : '';
  document.getElementById('ne-contacto').value = empresa ? (empresa.contacto || '') : '';
  const sec = document.getElementById('ne-sector');
  if (empresa && empresa.sector) {
    for (let opt of sec.options) if (opt.value === empresa.sector || opt.text === empresa.sector) { sec.value = opt.value; break; }
  } else sec.selectedIndex = 0;
  const reg = document.getElementById('ne-regimen');
  const regimenVal = empresa ? (empresa.regimen || 'Juridica') : 'Juridica';
  for (let opt of reg.options) if (opt.value === regimenVal) { reg.value = regimenVal; break; }

  document.getElementById('ne-error').style.display = 'none';
  document.getElementById('modal-empresa').style.display = 'flex';
}

function cerrarModalEmpresa() {
  document.getElementById('modal-empresa').style.display = 'none';
  _empresaEditandoId = null;
}

async function guardarEmpresa() {
  const btn = document.getElementById('ne-btn-guardar');
  const err = document.getElementById('ne-error');
  err.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Guardando...';

  const body = {
    nit:          document.getElementById('ne-nit').value.trim(),
    razon_social: document.getElementById('ne-razon').value.trim(),
    ciudad:       document.getElementById('ne-ciudad').value.trim(),
    sector:       document.getElementById('ne-sector').value,
    contacto:     document.getElementById('ne-contacto').value.trim(),
    regimen:      document.getElementById('ne-regimen').value,
  };

  try {
    const isEdit = !!_empresaEditandoId;
    const url    = isEdit ? `/api/empresa/${_empresaEditandoId}` : '/api/empresas';
    const method = isEdit ? 'PUT' : 'POST';
    const res    = await fetch(url, {
      method, headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!data.ok) {
      err.textContent = data.error;
      err.style.display = 'block';
      btn.disabled = false;
      btn.textContent = isEdit ? 'Guardar cambios' : 'Guardar empresa';
      return;
    }
    cerrarModalEmpresa();
    if (isEdit && empresaActual) {
      // Actualizar datos locales y recargar header
      Object.assign(empresaActual, data.empresa || body);
      abrirEmpresa(empresaActual);
    } else {
      await loadInicio();
      navTo('inicio', document.querySelector('[data-section="inicio"]'));
    }
  } catch (e) {
    err.textContent = 'Error de conexión';
    err.style.display = 'block';
    btn.disabled = false;
    btn.textContent = _empresaEditandoId ? 'Guardar cambios' : 'Guardar empresa';
  }
}

// ── DECLARACIONES F-300 / F-350 / ICA ────────────────────────────────────────

async function loadDeclaracionesEmpresa(eid) {
  const box = document.getElementById('decl-contenido');
  box.innerHTML = '<p style="color:var(--muted);padding:1rem 0">Calculando declaraciones...</p>';
  const data = await fetch(`/api/empresa/${eid}/declaraciones`).then(r => r.json());
  if (!data.ok) { box.innerHTML = '<p style="color:var(--red)">Error cargando declaraciones.</p>'; return; }

  const regimen  = data.regimen || 'Juridica';
  const noAplica = texto => `<p style="color:var(--muted);font-style:italic;padding:.5rem 0">⊘ No aplica para ${regimen === 'Natural' ? 'persona natural' : 'este régimen'}</p>`;

  // F-300 IVA
  const f300rows = data.aplica_iva && data.f300.length ? data.f300.map(r => `<tr>
    <td>${r.periodo}</td>
    <td>${COP(r.base_ventas)}</td>
    <td style="color:var(--red)">${COP(r.iva_generado)}</td>
    <td style="color:var(--green)">${COP(r.iva_descontable)}</td>
    <td style="font-weight:700;color:${r.iva_a_pagar > 0 ? 'var(--red)' : 'var(--green)'}">${COP(r.iva_a_pagar)}</td>
    <td style="color:var(--muted)">${r.n_facturas_v}v / ${r.n_facturas_g}g</td>
  </tr>`).join('') : null;

  // F-350 Retefuente
  const f350rows = data.aplica_rtefte && data.f350.length ? data.f350.map(r => `<tr>
    <td>${r.periodo}</td>
    <td>${COP(r.base)}</td>
    <td style="font-weight:700;color:var(--red)">${COP(r.retefte)}</td>
    <td style="color:var(--muted)">${r.n_facturas} facturas</td>
  </tr>`).join('') : (data.aplica_rtefte ? '<tr><td colspan="4" style="color:var(--muted);text-align:center">Sin retenciones en el período</td></tr>' : null);

  // ICA
  const icarows = data.aplica_ica && data.ica.length ? data.ica.map(r => `<tr>
    <td>${r.periodo}</td>
    <td>${COP(r.base)}</td>
    <td>${r.tasa}</td>
    <td style="font-weight:700;color:${r.ica_a_pagar > 0 ? 'var(--red)' : 'var(--muted)'}">${COP(r.ica_a_pagar)}</td>
    <td style="color:var(--muted)">${r.n_facturas} facturas</td>
  </tr>`).join('') : null;

  const secF300 = f300rows !== null
    ? `<div class="table-wrap" style="margin-bottom:2rem"><table class="data-table">
        <thead><tr><th>Período</th><th>Base Ventas</th><th>IVA Generado</th><th>IVA Descontable</th><th>IVA a Pagar</th><th>Facturas</th></tr></thead>
        <tbody>${f300rows}</tbody></table></div>`
    : noAplica();

  const secF350 = f350rows !== null
    ? `<div class="table-wrap" style="margin-bottom:2rem"><table class="data-table">
        <thead><tr><th>Mes</th><th>Base</th><th>Retención Practicada</th><th>Facturas</th></tr></thead>
        <tbody>${f350rows}</tbody></table></div>`
    : noAplica();

  const secICA = icarows !== null
    ? `<div class="table-wrap" style="margin-bottom:2rem"><table class="data-table">
        <thead><tr><th>Bimestre</th><th>Base (Ventas)</th><th>Tasa</th><th>ICA a Pagar</th><th>Facturas</th></tr></thead>
        <tbody>${icarows}</tbody></table></div>`
    : noAplica();

  box.innerHTML = `
    <p style="color:var(--muted);font-size:13px;margin:0 0 1.5rem">Régimen: <strong>${regimen}</strong></p>
    <h3 style="margin:0 0 1rem">Formulario 300 — IVA Cuatrimestral</h3>
    ${secF300}
    <h3 style="margin:1.5rem 0 1rem">Formulario 350 — Retefuente Mensual</h3>
    ${secF350}
    <h3 style="margin:1.5rem 0 1rem">ICA — Bimestral (Tasa Bogotá 4.14‰)</h3>
    ${secICA}`;
}

// ── CONCILIAR DIAN ────────────────────────────────────────────────────────────

function initDian() {
  document.getElementById('dian-upload-area').style.display = '';
  document.getElementById('dian-resultado').style.display   = 'none';
  document.getElementById('dian-file-input').value = '';
}
function dianDragOver(e) { e.preventDefault(); document.getElementById('dian-upload-area').classList.add('drag-over'); }
function dianDragLeave()  { document.getElementById('dian-upload-area').classList.remove('drag-over'); }
function dianDrop(e)      { e.preventDefault(); dianDragLeave(); const f = e.dataTransfer.files[0]; if(f) dianProcesar(f); }

async function dianProcesar(file) {
  if (!file || !empresaActual) return;
  const area = document.getElementById('dian-upload-area');
  const res_box = document.getElementById('dian-resultado');
  area.innerHTML = `<div class="li-upload-icon">⏳</div><div class="li-upload-text">Analizando Excel DIAN...</div>`;

  const form = new FormData();
  form.append('archivo', file);

  try {
    const res  = await fetch(`/api/empresa/${empresaActual.id}/importar-dian`, { method: 'POST', body: form });
    const data = await res.json();

    if (!data.ok) {
      area.innerHTML = `<div class="li-upload-icon">❌</div><div class="li-upload-text" style="color:var(--red)">${data.error}</div><button class="li-select-btn" onclick="initDian()">Intentar de nuevo</button>`;
      return;
    }

    area.style.display = 'none';
    res_box.style.display = 'block';

    const nuevasRows = (data.detalle_nuevas || []).map(f => `<tr>
      <td>${f.numero || '—'}</td>
      <td>${f.fecha || '—'}</td>
      <td>${f.nombre_emisor || '—'}</td>
      <td>${f.nit_emisor || '—'}</td>
      <td style="text-align:right">${f.total ? '$' + Math.round(f.total).toLocaleString('es-CO') : '—'}</td>
      <td style="font-family:monospace;font-size:10px">${(f.cufe||'').slice(0,16)}…</td>
    </tr>`).join('');

    res_box.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:1.5rem">
        <div class="cal-kpi ok"><div class="cal-kpi-num">${data.total_dian}</div><div class="cal-kpi-label">Total en DIAN</div></div>
        <div class="cal-kpi ok"><div class="cal-kpi-num">${data.ya_en_contabot}</div><div class="cal-kpi-label">Ya en ContaBot</div></div>
        <div class="cal-kpi ${data.nuevas > 0 ? 'urgente' : 'ok'}"><div class="cal-kpi-num">${data.nuevas}</div><div class="cal-kpi-label">Facturas nuevas</div></div>
      </div>
      ${data.nuevas > 0 ? `
        <h4 style="margin:0 0 .75rem">Facturas en DIAN que no están en ContaBot:</h4>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>N° Factura</th><th>Fecha</th><th>Emisor</th><th>NIT</th><th>Total</th><th>CUFE</th></tr></thead>
            <tbody>${nuevasRows}</tbody>
          </table>
        </div>` : '<p style="color:var(--green);font-weight:600">Todas las facturas DIAN ya están registradas en ContaBot.</p>'}
      <button class="btn-demo" style="margin-top:1rem" onclick="initDian();document.getElementById('dian-upload-area').style.display=''">Analizar otro archivo</button>`;

  } catch (err) {
    area.innerHTML = `<div class="li-upload-icon">❌</div><div class="li-upload-text" style="color:var(--red)">Error de conexión</div><button class="li-select-btn" onclick="initDian()">Reintentar</button>`;
  }
}

// ── CALENDARIO TRIBUTARIO ─────────────────────────────────────────────────────

let _calData = [];

async function cargarCalendario() {
  const lista = document.getElementById('cal-lista');
  lista.innerHTML = '<p style="color:var(--muted);padding:2rem 0">Cargando obligaciones...</p>';
  try {
    const res  = await fetch('/api/calendario');
    const data = await res.json();
    if (!data.ok) { lista.innerHTML = '<p style="color:var(--red)">Error cargando calendario.</p>'; return; }
    _calData = data.obligaciones;

    // Poblar filtro de empresas
    const sel = document.getElementById('cal-filtro-empresa');
    const empresas = [...new Map(_calData.map(o => [o.empresa_id, o.empresa])).entries()];
    sel.innerHTML = '<option value="">Todas las empresas</option>';
    empresas.sort((a,b) => a[1].localeCompare(b[1])).forEach(([id, nombre]) => {
      sel.innerHTML += `<option value="${id}">${nombre}</option>`;
    });

    renderCalendario();
  } catch (e) {
    lista.innerHTML = '<p style="color:var(--red)">Error de conexión.</p>';
  }
}

function renderCalendario() {
  const filtroEmp        = document.getElementById('cal-filtro-empresa').value;
  const filtroTipo       = document.getElementById('cal-filtro-tipo').value;
  const filtroEstado     = document.getElementById('cal-filtro-estado').value;
  const mostrarCompletadas = document.getElementById('cal-mostrar-completadas').checked;

  let obs = _calData;
  if (filtroEmp)    obs = obs.filter(o => String(o.empresa_id) === filtroEmp);
  if (filtroTipo)   obs = obs.filter(o => o.tipo === filtroTipo || o.tipo.startsWith(filtroTipo));
  if (filtroEstado) obs = obs.filter(o => o.estado === filtroEstado);
  if (!mostrarCompletadas) obs = obs.filter(o => !o.completada);

  // KPIs (solo pendientes, no completadas)
  const pendientes = obs.filter(o => !o.completada);
  const conteos = { urgente: 0, proxima: 0, ok: 0, vencida: 0 };
  pendientes.forEach(o => { if (conteos[o.estado] !== undefined) conteos[o.estado]++; });
  const totalCompletadas = _calData.filter(o => o.completada).length;
  document.getElementById('cal-kpis').innerHTML = [
    ['urgente', 'Urgentes ≤7d',  conteos.urgente],
    ['proxima', 'Próximas ≤30d', conteos.proxima],
    ['ok',      'A tiempo',      conteos.ok],
    ['vencida', 'Vencidas',      conteos.vencida],
  ].map(([cls, label, n]) => `
    <div class="cal-kpi ${cls}">
      <div class="cal-kpi-num">${n}</div>
      <div class="cal-kpi-label">${label}</div>
    </div>`).join('')
  + (totalCompletadas ? `<div class="cal-kpi completada"><div class="cal-kpi-num">✓ ${totalCompletadas}</div><div class="cal-kpi-label">Realizadas</div></div>` : '');

  if (!obs.length) {
    document.getElementById('cal-lista').innerHTML = '<p style="color:var(--muted);padding:2rem 0">Sin obligaciones con estos filtros.</p>';
    return;
  }

  const ETIQUETAS = { urgente: 'Urgente', proxima: 'Próxima', ok: 'A tiempo', vencida: 'Vencida', completada: '✓ Realizada' };

  const filas = obs.map(o => {
    const dias = o.dias_restantes;
    const diasLabel = o.completada ? '—' : dias < 0 ? `Vencida hace ${Math.abs(dias)}d` : dias === 0 ? 'Hoy' : `${dias}d`;
    const rowStyle  = o.completada ? 'opacity:.45;' : '';
    const btnLabel  = o.completada ? '↩ Deshacer' : '✓ Marcar hecha';
    const btnStyle  = o.completada
      ? 'background:transparent;border:1px solid var(--border);color:var(--muted);font-size:11px;padding:.25rem .6rem;border-radius:6px;cursor:pointer'
      : 'background:#10b981;border:none;color:#fff;font-size:11px;padding:.25rem .6rem;border-radius:6px;cursor:pointer;font-weight:600';
    const eid  = o.empresa_id;
    const tipo = o.tipo.replace(/'/g, "\\'");
    const vto  = o.vencimiento;
    return `<tr style="${rowStyle}">
      <td><span class="cal-empresa-tag">${o.empresa.split(' ').slice(0,3).join(' ')}</span></td>
      <td><strong>${o.tipo}</strong></td>
      <td style="color:var(--muted)">${o.periodo}</td>
      <td>${o.vencimiento}</td>
      <td style="font-weight:600">${diasLabel}</td>
      <td><span class="cal-badge ${o.estado}">${ETIQUETAS[o.estado] || o.estado}</span></td>
      <td><button style="${btnStyle}" onclick="marcarObligacion(${eid},'${tipo}','${vto}',${!o.completada})">${btnLabel}</button></td>
    </tr>`;
  }).join('');

  document.getElementById('cal-lista').innerHTML = `
    <table class="cal-tabla">
      <thead><tr>
        <th>Empresa</th><th>Obligación</th><th>Período</th>
        <th>Vencimiento</th><th>Días</th><th>Estado</th><th></th>
      </tr></thead>
      <tbody>${filas}</tbody>
    </table>`;
}

async function marcarObligacion(empresaId, tipo, vencimiento, completar) {
  const method = completar ? 'POST' : 'DELETE';
  await fetch('/api/obligacion/completar', {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ empresa_id: empresaId, tipo, vencimiento }),
  });
  await cargarCalendario();
}

async function notificarObligaciones() {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Enviando...';
  try {
    const res  = await fetch('/api/calendario/notificar', { method: 'POST' });
    const data = await res.json();
    btn.textContent = data.ok ? `Enviado (${data.enviadas} alertas)` : 'Error';
    setTimeout(() => { btn.disabled = false; btn.textContent = 'Enviar resumen a Telegram'; }, 3000);
  } catch {
    btn.textContent = 'Error';
    setTimeout(() => { btn.disabled = false; btn.textContent = 'Enviar resumen a Telegram'; }, 2000);
  }
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

  const conRtefte = data.empresas.filter(e => e.aplica_rtefte);
  const sinRtefte = data.empresas.filter(e => !e.aplica_rtefte);

  document.getElementById('badge-decl').textContent = conRtefte.length + ' agentes retenedores';

  // Consolidado
  document.getElementById('decl-consolidado').innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin-bottom:1.5rem">
      <div style="background:var(--bg2);border-radius:12px;padding:1.25rem;border:1px solid var(--border)">
        <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:.5rem">Total a declarar</div>
        <div style="font-size:1.6rem;font-weight:800;color:var(--red)">${COP(data.total_consolidado)}</div>
        <div style="font-size:12px;color:var(--muted);margin-top:.25rem">Período ${data.mes}</div>
      </div>
      <div style="background:var(--bg2);border-radius:12px;padding:1.25rem;border:1px solid var(--border)">
        <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:.5rem">Agentes retenedores</div>
        <div style="font-size:1.6rem;font-weight:800;color:var(--blue)">${conRtefte.length}</div>
        <div style="font-size:12px;color:var(--muted);margin-top:.25rem">de ${data.empresas.length} empresas</div>
      </div>
      ${sinRtefte.length ? `<div style="background:var(--bg2);border-radius:12px;padding:1.25rem;border:1px solid var(--border)">
        <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:.5rem">No obligados Rtefte</div>
        <div style="font-size:1.6rem;font-weight:800;color:var(--muted)">${sinRtefte.length}</div>
        <div style="font-size:12px;color:var(--muted);margin-top:.25rem">${sinRtefte.map(e=>e.razon_social).join(', ')}</div>
      </div>` : ''}
    </div>`;

  // Grid por empresa (solo agentes retenedores)
  const grid = document.getElementById('decl-empresas-grid');

  const cardHTML = (e) => {
    const diasCls  = !e.aplica_rtefte ? '' : e.dias <= 0 ? '#ef4444' : e.dias <= 7 ? '#f59e0b' : '#10b981';
    const diasText = e.dias == null ? '' : e.dias <= 0 ? '⚠ DECLARACIÓN VENCIDA' : e.dias <= 3 ? `🔴 Vence en ${e.dias} días` : e.dias <= 7 ? `🟡 Vence en ${e.dias} días` : `✓ Vence el ${e.fecha_limite_label}`;
    return `
    <div style="background:var(--bg2);border-radius:14px;border:1px solid var(--border);overflow:hidden">
      <div style="padding:1rem 1.25rem;border-left:4px solid ${e.color};display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-size:15px;font-weight:700">${e.razon_social}</div>
          <div style="font-size:12px;color:var(--muted)">NIT ${e.nit} · <span style="color:${e.aplica_rtefte?'var(--blue)':'var(--muted)'}">${e.regimen}</span></div>
        </div>
        <div style="text-align:right">
          <div style="font-size:1.3rem;font-weight:800;color:${e.total>0?'var(--red)':'var(--muted)'}">${COP(e.total)}</div>
          <div style="font-size:11px;color:var(--muted)">a declarar</div>
        </div>
      </div>
      ${e.aplica_rtefte ? `
      <div style="padding:.75rem 1.25rem;display:flex;flex-direction:column;gap:.5rem;border-top:1px solid var(--border)">
        <div style="display:flex;justify-content:space-between;font-size:13px">
          <span style="color:var(--muted)">Retefuente practicada</span>
          <span style="font-weight:600;color:${e.retefuente>0?'var(--red)':'var(--muted)'}">${COP(e.retefuente)}</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:13px">
          <span style="color:var(--muted)">ReteIVA practicada</span>
          <span style="font-weight:600;color:${e.reteiva>0?'var(--red)':'var(--muted)'}">${COP(e.reteiva)}</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:13px">
          <span style="color:var(--muted)">ReteICA practicada</span>
          <span style="font-weight:600;color:${e.reteica>0?'var(--red)':'var(--muted)'}">${COP(e.reteica)}</span>
        </div>
        ${e.sufrido_retefuente > 0 ? `<div style="display:flex;justify-content:space-between;font-size:12px;padding-top:.25rem;border-top:1px solid var(--border)">
          <span style="color:var(--muted)">Retefuente sufrida (a compensar)</span>
          <span style="color:var(--blue)">(${COP(e.sufrido_retefuente)})</span>
        </div>` : ''}
      </div>
      <div style="padding:.6rem 1.25rem;font-size:12px;font-weight:600;color:${diasCls};background:${diasCls}18;border-top:1px solid var(--border)">
        ${diasText}
      </div>` : `
      <div style="padding:.75rem 1.25rem;font-size:13px;color:var(--muted);border-top:1px solid var(--border);font-style:italic">
        ⊘ ${e.regimen === 'Natural' ? 'Persona natural — no es agente retenedor' : 'No obligado a declarar retenciones'}
      </div>`}
    </div>`;
  };

  grid.innerHTML = `
    ${conRtefte.length ? `<h3 style="font-size:14px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:0 0 .75rem">Agentes Retenedores</h3>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1rem;margin-bottom:1.5rem">
      ${conRtefte.map(cardHTML).join('')}
    </div>` : ''}
    ${sinRtefte.length ? `<h3 style="font-size:14px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:0 0 .75rem">Sin obligación de Retefuente</h3>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1rem">
      ${sinRtefte.map(cardHTML).join('')}
    </div>` : ''}`;
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
