'use strict';

const get = id => document.getElementById(id);
const fmt = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 });
const stageInfo = {
  audio: ['Audio a texto', 'Whisper Small', 'Un Transformer transcribe notas de voz y audio de video.'],
  detect: ['Detección visual', 'YOLO11n', 'Una red convolucional con atención localiza semáforos en fotos y fotogramas.'],
  text: ['Extracción de texto', 'Qwen3 4B Instruct', 'Un Transformer identifica ubicación, daño, duración y afectaciones a partir de citas verificables.'],
  video: ['Preparación de video', 'FFmpeg', 'Extrae el audio y los fotogramas. Es una etapa de preparación de datos.'],
};
const errorLabels = {
  unbacked_quote:'Cita sin respaldo literal',
  truncated_model_output:'Respuesta truncada',
  unknown_source:'Fuente sin identificar',
  incomplete_model_output:'Respuesta incompleta',
  HTTPError:'Error HTTP sin código guardado',
  adapter_failed:'El adaptador terminó con error',
  sin_codigo:'Sin código registrado',
};
let activeRequest;

function element(tag, content) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  return node;
}
function svgElement(tag, attributes = {}, content) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (content !== undefined) node.textContent = content;
  return node;
}
function number(value) { return Number.isFinite(value) ? fmt.format(value) : '—'; }
function seconds(value) { return Number.isFinite(value) ? number(value) + ' s' : '—'; }
function percent(value) { return Number.isFinite(value) ? number(value * 100) + ' %' : '—'; }
function ratio(numerator, denominator) { return denominator ? numerator / denominator : null; }
function values(entries) {
  const list = element('dl');
  list.className = 'metrics-values';
  for (const [label, value] of entries) {
    const item = element('div');
    item.append(element('dt', label), element('dd', value));
    list.append(item);
  }
  return list;
}
function outcomeChart(stage, data) {
  const points = [
    ['Completadas', data.completed, 'ok'],
    ['Parciales', data.partial, 'partial'],
    ['Fallidas', data.failed, 'failed'],
  ];
  const finished = data.completed + data.partial + data.failed;
  const figure = element('figure');
  figure.className = 'metrics-figure';
  if (finished) {
    const svg = svgElement('svg', {viewBox:'0 0 300 14',class:'metrics-bar',preserveAspectRatio:'none',
      role:'img', 'aria-label':'Resultados de ' + stage + ': ' + points.map(([label, count]) => count + ' ' + label).join(', ')});
    let x = 0;
    for (const [label, count, tone] of points) {
      if (!count) continue;
      const width = 300 * count / finished;
      const bar = svgElement('rect', {x, y:0, width, height:14, class:'outcome-' + tone});
      bar.append(svgElement('title', {}, label + ': ' + number(count)));
      svg.append(bar);x += width;
    }
    figure.append(svg);
  }
  const legend = element('ul');
  legend.className = 'metrics-list';
  for (const [label, count] of points) {
    const item = element('li');
    item.append(element('b', number(count)), document.createTextNode(' ' + label.toLowerCase()));
    legend.append(item);
  }
  figure.append(legend);
  if (data.pending || data.running || data.excluded) {
    figure.append(element('figcaption', `${number(data.pending)} en cola · ${number(data.running)} en proceso · ${number(data.excluded)} excluidas`));
  }
  return figure;
}
function quality(stage, data) {
  const block = element('div');
  if (stage === 'video') return block;
  block.append(element('h3', 'Calidad de la salida'));
  if (stage === 'text') {
    block.append(element('p', 'Las métricas de daño, gestión, peligro y ubicación se calculan con las evaluaciones humanas mostradas más abajo.'));
  } else if (!data.quality_samples) {
    block.append(element('p', 'Aún no hay referencias humanas utilizables en este filtro.'));
  } else if (stage === 'audio') {
    block.append(values([['WER · tasa de error de palabras', percent(ratio(data.word_errors, data.reference_words))]]),
      element('small', `${number(data.quality_samples)} transcripciones evaluadas · ${number(data.reference_words)} palabras de referencia. Un WER menor indica menos diferencias.`));
    block.append(element('small', 'Se excluyen las aprobaciones que reutilizan la predicción como referencia.'));
  } else {
    block.append(values([['Precisión', percent(ratio(data.tp, data.tp + data.fp))],
      ['Exhaustividad', percent(ratio(data.tp, data.tp + data.fn))]]),
      element('small', `${number(data.quality_samples)} imágenes evaluadas con IoU ≥ 0,5. Precisión: qué proporción de las detecciones coincidió. Exhaustividad: qué proporción de las cajas de referencia se encontró.`));
  }
  return block;
}
function modelCard(stage, row) {
  const [title, fallback, summary] = stageInfo[stage];
  const data = row || {completed:0, partial:0, failed:0, pending:0, running:0, excluded:0, time_samples:0};
  const card = element('section');
  card.className = 'metrics-card';
  const models = data.models?.length ? data.models.join(', ') : fallback;
  card.append(element('small', title), element('h2', models), element('p', summary));
  card.append(element('h3', 'Resultado de las tareas'), outcomeChart(title, data));
  const finished = data.completed + data.partial + data.failed;
  card.append(values([['Tasa de fallo', percent(ratio(data.failed, finished))], ['Tiempo típico · mediana', seconds(data.seconds_p50)],
    ['Tiempo de los casos lentos · P90', seconds(data.seconds_p90)],
    ['Memoria del proceso Python · P90', Number.isFinite(data.rss_bytes_p90) ? number(data.rss_bytes_p90 / 2**20) + ' MiB' : '—']]));
  const measured = data.time_samples ? `${number(data.time_samples)} ejecuciones con duración medida.` : 'Sin mediciones de duración.';
  card.append(element('small', measured + ' P90: 9 de cada 10 mediciones quedan en ese valor o por debajo.'));
  if (Number.isFinite(data.cpu_seconds_p50)) {
    card.append(element('small', 'CPU del proceso Python · mediana: ' + seconds(data.cpu_seconds_p50)));
  }
  if (stage === 'text' && data.token_samples) {
    card.append(element('h3','Generación de texto en Ollama'),
      values([['Tokens de entrada · mediana',number(data.input_tokens_p50)],
        ['Tokens de salida · mediana',number(data.output_tokens_p50)],
        ['Tokens de salida por segundo',number(data.tokens_per_second)]]),
      element('small',number(data.token_samples) + ' tareas con telemetría de salida. La velocidad usa solo el tiempo de generación.'));
  }
  if (stage === 'audio' && data.audio_check_samples) {
    card.append(element('small',number(data.audio_needs_review) + ' de ' +
      number(data.audio_check_samples) + ' transcripciones con control automático quedaron señaladas para revisión.'));
  }
  card.append(quality(stage, data));
  return card;
}
function dataTable(columns, rows) {
  const wrap = element('div');
  wrap.className = 'tableScroll';
  const table = element('table');
  const head = table.createTHead().insertRow();
  for (const column of columns) head.append(element('th', column));
  const body = table.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const value of row) tr.append(element('td', value));
  }
  wrap.append(table);
  return wrap;
}
function dailyGraph(container, days, records, selected) {
  const points = new Map(days.map(day => [day, {results:0, failed:0}]));
  for (const record of records) {
    if (selected && record.stage !== selected) continue;
    const point = points.get(record.day);
    if (point) {point.results += record.results;point.failed += record.failed;}
  }
  container.replaceChildren();
  const maximum = Math.max(0, ...Array.from(points.values(), point => point.results + point.failed));
  if (!maximum) {
    container.append(element('p', 'Sin resultados finalizados en las fechas del gráfico.'));
    return;
  }
  const svg = svgElement('svg', {viewBox:'0 0 620 185', class:'metrics-chart',role:'img',
    'aria-label':'Barras diarias de tareas con resultado y tareas fallidas. Valores exactos en la tabla.'});
  const top = 14, bottom = 149, left = 54, span = 547 / points.size;
  for (const tick of new Set([0, Math.round(maximum / 2), maximum])) {
    const y = bottom - tick * (bottom - top) / maximum;
    svg.append(svgElement('line', {x1:left, x2:606, y1:y, y2:y, class:'gridline'}),
      svgElement('text', {x:left - 6, y:y + 4, 'text-anchor':'end'}, number(tick)));
  }
  const rows = [];
  let index = 0;
  for (const [day, point] of points) {
    const shortDay = day.slice(8) + '/' + day.slice(5,7);
    const width = Math.min(32, span * .62);
    const x = left + (index + .5) * span - width / 2;
    let y = bottom;
    for (const name of ['results', 'failed']) {
      const height = point[name] * (bottom - top) / maximum;
      y -= height;
      if (height) {
        const bar = svgElement('rect', {x, y, width, height, class:'outcome-' + name});
        bar.append(svgElement('title', {}, day + ' · ' + (name === 'results' ? 'Con resultado' : 'Fallidas') + ': ' + number(point[name])));
        svg.append(bar);
      }
    }
    if (index === points.size - 1 || index % 2 === 0) {
      svg.append(svgElement('text', {x:x+width/2, y:171, 'text-anchor':'middle'}, shortDay));
    }
    rows.push([day,number(point.results),number(point.failed)]);
    index += 1;
  }
  const details = element('details');
  details.className = 'metrics-detail';
  details.append(element('summary','Ver valores por día'), dataTable(['Fecha Colombia','Con resultado','Fallidas'],rows));
  container.append(svg, element('small','Verde: con resultado, incluidos los parciales. Rojo: fallidas.'), details);
}
function latencyChart(byStage) {
  const section = element('section');
  section.append(element('h2','Comparación de tiempos'),
    element('p','Mediana de la duración por tarea con resultado. Cada etapa procesa una unidad distinta.'));
  const maximum = Math.max(0, ...Array.from(byStage.values(), row => row.seconds_p50 ?? 0));
  if (!maximum) {
    section.append(element('p','Sin mediciones de duración en este filtro.'));
    return section;
  }
  for (const [stage,[title]] of Object.entries(stageInfo)) {
    const value = byStage.get(stage)?.seconds_p50;
    if (!Number.isFinite(value)) continue;
    const item = element('div');
    item.className = 'metrics-latency';
    const meter = element('meter');
    meter.max = maximum;
    meter.value = value;
    meter.setAttribute('aria-label', title + ' · ' + seconds(value));
    item.append(element('span',title),element('strong',seconds(value)),meter);
    section.append(item);
  }
  return section;
}
function evidenceLevel(samples) {
  if (!samples) return ['Sin muestra','Todavía no hay evaluaciones humanas guardadas para este modelo.','empty'];
  if (samples < 10) return ['Muestra inicial','Resultado descriptivo; todavía es muy sensible a cada nueva evaluación.','low'];
  if (samples < 30) return ['Muestra exploratoria','Permite detectar tendencias, pero aún no sustenta conclusiones estables.','medium'];
  return ['Muestra acumulada','Indicador calculado con 30 o más evaluaciones; debe interpretarse junto con la composición de la muestra.','high'];
}
function sampleNotice(samples, unit='evaluaciones') {
  const [title,description,tone]=evidenceLevel(samples);
  const notice=element('div');
  notice.className='metrics-sample metrics-sample-'+tone;
  notice.append(element('strong',title+' · '+number(samples)+' '+unit),element('span',description));
  return notice;
}
function scoreBar(label, value, description) {
  const wrap=element('div');
  wrap.className='metrics-score';
  const heading=element('div');
  heading.append(element('span',label),element('strong',percent(value)));
  const meter=element('meter');
  meter.min=0;meter.max=1;meter.value=Number.isFinite(value)?value:0;
  meter.setAttribute('aria-label',label+' · '+percent(value));
  wrap.append(heading,meter,element('small',description));
  return wrap;
}
function semanticModel(model, row, completed) {
  const section=element('article');
  section.className='metrics-review-model';
  section.append(element('h3',model),sampleNotice(row?.evaluations||0));
  if(!row?.evaluations)return section;
  const micro=row.micro||{};
  const scores=element('div');
  scores.className='metrics-scores';
  scores.append(
    scoreBar('F1 macro',row.macro_f1,'Promedio del F1 de los campos que tuvieron positivos observados o detectados.'),
    scoreBar('F1 micro',micro.f1,'Balance global entre omisiones y detecciones incorrectas en todos los campos.'),
    scoreBar('Coincidencia completa',row.exact_match_rate,'Proporción de evaluaciones donde todos los campos calificados coincidieron.'),
    scoreBar('Exactitud de etiquetas',row.label_accuracy,'Proporción de casillas observado/detectado correctamente emparejadas.')
  );
  section.append(scores,values([
    ['Precisión micro',percent(micro.precision)],
    ['Exhaustividad micro',percent(micro.recall)],
    ['Especificidad micro',percent(micro.specificity)],
    ['Cobertura revisada',percent(ratio(row.evaluations,completed))],
    ['Campos evaluados',number(row.fields_evaluated)],
    ['Falsos positivos',number(micro.fp)],
    ['Falsos negativos',number(micro.fn)]
  ]));
  const labels={dano:'Daño',gestion:'Gestión',peligro:'Peligro',ubicacion:'Ubicación'};
  section.append(dataTable(
    ['Campo','n','TP','FP','FN','TN','Precisión','Exhaustividad','Especificidad','Exactitud','F1'],
    Object.entries(row.fields).map(([key,value])=>[
      labels[key],number(value.samples),number(value.tp),number(value.fp),number(value.fn),number(value.tn),
      percent(value.precision),percent(value.recall),percent(value.specificity),percent(value.accuracy),percent(value.f1)
    ])
  ));
  return section;
}
function reviewedModels(data) {
  const panel=element('section');
  panel.className='metrics-section';
  panel.append(element('h2','Resultados de la evaluación humana'),
    element('p','Estos indicadores usan únicamente la última evaluación guardada por ejecución. No sustituyen una muestra de validación estratificada; muestran el desempeño observado en el trabajo de revisión realizado.'));
  const quality=data.human_evaluations||{};
  const completed=new Map((data.stages||[]).map(row=>[row.stage,row.completed||0]));
  const vision=quality.detect;
  const yolo=element('article');
  yolo.className='metrics-review-model';
  yolo.append(element('h3','YOLO11n · conteo de semáforos'),sampleNotice(vision?.samples||0,'imágenes'));
  if(vision?.samples) {
    const scores=element('div');scores.className='metrics-scores';
    scores.append(
      scoreBar('Conteo exacto',vision.exact_rate,'La cantidad detectada coincide exactamente con la observada por la persona.'),
      scoreBar('Error máximo de una unidad',vision.within_one_rate,'La diferencia entre observado y detectado es cero o un semáforo.')
    );
    yolo.append(scores,values([
      ['Imágenes evaluadas',number(vision.samples)],
      ['Cobertura revisada',percent(ratio(vision.samples,completed.get('detect')))],
      ['Semáforos observados',number(vision.observed)],
      ['Semáforos detectados',number(vision.detected)],
      ['MAE · error absoluto medio',number(vision.mae)],
      ['RMSE',number(vision.rmse)],
      ['Sesgo medio detectado − observado',number(vision.mean_bias)],
      ['Sobreconteos',number(vision.over)],
      ['Subconteos',number(vision.under)],
      ['Error absoluto relativo',percent(vision.relative_abs_error)]
    ]),element('small','Para YOLO se evalúa el conteo, no la coincidencia geométrica caja por caja. Por eso no se presenta precisión IoU con estas etiquetas manuales.'));
  }
  panel.append(yolo,semanticModel('Whisper Small · contenido recuperado del audio',quality.audio,completed.get('audio')),
    semanticModel('Qwen3 4B Instruct · extracción semántica',quality.text,completed.get('text')));
  panel.append(element('p','TP: positivo correctamente detectado. FP: detección no observada. FN: elemento observado que el modelo omitió. TN: ausencia correctamente reconocida. Un campo sin positivos observados ni detectados queda fuera del F1 macro.'));
  return panel;
}
function extractionTelemetry(data) {
  const panel=element('section');
  panel.className='metrics-section';
  panel.append(element('h2','Inferencia de Qwen'));
  const row=data.qwen_calls||{};
  if(row.conversations)panel.append(values([
    ['Conversaciones con telemetría',number(row.conversations)],
    ['Llamadas',number(row.calls)], ['Truncadas',number(row.truncated)], ['Con error',number(row.errors)],
    ['Llamadas por conversación · mediana',number(row.calls_p50)],
    ['Tokens de entrada por conversación · mediana',number(row.input_tokens_p50)],
    ['Tokens de salida por conversación · mediana',number(row.output_tokens_p50)],
    ['Tiempo de llamadas por conversación · p50',seconds(row.total_seconds_p50)],
    ['Tiempo de llamadas por conversación · p90',seconds(row.total_seconds_p90)]
  ]));
  else panel.append(element('p','Aún no hay inferencias con telemetría por llamada en este corte.'));
  return panel;
}
function formatAlerts(data) {
  const panel=element('section');
  panel.className='metrics-section';
  panel.append(element('h2','Alertas del formato de WhatsApp'));
  const rows=data.chat_format_alerts||[];
  if(!rows.length)panel.append(element('p','Sin alertas registradas en los TXT revisados.'));
  else panel.append(dataTable(['TXT y conversación','Parser','Estado','Cabeceras reconocidas','Causas'],
    rows.map(row=>[row.original_name+' · '+row.conversation_name,row.parser_version,
      row.format_health.severity==='degraded'?'Degradado':'Aviso',
      number(row.format_health.recognized_headers)+' de '+number(row.format_health.probable_headers),
      row.format_health.reasons.map(reason=>({unknown_headers:'Cabecera nueva',unknown_attachments:'Adjunto con estructura nueva',
        invalid_timestamps:'Fecha u hora no interpretable',no_recognized_header:'Sin cabecera reconocida',
        unknown_sender_shape:'Separador de remitente nuevo'})[reason]||reason).join(', ')])));
  panel.append(element('p','La alerta mide cambios de estructura en la entrada. Los TXT históricos aparecen a medida que se vuelven a inspeccionar.'));
  return panel;
}
function render(data) {
  const grid = element('div');
  grid.className = 'metrics-grid';
  const byStage = new Map(data.stages.map(row => [row.stage,row]));
  for (const stage of Object.keys(stageInfo)) grid.append(modelCard(stage, byStage.get(stage)));
  const chart = element('section');
  chart.className = 'metrics-section';
  const chartPick = element('select');
  chartPick.id = 'metricsDailyStage';
  const chartLabel = element('label','Etapa en el gráfico');
  chartLabel.htmlFor = chartPick.id;
  chartPick.add(new Option('Todas las etapas',''));
  for (const [stage, [title]] of Object.entries(stageInfo)) chartPick.add(new Option(title, stage));
  const plot = element('div');
  plot.className = 'metrics-detail';
  chart.append(element('h2','Actividad reciente por fecha de finalización'), chartLabel, chartPick, plot);
  dailyGraph(plot, data.chart_days, data.daily, '');
  chartPick.onchange = () => dailyGraph(plot,data.chart_days,data.daily,chartPick.value);
  const failures = element('section');
  failures.append(element('h2','Causas de fallo'));
  if (data.errors.length) {
    failures.append(dataTable(['Etapa','Causa','Tareas'], data.errors.map(err => [
      stageInfo[err.stage][0], errorLabels[err.code] || err.code, number(err.count),
    ])));
  } else {
    failures.append(element('p','No se registran fallos en este filtro.'));
  }
  get('metricsContent').replaceChildren(grid,reviewedModels(data),extractionTelemetry(data),formatAlerts(data),latencyChart(byStage),chart,failures);
  const timestamp = new Date(data.as_of).toLocaleString('es-CO',{timeZone:'America/Bogota'});
  get('metricsCut').textContent = 'Corte: ' + timestamp + ' (Colombia). Se toma el último intento por tarea. '
    + 'CPU y memoria miden el proceso Python. El consumo de Ollama y FFmpeg como procesos separados queda fuera.';
}
async function update() {
  activeRequest?.abort();
  const controller = new AbortController();
  activeRequest = controller;
  const experiment = get('metricsExperiment').value;
  const days = get('metricsPeriod').value;
  const query = new URLSearchParams();
  if (experiment) query.set('experiment',experiment);
  if (days) query.set('days',days);
  get('metricsContent').setAttribute('aria-busy','true');
  get('metricsStatus').textContent = 'Consultando resultados…';
  try {
    const response = await fetch('/model-metrics?' + query, {
      cache:'no-store',signal:controller.signal,
    });
    if (response.status === 401) {
      signOut();
      get('metricsStatus').textContent = 'La clave no es válida. Vuelve a ingresarla.';
      return;
    }
    if (!response.ok) throw Error('No se pudieron cargar las métricas.');
    const data = await response.json();
    if (activeRequest !== controller) return;
    const options = get('metricsExperiment');
    options.replaceChildren(new Option('Todos',''), ...data.experiments.map(name=>new Option(name,name)));
    options.value = experiment;
    render(data);
    get('metricsWorkspace').hidden = false;
    get('login').hidden = true;
    get('metricsStatus').textContent = '';
  } catch (error) {
    if (activeRequest === controller) {
      get('metricsContent').replaceChildren();
      get('metricsCut').textContent = '';
      get('metricsStatus').textContent = 'No se pudieron cargar las métricas. Intenta actualizar.';
    }
  } finally {
    if (activeRequest === controller) get('metricsContent').setAttribute('aria-busy','false');
  }
}
function signOut() {
  activeRequest?.abort();
  activeRequest = undefined;
  get('metricsWorkspace').hidden = true;
  get('login').hidden = false;
  get('metricsContent').replaceChildren();
  get('metricsContent').setAttribute('aria-busy','false');
  get('metricsCut').textContent = '';
  get('metricsExperiment').replaceChildren(new Option('Todos',''));
  get('metricsPeriod').value = '';
  get('metricsStatus').textContent = '';
  get('metricsToken').focus();
}
get('metricsLogin').onsubmit = async event => {
  event.preventDefault();
  const key=get('metricsToken').value;
  get('metricsToken').value='';
  try { await teamSession.open(key); await update(); }
  catch (error) { get('metricsStatus').textContent=error.message; }
};
get('metricsLogout').onclick = async () => {
  try { await teamSession.close(); signOut(); }
  catch (error) { get('metricsStatus').textContent=error.message; }
};
teamSession.active().then(active=>{if(active)update();});
get('metricsRefresh').onclick = update;
get('metricsPeriod').onchange = update;
get('metricsExperiment').onchange = update;
